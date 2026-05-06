# Deploy — legal-one-client

Runbook completo para build e deploy da função Lambda via SAM CLI.

---

## Estrutura de arquivos de deploy

```
raiz do projeto
├── Dockerfile          # imagem Docker da função Lambda (deve ficar na raiz)
├── template.yaml       # stack SAM/CloudFormation (deve ficar na raiz)
├── samconfig.toml      # configuração persistente do SAM CLI (deve ficar na raiz)
├── requirements-runtime.txt  # dependências de runtime (copiadas na imagem)
└── deploy/
    ├── README.md       # este arquivo — runbook de deploy
    └── deploy_plan.md  # histórico de decisões de arquitetura
```

> `Dockerfile`, `template.yaml` e `samconfig.toml` **precisam estar na raiz** —
> o SAM CLI os busca lá por padrão e o `DockerContext: .` aponta para a raiz.

---

## Pré-requisitos

| Ferramenta | Versão mínima | Verificar com |
|---|---|---|
| AWS CLI | v2 | `aws --version` |
| SAM CLI | 1.100+ | `sam --version` |
| Docker Desktop | qualquer | `docker info` |
| Conta AWS autenticada | — | `aws sts get-caller-identity` |

---

## Parâmetros SSM necessários

Todos os segredos ficam no SSM Parameter Store como `SecureString`.
Crie-os **uma única vez** antes do primeiro deploy:

```bash
# Credenciais de acesso ao LegalOne
aws ssm put-parameter --name /legal-one/username --value "SEU_USUARIO"  --type SecureString
aws ssm put-parameter --name /legal-one/password --value "SUA_SENHA"    --type SecureString

# Segredos da API (já criados — apenas para referência)
aws ssm put-parameter --name /legal-one/jwt-secret --value "$(openssl rand -hex 32)" --type SecureString
aws ssm put-parameter --name /legal-one/api-key    --value "$(openssl rand -hex 32)" --type SecureString
```

Para atualizar um parâmetro existente, adicione `--overwrite`:
```bash
aws ssm put-parameter --name /legal-one/password --value "NOVA_SENHA" --type SecureString --overwrite
```

---

## Repositório ECR

O SAM faz push da imagem Docker para o ECR. O repositório precisa existir antes do primeiro deploy:

```bash
aws ecr create-repository \
  --repository-name legalone-client \
  --region us-east-1
```

Se já existir (checar com `aws ecr describe-repositories`), pule este passo.

---

## Comandos de deploy

### Primeiro deploy

```bash
# 1. Inicie o Docker Desktop

# 2. Autentique o Docker no ECR
aws ecr get-login-password --region us-east-1 \
  | docker login --username AWS --password-stdin \
    021891594077.dkr.ecr.us-east-1.amazonaws.com

# 3. Build da imagem + deploy
sam build && sam deploy
```

O `samconfig.toml` já tem todas as configurações — não será necessário responder perguntas.

### Deploys subsequentes

```bash
sam build && sam deploy
```

### Forçar rebuild completo (sem cache)

```bash
sam build --no-cached && sam deploy
```

---

## Token JWT permanente

A API usa autenticação JWT. O token abaixo **não expira** e foi gerado com
o `jwt-secret` atual do SSM. Use-o nas aplicações clientes internas:

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhcGktY2xpZW50In0.FDfqmReazfF8YGsCUnPRvd1xA30lyJLRt-C5xQzm7aU
```

**Como usar:**
```http
GET /contacts/12345678900
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhcGktY2xpZW50In0.FDfqmReazfF8YGsCUnPRvd1xA30lyJLRt-C5xQzm7aU
```

> ⚠️ Se o `/legal-one/jwt-secret` for rotacionado no SSM, este token deixará
> de funcionar e um novo deverá ser gerado. Para regenerar:
>
> **Opção 1 — via SSM (produção):**
> ```bash
> cd /caminho/do/projeto && source .venv/bin/activate
> python -c "
> from jose import jwt
> import boto3
> secret = boto3.client('ssm', region_name='us-east-1').get_parameter(
>     Name='/legal-one/jwt-secret', WithDecryption=True)['Parameter']['Value']
> print(jwt.encode({'sub': 'api-client'}, secret, algorithm='HS256'))
> "
> ```
>
> **Opção 2 — via `.env` local (desenvolvimento):**
> ```bash
> cd /caminho/do/projeto && source .venv/bin/activate
> python -c "
> from dotenv import dotenv_values
> from jose import jwt
> secret = dotenv_values('.env')['JWT_SECRET']
> print(jwt.encode({'sub': 'api-client'}, secret, algorithm='HS256'))
> "
> ```

---

## Verificar o deploy

Após o deploy, o SAM exibirá os Outputs:

```
Key                 ApiUrl
Value               https://<id>.execute-api.us-east-1.amazonaws.com/prod

Key                 FunctionArn
Value               arn:aws:lambda:us-east-1:021891594077:function:legalone-client

Key                 SessionTableArn
Value               arn:aws:dynamodb:us-east-1:021891594077:table/legal-one-session-store
```

Teste rápido:
```bash
# Health check (docs do FastAPI — não requer autenticação)
curl https://<id>.execute-api.us-east-1.amazonaws.com/prod/docs

# Endpoint protegido
curl -H "Authorization: Bearer <TOKEN>" \
  https://<id>.execute-api.us-east-1.amazonaws.com/prod/contacts/12345678900
```

---

## Rollback

```bash
# Ver versões anteriores do stack
aws cloudformation describe-stack-events --stack-name legalone-client | head -50

# O CloudFormation faz rollback automático em caso de falha no deploy.
# Para forçar rollback manual para uma versão anterior:
aws cloudformation cancel-update-stack --stack-name legalone-client
```

---

## Remover o stack

```bash
sam delete --stack-name legalone-client
```

> ⚠️ Isso apaga a função Lambda, o API Gateway e a tabela DynamoDB.
> Os parâmetros SSM **não** são apagados — remova manualmente se necessário.

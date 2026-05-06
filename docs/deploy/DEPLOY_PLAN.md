Vou ler os arquivos relevantes para entender a stack completa antes de planejar: Tenho todo o contexto necessário. Aqui está o planejamento completo:

---

## Recursos necessários no `template.yaml`

### 1. `AWS::Serverless::Function` — Lambda (a aplicação)

**Runtime:** `python3.13`
**Handler:** `app.main.handler` (o `Mangum(app)` exportado em main.py)
**Timeout:** 30s (crawlers fazem requests HTTP externos ao LegalOne — podem demorar)
**MemorySize:** 512 MB (BeautifulSoup + requests em memória; 128 MB seria arriscado)

**Variáveis de ambiente** (mapeadas de SSM/Secrets Manager ou inline no template):
- `LEGALONE_USERNAME`
- `LEGALONE_PASSWORD`
- `LEGALONE_BASE_URL`
- `DYNAMODB_TABLE` → nome da tabela criada no mesmo template
- `AWS_REGION` / `AWS_DEFAULT_REGION`

**Permissões IAM necessárias** (via `Policies`):
- `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:DeleteItem` na tabela de sessão — para o `SessionManager` ler/gravar cookies e adquirir/liberar o lock distribuído

**Eventos:** `HttpApi` (API Gateway v2) com `/{proxy+}` — Mangum roteia tudo internamente

---

### 2. `AWS::Serverless::HttpApi` — API Gateway (HTTP API v2)

Usar **HTTP API v2**, não REST API v1:
- Mais barato e com latência menor
- Mangum suporta ambos, mas HTTP API v2 tem o event payload mais simples
- Configurar `StageName: prod` (ou `$default` para URL sem prefixo de stage)
- CORS: configurar `AllowOrigins`, `AllowMethods`, `AllowHeaders` se a API será consumida por frontend

---

### 3. `AWS::DynamoDB::Table` — tabela de sessão

O `SessionManager` usa **dois itens fixos** na mesma tabela:
- `pk = "COOKIES"` — armazena o JSON de cookies + `expires_at`
- `pk = "LOCK"` — lock distribuído de refresh

**Estrutura:**
- `BillingMode: PAY_PER_REQUEST` (tráfego baixo e irregular — on-demand é mais barato que provisionado)
- Chave de partição: `pk` (String)
- **TTL:** habilitar no atributo `expires_at` — o DynamoDB vai limpar automaticamente cookies e locks expirados, sem custo de operação manual

---

### 4. `AWS::SSM::Parameter` (opcional, recomendado) — credenciais

`LEGALONE_USERNAME` e `LEGALONE_PASSWORD` **não devem** ficar em texto puro no `template.yaml`. Opções:

- **SSM Parameter Store** (`SecureString`) — referenciados no template como `{{resolve:ssm-secure:/legal-one/password}}` — mais simples, sem custo adicional
- **Secrets Manager** — mais robusto para rotação automática, mas tem custo por secret ($0.40/mês)

**Recomendação:** SSM Parameter Store com `SecureString` para este caso (sem necessidade de rotação automática).

---

### 5. Camada de dependências — `AWS::Serverless::LayerVersion`

As dependências (`fastapi`, `mangum`, `requests`, `beautifulsoup4`, `pydantic`, etc.) somam ~50-80 MB. Estratégias:

**Opção A — Layer separada:** empacota requirements.txt numa Lambda Layer. O código da aplicação fica pequeno (~1 MB), o deploy é rápido após a primeira vez.

**Opção B — tudo junto no pacote da função:** mais simples de configurar, mas o ZIP cresce (~80 MB), ultrapassa o limite de upload direto (50 MB comprimido) e precisaria de S3.

**Recomendação:** usar uma **Layer** para dependências + `ContentUri` do código apontando apenas para o código-fonte. O SAM tem o `sam build` que monta isso automaticamente via `BuildMethod: python3.13`.

---

### Resumo do template

```
template.yaml
├── Globals
│   └── Function: Timeout, MemorySize, Environment (vars comuns)
│
├── Parameters
│   ├── LegalOneUsername  (SSM SecureString ref)
│   └── LegalOnePassword  (SSM SecureString ref)
│
├── Resources
│   ├── LegalOneApi          (AWS::Serverless::HttpApi)
│   ├── LegalOneFunction     (AWS::Serverless::Function)
│   │   ├── Events: HttpApi /{proxy+} → LegalOneApi
│   │   └── Policies: DynamoDBCrudPolicy na SessionTable
│   └── SessionTable         (AWS::DynamoDB::Table)
│       ├── pk (String, hash key)
│       └── TTL em expires_at
│
└── Outputs
    ├── ApiUrl   → URL do API Gateway
    └── TableName → nome da tabela (útil para scripts de operação)
```

---

### Pontos de atenção antes de escrever o template

1. **`sam build`** precisa de um `requirements.txt` limpo (sem `uvicorn`, `pytest`, `black`, etc. — só deps de runtime). Faz sentido separar em `requirements-dev.txt`.
2. O `PYTHONPATH` no Lambda precisa incluir a raiz do projeto para que imports como `from services.contact.service import ...` funcionem. Isso é configurado via `PYTHONPATH: /var/task` no environment da função.
3. O `legalone_base_url` é uma configuração, não um segredo — pode ficar diretamente no `Environment` do template.

Posso escrever o `template.yaml` quando quiser.


Respondendo sem código:

---

## 1. Como criar autenticação JWT para a API

O fluxo básico é:

1. Existe um **emissor** (issuer) que autentica a aplicação cliente e entrega um JWT assinado com uma chave secreta ou par RSA
2. A aplicação cliente inclui o token em cada requisição: `Authorization: Bearer <token>`
3. Sua API verifica a assinatura e as claims (expiração, audience, etc.) antes de processar

**Para aplicações internas de um escritório, a abordagem mais simples é JWT estático com chave compartilhada (HS256):**
- Você gera um segredo forte e o armazena no SSM Parameter Store
- Emite manualmente um JWT para cada aplicação cliente (ou cria um endpoint `/auth` interno)
- O FastAPI valida com uma dependência global usando `python-jose` ou `PyJWT`
- Sem servidor de identidade, sem Cognito, sem infra extra

**Se no futuro precisar de mais controle** (revogar tokens, múltiplos clientes, rotação automática):
- **AWS Cognito Machine-to-Machine** (Client Credentials flow, OAuth 2.0) — cada aplicação tem `client_id` + `client_secret`, troca por JWT com TTL curto
- O API Gateway HTTP API tem suporte nativo a JWT authorizer apontando para o Cognito — valida o token antes de invocar o Lambda, sem código na sua aplicação

Para o cenário de escritório com poucas aplicações internas, **JWT com chave compartilhada + dependência no FastAPI é suficiente e simples**.

---

## 2. O que é throttling por rota

É a capacidade de limitar a **taxa de requisições por rota específica**, não apenas globalmente.

Exemplo sem throttling por rota: se você tem um limite de 100 req/s na API inteira, um cliente que chama `GET /lawsuits` em loop consome todo o limite e deixa `POST /contacts` sem cota.

Com throttling por rota você define:
- `GET /lawsuits` → máximo 10 req/s (operação pesada, faz scraping)
- `GET /contacts/lookup` → máximo 50 req/s
- `POST /contacts` → máximo 5 req/s (escrita)

O API Gateway REST (v1) tem isso por estágio e por método/rota. O **HTTP API (v2) não tem throttling por rota** — só global. A Function URL também só tem throttling global (limite de concorrência do Lambda).

Para o seu caso (poucas aplicações internas, volume baixo), **isso não é relevante**.

---

## 3. Como funciona o WAF padrão do API Gateway

O API Gateway **não tem WAF embutido por padrão** — é um serviço separado (AWS WAF) que você associa ao API Gateway manualmente, com custo adicional.

O que o API Gateway oferece nativamente (sem WAF):
- **Throttling global** — rejeita com 429 quando excede a cota
- **Mutual TLS** — certificado de cliente (mais complexo, não relevante aqui)
- Nenhuma proteção contra SQL injection, XSS, bots, etc.

O AWS WAF quando associado permite:
- Bloquear IPs específicos ou países
- Regras gerenciadas (OWASP Top 10, bots conhecidos)
- Rate limiting por IP

Custo: ~$5/mês base + $1/milhão de requisições inspecionadas. Para uma API interna com autenticação JWT própria, **WAF é overhead desnecessário**.

---

## 4. Function URL ou API Gateway — o que é melhor no seu caso

**Lambda Function URL é a escolha certa.** Justificativas:

| Critério | Seu caso | Conclusão |
|---|---|---|
| Clientes | Aplicações internas do escritório | Não precisa de features enterprise |
| Autenticação | JWT próprio no FastAPI | API Gateway Authorizer não agrega nada |
| Volume | Baixo e irregular | Custo do API Gateway ($1/mi req) desnecessário |
| Throttling por rota | Irrelevante | Ambos equivalentes |
| WAF | Desnecessário com JWT | Não justifica o custo |
| Domínio customizado | Possível com CloudFront na frente da Function URL | Mesma capacidade |
| Complexidade do template SAM | Function URL = 3 linhas | API Gateway = 20+ linhas com stage, cors, etc. |
| Latência | Function URL tem ~1ms a menos (sem camada extra) | Marginal, mas real |

O único cenário onde o API Gateway valeria para você seria se quisesse usar o **JWT Authorizer nativo** do HTTP API apontando para Cognito — aí a validação do token acontece antes do Lambda ser invocado (economiza execuções em requisições inválidas). Mas dado que você vai implementar JWT no FastAPI mesmo, essa vantagem não existe.

**Resumo:** Function URL + JWT no FastAPI + CloudFront na frente se quiser domínio customizado no futuro. Mais simples, mais barato, suficiente para o contexto.

Respondendo sem código:

---

## 1. Como criar autenticação JWT para a API

O fluxo básico é:

1. Existe um **emissor** (issuer) que autentica a aplicação cliente e entrega um JWT assinado com uma chave secreta ou par RSA
2. A aplicação cliente inclui o token em cada requisição: `Authorization: Bearer <token>`
3. Sua API verifica a assinatura e as claims (expiração, audience, etc.) antes de processar

**Para aplicações internas de um escritório, a abordagem mais simples é JWT estático com chave compartilhada (HS256):**
- Você gera um segredo forte e o armazena no SSM Parameter Store
- Emite manualmente um JWT para cada aplicação cliente (ou cria um endpoint `/auth` interno)
- O FastAPI valida com uma dependência global usando `python-jose` ou `PyJWT`
- Sem servidor de identidade, sem Cognito, sem infra extra

**Se no futuro precisar de mais controle** (revogar tokens, múltiplos clientes, rotação automática):
- **AWS Cognito Machine-to-Machine** (Client Credentials flow, OAuth 2.0) — cada aplicação tem `client_id` + `client_secret`, troca por JWT com TTL curto
- O API Gateway HTTP API tem suporte nativo a JWT authorizer apontando para o Cognito — valida o token antes de invocar o Lambda, sem código na sua aplicação

Para o cenário de escritório com poucas aplicações internas, **JWT com chave compartilhada + dependência no FastAPI é suficiente e simples**.

---

## 2. O que é throttling por rota

É a capacidade de limitar a **taxa de requisições por rota específica**, não apenas globalmente.

Exemplo sem throttling por rota: se você tem um limite de 100 req/s na API inteira, um cliente que chama `GET /lawsuits` em loop consome todo o limite e deixa `POST /contacts` sem cota.

Com throttling por rota você define:
- `GET /lawsuits` → máximo 10 req/s (operação pesada, faz scraping)
- `GET /contacts/lookup` → máximo 50 req/s
- `POST /contacts` → máximo 5 req/s (escrita)

O API Gateway REST (v1) tem isso por estágio e por método/rota. O **HTTP API (v2) não tem throttling por rota** — só global. A Function URL também só tem throttling global (limite de concorrência do Lambda).

Para o seu caso (poucas aplicações internas, volume baixo), **isso não é relevante**.

---

## 3. Como funciona o WAF padrão do API Gateway

O API Gateway **não tem WAF embutido por padrão** — é um serviço separado (AWS WAF) que você associa ao API Gateway manualmente, com custo adicional.

O que o API Gateway oferece nativamente (sem WAF):
- **Throttling global** — rejeita com 429 quando excede a cota
- **Mutual TLS** — certificado de cliente (mais complexo, não relevante aqui)
- Nenhuma proteção contra SQL injection, XSS, bots, etc.

O AWS WAF quando associado permite:
- Bloquear IPs específicos ou países
- Regras gerenciadas (OWASP Top 10, bots conhecidos)
- Rate limiting por IP

Custo: ~$5/mês base + $1/milhão de requisições inspecionadas. Para uma API interna com autenticação JWT própria, **WAF é overhead desnecessário**.

---

## 4. Function URL ou API Gateway — o que é melhor no seu caso

**Lambda Function URL é a escolha certa.** Justificativas:

| Critério | Seu caso | Conclusão |
|---|---|---|
| Clientes | Aplicações internas do escritório | Não precisa de features enterprise |
| Autenticação | JWT próprio no FastAPI | API Gateway Authorizer não agrega nada |
| Volume | Baixo e irregular | Custo do API Gateway ($1/mi req) desnecessário |
| Throttling por rota | Irrelevante | Ambos equivalentes |
| WAF | Desnecessário com JWT | Não justifica o custo |
| Domínio customizado | Possível com CloudFront na frente da Function URL | Mesma capacidade |
| Complexidade do template SAM | Function URL = 3 linhas | API Gateway = 20+ linhas com stage, cors, etc. |
| Latência | Function URL tem ~1ms a menos (sem camada extra) | Marginal, mas real |

O único cenário onde o API Gateway valeria para você seria se quisesse usar o **JWT Authorizer nativo** do HTTP API apontando para Cognito — aí a validação do token acontece antes do Lambda ser invocado (economiza execuções em requisições inválidas). Mas dado que você vai implementar JWT no FastAPI mesmo, essa vantagem não existe.

**Resumo:** Function URL + JWT no FastAPI + CloudFront na frente se quiser domínio customizado no futuro. Mais simples, mais barato, suficiente para o contexto.

Respondendo sem código:

---

## 1. Como criar autenticação JWT para a API

O fluxo básico é:

1. Existe um **emissor** (issuer) que autentica a aplicação cliente e entrega um JWT assinado com uma chave secreta ou par RSA
2. A aplicação cliente inclui o token em cada requisição: `Authorization: Bearer <token>`
3. Sua API verifica a assinatura e as claims (expiração, audience, etc.) antes de processar

**Para aplicações internas de um escritório, a abordagem mais simples é JWT estático com chave compartilhada (HS256):**
- Você gera um segredo forte e o armazena no SSM Parameter Store
- Emite manualmente um JWT para cada aplicação cliente (ou cria um endpoint `/auth` interno)
- O FastAPI valida com uma dependência global usando `python-jose` ou `PyJWT`
- Sem servidor de identidade, sem Cognito, sem infra extra

**Se no futuro precisar de mais controle** (revogar tokens, múltiplos clientes, rotação automática):
- **AWS Cognito Machine-to-Machine** (Client Credentials flow, OAuth 2.0) — cada aplicação tem `client_id` + `client_secret`, troca por JWT com TTL curto
- O API Gateway HTTP API tem suporte nativo a JWT authorizer apontando para o Cognito — valida o token antes de invocar o Lambda, sem código na sua aplicação

Para o cenário de escritório com poucas aplicações internas, **JWT com chave compartilhada + dependência no FastAPI é suficiente e simples**.

---

## 2. O que é throttling por rota

É a capacidade de limitar a **taxa de requisições por rota específica**, não apenas globalmente.

Exemplo sem throttling por rota: se você tem um limite de 100 req/s na API inteira, um cliente que chama `GET /lawsuits` em loop consome todo o limite e deixa `POST /contacts` sem cota.

Com throttling por rota você define:
- `GET /lawsuits` → máximo 10 req/s (operação pesada, faz scraping)
- `GET /contacts/lookup` → máximo 50 req/s
- `POST /contacts` → máximo 5 req/s (escrita)

O API Gateway REST (v1) tem isso por estágio e por método/rota. O **HTTP API (v2) não tem throttling por rota** — só global. A Function URL também só tem throttling global (limite de concorrência do Lambda).

Para o seu caso (poucas aplicações internas, volume baixo), **isso não é relevante**.

---

## 3. Como funciona o WAF padrão do API Gateway

O API Gateway **não tem WAF embutido por padrão** — é um serviço separado (AWS WAF) que você associa ao API Gateway manualmente, com custo adicional.

O que o API Gateway oferece nativamente (sem WAF):
- **Throttling global** — rejeita com 429 quando excede a cota
- **Mutual TLS** — certificado de cliente (mais complexo, não relevante aqui)
- Nenhuma proteção contra SQL injection, XSS, bots, etc.

O AWS WAF quando associado permite:
- Bloquear IPs específicos ou países
- Regras gerenciadas (OWASP Top 10, bots conhecidos)
- Rate limiting por IP

Custo: ~$5/mês base + $1/milhão de requisições inspecionadas. Para uma API interna com autenticação JWT própria, **WAF é overhead desnecessário**.

---

## 4. Function URL ou API Gateway — o que é melhor no seu caso

**Lambda Function URL é a escolha certa.** Justificativas:

| Critério | Seu caso | Conclusão |
|---|---|---|
| Clientes | Aplicações internas do escritório | Não precisa de features enterprise |
| Autenticação | JWT próprio no FastAPI | API Gateway Authorizer não agrega nada |
| Volume | Baixo e irregular | Custo do API Gateway ($1/mi req) desnecessário |
| Throttling por rota | Irrelevante | Ambos equivalentes |
| WAF | Desnecessário com JWT | Não justifica o custo |
| Domínio customizado | Possível com CloudFront na frente da Function URL | Mesma capacidade |
| Complexidade do template SAM | Function URL = 3 linhas | API Gateway = 20+ linhas com stage, cors, etc. |
| Latência | Function URL tem ~1ms a menos (sem camada extra) | Marginal, mas real |

O único cenário onde o API Gateway valeria para você seria se quisesse usar o **JWT Authorizer nativo** do HTTP API apontando para Cognito — aí a validação do token acontece antes do Lambda ser invocado (economiza execuções em requisições inválidas). Mas dado que você vai implementar JWT no FastAPI mesmo, essa vantagem não existe.

**Resumo:** Function URL + JWT no FastAPI + CloudFront na frente se quiser domínio customizado no futuro. Mais simples, mais barato, suficiente para o contexto.


# Fluxo completo

1. POST /auth/token  { "api_key": "..." }
        ↓
2. API valida com secrets.compare_digest (timing-safe)
        ↓
3. Retorna { "access_token": "<JWT>", "token_type": "bearer", "expires_in": 3600 }
        ↓
4. Cliente envia em todas as chamadas:
   Authorization: Bearer <JWT>
        ↓
5. require_auth (Depends) decodifica + valida assinatura e exp
   → 401 se inválido/expirado
   → passa o payload para o endpoint se OK


# Antes do primeiro deploy, crie os parâmetros no SSM:
```sh
aws ssm put-parameter --name /legal-one/jwt-secret --value "$(openssl rand -hex 32)" --type SecureString
aws ssm put-parameter --name /legal-one/api-key    --value "$(openssl rand -hex 32)" --type SecureString
```


# O que faz $(openssl rand -hex 32)?
```sh
$(openssl rand -hex 32)?
```
Gera 32 bytes aleatórios e os imprime em hexadecimal — resulta numa string de 64 caracteres. É a forma padrão de criar um segredo criptograficamente seguro no terminal: a3f8c1d2e4b9071f6a5e2c8d3b1f9e7a4c6d0e8b2a5f3c1d7e9b0a4f2c6d8e1

# Lê o jwt-secret atual para assinar o token permanente localmente
```sh
aws ssm get-parameter --name /legal-one/jwt-secret --with-decryption --query "Parameter.Value" --output text 2>&1
```

# Gerar token JWT permanente
cd /Users/thomas/Documents/projetos/legal-one-client && source .venv/bin/activate && python - <<'EOF'
from jose import jwt
SECRET = "c6d0ffdb232a8d4a1d039440e01690c6f143f83c1d79ea974126217876b66152"
payload = {"sub": "api-client"}   # sem "exp" → token não expira
token = jwt.encode(payload, SECRET, algorithm="HS256")
print(token)
EOF
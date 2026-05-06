# legal-one-client

API HTTP para automação de cadastros e consultas no sistema LegalOne (plataforma jurídica Novajus).
Implementada em Python com FastAPI, empacotada para execução em AWS Lambda via Mangum.

---

## Índice

- [Configuração](#configuração)
- [Executando localmente](#executando-localmente)
- [Rotas](#rotas)
  - [POST /contacts](#post-contacts)
  - [POST /lawsuits/search](#post-lawsuitssearch)
  - [GET /lawsuits/{lawsuit_id}](#get-lawsuitslawsuit_id)
- [Schemas de request e response](#schemas-de-request-e-response)
  - [Contatos](#contatos)
  - [Processos](#processos)
- [Códigos de status e erros](#códigos-de-status-e-erros)
- [Arquitetura resumida](#arquitetura-resumida)

---

## Configuração

Crie um arquivo `.env` na raiz do projeto com as variáveis abaixo:

```env
LEGALONE_USERNAME=seu_usuario
LEGALONE_PASSWORD=sua_senha

# Opcional — padrão: https://abladv.novajus.com.br
LEGALONE_BASE_URL=https://abladv.novajus.com.br

# DynamoDB para armazenar cookies de sessão entre execuções Lambda
DYNAMODB_TABLE=session-store
AWS_REGION=us-east-1
```

---

## Executando localmente

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Documentação interativa disponível em `http://localhost:8000/docs`.

---

## Rotas

### POST /contacts

Cria um novo contato (pessoa física) no LegalOne.

- **Content-Type:** `application/json`
- **Autenticação:** gerenciada internamente (cookies de sessão via DynamoDB)

#### Request body

```json
{
  "dados_pessoais": {
    "cpf": "083.863.794-99",
    "nome": "João da Silva",
    "data_nascimento": "15/03/1985",
    "sexo": "M",
    "observacao": "Cliente indicado por fulano."
  },
  "telefones": {
    "celular": "(11) 91234-5678",
    "telefone_residencial": "(11) 3456-7890"
  },
  "endereco": {
    "cep": "01310-100",
    "logradouro": "Avenida Paulista",
    "numero": "1000",
    "complemento": "Apto 42",
    "bairro": "Bela Vista",
    "cidade": "São Paulo",
    "uf": "SP",
    "pais": "Brasil"
  },
  "personalized_fields": {
    "tag": "VIP",
    "cid": "M54",
    "referencia": "REF-2026-001",
    "link_drive": "https://drive.google.com/...",
    "data_vencimento_kit": "30/04/2026",
    "data_vencimento_comprovante": "30/06/2026",
    "classificacao_backoffice": "1",
    "natureza_do_acidente": "Trabalho",
    "tratamento_da_lesao": "Cirúrgico",
    "tramitacao_prioritaria": "Sim"
  }
}
```

Apenas `dados_pessoais` é obrigatório. Todos os outros blocos (`telefones`,
`endereco`, `personalized_fields`) são opcionais e podem ser omitidos.

#### Response — 200 OK (sucesso)

```json
{
  "success": true,
  "optional_field_errors": []
}
```

#### Response — 200 OK (criado com avisos)

Quando campos opcionais são ignorados pelo servidor (ex.: endereço com UF
inválida), o contato **é criado mesmo assim** e os erros aparecem em
`optional_field_errors`:

```json
{
  "success": false,
  "optional_field_errors": [
    {
      "field_name": "Enderecos[...].UFId",
      "message": "UF 'XX' não reconhecida. Use a sigla (ex.: 'SP') ou o nome completo (ex.: 'São Paulo')."
    }
  ]
}
```

---

### POST /lawsuits/search

Busca processos vinculados a um contato.

> **Fase 1:** retorna o HTML cru do LegalOne. Resposta estruturada será
> implementada na Fase 2 (lawsuit_parser.py).

#### Request body

```json
{
  "contact_id": "12345",
  "contact_name": "João da Silva"
}
```

#### Response — 200 OK

```json
{
  "html": "<html>...</html>"
}
```

---

### GET /lawsuits/{lawsuit_id}

Retorna os detalhes de um processo.

> **Fase 1:** retorna o HTML cru do LegalOne.

#### Parâmetro de path

| Parâmetro    | Tipo   | Descrição                      |
|--------------|--------|--------------------------------|
| `lawsuit_id` | string | ID do processo no LegalOne     |

#### Response — 200 OK

```json
{
  "html": "<html>...</html>"
}
```

---

## Schemas de request e response

### Contatos

#### `DadosPessoaisSchema`

| Campo               | Tipo           | Obrigatório | Formato / Restrições                          |
|---------------------|----------------|-------------|-----------------------------------------------|
| `cpf`               | string         | ✅           | `###.###.###-##` (com pontos e hífen)         |
| `nome`              | string         | ✅           | Mínimo duas palavras                          |
| `data_nascimento`   | string \| null | —           | Texto livre (ex.: `"15/03/1985"`)             |
| `sexo`              | string \| null | —           | `"M"` ou `"F"` (case-insensitive)             |
| `observacao`        | string \| null | —           | Texto livre                                   |

#### `TelefonesSchema`

| Campo                  | Tipo           | Obrigatório | Observações                        |
|------------------------|----------------|-------------|------------------------------------|
| `celular`              | string \| null | —           | Qualquer formato de string         |
| `telefone_residencial` | string \| null | —           | Qualquer formato de string         |

Pelo menos um dos dois deve ser preenchido para que o bloco tenha efeito.

#### `EnderecoSchema`

| Campo         | Tipo   | Obrigatório | Restrições                          |
|---------------|--------|-------------|-------------------------------------|
| `cep`         | string | ✅           | Texto livre                         |
| `logradouro`  | string | ✅           | Texto livre                         |
| `cidade`      | string | ✅           | Nome exato do município             |
| `uf`          | string | ✅           | Exatamente 2 letras — ex.: `"SP"`  |
| `bairro`      | string | ✅           | Texto livre                         |
| `pais`        | string | —           | Padrão: `"Brasil"`                  |
| `numero`      | string | —           | Padrão: `""`                        |
| `complemento` | string | —           | Padrão: `""`                        |

O service valida se a UF e a cidade existem nos JSONs de mapeamento interno.
Se não existirem, o endereço inteiro é omitido do payload e o erro aparece
em `optional_field_errors`.

#### `PersonalizedFieldsSchema`

Todos os campos são opcionais (`null` = não enviar ao LegalOne).

**Campos de texto livre:**

| Campo                         | Tipo           | Observações                       |
|-------------------------------|----------------|-----------------------------------|
| `tag`                         | string \| null | Etiqueta interna                  |
| `cid`                         | string \| null | Código CID (ex.: `"M54"`)         |
| `referencia`                  | string \| null | Referência interna do escritório  |
| `link_drive`                  | string \| null | URL da pasta no Google Drive      |
| `data_vencimento_kit`         | string \| null | Data livre (ex.: `"30/04/2026"`)  |
| `data_vencimento_comprovante` | string \| null | Data livre                        |

**Campos SelectOne** — o valor enviado deve ser **exatamente** um dos aceitos
(incluindo acentos e capitalização):

| Campo                      | Tipo           | Valores aceitos                         |
|----------------------------|----------------|-----------------------------------------|
| `classificacao_backoffice` | string \| null | `"0"` · `"1"` · `"2"` · `"3"`          |
| `natureza_do_acidente`     | string \| null | `"Trabalho"` · `"Qualquer natureza"`    |
| `tratamento_da_lesao`      | string \| null | `"Cirúrgico"` · `"Conservador"`         |
| `tramitacao_prioritaria`   | string \| null | `"Sim"` · `"Não"`                       |

Se o valor enviado não constar entre os aceitos, o campo é omitido do
payload e o erro aparece em `optional_field_errors`.

#### `CreateContactResponse`

| Campo                   | Tipo                 | Descrição                                      |
|-------------------------|----------------------|------------------------------------------------|
| `success`               | boolean              | `true` quando o LegalOne confirmou o cadastro  |
| `optional_field_errors` | `FieldErrorSchema[]` | Lista de campos opcionais ignorados (pode ser vazia) |

#### `FieldErrorSchema`

| Campo        | Tipo   | Descrição                              |
|--------------|--------|----------------------------------------|
| `field_name` | string | Nome interno do campo no LegalOne      |
| `message`    | string | Mensagem descritiva do erro            |

---

### Processos

#### `LawsuitSearchRequest`

| Campo          | Tipo   | Obrigatório | Descrição                      |
|----------------|--------|-------------|--------------------------------|
| `contact_id`   | string | ✅           | ID do contato no LegalOne      |
| `contact_name` | string | ✅           | Nome do contato                |

#### `LawsuitSearchResponse` / `LawsuitDetailsResponse`

| Campo  | Tipo   | Descrição            |
|--------|--------|----------------------|
| `html` | string | HTML cru do LegalOne |

---

## Códigos de status e erros

Todos os erros retornam JSON no formato:

```json
{ "detail": "<mensagem>" }
```

Para erros múltiplos (campos obrigatórios rejeitados pelo servidor):

```json
{ "detail": ["CPF já cadastrado.", "Nome inválido."] }
```

| Status | Situação                                                                                                                                  |
|--------|-------------------------------------------------------------------------------------------------------------------------------------------|
| 200    | Sucesso. `optional_field_errors` pode ser não-vazio — o contato foi criado, mas alguns campos opcionais foram ignorados.                  |
| 422    | Dados inválidos no request (CPF malformado, nome com uma palavra, UF inválida) **ou** LegalOne rejeitou campos obrigatórios após o envio. |
| 502    | Erro HTTP ao se comunicar com o LegalOne, ou resposta em formato inesperado.                                                              |
| 503    | Falha de autenticação ou sessão indisponível temporariamente.                                                                             |
| 500    | Erro interno não classificado.                                                                                                            |

---

## Arquitetura resumida

```
app/
  routers/            ← FastAPI: valida schema, delega ao service
  schemas/            ← Contratos Pydantic da API pública
  error_handler.py    ← Mapeamento de exceções → HTTP status

services/
  contact_service.py  ← Lógica: resolve IDs, constrói DTO, chama crawler
  contact_types.py    ← Tipos públicos de entrada (NewContactRequest, etc.)

infrastructure/
  crawler/
    contacts.py         ← HTTP: monta multipart/form-data, executa POST
    contact_dto.py      ← DTO interno (ContactPayloadDTO e tipos *Resolvido)
    base_crawler.py     ← Retry com reautenticação, validação de sessão
    authenticator.py    ← Fluxo OAuth/BrowserHawk (Thomson Reuters)
    session_manager.py  ← Cookies persistidos em DynamoDB (lock distribuído)
    constants.py        ← User-Agent e sec-ch-ua compartilhados
    data/
      diarios_monitoramento.json  ← 84 diários monitorados

parsers/
  contact_parser.py   ← Interpreta HTML de resposta do POST

errors.py             ← Hierarquia de exceções do domínio
config.py             ← Settings (pydantic-settings, lê .env)
```


# Rota de tarefas (Fase 2, em desenvolvimento)
API caller                    Router              TaskService                    TasksCrawler              PayloadBuilder
    |                           |                      |                              |                         |
    |-- POST /tasks ----------->|                      |                              |                         |
    |   {numero_processo,       |-- schema → DTO cru ->|                              |                         |
    |    nomes_responsaveis,    |                      |-- resolve_processo_vinculo -->|                         |
    |    kanban_board_name?,    |                      |<--- (id, "Proc - 0008579") --|                         |
    |    kanban_column_name?,   |                      |-- lookup_usuario (N vezes) -->|                         |
    |    descricao,             |                      |<--- (envolvido_id, text) -----|                         |
    |    dt_*, hr_*, deadline_*,|                      |-- resolve_kanban (se dado) -->|                         |
    |    observacoes?}          |                      |<--- (board_id, col_id) -------|                         |
    |                           |                      |                              |                         |
    |                           |                      |-- monta TaskPayload -------->|                         |
    |                           |                      |   (DTO com todos IDs)        |-- build_payload ------->|
    |                           |                      |                              |<--- form-data fields ---|
    |                           |                      |                              |-- POST /Tarefas/Edit    |
    |                           |                      |<--- HTML response ------------|                         |
    |                           |<-- CreateTaskResult --|                              |                         |
    |<-- 200 {success, message}-|                      |                              |                         |
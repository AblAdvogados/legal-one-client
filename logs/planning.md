# Plano de Desenvolvimento — `legal-one-client`
> Revisado em 26/03/2026 (v10)

---

## Estado Atual dos Arquivos

| Arquivo | Situação |
|---|---|
| `errors.py` | ✅ Concluído — hierarquia completa com subclasses concretas |
| `config.py` | ✅ Concluído — Pydantic Settings; lê `.env` |
| `.env` / `.gitignore` | ✅ Concluídos |
| `infrastructure/crawler/base_crawler.py` | ✅ Concluído — sem alterações pendentes |
| `infrastructure/crawler/contacts.py` | ✅ Concluído — recebe `ContactPayloadDTO`; monta tuplas multipart; adiciona monitoramento |
| `infrastructure/crawler/lawsuits.py` | ✅ Concluído — HTTP puro |
| `parsers/contact_parser.py` | ✅ Concluído — `FieldError`, `CreateContactResult`, `interpret_create_response()` |
| `services/contact_types.py` | ✅ Concluído — `NewContactRequest`, `PersonalizedField` (atributos nomeados), `ContactPayloadDTO` e tipos internos |
| `services/contact_service.py` | ✅ Concluído — `build_dto()`, `ContactService.create_contact()`; erros específicos |
| `services/lawsuit_service.py` | ✅ Concluído — wrapper simples sobre `LawsuitsCrawler` |
| `tests/helpers.py` | ✅ Concluído — credenciais via `config.settings`; sem hardcode |
| `tests/contacts/test_create_contact.py` | ✅ Concluído — usa `ContactService` e `build_dto()` |
| `app/` | ✅ **Concluído** — `main.py`, `error_handler.py`, `dependencies.py`, routers e schemas |

---

## Hierarquia de Erros Atual (`errors.py`)

```
LegalOneError
├── SessionExpiredError
├── AuthenticationError
├── CrawlerError              (status_code, url)
├── ParseError
├── MappingError              ← base para erros de mapeamento de IDs
│   ├── UFNaoEncontradaError          (uf)
│   ├── MunicipioNaoEncontradoError   (cidade)
│   └── OpcaoSelectInvalidaError      (campo, valor, aceitos)
└── ValidationError           (errors: list[str])
    ├── EnderecoIncompletoError
    └── ContatoRejeitadoError         (errors: list[str])
```

---

## Arquitetura Alvo (completa)

```
legal-one-client/
│
├── errors.py                        ← hierarquia de exceções (transversal)
├── config.py                        ← Pydantic Settings; lê .env
│
├── infrastructure/
│   ├── crawler/
│   │   ├── base_crawler.py          ← headers, retry, _validate_response()
│   │   ├── contacts.py              ← recebe ContactPayloadDTO; monta multipart; POST
│   │   └── lawsuits.py              ← HTTP puro
│   └── database/
│       └── dynamo_client.py         ← wrapper boto3 (futuro)
│
├── parsers/
│   ├── contact_parser.py            ← interpret_create_response() → CreateContactResult
│   └── lawsuit_parser.py            ← Fase 2
│
├── services/
│   ├── contact_types.py             ← tipos públicos (NewContactRequest, PersonalizedField,
│   │                                   ContactPayloadDTO e tipos internos _*)
│   ├── contact_service.py           ← build_dto() + ContactService.create_contact()
│   ├── lawsuit_service.py           ← wrapper LawsuitsCrawler
│   └── data/
│       ├── estados_mapeados.json
│       └── municipios_mapeados.json
│
├── app/                             ← ❌ criar nos próximos passos
│   ├── main.py                      ← FastAPI + Mangum; registra routers e handlers
│   ├── error_handler.py             ← exceção do domínio → status HTTP + JSON
│   ├── routers/
│   │   ├── contacts.py              ← POST /contacts
│   │   └── lawsuits.py              ← POST /lawsuits/search, GET /lawsuits/{id}
│   └── schemas/
│       ├── contact_schemas.py       ← CreateContactRequest, CreateContactResponse
│       └── lawsuit_schemas.py       ← LawsuitSearchRequest, LawsuitSearchResponse
│
└── tests/
    ├── helpers.py
    ├── contacts/
    │   ├── test_create_contact.py
    │   └── test_get_contact_modal.py
    └── lawsuits/
        ├── test_search_by_contact.py
        └── test_get_lawsuit_details.py
```
---

app/
├─ main.py                     # Inicializa o FastAPI, registra rotas, middlewares e handlers de erro
│
├─ api/
│  └─ v1/
│     ├─ routers/             # Endpoints HTTP (controladores)
│     │  ├─ clients.py        # Recebe requisições de criação/consulta de clientes
│     │  ├─ processes.py      # Endpoints relacionados a processos
│     │  └─ tasks.py          # Endpoints relacionados a tarefas
│     │
│     └─ schemas/             # Pydantic models (validação de entrada/saída HTTP)
│        ├─ client.py         # Schemas do cliente (ClientCreateSchema, etc.)
│        ├─ process.py        # Schemas de processos
│        └─ task.py           # Schemas de tarefas
│
├─ services/                  # Camada de aplicação (orquestração)
│  ├─ client/
│  │  ├─ service.py           # Orquestra o caso de uso: valida, resolve lookups, monta payload limpo, chama crawler
│  │  ├─ dto.py               # DTOs do caso de uso (CreateClientInput, ClientCreatePayload, CreateClientResult)
│  │  └─ validators.py        # Regras de negócio (ex.: campo X só aceita A/B/C)
│  │
│  ├─ process/
│  │  ├─ service.py           # Orquestra casos de uso de processos
│  │  ├─ dto.py               # DTOs de processos
│  │  └─ validators.py        # Regras de negócio de processos
│  │
│  └─ task/
│     ├─ service.py           # Orquestra casos de uso de tarefas
│     ├─ dto.py               # DTOs de tarefas
│     └─ validators.py        # Regras de negócio de tarefas
│
├─ infra/                     # Infraestrutura (tudo que depende do site, HTML, Selenium, HTTP, DB)
│  ├─ crawlers/
│  │  ├─ client_crawler.py    # Executa automação do site para clientes (Selenium/HTTP)
│  │  ├─ process_crawler.py   # Automação para processos
│  │  ├─ task_crawler.py      # Automação para tarefas
│  │  │
│  │  ├─ payload_builders/    # Montagem do payload multipart/form-data exigido pelo site
│  │  │  ├─ client_payload_builder.py   # Constrói lista de tuplas (multipart) para criação de cliente
│  │  │  ├─ process_payload_builder.py  # Payload de processos
│  │  │  └─ task_payload_builder.py     # Payload de tarefas
│  │  │
│  │  └─ parsers/             # Parsing de HTML retornado pelo site
│  │     ├─ client_parser.py  # Interpreta HTML de sucesso/erro do cadastro de cliente
│  │     ├─ process_parser.py # Interpreta HTML de processos
│  │     └─ task_parser.py    # Interpreta HTML de tarefas
│  │
│  ├─ lookup/                 # Mapeamentos estáticos exigidos pelo site (não são domínio)
│  │  ├─ city_mapper.py       # "São Paulo" → "1234" (ID exigido pelo site)
│  │  ├─ state_mapper.py      # "SP" → "35"
│  │  └─ select_mapper.py     # Campos de select → valores esperados pelo site
│  │
│  └─ db/
│     └─ dynamo_session.py    # Armazena cookies/sessão no DynamoDB (TTL, renovação)
│
├─ core/
│  ├─ config.py               # Configurações globais (env vars, settings)
│  ├─ logging.py              # Configuração de logs estruturados
│  └─ errors.py               # Exceções customizadas + handler central do FastAPI
│
└─ tests/
   ├─ unit/                   # Testes unitários (services, payload builders, parsers)
   └─ integration/            # Testes integrados (crawler + sessão + lookup)

## Próximos Passos

### Passo A — `app/error_handler.py`

Mapeia cada exceção do domínio para status HTTP + corpo JSON padronizado.
Precisa existir antes de `main.py`.

| Exceção capturada | Status | `detail` no JSON |
|---|---|---|
| `EnderecoIncompletoError` | 422 | mensagem da exceção |
| `UFNaoEncontradaError` | 422 | mensagem da exceção |
| `MunicipioNaoEncontradoError` | 422 | mensagem da exceção |
| `OpcaoSelectInvalidaError` | 422 | mensagem da exceção |
| `ContatoRejeitadoError` | 422 | `errors` da exceção |
| `ValidationError` (base) | 422 | `errors` da exceção |
| `MappingError` (base) | 422 | mensagem da exceção |
| `AuthenticationError` | 503 | `"Falha de autenticação com o LegalOne"` |
| `SessionExpiredError` | 503 | `"Sessão expirada — tente novamente"` |
| `CrawlerError` | 502 | `"Erro HTTP ao acessar o LegalOne"` |
| `ParseError` | 502 | `"Resposta do LegalOne em formato inesperado"` |
| `LegalOneError` (base) | 500 | `"Erro interno inesperado"` |

> **Importante:** erros em campos **opcionais** (`optional_field_errors`)
> **não passam pelo error handler** — o service retorna `CreateContactResult`
> normalmente com status 200; o router os serializa no body.

```python
# app/error_handler.py
from fastapi import Request
from fastapi.responses import JSONResponse
from errors import (
    ContatoRejeitadoError, ValidationError, MappingError,
    AuthenticationError, SessionExpiredError, CrawlerError, ParseError, LegalOneError,
)

def register_error_handlers(app): ...
```

---

### Passo B — `app/schemas/contact_schemas.py` e `app/schemas/lawsuit_schemas.py`

Contratos Pydantic da API pública — independentes dos dataclasses dos services.

**`contact_schemas.py`**

```python
class PersonalizedFieldSchema(BaseModel):
    tag: str | None = None
    cid: str | None = None
    referencia: str | None = None
    link_drive: str | None = None
    data_vencimento_kit: str | None = None
    data_vencimento_comprovante: str | None = None
    classificacao_backoffice: str | None = None
    natureza_do_acidente: str | None = None
    tratamento_da_lesao: str | None = None
    tramitacao_prioritaria: str | None = None

class DadosPessoaisSchema(BaseModel):
    cpf: str                          # validar formato ###.###.###-##
    nome: str                         # validar mínimo 2 palavras
    data_nascimento: str | None = None  # formato DD/MM/AAAA
    sexo: str | None = None           # 'M' | 'F'
    observacao: str | None = None

class TelefonesSchema(BaseModel):
    celular: str | None = None
    telefone_residencial: str | None = None

class EnderecoSchema(BaseModel):
    cep: str
    logradouro: str
    cidade: str
    uf: str                           # validar 2 letras maiúsculas
    bairro: str
    pais: str = "Brasil"
    numero: str = ""
    complemento: str = ""

class CreateContactRequest(BaseModel):
    dados_pessoais: DadosPessoaisSchema
    telefones: TelefonesSchema | None = None
    endereco: EnderecoSchema | None = None
    personalized_fields: PersonalizedFieldSchema | None = None

class FieldErrorSchema(BaseModel):
    field_name: str
    message: str

class CreateContactResponse(BaseModel):
    success: bool
    optional_field_errors: list[FieldErrorSchema] = []
```

**`lawsuit_schemas.py`** (mínimo para o router funcionar)

```python
class LawsuitSearchRequest(BaseModel):
    contact_id: str
    contact_name: str

class LawsuitSearchResponse(BaseModel):
    html: str   # temporário até lawsuit_parser.py existir (Fase 2)
```

---

### Passo C — `app/routers/contacts.py` e `app/routers/lawsuits.py`

Os routers convertem schema → service call → response schema.
Não contêm lógica; não acessam infra diretamente.

**`contacts.py`**

```python
# POST /contacts
# 1. Converte CreateContactRequest → NewContactRequest (service types)
# 2. Chama ContactService.create_contact()
# 3. Converte CreateContactResult → CreateContactResponse
# 4. Retorna 200 mesmo com optional_field_errors preenchido
```

**`lawsuits.py`**

```python
# POST /lawsuits/search  → LawsuitService.search_by_contact()
# GET  /lawsuits/{id}    → LawsuitService.get_lawsuit_details()
```

---

### Passo D — `app/main.py`

Cola tudo: instancia serviços, registra routers e handlers, exporta `handler = Mangum(app)`.

```python
from fastapi import FastAPI
from mangum import Mangum
from app.error_handler import register_error_handlers
from app.routers import contacts, lawsuits
from config import settings
from infrastructure.crawler.contacts import ContactsCrawler
from infrastructure.crawler.lawsuits import LawsuitsCrawler
from infrastructure.crawler.session_manager import SessionManager
from services.contact_service import ContactService
from services.lawsuit_service import LawsuitService

app = FastAPI(title="LegalOne Client API")
register_error_handlers(app)
app.include_router(contacts.router, prefix="/contacts", tags=["contacts"])
app.include_router(lawsuits.router, prefix="/lawsuits", tags=["lawsuits"])

handler = Mangum(app)   # entrypoint AWS Lambda
```

A instanciação dos services/crawlers/session_manager pode usar
[FastAPI dependency injection](https://fastapi.tiangolo.com/tutorial/dependencies/)
para desacoplar do `main.py` e facilitar mocks nos testes.

---

## Fase 2 — Parsers completos e CU2 (após Fase 1)

| Tarefa | Arquivo | HTMLs de referência |
|---|---|---|
| `parse_contact_modal()` | `parsers/contact_parser.py` | `tests/contacts/results/contact_modal.html` |
| `parse_contact_details()` | `parsers/contact_parser.py` | `logs/customer_main_details.html`, `logs/customer_address.html`, `logs/customer_phones.html` |
| Parser busca processos | `parsers/lawsuit_parser.py` | `logs/search_processes_by_contact.html` |
| Parser detalhes processo | `parsers/lawsuit_parser.py` | `logs/detalhes_processo.html` |
| CU2 `get_contact()` | `services/contact_service.py` | — |
| `LawsuitService` com tipos | `services/lawsuit_service.py` | — |

---

## Fase 3 — Qualidade e Deploy

1. **Testes unitários offline** dos parsers (HTMLs de `logs/` como fixtures)
2. **Testes unitários** de `build_dto()` com mocks dos JSONs
3. **README** — exemplos de request/response JSON para CU1 e CU2
4. **IaC** — `template.yaml` (SAM): Lambda, DynamoDB, API Gateway, IAM roles

---

## Separação de Responsabilidades (estado atual)

| Camada | Faz | Não faz |
|---|---|---|
| `errors.py` | Define hierarquia de exceções com mensagens centralizadas | Nenhuma lógica |
| `config.py` | Lê variáveis de ambiente | Não acessa serviços externos |
| `infrastructure/crawler/` | HTTP; converte DTO → multipart; retry com reauth | Não valida, não mapeia IDs, não interpreta HTML |
| `parsers/` | HTML → tipos Python (funções puras, sem I/O) | Não faz I/O |
| `services/contact_types.py` | Tipos públicos de entrada e DTO intermediário | Sem lógica |
| `services/contact_service.py` | Valida entrada; resolve mapeamentos; produz `ContactPayloadDTO`; orquestra crawler + parser | Não monta tuplas multipart; não acessa externos diretamente |
| `app/schemas/` | Contratos Pydantic da API; validações de formato | Sem lógica de negócio |
| `app/routers/` | Define rotas; converte schema ↔ service types | Sem lógica; sem acesso a infra |
| `app/error_handler.py` | Exceção do domínio → status HTTP + JSON | Sem lógica de negócio |
| `app/main.py` | Instancia app; registra routers e handlers | Só cola as peças |
| `tests/helpers.py` | Fixtures de sessão; asserções genéricas | Sem credenciais hardcoded; sem lógica de domínio |


---


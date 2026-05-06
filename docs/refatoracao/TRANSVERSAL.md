# Refatoração — Temas Transversais

> Questões que afetam múltiplas rotas ou a arquitetura geral do projeto.  
> Estas etapas devem ser executadas em coordenação com as etapas específicas de cada rota.

---

## Sumário

| # | Etapa | Risco | Status |
|---|-------|-------|--------|
| 1 | [Centralizar funções `get_*_service()` em `app/dependencies.py`](#etapa-1--centralizar-funções-get_service-em-appdependenciespy) | 🟢 Baixo | ⬜ |
| 2 | [Interface Protocol para `ContactsCrawler`](#etapa-2--interface-protocol-para-contactscrawler) | 🟢 Baixo | ⬜ |
| 3 | [Hierarquia e semântica de exceções em `core/errors.py`](#etapa-3--hierarquia-e-semântica-de-exceções-em-coreerrorspy) | 🟢 Baixo | ⬜ |
| 4 | [Localização dos objetos de domínio e DTOs](#etapa-4--localização-dos-objetos-de-domínio-e-dtos) | 🟡 Médio | ⬜ |
| 5 | [Cobertura de testes — gaps identificados](#etapa-5--cobertura-de-testes--gaps-identificados) | 🟢 Baixo | ⬜ |

---

## Etapa 1 — Centralizar funções `get_*_service()` em `app/dependencies.py`

### Problema

Cada router define localmente sua própria função `get_*_service()` com corpo idêntico — simplesmente importa a instância de `app.dependencies` e a retorna. Este boilerplate está duplicado em quatro routers:

| Router | Funções locais |
|--------|---------------|
| `app/routers/contacts.py` | `get_contact_service()`, `get_lawsuit_service()` |
| `app/routers/lawsuits.py` | `get_lawsuit_service()` |
| `app/routers/tasks.py` | `get_task_service()` |
| `app/routers/search.py` | `get_search_service()` |

`get_lawsuit_service()` está duplicada em `contacts.py` e `lawsuits.py` — qualquer mudança precisa ser replicada.

### Ação

1. Em `app/dependencies.py`, adicionar as funções públicas de injeção:
   ```python
   def get_contact_service() -> ContactService:
       return contact_service

   def get_lawsuit_service() -> LawsuitService:
       return lawsuit_service

   def get_task_service() -> TaskService:
       return task_service

   def get_search_service() -> GlobalSearchService:
       return search_service
   ```
2. Em cada router, remover as definições locais e importar: `from app.dependencies import get_contact_service`.

### Justificativa

> Ponto único de modificação. `app.dependency_overrides` nos testes funciona independentemente de onde a função é importada, desde que seja a mesma referência.

---

## Etapa 2 — Interface Protocol para `ContactsCrawler`

### Problema

`ContactsCrawler` não tem interface formal. O método `lookup_grid_contact()` é chamado por dois services distintos (`ContactService` e `LawsuitService`) — é o ponto de acoplamento mais crítico. Sem interface:
- Mocks nos testes dependem de `MagicMock` sem verificação de assinatura.
- Não há documentação formal do contrato público do crawler.
- Substituir a implementação (ex.: para testes de integração offline) requer monkey-patching.

### Achados

| Arquivo | Situação |
|---------|---------|
| `infrastructure/crawler/contacts.py` | Sem ABC ou Protocol |
| `services/contact/service.py` | `ContactService.__init__(self, crawler: ContactsCrawler)` — tipo concreto |
| `services/lawsuit/lawsuit_service.py` | `LawsuitService.__init__(self, ..., contacts_crawler: ContactsCrawler)` — tipo concreto |

### Ação

1. Criar `infrastructure/crawler/interfaces.py`:
   ```python
   from typing import Protocol
   from services.contact.dto import ContactPayload  # ou infrastructure/crawler/dto.py após Etapa 4
   from infrastructure.crawler.dto import GridContact

   class ContactsCrawlerProtocol(Protocol):
       def get_contact_details(self, contato_id: str) -> str: ...
       def get_contact_lawsuits(self, contato_id: str) -> str: ...
       def get_contact_modal(self, contato_id: str) -> str: ...
       def create_contact(self, payload: ContactPayload) -> str: ...
       def lookup_grid_contact(self, termo: str) -> GridContact: ...
   ```
2. Anotar `ContactService.__init__` e `LawsuitService.__init__` para receber `ContactsCrawlerProtocol`.
3. Nos testes, criar stubs que satisfaçam o Protocol.

### Justificativa

> **Dependency Inversion Principle.** `Protocol` (structural typing do Python) não requer herança — a implementação concreta existente já satisfaz o contrato sem nenhuma modificação.

---

## Etapa 3 — Hierarquia e semântica de exceções em `core/errors.py`

### Problema

A hierarquia de exceções em `core/errors.py` está bem estruturada, mas há dois pontos de uso incorreto identificados:

#### 3a — `ParseError` usado para `Unauthorized` no crawler de busca
Detalhado em [GET_search.md — Etapa 1](GET_search.md#etapa-1--corrigir-parseerror--authenticationerror-no-crawler). Resumo: `raise ParseError(...)` para `Unauthorized=true` deveria ser `raise AuthenticationError(...)`.

#### 3b — Docstring incorreta em `ContactService`
Detalhado em [GET_contacts_cpf.md — Etapa 1](GET_contacts_cpf.md#etapa-1--corrigir-docstring--remover-parseerror-do-caminho-não-encontrado). A docstring de `get_contact_info_by_cpf` cita `ParseError` como caminho de "não encontrado" quando deveria ser `ContatoNaoEncontradoError`.

### Ação

Ver etapas específicas referenciadas acima.

### Mapa de exceções → status HTTP (estado atual)

| Exceção | Status HTTP | Handler |
|---------|------------|---------|
| `ContatoNaoEncontradoError` | 404 | `error_handler.py` |
| `ProcessoNaoEncontradoError` | 404 | `error_handler.py` |
| `UsuarioNaoEncontradoError` | 404 | `error_handler.py` |
| `AmbiguousUserError` | 409 | `error_handler.py` |
| `ContatoRejeitadoError` | 422 | `error_handler.py` |
| `TarefaRejeitadaError` | 422 | `error_handler.py` |
| `CrawlerError` | 502 | `error_handler.py` |
| `AuthenticationError` | 503 | `error_handler.py` |
| `SessionRefreshTimeoutError` | 503 | `error_handler.py` |
| `ParseError` | *(sem handler específico → 500)* | `LegalOneError` fallback |
| `ContactBuildError` | *(sem handler específico → 500)* | `LegalOneError` fallback |

---

## Etapa 4 — Localização dos objetos de domínio e DTOs

### Problema

Há objetos de domínio e DTOs espalhados em locais inconsistentes:

| Objeto | Local atual | Localização correta |
|--------|-------------|---------------------|
| `RowGridContact`, `GridContact` | `services/contact/dto.py` | `infrastructure/crawler/dto.py` (DTO de resposta do crawler) |
| `ContactPayload`, `ResolvedAddress`, `ResolvedPhone`, `ResolvedTextField`, `ResolvedSelectField` | `services/contact/dto.py` | Correto — são DTOs service → crawler |
| `CreateContactResult`, `FieldError` | `parsers/contact_parser.py` | Correto — tipos de retorno do parser |
| `LawsuitSummary` | `services/lawsuit/dto.py` | Poderia estar em `domain/lawsuit.py` se for value object de domínio |
| `CreateContactInput`, `PersonalData`, `Address`, `Phone`, `CustomFields` | `domain/contact.py` | Correto |
| `CreateTaskServiceInput`, `ResponsavelInput`, etc. | `services/task/dto.py` | Correto — DTOs de entrada do service |

### Regra de localização adotada no projeto

```
domain/          → Value objects de entrada/saída do domínio (sem dependência de framework)
services/*/dto.py → DTOs de entrada do service (sem IDs resolvidos) e 
                    DTOs de saída (service → crawler, totalmente resolvidos)
infrastructure/crawler/dto.py → DTOs que espelham estruturas JSON/HTML do LegalOne
parsers/         → Tipos de retorno dos parsers (resultado de leitura de HTML)
app/schemas/     → Schemas Pydantic — contrato público da API HTTP
```

### Ação

1. Criar `infrastructure/crawler/dto.py` e mover `RowGridContact`, `GridContact` para lá (ver [GET_contacts_lookup.md — Etapa 1](GET_contacts_lookup.md#etapa-1--mover-rowgridcontactgridcontact-para-infrastructure)).
2. Avaliar se `LawsuitSummary` pertence a `domain/lawsuit.py` ou permanece em `services/lawsuit/dto.py`.
3. Documentar a regra de localização no `README.md` ou em um `docs/ARQUITETURA.md`.

---

## Etapa 5 — Cobertura de testes — gaps identificados

### Contacts

| Arquivo | Lacuna |
|---------|--------|
| `tests/contacts/test_create_contact.py` | Cenário de `ContatoRejeitadoError` via router — verificar status HTTP retornado |
| `tests/contacts/test_lookup_by_cpf.py` | `GET /contacts/{cpf}?summary=false` — `ContactDetailsResponse` não testado via router |
| `tests/contacts/` | Teste unitário do mapper `contact_request_to_input()` após Etapa 4 de `POST_contacts.md` |

### Search

| Arquivo | Lacuna |
|---------|--------|
| `tests/search/` | `AuthenticationError` quando crawler recebe `Unauthorized=true` |
| `tests/search/` | `ValueError` para contexto inválido via `GET /search?contexts=Invalido` |
| `tests/search/` | Teste unitário de `GlobalSearchService.search()` após renomeação |

### Tasks

| Arquivo | Lacuna |
|---------|--------|
| `tests/tasks/` | Verificar cobertura do cenário `TarefaRejeitadaError` via router |
| `tests/tasks/` | Teste unitário do mapper `task_request_to_input()` após Etapa 1 de `POST_tasks.md` |

### Lawsuits

| Arquivo | Lacuna |
|---------|--------|
| `tests/lawsuits/` | Teste para `GET /lawsuits?term=` após renomeação do parâmetro |
| `tests/lawsuits/` | Teste unitário de `parse_list_of_lawsuits()` após movê-la para `parsers/lawsuit_parser.py` |

### Princípios para os testes

- **Testes de router** usam `TestClient` com `app.dependency_overrides` — verificam status HTTP e formato de resposta, sem I/O real.
- **Testes unitários de service** usam mocks que satisfazem o `Protocol` do crawler — sem HTTP real.
- **Testes unitários de parser** usam fixtures HTML de `tests/*/results/` — sem nenhuma dependência externa.
- **Testes de integração** (login real) ficam em classes separadas com sufixo `Integration` e podem ser skipados em CI.

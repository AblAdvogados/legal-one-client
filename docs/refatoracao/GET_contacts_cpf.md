# Refatoração — `GET /contacts/{cpf}`

> **Arquivo:** `app/routers/contacts.py`  
> **Service:** `services/contact/service.py`  
> **Parser:** `parsers/contact_parser.py`  
> **Schema:** `app/schemas/contact_schemas.py`

---

## Sumário

| # | Etapa | Risco | Status |
|---|-------|-------|--------|
| 1 | [Corrigir docstring — remover `ParseError` do caminho "não encontrado"](#etapa-1--corrigir-docstring--remover-parseerror-do-caminho-não-encontrado) | 🟢 Baixo | ⬜ |
| 2 | [Extrair `_contact_to_response()` para `app/mappers/`](#etapa-2--extrair-_contact_to_response-para-appmappers) | 🟡 Médio | ⬜ |
| 3 | [Centralizar `get_contact_service()` em `app/dependencies.py`](#etapa-3--centralizar-get_contact_service-em-appdependenciespy) | 🟢 Baixo | ⬜ |
| 4 | [Testes — cobrir `summary=false` e 404 no router](#etapa-4--testes--cobrir-summaryfalse-e-404-no-router) | 🟢 Baixo | ⬜ |

---

## Etapa 1 — Corrigir docstring — remover `ParseError` do caminho "não encontrado"

### Problema

A docstring de `ContactService.get_contact_info_by_cpf()` em `services/contact/service.py` lista `ParseError` como exceção possível para o caso "nenhum contato encontrado". Isso é semanticamente incorreto:

- `ContatoNaoEncontradoError` é a exceção correta — condição de negócio esperada.
- `ParseError` indica falha estrutural de HTML/JSON — reservado para quando o parser não consegue ler a resposta.

Confundir os dois tipos faz com que mantenedores esperem `ParseError` onde ocorre `ContatoNaoEncontradoError`, dificultando tratamento correto nos testes e nos callers.

### Achados

| Arquivo | Situação |
|---------|---------|
| `services/contact/service.py` | Docstring de `get_contact_info_by_cpf` cita `ParseError` como caminho de "não encontrado" |

### Ação

1. Atualizar a docstring de `get_contact_info_by_cpf` para listar apenas `ContatoNaoEncontradoError` no caminho "nenhum contato encontrado".
2. Manter `ParseError` apenas para o caso de HTML inesperado retornado pelos parsers.

### Justificativa

> Semântica de exceções: `ContatoNaoEncontradoError` é uma **condição de negócio esperada** — não um erro de programação. O `error_handler.py` já mapeia corretamente para 404. A docstring incorreta é um vetor de confusão para testes futuros.

---

## Etapa 2 — Extrair `_contact_to_response()` para `app/mappers/`

### Problema

A função `_contact_to_response()` em `app/routers/contacts.py` converte `ContactSummary` ou `ContactDetails` (domain) para `ContactSummaryResponse` ou `ContactDetailsResponse` (schema). Com ~60 linhas de mapeamento campo-a-campo, polui o router e não pode ser testada sem levantar o FastAPI.

Adicionalmente, a função contém um `assert isinstance(result, ContactSummary)` que pode lançar `AssertionError` em runtime se o service retornar um tipo inesperado — deveria ser uma verificação com mensagem clara.

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/routers/contacts.py` | `_contact_to_response()` com ~60 linhas dentro do router |
| `app/routers/contacts.py` | `assert isinstance(result, ContactSummary)` — `AssertionError` sem mensagem em caso de falha |

### Ação

1. Mover `_contact_to_response()` para `app/mappers/contact_mapper.py` (junto com o mapper da Etapa 4 de `POST_contacts.md`).
2. Substituir os `assert isinstance(...)` por verificação com `raise TypeError(...)` ou usar `if isinstance` com fallback.
3. No router, substituir pelo import: `from app.mappers.contact_mapper import contact_to_response`.

### Justificativa

> Mapeamento domain → response schema é responsabilidade de mapper, não de router. Testável unitariamente sem FastAPI.

---

## Etapa 3 — Centralizar `get_contact_service()` em `app/dependencies.py`

### Problema

`get_contact_service()` e `get_lawsuit_service()` são definidas localmente dentro de `app/routers/contacts.py`. Isso é boilerplate repetido — a mesma função (com corpo idêntico) existe em `lawsuits.py`. Qualquer mudança na instanciação dos services precisa ser replicada em cada router.

### Achados

| Arquivo | Função | Situação |
|---------|--------|---------|
| `app/routers/contacts.py` | `get_contact_service()` | Definida localmente, repete o padrão |
| `app/routers/contacts.py` | `get_lawsuit_service()` | Definida localmente, duplicada em `lawsuits.py` |
| `app/routers/lawsuits.py` | `get_lawsuit_service()` | Idem |
| `app/routers/tasks.py` | `get_task_service()` | Idem |
| `app/routers/search.py` | `get_search_service()` | Idem |

### Ação

1. Em `app/dependencies.py`, adicionar funções públicas `get_contact_service()`, `get_lawsuit_service()`, `get_task_service()`, `get_search_service()` — cada uma retornando a instância já criada.
2. Nos routers, remover as definições locais e importar de `app.dependencies`.

### Justificativa

> Centralizar injeção de dependência em `dependencies.py` garante ponto único de modificação e facilita substituição por mocks nos testes via `app.dependency_overrides`.

---

## Etapa 4 — Testes — cobrir `summary=false` e 404 no router

### Problema

O arquivo `tests/contacts/test_lookup_by_cpf.py` cobre o cenário `summary=True` (modal) e o 404, mas não cobre `summary=False` (página de detalhes) via router. Sem esse teste, uma regressão no path `ContactDetails` passaria despercebida.

### Achados

| Arquivo | Cobertura identificada | Lacuna |
|---------|----------------------|--------|
| `tests/contacts/test_lookup_by_cpf.py` | `summary=True`, 404 | `summary=False` — `ContactDetailsResponse` não testado pelo router |

### Ação

1. Adicionar em `TestLookupRouterUnit` um teste para `GET /contacts/{cpf}?summary=false`:
   - Mock de `ContactService.get_contact_info_by_cpf` retornando `ContactDetails`.
   - Verificar que a resposta tem status 200 e os campos `custom_fields` presentes.
2. Verificar que o teste de 404 usa `ContatoNaoEncontradoError` (não `ValueError`) — consistente com a Etapa 1.

### Justificativa

> Testes de router verificam o contrato HTTP (status codes, formato de resposta) de forma isolada e são a rede de segurança para refatorações futuras.

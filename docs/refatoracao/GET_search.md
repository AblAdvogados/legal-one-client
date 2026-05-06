# Refatoração — `GET /search`

> **Arquivo:** `app/routers/search.py`  
> **Service:** `services/search_service.py`  
> **Crawler:** `infrastructure/crawler/search.py`  
> **Parser:** `parsers/search_parser.py`

---

## Sumário

| # | Etapa | Risco | Status |
|---|-------|-------|--------|
| 1 | [Corrigir `ParseError` → `AuthenticationError` no crawler](#etapa-1--corrigir-parseerror--authenticationerror-no-crawler) | 🟢 Baixo | ⬜ |
| 2 | [Mover `SearchService` → `services/search/` e renomear](#etapa-2--mover-searchservice--servicessearch-e-renomear) | 🟢 Baixo | ⬜ |
| 3 | [Centralizar `get_search_service()` em `app/dependencies.py`](#etapa-3--centralizar-get_search_service-em-appdependenciespy) | 🟢 Baixo | ⬜ |
| 4 | [Testes — cobrir `AuthenticationError` e contexto inválido](#etapa-4--testes--cobrir-authenticationerror-e-contexto-inválido) | 🟢 Baixo | ⬜ |

---

## Etapa 1 — Corrigir `ParseError` → `AuthenticationError` no crawler

### Problema

Em `infrastructure/crawler/search.py`, quando a resposta JSON contém `Unauthorized=true`, o crawler lança `ParseError`:

```python
if data.get("Unauthorized"):
    raise ParseError(
        "Busca global retornou Unauthorized=true. "
        "Verifique se a conta tem permissão de acesso."
    )
```

`ParseError` é semanticamente reservado para falhas estruturais de HTML/JSON — quando o parser não consegue ler a resposta. `Unauthorized=true` é uma **falha de autorização/autenticação**, não uma falha de parsing. O tipo correto é `AuthenticationError`, que já existe em `core/errors.py` e já é mapeado pelo `error_handler.py`.

Consequência: o `error_handler.py` retorna o status errado para este caso, pois `ParseError` não tem handler específico e sobe como 500.

### Achados

| Arquivo | Situação |
|---------|---------|
| `infrastructure/crawler/search.py` | `raise ParseError(...)` para `Unauthorized=true` |
| `app/error_handler.py` | `ParseError` sem handler específico → 500 em vez de 401/503 |

### Ação

1. Substituir `raise ParseError(...)` no bloco `Unauthorized` por `raise AuthenticationError(...)`.
2. Verificar o `error_handler.py`: `AuthenticationError` deve retornar 503 (falha de sessão/autenticação) — já mapeado.
3. Atualizar a docstring de `GlobalSearchCrawler.search()` para refletir `AuthenticationError` no lugar de `ParseError`.

### Justificativa

> Tipos de exceção semânticos garantem que o `error_handler.py` mapeie status HTTP corretos. `ParseError` → 500; `AuthenticationError` → 503. A distinção importa para o caller e para os testes.

---

## Etapa 2 — Mover `SearchService` → `services/search/` e renomear

### Problema

`services/search_service.py` está na **raiz de `services/`**, enquanto todos os demais domínios têm subpastas organizadas (`contact/`, `lawsuit/`, `task/`). Há também assimetria de nomenclatura: o crawler se chama `GlobalSearchCrawler` mas o service se chama apenas `SearchService`.

Existe ainda um arquivo `services/search_service.py` duplicado na raiz que pode ser um artefato órfão — verificar.

### Achados

| Arquivo | Situação |
|---------|---------|
| `services/search_service.py` (raiz) | Fora do padrão estrutural do projeto |
| `services/search_service.py` | Classe `SearchService` — assimétrica com `GlobalSearchCrawler` |
| `infrastructure/crawler/search.py` | `GlobalSearchCrawler` — já correto |

### Ação

1. Criar `services/search/__init__.py`.
2. Mover `services/search_service.py` → `services/search/service.py`.
3. Renomear a classe `SearchService` → `GlobalSearchService`.
4. Atualizar todos os imports:
   - `app/routers/search.py`
   - `app/dependencies.py`
   - `tests/search/` (todos os arquivos de teste)
5. Verificar e remover o arquivo `services/search_service.py` na raiz se for órfão.

### Justificativa

> Consistência estrutural: todos os domínios têm subpastas em `services/`. A renomeação para `GlobalSearchService` espelha o nome do crawler e documenta o escopo global da busca.

---

## Etapa 3 — Centralizar `get_search_service()` em `app/dependencies.py`

### Problema

A função `get_search_service()` é definida localmente em `app/routers/search.py`, seguindo o mesmo anti-padrão de todos os outros routers (ver [GET_contacts_cpf.md — Etapa 3](GET_contacts_cpf.md#etapa-3--centralizar-get_contact_service-em-appdependenciespy)).

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/routers/search.py` | `get_search_service()` definida localmente |

### Ação

1. Mover `get_search_service()` para `app/dependencies.py` como função pública.
2. Em `app/routers/search.py`, substituir pela importação: `from app.dependencies import get_search_service`.

### Justificativa

> Ponto único de definição das funções de injeção de dependência. Facilita `app.dependency_overrides` nos testes.

---

## Etapa 4 — Testes — cobrir `AuthenticationError` e contexto inválido

### Problema

Após a Etapa 1, o comportamento do crawler muda para `AuthenticationError` quando `Unauthorized=true`. Sem testes, essa mudança pode ser revertida inadvertidamente.

### Achados

| Arquivo | Cobertura identificada | Lacuna |
|---------|----------------------|--------|
| `tests/search/` | A verificar | `AuthenticationError` para `Unauthorized=true` |
| `tests/search/` | A verificar | `ValueError` para contexto inválido via router |

### Ação

1. Adicionar teste unitário para `GlobalSearchCrawler.search()`:
   - Mock da resposta HTTP retornando `{"Unauthorized": true}`.
   - Verificar que `AuthenticationError` é levantada (não `ParseError`).
2. Adicionar teste de router para `GET /search?contexts=ContextoInvalido`:
   - Verificar retorno 422 com mensagem indicando o contexto inválido.
3. Adicionar teste unitário para `GlobalSearchService.search()` com contextos válidos:
   - Verificar que o resultado é um `GlobalSearchResult` com os grupos esperados.

### Justificativa

> Estes testes servem como rede de segurança para as refatorações das Etapas 1 e 2, garantindo que o comportamento de erro permanece correto após as mudanças.

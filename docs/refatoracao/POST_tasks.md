# Refatoração — `POST /tasks`

> **Arquivo:** `app/routers/tasks.py`  
> **Service:** `services/task/task_service.py`  
> **Schema:** `app/schemas/task_schemas.py`  
> **DTOs:** `services/task/dto.py`

---

## Sumário

| # | Etapa | Risco | Status |
|---|-------|-------|--------|
| 1 | [Extrair `_to_service_input()` para `app/mappers/`](#etapa-1--extrair-_to_service_input-para-appmappers) | 🟡 Médio | ⬜ |
| 2 | [Adicionar `warnings` em `CreateTaskResponse`](#etapa-2--adicionar-warnings-em-createtaskresponse) | 🟢 Baixo | ⬜ |
| 3 | [Centralizar `get_task_service()` em `app/dependencies.py`](#etapa-3--centralizar-get_task_service-em-appdependenciespy) | 🟢 Baixo | ⬜ |

---

## Etapa 1 — Extrair `_to_service_input()` para `app/mappers/`

### Problema

A função `_to_service_input()` em `app/routers/tasks.py` converte `CreateTaskRequest` (schema Pydantic) para `CreateTaskServiceInput` (domain DTO). Com ~50 linhas de mapeamento campo-a-campo, polui o router e não pode ser testada isoladamente sem levantar o FastAPI.

O mesmo problema existe em `contacts.py` — esta etapa deve ser feita em paralelo com [POST_contacts.md — Etapa 4](POST_contacts.md#etapa-4--extrair-_to_service_input-para-appmappers).

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/routers/tasks.py` | `_to_service_input()` com ~50 linhas dentro do router |

### Ação

1. Criar `app/mappers/task_mapper.py`.
2. Mover `_to_service_input()` para `task_mapper.py` renomeando para `task_request_to_input(req: CreateTaskRequest) → CreateTaskServiceInput`.
3. No router, substituir pela importação e chamada direta: `input_data = task_request_to_input(body)`.

### Justificativa

> Mesmo princípio do mapper de contacts: o router deve apenas rotear. Mapper em módulo separado é testável unitariamente e reutilizável.

---

## Etapa 2 — Adicionar `warnings` em `CreateTaskResponse`

### Problema

`CreateTaskResponse` tem `errors: list[str]` mas não tem `warnings`. `CreateContactResponse` (após refatoração) terá ambos os campos. A assimetria força callers a tratar as duas rotas de forma diferente.

Hoje o `TaskService` não produz warnings, mas a estrutura do payload builder pode gerar situações de degradação graciosa futura (campos opcionais que falham no mapeamento) — o mesmo padrão já existe em `ContactService`.

### Achados

| Schema | Campos atuais | Lacuna |
|--------|-------------|--------|
| `CreateTaskResponse` | `success`, `task_id`, `errors: list[str]` | Sem `warnings` |
| `CreateContactResponse` | `success`, `contact_id`, `errors: list[str]`, `warnings: list[str]` | — (após refatoração) |

### Ação

1. Adicionar `warnings: list[str] = []` em `CreateTaskResponse`.
2. O router já pode popular como lista vazia por enquanto — sem mudança de comportamento.

### Justificativa

> Consistência de contrato: callers que integram com `POST /contacts` e `POST /tasks` devem poder tratar as respostas de forma uniforme. Adicionar o campo agora evita uma quebra de contrato futura.

---

## Etapa 3 — Centralizar `get_task_service()` em `app/dependencies.py`

### Problema

`get_task_service()` é definida localmente em `app/routers/tasks.py`, seguindo o mesmo anti-padrão dos demais routers.

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/routers/tasks.py` | `get_task_service()` definida localmente |

### Ação

1. Mover `get_task_service()` para `app/dependencies.py` como função pública.
2. Em `app/routers/tasks.py`, substituir pela importação: `from app.dependencies import get_task_service`.

### Justificativa

> Ponto único de definição. Facilita `app.dependency_overrides` nos testes de integração do router.

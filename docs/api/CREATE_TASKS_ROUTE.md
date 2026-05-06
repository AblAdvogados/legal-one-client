# API — Criação de Tarefas (`POST /tasks`)

Referência rápida para consumidores da API e mantenedores do código.

> Documentação interativa completa disponível em `/docs` (Swagger UI) quando o servidor estiver rodando.

---

## Sumário

- [Request](#request)
- [Response](#response)
- [Códigos HTTP](#códigos-http)
- [Erros e soluções](#erros-e-soluções)
- [Exemplos](#exemplos)
- [Fluxo interno](#fluxo-interno)

---

## Request

**`POST /tasks`**

```json
{
  "numero_processo": "0008579",
  "responsaveis": [
    {
      "cpf": "485.180.028-26",
      "nome": "Maria Souza",
      "is_solicitante": true,
      "is_responsavel": true,
      "is_executante": false
    }
  ],
  "descricao": "Designar audiência",
  "dt_inicial": "20/05/2026",
  "hr_inicio": "09:00:00",
  "dt_final": "20/05/2026",
  "hr_final": "18:00:00",
  "deadline_date": "25/05/2026",
  "deadline_time": "17:00:00",
  "kanban": {
    "board_name": "BACKOFFICE",
    "column_name": "A DESIGNAR"
  },
  "lembretes": [],
  "incluir_recorrencia": false,
  "observacoes": "Verificar documentação prévia."
}
```

### Campos obrigatórios

| Campo | Tipo | Descrição |
|---|---|---|
| `numero_processo` | string | Número da pasta do processo no LegalOne |
| `responsaveis` | array (≥1) | Lista de responsáveis (ver regras abaixo) |
| `descricao` | string | Título da tarefa (modelo de descrição) |
| `dt_inicial` | string `dd/MM/yyyy` | Data de início |
| `hr_inicio` | string `HH:mm:ss` | Hora de início |
| `dt_final` | string `dd/MM/yyyy` | Data de conclusão prevista |
| `hr_final` | string `HH:mm:ss` | Hora de conclusão prevista |

### Campos opcionais

| Campo | Tipo | Padrão | Descrição |
|---|---|---|---|
| `deadline_date` | string `dd/MM/yyyy` | `null` | Data do prazo fatal. Se fornecido, `deadline_time` também é obrigatório |
| `deadline_time` | string `HH:mm:ss` | `null` | Hora do prazo fatal |
| `kanban` | objeto | `null` | Board e coluna Kanban |
| `lembretes` | array | `[]` | Lembretes por envolvido |
| `incluir_recorrencia` | bool | `false` | Inclui bloco de recorrência padrão |
| `observacoes` | string | `""` | Texto livre |

### Regras de validação do payload

- **`responsaveis`:** exatamente um item deve ter `is_solicitante=true`.
- **`responsaveis[].cpf` vs `nome`:** ao menos um dos dois é obrigatório por item. CPF é preferível — o lookup é exato e sem ambiguidade. Nome parcial pode retornar múltiplos usuários → erro `AmbiguousUserError`.
- **`deadline_date` + `deadline_time`:** ambos ou nenhum.

---

## Response

```json
{
  "success": true,
  "task_id": "102",
  "errors": []
}
```

| Campo | Tipo | Descrição |
|---|---|---|
| `success` | bool | `true` se a tarefa foi criada no LegalOne |
| `task_id` | string \| null | ID interno da tarefa no LegalOne (pode ser `null` se não identificado) |
| `errors` | array de string | Mensagens de rejeição do LegalOne quando `success=false` |

### `success=false` com HTTP 200

Quando o LegalOne rejeita campos obrigatórios, a API retorna **HTTP 200** com
`success=false` e `errors` preenchido. Isso é esperado — não é um erro de
infraestrutura, mas uma rejeição de negócio pelo sistema externo.

---

## Códigos HTTP

| Código | Situação |
|---|---|
| `200` | Processado — verificar campo `success` para saber se criou |
| `422` | Payload inválido (validação Pydantic falhou antes de chamar o LegalOne) |
| `502` | Erro HTTP inesperado ao acessar o LegalOne |
| `503` | Sessão expirada ou falha de autenticação com o LegalOne |

---

## Erros e soluções

| Erro | Causa | Solução |
|---|---|---|
| `ProcessoNaoEncontradoError` | `numero_processo` não encontrado no LegalOne | Verificar o número da pasta |
| `UsuarioNaoEncontradoError` | CPF ou nome não encontrado no LegalOne | Verificar CPF/nome do responsável |
| `AmbiguousUserError` | Nome retornou mais de um usuário | Informar `cpf` para desambiguar |
| `KanbanBoardNotFoundError` | `kanban.board_name` não encontrado | Verificar nome exato do board |
| `KanbanBoardColumnNotFoundError` | `kanban.column_name` não encontrada no board | Verificar nome exato da coluna |
| `TarefaRejeitadaError` (HTTP 200, `success=false`) | LegalOne rejeitou campos do formulário | Verificar campo `errors` da resposta |

---

## Exemplos

### Mínimo (sem Kanban, sem deadline)

```json
{
  "numero_processo": "0008579",
  "responsaveis": [
    {
      "cpf": "485.180.028-26",
      "is_solicitante": true,
      "is_responsavel": true,
      "is_executante": false
    }
  ],
  "descricao": "Designar audiência",
  "dt_inicial": "20/05/2026",
  "hr_inicio": "09:00:00",
  "dt_final": "20/05/2026",
  "hr_final": "18:00:00"
}
```

### Com Kanban e deadline

```json
{
  "numero_processo": "0008579",
  "responsaveis": [
    {
      "cpf": "485.180.028-26",
      "is_solicitante": true,
      "is_responsavel": true,
      "is_executante": false
    }
  ],
  "descricao": "Designar audiência",
  "dt_inicial": "20/05/2026",
  "hr_inicio": "09:00:00",
  "dt_final": "20/05/2026",
  "hr_final": "18:00:00",
  "deadline_date": "25/05/2026",
  "deadline_time": "17:00:00",
  "kanban": {
    "board_name": "BACKOFFICE",
    "column_name": "A DESIGNAR"
  }
}
```

### Resposta — tarefa criada

```json
{
  "success": true,
  "task_id": "102",
  "errors": []
}
```

### Resposta — rejeitada pelo LegalOne

```json
{
  "success": false,
  "task_id": null,
  "errors": [
    "O campo 'Hora de início previsto/efetivo' é obrigatório.",
    "O campo 'Envolvidos' é obrigatório."
  ]
}
```

---

## Fluxo interno

```
POST /tasks  (app/routers/tasks.py)
    │
    ├─ Validação Pydantic  (app/schemas/task_schemas.py)
    │
    ├─ _to_service_input()  → CreateTaskServiceInput
    │
    └─ TaskService.create_task()  (services/task/task_service.py)
            │
            ├─ _resolve_vinculo()         crawler.lookup_lawsuit()
            ├─ _resolve_responsavel()     crawler.lookup_user()
            ├─ _lookup_kanban_board()     crawler.lookup_kanban_boards()
            ├─ _lookup_kanban_column()    crawler.lookup_kanban_columns()
            │
            └─ _create_task_with_verification()
                    │
                    ├─ TasksCrawler.post_create_task()   (infrastructure/crawler/tasks.py)
                    │       └─ build_payload()  →  POST /processos/Tarefas/Edit
                    │
                    └─ interpret_create_task_response()  (parsers/task_parser.py)
                            │
                            ├─ form_error   → success=False + errors
                            ├─ listing      → busca tarefa na listagem
                            └─ post_success → extrai task_id do HTML
```

### Onde cada responsabilidade vive

| O quê | Onde |
|---|---|
| Contrato público (campos, validações) | `app/schemas/task_schemas.py` |
| Roteamento HTTP e tratamento de exceções | `app/routers/tasks.py` |
| Orquestração e resolução de IDs | `services/task/task_service.py` |
| Chamadas HTTP ao LegalOne | `infrastructure/crawler/tasks.py` |
| Montagem do form-data | `infrastructure/crawler/payload_builders/task_payload_builder.py` |
| Interpretação do HTML de resposta | `parsers/task_parser.py` |
| Testes | `tests/tasks/` |

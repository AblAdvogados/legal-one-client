Vou ler todos os arquivos do fluxo de tarefas antes de planejar.
</s>

Tenho o mapa completo. Aqui está o plano:

---

## Plano de logging — rota `POST /tasks`

### Mapa de cobertura atual vs. proposta

```
Request HTTP
  │
  ├─ [router] create_task()                  ← ❌ sem log nenhum
  │    ├─ _to_service_input()                ← sem log (conversão pura, ok)
  │    │
  │    ├─ [service] create_task()            ← ❌ sem log nenhum
  │    │    │
  │    │    ├─ _resolve_vinculo()            ← ❌ sem log
  │    │    │    └─ crawler.lookup_lawsuit() ← ❌ sem log
  │    │    │
  │    │    ├─ _resolve_responsavel() ×N     ← ❌ sem log
  │    │    │    └─ crawler.lookup_user()    ← ❌ sem log
  │    │    │
  │    │    ├─ _lookup_kanban_board()        ← ❌ sem log
  │    │    │    └─ crawler.lookup_kanban_boards() ← ❌ sem log
  │    │    │
  │    │    ├─ _lookup_kanban_column()       ← ❌ sem log
  │    │    │    └─ crawler.lookup_kanban_columns() ← ❌ sem log
  │    │    │
  │    │    ├─ crawler.create_task() POST    ← ❌ sem log de início/fim
  │    │    │
  │    │    └─ interpret_create_task_response() ← ❌ sem log
  │    │
  │    └─ return CreateTaskResponse          ← ❌ sem log
  │
  ├─ [error_handler]
  │    ├─ ✅ handlers LegalOneError logam com traceback
  │    └─ ✅ handler Exception genérico (fallback)
  │
  └─ Response HTTP
```

---

### Logs propostos (10 adições)

| # | Camada | Local | Nível | Mensagem | Justificativa |
|---|--------|-------|-------|----------|---------------|
| **1** | [`app/routers/tasks.py`](app/routers/tasks.py ) | `create_task()` — início | `INFO` | `"POST /tasks iniciado — numero_processo=%s, responsaveis=%d"` | Fecha o ciclo de visibilidade na camada HTTP. Com o log de conclusão (#10), permite medir tempo total incluindo serialização do response. Número de responsáveis dá contexto imediato sem expor dados sensíveis |
| **2** | [`services/task/task_service.py`](services/task/task_service.py ) | `create_task()` — início | `INFO` | `"create_task iniciado — numero_processo=%s, responsaveis=%d, kanban=%s"` | Ponto de entrada do domínio. Separa tempo de service do tempo de router. `kanban=%s` (board_name ou `"None"`) indica qual branch de resolução será executado |
| **3** | [`services/task/task_service.py`](services/task/task_service.py ) | `_resolve_vinculo()` — início e resultado | `INFO` | `"_resolve_vinculo: buscando processo=%s"` / `"_resolve_vinculo: resolvido — vinculo_id=%s, pasta=%s"` | A busca por processo é o lookup mais suscetível a falhas (processo inexistente, número errado, timeout). Logar início + resultado permite distinguir "falhou no lookup" de "falhou no parse do resultado" |
| **4** | [`services/task/task_service.py`](services/task/task_service.py ) | `_resolve_vinculo()` — no `raise ProcessoNaoEncontradoError` | `WARNING` | `"_resolve_vinculo: processo não encontrado — numero_processo=%s, count=%d"` | Diferente de um erro de sistema — é uma falha de negócio esperada. `WARNING` (não `ERROR`) porque o sistema funcionou corretamente ao rejeitar. `count` revela se o lookup retornou zero ou múltiplos resultados |
| **5** | [`services/task/task_service.py`](services/task/task_service.py ) | `_resolve_responsavel()` — início e resultado | `INFO` / `WARNING` | `"_resolve_responsavel: buscando por %s=%s"` (cpf ou nome) / `"_resolve_responsavel: resolvido — id=%s, text=%s"` | Executado N vezes (um por responsável). O `%s` inicial indica `"cpf"` ou `"nome"` — revela qual branch foi usado. Crítico para diagnosticar `AmbiguousUserError` (nome ambíguo) e `UsuarioNaoEncontradoError` |
| **6** | [`services/task/task_service.py`](services/task/task_service.py ) | `_resolve_responsavel()` — nos `raise` de erro | `WARNING` | `"_resolve_responsavel: usuário não encontrado — termo=%s"` / `"_resolve_responsavel: nome ambíguo — nome=%s, count=%d"` | Falhas de negócio esperadas — `WARNING`. `count` no caso ambíguo é valioso: permite saber se o sistema retornou 2 ou 20 resultados, ajudando o caller a entender se precisa usar CPF |
| **7** | [`services/task/task_service.py`](services/task/task_service.py ) | `_lookup_kanban_board()` e `_lookup_kanban_column()` — resultado | `INFO` / `WARNING` | `"_lookup_kanban_board: resolvido — board=%s, id=%s"` / `"_lookup_kanban_board: não encontrado — board_name=%s"` | Kanban é opcional — se não resolvido, a tarefa é criada sem kanban silenciosamente. O `WARNING` transforma esse comportamento silencioso em algo visível no CloudWatch |
| **8** | [`infrastructure/crawler/tasks.py`](infrastructure/crawler/tasks.py ) | `create_task()` — antes e depois do POST | `INFO` | `"create_task POST iniciado — processo_id=%s"` / `"create_task POST concluído — status=%d, html_len=%d, elapsed=%.2fs"` | Isola o tempo HTTP puro (rede + LegalOne) do tempo total do service. Análogo ao log #1 do crawler de contatos. `processo_id` correlaciona com os logs do service |
| **9** | [`parsers/task_parser.py`](parsers/task_parser.py ) | `_extract_title()` — no `raise ParseError` | `ERROR` | `"_extract_title: <title> não encontrada — html[:500]=%s"` | Análogo ao log crítico #3 do contact_parser. Captura o HTML que causou o `ParseError` antes que o error_handler o descarte. Sem esse log, `ParseError` em produção é completamente cego |
| **10** | `interpret_create_task_response()` — após extrair título | `DEBUG` | `"interpret_create_task_response: title=%s, errors=%d"` | Permite confirmar em DEBUG qual título foi extraído e quantos erros foram encontrados — útil em desenvolvimento sem ser verboso em produção |
| **11** | [`app/routers/tasks.py`](app/routers/tasks.py ) | `create_task()` — response final | `INFO` | `"POST /tasks concluído — success=%s, task_id=%s, warnings=%d"` | Fecha o ciclo. `task_id` confirma que o ID foi extraído corretamente pelo parser. Correlaciona com o log de início (#1) |

---

### O que **não** ganha log (e por quê)

| Local | Por quê não |
|-------|-------------|
| `_to_service_input()` (router) | Conversão pura 1:1, sem I/O |
| `build_payload()` (payload builder) | Montagem pura de tuplas, sem I/O |
| Lembretes e recorrência no payload builder | Condicionais simples, sem I/O — falha seria bug de código |
| `_ts()` no crawler | Função trivial sem I/O |

---

### Diferenças em relação ao fluxo de contatos

| Aspecto | Contatos | Tarefas |
|---------|----------|---------|
| Lookups antes do POST | nenhum | 3 a 5 (processo + N responsáveis + kanban opcional) |
| Falhas de negócio esperadas | `ContatoRejeitadoError` | `ProcessoNaoEncontradoError`, `UsuarioNaoEncontradoError`, `AmbiguousUserError`, `KanbanBoardNotFoundError`, `KanbanBoardColumnNotFoundError` |
| Logs de resolução | não se aplica | necessário em cada `_resolve_*` porque cada um pode falhar independentemente |
| Iteração por responsável | não se aplica | log #5 e #6 executam N vezes — nível `INFO`/`WARNING` (não `DEBUG`) porque cada resolução envolve I/O real |

---

### Princípios seguidos

1. **Correlação** — `numero_processo` e `processo_id` aparecem nos logs de router, service e crawler — permite rastrear uma request completa no CloudWatch Logs Insights com um único filtro.
2. **Dados sensíveis** — CPF não aparece em nenhum log de tarefa (não faz parte do fluxo de criação); nomes de responsáveis aparecem apenas em `WARNING` de falha, nunca em `INFO` de fluxo normal.
3. **Falha de negócio vs. erro de sistema** — `WARNING` para "não encontrado" / "ambíguo" (comportamento esperado), `ERROR` para falha de parse (inesperado), `CRITICAL` reservado para exceções não tratadas.
4. **HTML truncado** — apenas nos logs de `ERROR` de parse, limitado a 500 chars.
5. **Lazy interpolation** — `%s`/`%d` com argumentos separados em todos os loggers.

---

Quer que eu implemente?
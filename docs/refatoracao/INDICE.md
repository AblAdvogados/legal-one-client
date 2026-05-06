# Plano de Refatoração — legal-one-client

> **Como usar:**
> Cada arquivo cobre uma rota ou tema transversal.
> As etapas dentro de cada arquivo estão ordenadas por **prioridade de execução**.
> Marque os checkboxes conforme concluir cada etapa.

---

## Rotas

| Rota | Arquivo | Status |
|------|---------|--------|
| `POST /contacts` | [POST_contacts.md](POST_contacts.md) | 🔴 Pendente |
| `GET /contacts/lookup` | [GET_contacts_lookup.md](GET_contacts_lookup.md) | 🔴 Pendente |
| `GET /contacts/{cpf}` | [GET_contacts_cpf.md](GET_contacts_cpf.md) | 🔴 Pendente |
| `GET /lawsuits` | [GET_lawsuits.md](GET_lawsuits.md) | 🔴 Pendente |
| `GET /lawsuits/{id}` | [GET_lawsuits_id.md](GET_lawsuits_id.md) | 🔴 Pendente |
| `GET /search` | [GET_search.md](GET_search.md) | 🔴 Pendente |
| `POST /tasks` | [POST_tasks.md](POST_tasks.md) | 🔴 Pendente |

## Temas Transversais

| Tema | Arquivo | Status |
|------|---------|--------|
| Arquitetura de camadas, DTOs, interfaces, testes | [TRANSVERSAL.md](TRANSVERSAL.md) | 🔴 Pendente |

---

## Visão geral das prioridades

| Prioridade | Etapa | Rota / Tema | Risco |
|-----------|-------|-------------|-------|
| 1 | Validator de UF comentado | `POST /contacts` | 🟢 Baixo |
| 2 | `ParseError` vs `AuthenticationError` no crawler de busca | `GET /search` | 🟢 Baixo |
| 3 | Relocar `parse_list_of_lawsuits` para `parsers/` | `GET /lawsuits` | 🟢 Baixo |
| 4 | Renomear `SearchService` → `GlobalSearchService` e mover para `services/search/` | `GET /search` | 🟢 Baixo |
| 5 | Constantes `_FN_*` de texto livre no service → mover para `infrastructure/lookup/` | `POST /contacts` | 🟡 Médio |
| 6 | `RowGridContact`/`GridContact` no DTO do service → mover para `infrastructure/` | `GET /contacts/lookup` | 🟡 Médio |
| 7 | Extrair `_to_service_input()` do router para `app/mappers/` | `POST /contacts`, `POST /tasks` | 🟡 Médio |
| 8 | Centralizar funções `get_*_service()` em `app/dependencies.py` | Transversal | 🟡 Médio |
| 9 | `contact_id` ausente na resposta de criação de contato | `POST /contacts` | 🟡 Médio |
| 10 | Consistência `errors`/`warnings` entre `CreateContactResponse` e `CreateTaskResponse` | `POST /contacts`, `POST /tasks` | 🟡 Médio |
| 11 | Renomear `cpf` → `term` na rota de listagem de processos | `GET /lawsuits` | 🟡 Médio |
| 12 | Interface Protocol para `ContactsCrawler` | Transversal | 🟢 Baixo |
| 13 | `ContactFilterParams` / `LawsuitFilterParams` como classes `Depends` | `GET /contacts/lookup`, `GET /lawsuits` | 🟡 Médio |
| 14 | Validators `None → ""` centralizados nos schemas | `POST /contacts` | 🟢 Baixo |
| 15 | Cobertura de testes — contacts e search | Transversal | 🟢 Baixo |

# Refatoração — `GET /lawsuits`

> **Arquivo:** `app/routers/lawsuits.py`  
> **Service:** `services/lawsuit/lawsuit_service.py`  
> **Schema:** `app/schemas/lawsuit_schemas.py`  
> **Parser:** *(a criar)* `parsers/lawsuit_parser.py`

---

## Sumário

| # | Etapa | Risco | Status |
|---|-------|-------|--------|
| 1 | [Mover `parse_list_of_lawsuits` para `parsers/`](#etapa-1--mover-parse_list_of_lawsuits-para-parsers) | 🟢 Baixo | ⬜ |
| 2 | [Renomear parâmetro `cpf` → `term`](#etapa-2--renomear-parâmetro-cpf--term) | 🟡 Médio | ⬜ |
| 3 | [Remover `services/lawsuit_service.py` órfão](#etapa-3--remover-serviceslawsuit_servicepy-órfão) | 🟢 Baixo | ⬜ |
| 4 | [Encapsular filtros em `LawsuitFilterParams`](#etapa-4--encapsular-filtros-em-lawsuitfilterparams) | 🟡 Médio | ⬜ |

---

## Etapa 1 — Mover `parse_list_of_lawsuits` para `parsers/`

### Problema

A função `parse_list_of_lawsuits()` vive em `services/lawsuit/lawsuit_service.py`, mas é um **parser puro de HTML** — sem estado, sem I/O, sem dependência de infraestrutura. Seu contrato é idêntico ao dos demais parsers do projeto (`parsers/contact_parser.py`, `parsers/search_parser.py`): recebe HTML como string e retorna tipos Python estruturados.

Ter um parser dentro de um service viola a separação de camadas e impede que o parser seja testado isoladamente com fixtures HTML sem instanciar o service.

### Achados

| Arquivo | Função | Situação |
|---------|--------|---------|
| `services/lawsuit/lawsuit_service.py` | `parse_list_of_lawsuits(html: str)` | Parser puro vivendo no service |

### Ação

1. Criar `parsers/lawsuit_parser.py`.
2. Mover `parse_list_of_lawsuits()` para lá (junto com seus imports de `BeautifulSoup`, `re`, `LawsuitSummary`).
3. Em `services/lawsuit/lawsuit_service.py`, atualizar o import: `from parsers.lawsuit_parser import parse_list_of_lawsuits`.

### Justificativa

> Parsers puros em `services/` violam a separação de camadas. A convenção do projeto (`parsers/`) já está estabelecida e deve ser aplicada consistentemente.

---

## Etapa 2 — Renomear parâmetro `cpf` → `term`

### Problema

A rota `GET /lawsuits?cpf=...` aceita **apenas CPF** no nome do parâmetro, mas internamente `lookup_grid_contact()` já faz busca **por continência** — aceita nome ou CPF. O parâmetro `cpf` mente semanticamente para o caller: sugere que apenas CPF é aceito quando na verdade um nome parcial também funciona.

A assimetria se propaga para o service (`list_lawsuits_by_cpf`) e para o schema de resposta (`LawsuitListResponse.cpf`).

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/routers/lawsuits.py` | Parâmetro `cpf: str = Query(...)` — nome limitante |
| `services/lawsuit/lawsuit_service.py` | Método `list_lawsuits_by_cpf(cpf)` — nome incorreto |
| `app/schemas/lawsuit_schemas.py` | `LawsuitListResponse.cpf` — campo de resposta com nome errado |

### Ação

1. Renomear o query param de `cpf` para `term` em `app/routers/lawsuits.py`.
2. Atualizar a `description`: `"Termo de busca: nome completo ou parcial, ou CPF no formato ###.###.###-##."`.
3. Renomear `LawsuitService.list_lawsuits_by_cpf()` → `list_lawsuits_by_contact_term(term: str)`.
4. Atualizar `LawsuitListResponse`: renomear campo `cpf` → `term`.
5. Atualizar testes e docstrings.

### Justificativa

> A rota deve refletir o que ela faz. Expor `term` é honesto com o caller, elimina a restrição artificial de "apenas CPF" e abre espaço para buscas por nome sem quebrar o contrato.

---

## Etapa 3 — Remover `services/lawsuit_service.py` órfão

### Problema

Existe o arquivo `services/lawsuit_service.py` na **raiz de `services/`**, enquanto o service real está em `services/lawsuit/lawsuit_service.py`. O arquivo na raiz é um artefato de uma migração incompleta — um módulo morto que pode confundir importações futuras.

### Achados

| Arquivo | Situação |
|---------|---------|
| `services/lawsuit_service.py` | Arquivo na raiz — provavelmente órfão/obsoleto |
| `services/lawsuit/lawsuit_service.py` | Service real e em uso |

### Ação

1. Verificar se `services/lawsuit_service.py` tem algum conteúdo diferente do service real ou se é importado em algum lugar.
2. Se for órfão, remover o arquivo.
3. Verificar `services/search_service.py` na raiz pelo mesmo motivo (ver [GET_search.md](GET_search.md)).

### Justificativa

> Arquivos mortos são fontes de confusão. Um `import services.lawsuit_service` poderia silenciosamente importar o módulo errado.

---

## Etapa 4 — Encapsular filtros em `LawsuitFilterParams`

### Problema

Após a Etapa 2, a rota ficará com `term: str = Query(...)`. Futuros filtros (`status_processo`, `data_inicio`, `data_fim`, `page`, `page_size`) serão adicionados como parâmetros soltos na assinatura do endpoint.

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/routers/lawsuits.py` | Parâmetro de query solto — sem estrutura para extensão |

### Ação

1. Criar `LawsuitFilterParams` em `app/schemas/lawsuit_schemas.py`:
   ```python
   class LawsuitFilterParams:
       def __init__(self, term: str = Query(..., description="...")):
           self.term = term
   ```
2. Substituir `term: str = Query(...)` no endpoint por `filters: LawsuitFilterParams = Depends(LawsuitFilterParams)`.
3. Alinhar com `ContactFilterParams` (ver [GET_contacts_lookup.md](GET_contacts_lookup.md)) para consistência entre as rotas de listagem.

### Justificativa

> Padrão FastAPI para endpoints com múltiplos filtros. Facilita adição de novos filtros sem alterar a assinatura do endpoint.

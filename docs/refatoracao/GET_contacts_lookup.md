# Refatoração — `GET /contacts/lookup`

> **Arquivo:** `app/routers/contacts.py`  
> **Service:** `services/contact/service.py`  
> **Schema:** `app/schemas/contact_schemas.py`  
> **Crawler:** `infrastructure/crawler/contacts.py`

---

## Sumário

| # | Etapa | Risco | Status |
|---|-------|-------|--------|
| 1 | [Mover `RowGridContact`/`GridContact` para `infrastructure/`](#etapa-1--mover-rowgridcontactgridcontact-para-infrastructure) | 🟡 Médio | ⬜ |
| 2 | [Implementar interface Protocol no crawler](#etapa-2--implementar-interface-protocol-no-crawler) | 🟢 Baixo | ⬜ |
| 3 | [Encapsular parâmetros de filtro em `ContactFilterParams`](#etapa-3--encapsular-parâmetros-de-filtro-em-contactfilterparams) | 🟡 Médio | ⬜ |

---

## Etapa 1 — Mover `RowGridContact`/`GridContact` para `infrastructure/`

### Problema

Em `services/contact/dto.py`, a seção 3 define `RowGridContact` e `GridContact`:

```python
@dataclass
class RowGridContact:
    contact_id: int
    name: str
    cpf: str

@dataclass
class GridContact:
    contacts: List[RowGridContact]
    count: int
```

Estes tipos espelham diretamente a estrutura JSON retornada pelo endpoint `/contatos/Contatos/LookupGridContato` do LegalOne — são **DTOs de resposta do crawler**, não tipos de domínio do service. O método `ContactService.lookup_grid_contact()` faz o mapeamento `dict → RowGridContact` dentro do service, o que evidencia que o parsing do JSON cru está na camada errada.

Além disso, `LawsuitService` também chama `self._contacts_crawler.lookup_grid_contact()` e acessa o dict diretamente (`lookup_results["Rows"][0]["ContatoNome"]`), sem usar esses tipos — inconsistência entre os dois consumidores.

### Achados

| Arquivo | Situação |
|---------|---------|
| `services/contact/dto.py` | `RowGridContact`, `GridContact` — DTOs de crawler vivendo no service |
| `services/contact/service.py` | Mapeamento `dict → RowGridContact` dentro de `lookup_grid_contact()` |
| `services/lawsuit/lawsuit_service.py` | Acessa dict cru direto (`["Rows"][0]["ContatoNome"]`) — inconsistente |

### Ação

1. Criar `infrastructure/crawler/dto.py` (se não existir) e mover `RowGridContact` e `GridContact` para lá.
2. O mapeamento `dict → RowGridContact` pode migrar para dentro de `ContactsCrawler.lookup_grid_contact()`: o crawler passa a retornar `GridContact` em vez de `dict`.
3. Atualizar `ContactService.lookup_grid_contact()` para consumir `GridContact` diretamente.
4. Atualizar `LawsuitService.list_lawsuits_by_cpf()` para usar os campos tipados em vez de acessar o dict cru.
5. Atualizar todos os imports afetados.

### Justificativa

> O service não deve conhecer a estrutura interna do JSON retornado pela API. Encapsular o parsing no crawler elimina o acoplamento e garante que ambos os consumidores (`ContactService` e `LawsuitService`) usem o mesmo tipo tipado.

---

## Etapa 2 — Implementar interface Protocol no crawler

### Problema

`ContactsCrawler` não possui interface formal (ABC ou `Protocol`). O método `lookup_grid_contact` é chamado por **dois services distintos** (`ContactService` e `LawsuitService`) — é o ponto de acoplamento mais crítico da camada de infraestrutura. Sem interface:
- Mocks nos testes dependem de `MagicMock` sem verificação de assinatura.
- Não há documentação formal do contrato público do crawler.
- Não é possível substituir a implementação por um stub tipado.

### Achados

| Arquivo | Situação |
|---------|---------|
| `infrastructure/crawler/contacts.py` | Nenhuma ABC ou Protocol definindo o contrato |
| `services/contact/service.py` | `__init__(self, crawler: ContactsCrawler)` — tipo concreto |
| `services/lawsuit/lawsuit_service.py` | `__init__(self, ..., contacts_crawler: ContactsCrawler)` — tipo concreto |

### Ação

1. Criar `infrastructure/crawler/interfaces.py` com:
   ```python
   class ContactsCrawlerProtocol(Protocol):
       def get_contact_details(self, contato_id: str) -> str: ...
       def get_contact_lawsuits(self, contato_id: str) -> str: ...
       def get_contact_modal(self, contato_id: str) -> str: ...
       def create_contact(self, payload: ContactPayload) -> str: ...
       def lookup_grid_contact(self, termo: str) -> GridContact: ...
   ```
2. Anotar `ContactService.__init__` e `LawsuitService.__init__` para receber `ContactsCrawlerProtocol`.
3. Nos testes, criar stubs que satisfaçam o Protocol sem precisar de `MagicMock`.

### Justificativa

> **Dependency Inversion Principle**: services dependem de abstrações. `Protocol` (structural typing) não exige herança explícita — a implementação concreta existente já satisfaz o contrato sem modificação.

---

## Etapa 3 — Encapsular parâmetros de filtro em `ContactFilterParams`

### Problema

A rota `GET /contacts/lookup?term=...` recebe o filtro como query param simples. Hoje há apenas `term`, mas futuros filtros (`tipo_contato`, `ativo`, `page`, `page_size`) serão adicionados diretamente na assinatura do endpoint — crescimento ad hoc.

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/routers/contacts.py` | `term: str = Query(...)` — parâmetro solto na assinatura |
| `infrastructure/crawler/contacts.py` | `lookup_grid_contact(termo, pageSize='10')` — `pageSize` hardcoded |

### Ação

1. Criar `app/schemas/contact_schemas.py` → classe `ContactFilterParams`:
   ```python
   class ContactFilterParams:
       def __init__(self, term: str = Query(...), page_size: int = Query(default=10)):
           self.term = term
           self.page_size = page_size
   ```
2. Substituir `term: str = Query(...)` no endpoint por `filters: ContactFilterParams = Depends(ContactFilterParams)`.
3. Passar `filters.page_size` para `ContactService.lookup_grid_contact()` e propagar até o crawler.

### Justificativa

> Padrão FastAPI para endpoints com múltiplos filtros: encapsular em classe `Depends`-injetável evita assinaturas longas e facilita testes unitários do conjunto de parâmetros.

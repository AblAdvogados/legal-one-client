# Refatoração — `POST /contacts`

> **Arquivo:** `app/routers/contacts.py`  
> **Service:** `services/contact/service.py`  
> **Schema:** `app/schemas/contact_schemas.py`  
> **Parser:** `parsers/contact_parser.py`

---

## Sumário

| # | Etapa | Risco | Status |
|---|-------|-------|--------|
| 1 | [Ativar validator de UF](#etapa-1--ativar-validator-de-uf) | 🟢 Baixo | ⬜ |
| 2 | [Padronizar validators `None → ""`](#etapa-2--padronizar-validators-none---nos-schemas) | 🟢 Baixo | ⬜ |
| 3 | [Mover constantes `_FN_*` para `infrastructure/lookup/`](#etapa-3--mover-constantes-_fn_-para-infrastructurelookup) | 🟡 Médio | ⬜ |
| 4 | [Extrair `_to_service_input()` para `app/mappers/`](#etapa-4--extrair-_to_service_input-para-appmappers) | 🟡 Médio | ⬜ |
| 5 | [Incluir `contact_id` na resposta](#etapa-5--incluir-contact_id-na-resposta) | 🟡 Médio | ⬜ |
| 6 | [Padronizar `errors` e `warnings` como `list[str]`](#etapa-6--padronizar-errors-e-warnings-como-liststr) | 🟡 Médio | ⬜ |

---

## Etapa 1 — Ativar validator de UF

### Problema

O validator `validar_uf` em `AddressSchema` está **comentado**. Sem ele, o campo `uf` aceita qualquer string — incluindo valores absurdos como `"PARQUE BRISTOL"` (bairro/cidade passado por engano no campo errado). O erro só é detectado tardiamente no service, dentro de `map_uf_to_id()`, e sobe como um `value_error` genérico do Pydantic com mensagem confusa para o caller.

**Erro real observado:**
```
{'detail': [{'type': 'value_error', 'loc': ['body', 'endereco', 'uf'],
 'msg': "Value error, UF deve conter exatamente 2 letras (ex.: 'SP').",
 'input': 'PARQUE BRISTOL', 'ctx': {'error': {}}}]}
```
A mensagem é correta, mas o mecanismo está errado: o erro deveria ser validado no schema, não vazar do service como `ValueError`.

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/schemas/contact_schemas.py` | `validar_uf` comentado — nenhuma validação de formato de UF |
| `services/contact/service.py` | `map_uf_to_id(e.uf)` — falha tardia com mensagem opaca |

### Ação

1. Descomentar e ativar o validator `validar_uf` em `AddressSchema`.
2. Ajustar a mensagem: `"UF inválida: use a sigla de 2 letras (ex.: 'SP', 'RJ')."`.
3. Garantir `.strip().upper()` antes do `re.fullmatch` para tolerar caixa baixa e espaços.

### Justificativa

> **Fail fast:** erros de formato pertencem à fronteira da API (schema Pydantic) e devem retornar 422 com mensagem clara antes de qualquer chamada ao service.

---

## Etapa 2 — Padronizar validators `None → ""` nos schemas

### Problema

Campos opcionais dos schemas (`data_nascimento`, `sexo`, `observacao`) aceitam `None` do JSON de entrada, mas o service espera `""` para campos não informados. A conversão é feita manualmente com `or ""` espalhada na função `_to_service_input()` no router — lógica de contrato de dados vivendo fora da fronteira de validação.

### Achados

| Arquivo | Trecho | Problema |
|---------|--------|---------|
| `app/routers/contacts.py` | `dp.data_nascimento or ""` | Conversão manual no router |
| `app/routers/contacts.py` | `dp.sexo or ""`, `dp.observacao or ""` | Idem |
| `domain/contact.py` | `data_nascimento: Optional[str] = ""` | Default `""` mas aceita `None` — ambíguo |

### Ação

1. Em `PersonalDataSchema`, adicionar `@field_validator("data_nascimento", "sexo", "observacao", mode="before")` convertendo `None → ""`.
2. Após mover o mapper (Etapa 4), remover os `or ""` do `_to_service_input()`.
3. Manter `Optional[str] = None` nos domain objects que usam `None` como sentinela (ex.: `Address`, `CustomFields`).

### Justificativa

> A conversão `None → ""` é uma regra de contrato da API e deve estar no schema Pydantic (fronteira de entrada), não espalhada no código de mapeamento.

---

## Etapa 3 — Mover constantes `_FN_*` para `infrastructure/lookup/`

### Problema

Em `services/contact/service.py` existem seis constantes com os **nomes internos dos campos de texto livre** do formulário HTML do LegalOne:

```python
_FN_TAG        = "Tag_PessoaFisicaEntitySchema_p3699_o"
_FN_LINK_DRIVE = "LinkDaPasta_PessoaFisicaEntitySchema_p3700_o"
_FN_DT_KIT     = "DataVencimentoKit_PessoaFisicaEntitySchema_p3701_o"
_FN_DT_COMP    = "DataVencimentoComprovante_PessoaFisicaEntitySchema_p3702_o"
_FN_CID        = "CID_PessoaFisicaEntitySchema_p3706_o"
_FN_REFERENCIA = "Referencia_PessoaFisicaEntitySchema_p3716_o"
```

As constantes equivalentes dos campos `SelectOne` (`FN_CLASS_BACK`, `FN_NAT_ACIDENTE`, etc.) já estão corretamente em `infrastructure/lookup/select_mapper.py`. As constantes de texto livre estão deslocadas — são detalhes de implementação da API do LegalOne, não lógica de negócio.

### Achados

| Objeto | Local atual | Onde deve ficar |
|--------|-------------|-----------------|
| `_FN_TAG`, `_FN_LINK_DRIVE`, `_FN_DT_KIT`, `_FN_DT_COMP`, `_FN_CID`, `_FN_REFERENCIA` | `services/contact/service.py` | `infrastructure/lookup/select_mapper.py` (nova seção "campos de texto livre") |

### Ação

1. Mover as seis constantes para `infrastructure/lookup/select_mapper.py` em uma seção separada, como constantes públicas (sem prefixo `_`), seguindo o padrão `FN_TAG`, `FN_LINK_DRIVE`, etc.
2. Atualizar os imports em `services/contact/service.py`.

### Justificativa

> Se o LegalOne renomear um campo HTML, a mudança deve ser feita em um único lugar — `infrastructure/lookup/` — sem tocar no service.

---

## Etapa 4 — Extrair `_to_service_input()` para `app/mappers/`

### Problema

A função `_to_service_input()` em `app/routers/contacts.py` converte `CreateContactRequest` (schema Pydantic) para `CreateContactInput` (domain). Com ~40 linhas de mapeamento campo-a-campo, essa lógica polui o router e não pode ser testada isoladamente sem levantar o FastAPI.

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/routers/contacts.py` | `_to_service_input()` com ~40 linhas dentro do router |

### Ação

1. Criar `app/mappers/__init__.py` e `app/mappers/contact_mapper.py`.
2. Mover `_to_service_input()` para `contact_mapper.py` renomeando para `contact_request_to_input(req) → CreateContactInput`.
3. No router, substituir pelo import e chamada direta: `input_data = contact_request_to_input(body)`.
4. Mover também `_contact_to_response()` (conversor domain → response schema) para `contact_mapper.py`.

### Justificativa

> O router deve apenas receber a requisição HTTP, delegar ao service e retornar a resposta. Lógica de mapeamento em módulo separado é testável unitariamente e reutilizável.

---

## Etapa 5 — Incluir `contact_id` na resposta

### Problema

`CreateContactResponse` retorna apenas `success` e `warnings`. O LegalOne retorna o ID interno do contato criado no HTML de resposta — este ID não é capturado nem exposto. O caller que precisa vincular o contato recém-criado a um processo é forçado a fazer uma segunda chamada de busca por CPF.

`CreateTaskResponse` já retorna `task_id` — o comportamento deve ser simétrico.

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/schemas/contact_schemas.py` | `CreateContactResponse` sem campo `contact_id` |
| `parsers/contact_parser.py` | `CreateContactResult` sem campo `contact_id` |
| `services/contact/service.py` | `create_contact()` não repassa o ID ao resultado |

### Ação

1. Em `parsers/contact_parser.py`: verificar se o HTML de sucesso da criação de contato contém o ID (URL de redirect ou atributo de elemento). Extrair e adicionar `contact_id: str | None` em `CreateContactResult`.
2. Em `app/schemas/contact_schemas.py`: adicionar `contact_id: str | None = None` em `CreateContactResponse`.
3. Em `services/contact/service.py`: propagar `result.contact_id` ao retornar `CreateContactResult`.
4. Em `app/routers/contacts.py`: popular `contact_id` no `CreateContactResponse`.

### Justificativa

> Elimina round-trip extra para o caller. Simetria com `CreateTaskResponse.task_id`.

---

## Etapa 6 — Padronizar `errors` e `warnings` como `list[str]`

### Problema

Há inconsistências no contrato de resposta entre as rotas de criação:

| Schema | Campo | Tipo atual |
|--------|-------|-----------|
| `CreateContactResponse` | `warnings` | `list[FieldErrorDetail]` — objeto com `field_name` + `message` |
| `CreateContactResponse` | `errors` | **ausente** |
| `CreateTaskResponse` | `errors` | `list[str]` — string plana |
| `CreateTaskResponse` | `warnings` | **ausente** |

`FieldErrorDetail` duplica a estrutura de `FieldError` do parser. Objetos aninhados em campos de erro de API são over-engineering para o caso de uso atual.

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/schemas/contact_schemas.py` | `FieldErrorDetail` — duplicata desnecessária de `FieldError` |
| `app/schemas/contact_schemas.py` | `CreateContactResponse` sem `errors` |
| `app/schemas/task_schemas.py` | `CreateTaskResponse` sem `warnings` |
| `app/routers/contacts.py` | Converte `FieldError → FieldErrorDetail` manualmente |

### Ação

1. Remover `FieldErrorDetail` de `contact_schemas.py`.
2. Padronizar ambos os schemas:
   ```
   success: bool
   contact_id / task_id: str | None
   errors: list[str]
   warnings: list[str]
   ```
3. Atualizar o router `contacts.py` para converter `FieldError → str` (usar `e.message` ou `f"{e.field_name}: {e.message}"`).
4. Adicionar `warnings: list[str]` em `CreateTaskResponse` para simetria futura.

### Justificativa

> Contrato uniforme facilita integração do caller. `list[str]` é suficiente para mensagens de erro de API — o `field_name` pode compor a string quando relevante.

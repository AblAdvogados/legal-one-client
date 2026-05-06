# Refatoração — `GET /lawsuits/{id}`

> **Arquivo:** `app/routers/lawsuits.py`  
> **Service:** `services/lawsuit/lawsuit_service.py`  
> **Crawler:** `infrastructure/crawler/lawsuits.py`

---

## Sumário

| # | Etapa | Risco | Status |
|---|-------|-------|--------|
| 1 | [Estruturar resposta de detalhes do processo](#etapa-1--estruturar-resposta-de-detalhes-do-processo) | 🟡 Médio | ⬜ |

---

## Etapa 1 — Estruturar resposta de detalhes do processo

### Problema

A rota `GET /lawsuits/{lawsuit_id}` atualmente retorna o HTML bruto do LegalOne sem parsing estruturado:

```python
# LawsuitDetailsResponse
class LawsuitDetailsResponse(BaseModel):
    html: str
```

O próprio código documenta isso como provisório: _"Fase 2: retornar tipos estruturados"_. Expor HTML bruto como resposta de API é um anti-padrão — acopla o caller à estrutura interna do LegalOne e impede versionamento do contrato.

### Achados

| Arquivo | Situação |
|---------|---------|
| `app/routers/lawsuits.py` | `GET /{lawsuit_id}` retorna `LawsuitDetailsResponse(html=html)` |
| `app/schemas/lawsuit_schemas.py` | `LawsuitDetailsResponse` com campo `html: str` |
| `services/lawsuit/lawsuit_service.py` | `get_lawsuit_details()` repassa HTML sem transformação |
| `parsers/` | Nenhum parser de detalhes de processo existe |

### Ação

1. Analisar o HTML de `logs/html_lawsuit_details.html` para mapear os campos disponíveis.
2. Criar `parsers/lawsuit_parser.py` (se ainda não criado na Etapa 1 de [GET_lawsuits.md](GET_lawsuits.md)) e adicionar `parse_lawsuit_details(html: str) → LawsuitDetails`.
3. Definir `LawsuitDetails` em `domain/lawsuit.py` (criar se não existir) com os campos extraíveis.
4. Atualizar `LawsuitDetailsResponse` em `app/schemas/lawsuit_schemas.py` com os campos estruturados.
5. Atualizar `LawsuitService.get_lawsuit_details()` para usar o parser e retornar o domain object.
6. Atualizar o router para converter domain → response schema.

### Justificativa

> Retornar HTML bruto acopla o caller à estrutura do LegalOne. Qualquer mudança no HTML do LegalOne quebra silenciosamente quem consome a API. Parsing estruturado isola essa dependência no parser e garante um contrato estável para o caller.

> **Nota:** Esta é uma etapa de maior esforço (requer análise do HTML e definição do schema). Pode ser feita de forma incremental — iniciar com os campos mais utilizados e expandir.

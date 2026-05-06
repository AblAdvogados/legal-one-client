# filepath: app/schemas/search_schemas.py
"""
Schemas Pydantic para a rota GET /search.

Independentes dos dataclasses de parsers/ — são o contrato público da API.
"""

from typing import Literal
from pydantic import BaseModel, field_validator


# ── Response ──────────────────────────────────────────────────────────────────

class SearchResultItemResponse(BaseModel):
    """Um item de resultado dentro de um grupo."""
    description: str
    url: str
    extra_information: str | None = None


class SearchResultGroupResponse(BaseModel):
    """Grupo de resultados para um contexto (ex.: "Processos", "Contatos")."""
    context: str
    count: int
    items: list[SearchResultItemResponse]


class GlobalSearchResponse(BaseModel):
    """Resposta de GET /search."""
    groups: list[SearchResultGroupResponse]


# ── Query params ──────────────────────────────────────────────────────────────

VALID_CONTEXTS = Literal["Processos", "Contatos"]

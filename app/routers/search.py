# filepath: app/routers/search.py
"""
Router FastAPI para GET /search.

Busca global no LegalOne — retorna resultados de processos e/ou contatos
a partir de um termo livre (nome, CPF, número de processo, etc.).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.schemas.search_schemas import (
    GlobalSearchResponse,
    SearchResultGroupResponse,
    SearchResultItemResponse,
    VALID_CONTEXTS,
)
from services.search_service import SearchService

router = APIRouter()


# ── Dependency ────────────────────────────────────────────────────────────────

def get_search_service() -> SearchService:
    from app.dependencies import search_service
    return search_service


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("", response_model=GlobalSearchResponse)
async def global_search(
    term: Annotated[str, Query(description="Termo de busca: nome, CPF ou número de processo.")],
    contexts: Annotated[
        list[VALID_CONTEXTS],
        Query(description='Contextos a pesquisar. Repita o parâmetro para múltiplos valores.'),
    ] = ["Processos", "Contatos"],
    service: SearchService = Depends(get_search_service),
) -> GlobalSearchResponse:
    """
    Busca global no LegalOne por termo livre.

    - **200** — lista de grupos de resultados (um por contexto solicitado).
      Cada grupo expõe `count` (total no servidor) e `items` (até 20 por grupo).
    - **422** — `term` ausente ou `contexts` com valor inválido.
    - **502** — erro HTTP ao acessar o LegalOne.
    - **503** — falha de sessão ou autenticação.
    """
    result = service.search(term=term, contexts=list(contexts))

    return GlobalSearchResponse(
        groups=[
            SearchResultGroupResponse(
                context=group.context,
                count=group.count,
                items=[
                    SearchResultItemResponse(
                        description=item.description,
                        url=item.url,
                        extra_information=item.extra_information,
                    )
                    for item in group.items
                ],
            )
            for group in result.groups
        ]
    )

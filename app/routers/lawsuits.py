# filepath: app/routers/lawsuits.py
"""
Router FastAPI para a rota /lawsuits.
"""

from fastapi import APIRouter, Depends, Query

from app.schemas.lawsuit_schemas import (
    LawsuitDetailsResponse,
    LawsuitListResponse,
    LawsuitSummaryResponse,
)
from services.lawsuit.lawsuit_service import LawsuitService

router = APIRouter()


# ── Dependency ────────────────────────────────────────────────────────────────

def get_lawsuit_service() -> LawsuitService:
    from app.dependencies import lawsuit_service
    return lawsuit_service


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=LawsuitListResponse)
async def list_lawsuits(
    cpf: str = Query(description="CPF do contato no formato ###.###.###-##"),
    service: LawsuitService = Depends(get_lawsuit_service),
) -> LawsuitListResponse:
    """
    Lista os processos vinculados ao contato identificado pelo CPF.

    Internamente consulta a listagem de processos do LegalOne filtrada
    pelo nome e ID do contato correspondente ao CPF informado.

    - **200** — lista (possivelmente vazia) de processos encontrados.
    - **404** — nenhum contato encontrado para o CPF informado.
    - **502** — erro HTTP ao acessar o LegalOne.
    - **503** — falha de sessão ou autenticação.
    """
    processos = service.list_lawsuits_by_cpf(cpf=cpf)
    return LawsuitListResponse(
        cpf=cpf,
        total=len(processos),
        processos=[
            LawsuitSummaryResponse(
                processo_id=p.processo_id,
                numero_processo=p.numero_processo,
                titulo=p.titulo,
            )
            for p in processos
        ],
    )


@router.get("/{lawsuit_id}", response_model=LawsuitDetailsResponse)
async def get_lawsuit_details(
    lawsuit_id: str,
    service: LawsuitService = Depends(get_lawsuit_service),
) -> LawsuitDetailsResponse:
    """
    Retorna os detalhes de um processo pelo ID interno.

    Retorna HTML cru por ora (Fase 2: retornar tipos estruturados).
    """
    html = service.get_lawsuit_details(lawsuit_id)
    return LawsuitDetailsResponse(html=html)

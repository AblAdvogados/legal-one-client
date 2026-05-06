# filepath: app/schemas/lawsuit_schemas.py
"""
Schemas Pydantic para a rota /lawsuits.
"""

from pydantic import BaseModel


class LawsuitSummaryResponse(BaseModel):
    """Resumo de um processo retornado pela busca por CPF."""
    processo_id: str
    numero_processo: str
    titulo: str


class LawsuitListResponse(BaseModel):
    """Resposta de GET /lawsuits?cpf=... — lista de processos do contato."""
    cpf: str
    total: int
    processos: list[LawsuitSummaryResponse]


class LawsuitDetailsResponse(BaseModel):
    """Temporário — retorna HTML cru até lawsuit_parser.py existir (Fase 2)."""
    html: str

# filepath: parsers/search_parser.py
"""
Parser puro para a resposta JSON da busca global do LegalOne.

Não faz I/O — recebe o dict já decodificado e retorna tipos Python estruturados.
Testável offline com fixtures de dict sem precisar de sessão HTTP.
"""

from dataclasses import dataclass, field
from typing import Optional


# ── Tipos de retorno ──────────────────────────────────────────────────────────

@dataclass
class SearchResultItem:
    """Um item de resultado dentro de um grupo de busca."""
    description: str          # ex.: "ELIZABETE RIBEIRO DA SILVA SANTOS"
    url: str                  # ex.: "/contatos/Pessoas/Details/86797"
    extra_information: Optional[str] = None  # ex.: "Titulo AUXILIO ACIDENTE"; null para contatos


@dataclass
class SearchResultGroup:
    """
    Grupo de resultados para um contexto de busca (ex.: "Processos", "Contatos").

    count reflete o total no servidor — pode ser maior que len(items) se o
    servidor truncou os resultados (limite padrão: 20 por grupo).
    """
    context: str                        # "Processos" | "Contatos"
    count: int                          # total de resultados no servidor
    items: list[SearchResultItem] = field(default_factory=list)


@dataclass
class GlobalSearchResult:
    """Resultado completo da busca global — lista de grupos por contexto."""
    groups: list[SearchResultGroup] = field(default_factory=list)


# ── Função pública ────────────────────────────────────────────────────────────

def parse_search_results(data: dict) -> GlobalSearchResult:
    """
    Converte o dict JSON retornado pelo endpoint /shared/global/search em
    um GlobalSearchResult estruturado.

    Args:
        data: dict decodificado da resposta JSON do LegalOne.
              Espera a chave "Groups" com lista de grupos.

    Returns:
        GlobalSearchResult com todos os grupos e itens mapeados.
        Grupos ausentes ou vazios resultam em SearchResultGroup com items=[].
    """
    groups: list[SearchResultGroup] = []

    for raw_group in data.get("Groups", []):
        items = [
            SearchResultItem(
                description=item.get("Description") or "",
                url=item.get("Url") or "",
                extra_information=item.get("ExtraInformation") or None,
            )
            for item in raw_group.get("Items", [])
        ]
        groups.append(SearchResultGroup(
            context=raw_group.get("Name") or "",
            count=raw_group.get("Count") or 0,
            items=items,
        ))

    return GlobalSearchResult(groups=groups)

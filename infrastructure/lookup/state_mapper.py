"""
state_mapper.py — mapeia sigla/nome de UF para o ID interno do LegalOne.

Função pura: lê estados_mapeados.json uma única vez (via @cache) e resolve
a conversão sem nenhuma dependência de HTTP, sessão ou lógica de negócio.
"""

import json
from functools import cache
from pathlib import Path

from core.errors import UFNaoEncontradaError

_DATA_DIR = Path(__file__).parent / "data"

_SIGLA_PARA_NOME: dict[str, str] = {
    "AC": "Acre",              "AL": "Alagoas",          "AM": "Amazonas",
    "AP": "Amapá",             "BA": "Bahia",             "CE": "Ceará",
    "DF": "Distrito Federal",  "ES": "Espírito Santo",    "GO": "Goiás",
    "MA": "Maranhão",          "MG": "Minas Gerais",      "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso",       "PA": "Pará",              "PB": "Paraíba",
    "PE": "Pernambuco",        "PI": "Piauí",             "PR": "Paraná",
    "RJ": "Rio de Janeiro",    "RN": "Rio Grande do Norte","RO": "Rondônia",
    "RR": "Roraima",           "RS": "Rio Grande do Sul", "SC": "Santa Catarina",
    "SE": "Sergipe",           "SP": "São Paulo",          "TO": "Tocantins",
}


@cache
def _load_estados() -> dict[str, int]:
    with open(_DATA_DIR / "estados_mapeados.json", encoding="utf-8") as f:
        return json.load(f)


def map_uf_to_id(uf: str) -> str:
    """
    Converte sigla ou nome de UF para o ID interno do LegalOne.

    Args:
        uf: sigla ('SP') ou nome completo ('São Paulo') — case-insensitive.

    Returns:
        ID interno como string (ex.: '35').

    Raises:
        UFNaoEncontradaError: se a UF não constar no mapeamento.
    """
    estados = _load_estados()
    nome_estado = _SIGLA_PARA_NOME.get(uf.strip().upper(), uf.strip())
    uf_id = estados.get(nome_estado)
    if uf_id is None:
        raise UFNaoEncontradaError(uf)
    return str(uf_id)

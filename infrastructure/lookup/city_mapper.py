"""
city_mapper.py — mapeia nome de município para o ID interno do LegalOne.

Função pura: lê municipios_mapeados.json uma única vez (via @cache) e resolve
a conversão sem nenhuma dependência de HTTP, sessão ou lógica de negócio.
"""
import re
import json
import unicodedata
from functools import cache
from pathlib import Path

from core.errors import MunicipioNaoEncontradoError

_DATA_DIR = Path(__file__).parent / "data"


@cache
def _load_municipios() -> dict[str, int]:
    with open(_DATA_DIR / "municipios_mapeados.json", encoding="utf-8") as f:
        return json.load(f)


def _normalizar(texto: str) -> str:
    texto = re.sub(r'-', ' ', texto)  # remove hífens
    return (
        unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().lower().strip()
    )


def map_cidade_to_id(cidade: str) -> str:
    """
    Converte nome de município para o ID interno do LegalOne.

    A comparação é case-insensitive e ignora acentos.

    Args:
        cidade: nome do município (ex.: 'São Paulo', 'Atibaia').

    Returns:
        ID interno como string (ex.: '1234').

    Raises:
        MunicipioNaoEncontradoError: se o município não constar no mapeamento.
    """
    municipios = _load_municipios()
    cidade_norm = _normalizar(cidade)
    for nome, cidade_id in municipios.items():
        if _normalizar(nome) == cidade_norm:
            return str(cidade_id)
    raise MunicipioNaoEncontradoError(cidade)

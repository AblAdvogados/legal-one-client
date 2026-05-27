"""
tipo_tarefa_mapper.py — resolve tipo/subtipo de tarefa para (Path, Id) do LegalOne.

Lookup normalizado: strip + lowercase + remoção de acentos.
Lança TipoTarefaNaoEncontradoError se não encontrado.
"""

import json
import unicodedata
from functools import cache
from pathlib import Path

from core.errors import TipoTarefaNaoEncontradoError

DEFAULT_TIPO_TEXT = "Diversos"
DEFAULT_TIPO_ID = "tipo_4"

_JSON_PATH = Path(__file__).parent / "data" / "tipos_tarefa.json"

def _normalizar(texto: str) -> str:
    """Strip + lowercase + remove acentos (NFD → ASCII)."""
    sem_acento = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.strip().lower()


@cache
def _load_index() -> dict[str, dict]:
    """Retorna dict: path_normalizado → entry. Executado uma vez."""
    with open(_JSON_PATH, encoding="utf-8") as f:
        data: list[dict] = json.load(f)["data"]
    return {_normalizar(entry["Path"]): entry for entry in data}


def map_tipo_tarefa(tipo: str | None, subtipo: str | None = None) -> tuple[str, str]:
    """
    Resolve tipo (e opcionalmente subtipo) para (tipo_text, tipo_id).

    Args:
        tipo: label do tipo (ex.: 'BACKOFFICE'). None → retorna defaults.
        subtipo: label do subtipo (ex.: 'ANALISE DE CASO'). None = sem subtipo.

    Returns:
        Tupla (Path, Id), ex.: ('BACKOFFICE / ANALISE DE CASO', 'subtipo_812').
        Quando tipo is None: ('Diversos', 'tipo_4').

    Raises:
        TipoTarefaNaoEncontradoError: tipo ou subtipo não encontrado no JSON.
    """
    if tipo is None:
        return DEFAULT_TIPO_TEXT, DEFAULT_TIPO_ID

    if subtipo:
        path_input = f"{tipo.strip()} / {subtipo.strip()}"
    else:
        path_input = tipo.strip()

    index = _load_index()
    entry = index.get(_normalizar(path_input))
    if entry is None:
        raise TipoTarefaNaoEncontradoError(tipo=tipo, subtipo=subtipo)

    return entry["Path"], entry["Id"]

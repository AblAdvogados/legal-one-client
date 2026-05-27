"""
estado_civil_mapper.py — mapeia label de estado civil para o ID interno do LegalOne.

Lookup case-insensitive com strip; lança OpcaoSelectInvalidaError se não encontrado.
"""

import json
from functools import cache
from pathlib import Path

from core.errors import OpcaoSelectInvalidaError

_DATA_DIR = Path(__file__).parent / "data"


@cache
def _load_estados_civis() -> dict[str, tuple[str, str]]:
    """Retorna dict: label_lower → (label_canônico, id_str). Executado uma vez."""
    with open(_DATA_DIR / "estados_civis_mapeados.json", encoding="utf-8") as f:
        raw: dict[str, int] = json.load(f)
    return {k.strip().lower(): (k.strip(), str(v)) for k, v in raw.items()}


def map_estado_civil_to_id(label: str) -> tuple[str, str]:
    """
    Converte label de estado civil para (label_canônico, ID interno do LegalOne).

    Args:
        label: label exibido ao usuário (ex.: 'Divorciado') — case-insensitive.

    Returns:
        Tupla (label_canônico, id_str), ex.: ('Divorciado', '4').

    Raises:
        OpcaoSelectInvalidaError: se o label não constar no mapeamento.
    """
    index = _load_estados_civis()
    entry = index.get(label.strip().lower())
    if entry is None:
        raise OpcaoSelectInvalidaError(
            campo="EstadoCivil",
            valor=label,
            aceitos=[canonical for canonical, _ in index.values()],
        )
    return entry

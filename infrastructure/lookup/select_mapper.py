"""
select_mapper.py — mapeia labels de campos SelectOne para IDs internos do LegalOne.

Dados estáticos: os IDs são fixos no formulário do LegalOne e não requerem I/O.
"""

from core.errors import MappingError, OpcaoSelectInvalidaError

# ── Nomes internos dos campos SelectOne no formulário LegalOne ───────────────
FN_CLASS_BACK   = "ClassificacaoBackoffice_PessoaFisicaEntitySchema_p3703_o"
FN_NAT_ACIDENTE = "NaturezaDoAcidente_PessoaFisicaEntitySchema_p3704_o"
FN_TRAT_LESAO   = "TratamentoDaLesao_PessoaFisicaEntitySchema_p3705_o"
FN_TRAMIT_PRIOR = "TramitacaoPrioritaria_PessoaFisicaEntitySchema_p3707_o"

# ── Mapeamento label → ID para cada campo ────────────────────────────────────
_SELECT_OPTIONS: dict[str, dict[str, str]] = {
    FN_CLASS_BACK: {
        "0": "1",
        "1": "2",
        "2": "3",
        "3": "4",
    },
    FN_NAT_ACIDENTE: {
        "Trabalho": "5",
        "Qualquer natureza": "6",
    },
    FN_TRAT_LESAO: {
        "Cirúrgico": "7",
        "Conservador": "8",
    },
    FN_TRAMIT_PRIOR: {
        "Sim": "9",
        "Não": "10",
    },
}


def map_select_to_id(field_name: str, value: str) -> str:
    """
    Converte o label exibido de um campo SelectOne para o ID interno do LegalOne.

    Args:
        field_name: nome interno do campo (use as constantes FN_* deste módulo).
        value: label exibido ao usuário (ex.: 'Trabalho', 'Sim').

    Returns:
        ID interno como string (ex.: '5').

    Raises:
        MappingError: se o field_name não tiver mapeamento registrado.
        OpcaoSelectInvalidaError: se o value não for uma opção válida.
    """
    options = _SELECT_OPTIONS.get(field_name)
    if options is None:
        raise MappingError(f"Campo SelectOne '{field_name}' sem mapeamento em select_mapper.")
    field_id = options.get(value)
    if field_id is None:
        raise OpcaoSelectInvalidaError(
            campo=field_name,
            valor=value,
            aceitos=list(options.keys()),
        )
    return field_id


def accepted_values(field_name: str) -> list[str]:
    """Retorna a lista de labels válidos para um campo SelectOne."""
    options = _SELECT_OPTIONS.get(field_name)
    if options is None:
        raise MappingError(f"Campo SelectOne '{field_name}' sem mapeamento em select_mapper.")
    return list(options.keys())

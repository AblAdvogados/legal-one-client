# filepath: infrastructure/crawler/lookup_responses.py
"""
Dataclasses que modelam as respostas JSON dos endpoints de lookup do LegalOne.

Cada classe mapeia apenas os campos de interesse do JSON retornado pela API,
ignorando campos irrelevantes para o domínio de tarefas.

Padrão geral da API LegalOne:
    { "Count": int, "Rows": [...], "Columns": [], "ColumnsHeaders": [], "CustomErrorMessage": null }

As classes aqui representam a estrutura ``{ count, rows }`` de cada lookup.
"""
from __future__ import annotations

from dataclasses import dataclass


# ══════════════════════════════════════════════════════════════════════════════
# Lookup de processo (LookupLawSuit)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class LawsuitLookupRow:
    """
    Uma linha do lookup de processo (``/agenda/Compromissos/LookupLawSuit``).

    Campos de interesse extraídos do JSON:
      - ``Id``                   → :attr:`id` (ID interno — usado como VinculoGridId no payload)
      - ``ProcessNumber``        → :attr:`numero_processo` (número CNJ ou antigo)
      - ``Pasta``                → :attr:`nome_pasta_processo` (ex: ``"Proc - 0008579"``)
      - ``Titulo``               → :attr:`titulo` (título do processo)
      - ``ClientePrincipalNome`` → :attr:`nome_cliente_principal`
      - ``ClientePrincipalId``   → :attr:`id_cliente_principal`
    """
    id: int
    numero_processo: str | None
    nome_pasta_processo: str | None
    titulo: str | None
    nome_cliente_principal: str | None
    id_cliente_principal: int | None

    @classmethod
    def from_dict(cls, raw: dict) -> LawsuitLookupRow:
        return cls(
            id=raw["Id"],
            numero_processo=raw.get("ProcessNumber"),
            nome_pasta_processo=raw.get("Pasta"),
            titulo=raw.get("Titulo"),
            nome_cliente_principal=raw.get("ClientePrincipalNome"),
            id_cliente_principal=raw.get("ClientePrincipalId"),
        )


@dataclass(frozen=True)
class LawsuitLookupResponse:
    """
    Resposta completa do lookup de processos.

    Retornada por ``GET /agenda/Compromissos/LookupLawSuit``.
    """
    count: int
    rows: list[LawsuitLookupRow]

    @classmethod
    def from_dict(cls, raw: dict) -> LawsuitLookupResponse:
        return cls(
            count=raw["Count"],
            rows=[LawsuitLookupRow.from_dict(r) for r in raw.get("Rows", [])],
        )


# ══════════════════════════════════════════════════════════════════════════════
# Lookup de usuário (LookupGridUsuario)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class UserLookupRow:
    """
    Uma linha do lookup de usuário (``/config/Usuarios/LookupGridUsuario``).

    Campos de interesse extraídos do JSON:
      - ``ContatoId``       → :attr:`contato_id`
      - ``ContatoNome``     → :attr:`contato_nome`
      - ``ContatoCPF_CNPJ`` → :attr:`cpf`
    """
    contato_id: int
    contato_nome: str
    cpf: str | None

    @classmethod
    def from_dict(cls, raw: dict) -> UserLookupRow:
        return cls(
            contato_id=raw["ContatoId"],
            contato_nome=raw["ContatoNome"],
            cpf=raw.get("ContatoCPF_CNPJ"),
        )


@dataclass(frozen=True)
class UserLookupResponse:
    """Resposta completa do lookup de usuários."""
    count: int
    rows: list[UserLookupRow]

    @classmethod
    def from_dict(cls, raw: dict) -> UserLookupResponse:
        return cls(
            count=raw["Count"],
            rows=[UserLookupRow.from_dict(r) for r in raw.get("Rows", [])],
        )


# ══════════════════════════════════════════════════════════════════════════════
# Lookup de Kanban Board (LookupKanbanBoard)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class KanbanBoardRow:
    """
    Uma linha do lookup de board Kanban (``/agenda/CompromissoTarefa/LookupKanbanBoard``).

    Campos de interesse extraídos do JSON:
      - ``Id``    → :attr:`id`
      - ``Value`` → :attr:`value` (nome do board, ex: ``"BACKOFFICE"``)
    """
    id: int
    value: str

    @classmethod
    def from_dict(cls, raw: dict) -> KanbanBoardRow:
        return cls(id=raw["Id"], value=raw["Value"])


@dataclass(frozen=True)
class KanbanBoardLookupResponse:
    """Resposta completa do lookup de boards Kanban."""
    count: int
    rows: list[KanbanBoardRow]

    @classmethod
    def from_dict(cls, raw: dict) -> KanbanBoardLookupResponse:
        return cls(
            count=raw["Count"],
            rows=[KanbanBoardRow.from_dict(r) for r in raw.get("Rows", [])],
        )


# ══════════════════════════════════════════════════════════════════════════════
# Lookup de Kanban Column (LookupKanbanColumn)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class KanbanColumnRow:
    """
    Uma linha do lookup de coluna Kanban (``/agenda/CompromissoTarefa/LookupKanbanColumn``).

    Campos de interesse extraídos do JSON:
      - ``Id``    → :attr:`id`
      - ``Value`` → :attr:`value` (nome da coluna, ex: ``"A DESIGNAR"``)
    """
    id: int
    value: str

    @classmethod
    def from_dict(cls, raw: dict) -> KanbanColumnRow:
        return cls(id=raw["Id"], value=raw["Value"])


@dataclass(frozen=True)
class KanbanColumnLookupResponse:
    """Resposta completa do lookup de colunas Kanban."""
    count: int
    rows: list[KanbanColumnRow]

    @classmethod
    def from_dict(cls, raw: dict) -> KanbanColumnLookupResponse:
        return cls(
            count=raw["Count"],
            rows=[KanbanColumnRow.from_dict(r) for r in raw.get("Rows", [])],
        )


# ══════════════════════════════════════════════════════════════════════════════
# Lookup de Descrição (LookupModeloDescricaoTarefa)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class DescricaoLookupRow:
    """
    Uma linha do lookup de descrição de tarefa
    (``/config/ModeloDescricaoCompromissoTarefa/LookupModeloDescricaoTarefa``).

    Campos de interesse extraídos do JSON:
      - ``Id``    → :attr:`id`
      - ``Value`` → :attr:`value` (nome da descrição, ex: ``"A designar"``)
    """
    id: int
    value: str

    @classmethod
    def from_dict(cls, raw: dict) -> DescricaoLookupRow:
        return cls(id=raw["Id"], value=raw["Value"])


@dataclass(frozen=True)
class DescricaoLookupResponse:
    """Resposta completa do lookup de descrições de tarefa."""
    count: int
    rows: list[DescricaoLookupRow]

    @classmethod
    def from_dict(cls, raw: dict) -> DescricaoLookupResponse:
        return cls(
            count=raw["Count"],
            rows=[DescricaoLookupRow.from_dict(r) for r in raw.get("Rows", [])],
        )

# filepath: services/task/dto.py
"""
DTOs do domínio de tarefas — estruturas de entrada e saída do TaskService.

Camadas:
  - CreateTaskServiceInput: DTO de entrada do service (sem IDs resolvidos,
    sem dependência de Pydantic). Construído pelo router a partir do schema.
  - TaskPayload: DTO totalmente resolvido, consumido pelo crawler/payload builder.
    Todos os IDs internos do LegalOne já foram preenchidos pelo TaskService.

Sem dependência de Pydantic, FastAPI ou boto3: apenas dataclasses puras.
"""
from dataclasses import dataclass, field
from typing import Optional


# ══════════════════════════════════════════════════════════════════════════════
# 1. DTOs de entrada do service (sem IDs — vindos do router)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ResponsavelInput:
    """Responsável informado pelo caller — sem IDs resolvidos."""
    nome: Optional[str]      # nome do responsável (None se só CPF informado)
    cpf: Optional[str]       # CPF do responsável (None se só nome informado)
    is_solicitante: bool
    is_responsavel: bool
    is_executante: bool


@dataclass
class KanbanInput:
    """Board + coluna do Kanban informados pelo caller — sem IDs resolvidos."""
    board_name: str
    column_name: str


@dataclass
class LembreteServiceInput:
    """Lembrete informado pelo caller — sem IDs resolvidos."""
    nome_envolvido: str
    numero_antecedencia: int = 1
    tipo_antecedencia: str = "2"


@dataclass
class CreateTaskServiceInput:
    """
    DTO de entrada do TaskService — sem IDs resolvidos, sem Pydantic.

    Construído pelo router a partir do schema Pydantic (CreateTaskRequest).
    O service resolve todos os IDs e monta o TaskPayload para o crawler.
    """
    numero_processo: str
    responsaveis: list[ResponsavelInput]
    descricao: str
    dt_inicial: str
    hr_inicio: str
    dt_final: str
    hr_final: str
    deadline_date: Optional[str] = None
    deadline_time: Optional[str] = None
    kanban: Optional[KanbanInput] = None
    lembretes: list[LembreteServiceInput] = field(default_factory=list)
    incluir_recorrencia: bool = False
    observacoes: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# 2. TaskPayload — envelope service → crawler (totalmente resolvido)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class EnvolvidoPayload:
    """Envolvido com IDs resolvidos — pronto para o payload builder."""
    envolvido_id: str
    envolvido_text: str
    is_solicitante: bool
    is_responsavel: bool
    is_executante: bool


@dataclass
class LembretePayload:
    """Lembrete com IDs resolvidos — pronto para o payload builder."""
    envolvido_id: str
    envolvido_text: str
    numero_antecedencia: int = 1
    tipo_antecedencia: str = "2"


@dataclass
class TaskPayload:
    """
    Envelope produzido pelo TaskService após resolver todos os mapeamentos.
    Recebido pelo TasksCrawler, que o converte em tuplas form-data via
    task_payload_builder.build_payload().

    Todos os IDs (processo, envolvidos, kanban) já foram resolvidos.
    Datas no formato dd/MM/yyyy, horas no formato HH:mm:ss.
    """
    # ── Processo (resolvido via crawler) ──────────────────────────────────────
    processo_id: str                              # ex: "3004"
    num_pasta_processo: str                       # ex: "Proc - 0008579"

    # ── Descrição ─────────────────────────────────────────────────────────────
    descricao: str

    # ── Datas obrigatórias ────────────────────────────────────────────────────
    dt_inicial: str
    hr_inicio: str
    dt_final: str
    hr_final: str

    # ── Deadline (opcionais — vazio se não fornecido) ─────────────────────────
    deadline_date: str = ""
    deadline_time: str = ""

    # ── Tipo (fixo) ──────────────────────────────────────────────────────────
    tipo_text: str = "Diversos"
    tipo_id: str = "tipo_4"

    # ── Kanban (resolvido via crawler, vazio se não fornecido) ────────────────
    show_activity_in_kanban: bool = False
    kanban_board_text: str = ""
    kanban_board_id: str = ""
    kanban_column_text: str = ""
    kanban_column_id: str = ""

    # ── Envolvidos (resolvidos via crawler) ───────────────────────────────────
    envolvidos: list[EnvolvidoPayload] = field(default_factory=list)

    # ── Lembretes (opcional — vazio = sem lembretes) ──────────────────────────
    lembretes: list[LembretePayload] = field(default_factory=list)

    # ── Recorrência (opcional — False = sem recorrência) ─────────────────────
    incluir_recorrencia: bool = False

    # ── Observações ──────────────────────────────────────────────────────────
    observacoes: str = ""


# ══════════════════════════════════════════════════════════════════════════════
# 3. Resultado da criação
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class CreateTaskResult:
    """
    Resultado da criação de uma tarefa.

    Atributos:
        success: True quando a tarefa foi criada com sucesso.
        task_id: ID interno da tarefa criada (None se não extraído).
    """
    success: bool
    task_id: str | None = None
    warnings: list = field(default_factory=list)
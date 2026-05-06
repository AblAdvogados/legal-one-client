# filepath: app/schemas/task_schemas.py
"""
Schemas Pydantic para a rota /tasks.

Contrato público da API — o caller envia apenas dados de negócio (nomes, números),
sem IDs internos do LegalOne. A resolução de IDs é feita pelo TaskService.
"""

from pydantic import BaseModel, Field, model_validator


class ResponsavelSchema(BaseModel):
    """
    Responsável pela tarefa.

    Obrigatório informar ao menos ``cpf`` ou ``nome``.
    Se ``cpf`` for fornecido, o lookup será feito por CPF (match exato, sem ambiguidade).
    Caso contrário, será feito por nome — e se houver mais de um usuário com o mesmo
    nome, a API retornará erro solicitando o CPF para desambiguar.

    Os três papéis (``is_solicitante``, ``is_responsavel``, ``is_executante``) são
    independentes e obrigatórios — o caller deve declarar cada um explicitamente.
    Exatamente um responsável do request deve ter ``is_solicitante=True``.
    """
    nome: str | None = Field(
        default=None,
        description="Nome completo ou parcial do responsável. Usado quando CPF não for informado.",
        examples=["Maria Souza"],
    )
    cpf: str | None = Field(
        default=None,
        description="CPF do responsável no formato ###.###.###-##. Preferível ao nome por ser match exato.",
        examples=["485.180.028-26"],
    )
    is_solicitante: bool = Field(
        description="Marca este responsável como solicitante da tarefa. Exatamente um por request.",
        examples=[True],
    )
    is_responsavel: bool = Field(
        description="Marca este responsável como responsável pela execução da tarefa.",
        examples=[True],
    )
    is_executante: bool = Field(
        description="Marca este responsável como executante da tarefa.",
        examples=[False],
    )

    @model_validator(mode="after")
    def ao_menos_cpf_ou_nome(self) -> "ResponsavelSchema":
        if not self.cpf and not self.nome:
            raise ValueError("Informe ao menos 'CPF' ou 'nome' do responsável.")
        return self


class KanbanSchema(BaseModel):
    """
    Board e coluna do Kanban onde a tarefa será exibida.

    Ambos os campos são obrigatórios quando o objeto for fornecido.
    O service resolve os nomes para IDs internos via lookup no LegalOne —
    o caller não precisa conhecer os IDs.
    """
    board_name: str = Field(
        description="Nome do board Kanban conforme cadastrado no LegalOne.",
        examples=["BACKOFFICE"],
    )
    column_name: str = Field(
        description="Nome da coluna dentro do board.",
        examples=["A DESIGNAR"],
    )


class LembreteSchema(BaseModel):
    """
    Lembrete vinculado a um envolvido da tarefa.

    O nome do envolvido é resolvido para ID interno pelo service
    (mesma lógica de ``ResponsavelSchema`` — se ambíguo, informar CPF não é
    suportado aqui; use um nome único).
    """
    nome_envolvido: str = Field(
        description="Nome do envolvido que receberá o lembrete.",
        examples=["João Silva"],
    )
    numero_antecedencia: int = Field(
        default=1,
        description="Quantidade de unidades de antecedência antes do prazo.",
        examples=[1],
    )
    tipo_antecedencia: str = Field(
        default="2",
        description="Unidade de antecedência: '1'=horas, '2'=dias, '3'=semanas.",
        examples=["2"],
    )


class CreateTaskRequest(BaseModel):
    """
    Payload para criação de tarefa no LegalOne vinculada a um processo.

    O caller envia apenas dados de negócio — a resolução de todos os IDs
    internos do LegalOne (processo, usuários, Kanban) é feita pelo service.

    **Campos obrigatórios:** ``numero_processo``, ``responsaveis`` (≥1 item),
    ``descricao``, ``dt_inicial``, ``hr_inicio``, ``dt_final``, ``hr_final``.

    **Regras de validação:**
    - Exatamente um item em ``responsaveis`` deve ter ``is_solicitante=True``.
    - Se ``deadline_date`` for fornecido, ``deadline_time`` também é obrigatório
      (e vice-versa).
    - Em ``responsaveis``, ao menos ``cpf`` ou ``nome`` deve ser informado por item.
    """
    numero_processo: str = Field(
        description="Número do processo no LegalOne (número da pasta).",
        examples=["0008579"],
    )
    responsaveis: list[ResponsavelSchema] = Field(
        min_length=1,
        description="Lista de responsáveis pela tarefa. Mínimo de 1 item. "
                    "Exatamente um deve ter is_solicitante=True.",
    )
    descricao: str = Field(
        description="Título da tarefa conforme cadastrado no LegalOne (modelo de descrição).",
        examples=["Designar audiência"],
    )

    # ── Datas obrigatórias ────────────────────────────────────────────────────
    dt_inicial: str = Field(
        description="Data de início no formato dd/MM/yyyy.",
        examples=["20/05/2026"],
    )
    hr_inicio: str = Field(
        description="Hora de início no formato HH:mm:ss.",
        examples=["09:00:00"],
    )
    dt_final: str = Field(
        description="Data de conclusão prevista no formato dd/MM/yyyy.",
        examples=["20/05/2026"],
    )
    hr_final: str = Field(
        description="Hora de conclusão prevista no formato HH:mm:ss.",
        examples=["18:00:00"],
    )

    # ── Deadline (opcional, mas se date → time obrigatório) ───────────────────
    deadline_date: str | None = Field(
        default=None,
        description="Data do prazo fatal no formato dd/MM/yyyy. "
                    "Se fornecido, deadline_time também é obrigatório.",
        examples=["25/05/2026"],
    )
    deadline_time: str | None = Field(
        default=None,
        description="Hora do prazo fatal no formato HH:mm:ss. "
                    "Obrigatório quando deadline_date for fornecido.",
        examples=["17:00:00"],
    )

    # ── Kanban (opcional) ─────────────────────────────────────────────────────
    kanban: KanbanSchema | None = Field(
        default=None,
        description="Board e coluna Kanban onde a tarefa será exibida. "
                    "Omitir para não vincular ao Kanban.",
    )

    # ── Lembretes (opcional) ──────────────────────────────────────────────────
    lembretes: list[LembreteSchema] = Field(
        default_factory=list,
        description="Lembretes associados a envolvidos da tarefa. Lista vazia = sem lembretes.",
    )

    # ── Recorrência (opcional) ────────────────────────────────────────────────
    incluir_recorrencia: bool = Field(
        default=False,
        description="Se True, inclui o bloco de recorrência padrão no payload enviado ao LegalOne.",
    )

    # ── Observações (opcional) ────────────────────────────────────────────────
    observacoes: str = Field(
        default="",
        description="Texto livre de observações associado à tarefa.",
        examples=["Verificar documentação prévia."],
    )

    @model_validator(mode="after")
    def deadline_completo(self) -> "CreateTaskRequest":
        """Se deadline_date for fornecido, deadline_time é obrigatório (e vice-versa)."""
        if self.deadline_date and not self.deadline_time:
            raise ValueError("'deadline_time' é obrigatório quando 'deadline_date' é fornecido.")
        if self.deadline_time and not self.deadline_date:
            raise ValueError("'deadline_date' é obrigatório quando 'deadline_time' é fornecido.")
        return self

    @model_validator(mode="after")
    def exatamente_um_solicitante(self) -> "CreateTaskRequest":
        """Exatamente um responsável deve ter is_solicitante=True."""
        qtd = sum(1 for r in self.responsaveis if r.is_solicitante)
        if qtd == 0:
            raise ValueError("Exatamente um responsável deve ser solicitante (is_solicitante=True).")
        if qtd > 1:
            raise ValueError(
                f"Apenas um responsável pode ser solicitante, mas {qtd} foram marcados."
            )
        return self


class CreateTaskResponse(BaseModel):
    """Resposta da criação de tarefa."""
    success: bool = Field(description="True se a tarefa foi criada com sucesso no LegalOne.")
    task_id: str | None = Field(
        default=None,
        description="ID interno da tarefa criada no LegalOne. Pode ser None se não identificado.",
        examples=["102"],
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Erros de validação retornados pelo LegalOne quando success=False. "
                    "Cada item descreve um campo rejeitado.",
    )
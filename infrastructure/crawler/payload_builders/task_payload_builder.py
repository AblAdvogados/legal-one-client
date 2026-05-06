"""
Constrói o form-data (list[tuple]) para o endpoint POST /processos/Tarefas/Edit.

Separação de responsabilidades:
- Este módulo só monta bytes/strings — sem HTTP, sem I/O, sem estado.
- Campos fixos: valores que o LegalOne sempre espera iguais, independente da tarefa.
- Campos dinâmicos: derivados do TaskPayload.
- Blocos UUID: Vinculos, Envolvidos e Lembretes usam UUIDs gerados em runtime
  porque o LegalOne usa o padrão de MVC model binding com índices arbitrários.
"""
from __future__ import annotations

import uuid
from services.task.dto import TaskPayload


def _new_uuid() -> str:
    """Gera um UUID4 como string minúscula — padrão aceito pelo LegalOne."""
    return str(uuid.uuid4())


def _bool(value: bool) -> str:
    """Converte bool Python para string capitalizada do .NET (True/False)."""
    return "True" if value else "False"


def _booljs(value: bool) -> str:
    """Converte bool Python para string lowercase do JavaScript (true/false)."""
    return "true" if value else "false"


def _build_vinculos_block(processo_id: str, processo_numero: str) -> list[tuple[str, str]]:
    """
    Monta o bloco Vinculos[] com UUID gerado em runtime.

    Campos dinâmicos:
      - VinculoGridId / RelationshipId → processo_id
      - VinculoGridText / Description  → processo_numero

    Campos fixos (comportamento padrão do formulário LegalOne):
      - DisableVinculo=True   → campo bloqueado para edição (vínculo principal)
      - IsMainRelationship=True → é o vínculo primário da tarefa
      - IsRequiredVinculo=True  → vínculo obrigatório
      - HasVinculoVariosItems=False → apenas um item vinculado
      - CompromissoId=0         → não é compromisso
      - TipoVinculo=1           → tipo padrão de vínculo

    Os campos VinculoId, VinculoGridCompromissoId etc. são enviados em branco
    porque esta tarefa é vinculada apenas ao processo (não a compromisso/tarefa pai).
    """
    uid = _new_uuid()
    prefix = f"Vinculos[{uid}]"
    return [
        ("Vinculos.Index", uid),
        (f"{prefix}._Index", prefix),
        (f"{prefix}.Id", ""),
        (f"{prefix}.VinculoParentId", ""),
        (f"{prefix}.LabelVinculo", "Vinculado a"),
        (f"{prefix}.DisableVinculo", "True"),
        (f"{prefix}.HasVinculoVariosItems", "False"),
        (f"{prefix}.IsRequiredVinculo", "True"),
        (f"{prefix}.ControleRecorrencia", ""),
        (f"{prefix}.CompromissoId", "0"),
        (f"{prefix}.HouveSugestaoAreasVinculos", "False"),
        (f"{prefix}.CantDelete", "False"),
        (f"{prefix}.IsOriginadoProcedimento", "False"),
        (f"{prefix}.TipoVinculoModuloPersonalizado", ""),
        # ── dinâmicos ───────────────────────────────────────────────────────
        (f"{prefix}.Description", processo_numero),
        (f"{prefix}.IsMainRelationship", "True"),
        (f"{prefix}.RelationshipId", processo_id),
        # ── campos de vínculo alternativos (em branco — só usa processo) ────
        (f"{prefix}.VinculoId", ""),
        (f"{prefix}.VinculoContatoId", ""),
        (f"{prefix}.VinculoGridId", processo_id),
        (f"{prefix}.VinculoGridCompromissoId", ""),
        (f"{prefix}.VinculoGridTarefaId", ""),
        (f"{prefix}.VinculoAdvisoryId", ""),
        (f"{prefix}.VinculoGridNegociacaoId", ""),
        (f"{prefix}.TipoVinculo", "1"),
        (f"{prefix}.VinculoText", ""),
        (f"{prefix}.VinculoId", ""),
        (f"{prefix}.VinculoGridNegociacaoText", ""),
        (f"{prefix}.VinculoGridNegociacaoId", ""),
        (f"{prefix}.VinculoContatoText", ""),
        (f"{prefix}.VinculoContatoId", ""),
        (f"{prefix}.VinculoGridText", processo_numero),
        (f"{prefix}.VinculoGridId", processo_id),
        (f"{prefix}.VinculoGridCompromissoText", ""),
        (f"{prefix}.VinculoGridCompromissoId", ""),
        (f"{prefix}.VinculoGridTarefaText", ""),
        (f"{prefix}.VinculoGridTarefaId", ""),
        (f"{prefix}.VinculoAdvisoryText", ""),
        (f"{prefix}.VinculoAdvisoryId", ""),
        (f"{prefix}.ProxyLinkText", ""),
        (f"{prefix}.ProxyLinkId", ""),
        (f"{prefix}.IsUseLinkToDeadlineCount", "false"),
    ]


def _build_envolvido_block(
    envolvido_id: str,
    envolvido_text: str,
    is_solicitante: bool,
    is_responsavel: bool,
    is_executante: bool,
) -> tuple[str, list[tuple[str, str]]]:
    """
    Monta o bloco Envolvidos[] para um único envolvido.

    Retorna (uid, fields) para que o bloco Lembretes[] correspondente
    possa reutilizar o mesmo uid como EnvolvidoId de referência.

    Padrão MVC binding do LegalOne:
      - Booleanos são enviados duas vezes: 'true' + 'false'
        O ASP.NET MVC usa o primeiro valor como real e ignora o segundo
        (hidden input pattern para checkboxes).

    Campos fixos:
      - HasHorasTrabalhadas=False → sem controle de horas
      - DisableEnvolvido=False    → campo editável
      - IsResponsavelArea=False   → não é responsável de área
      - IsSupervisor=False        → não é supervisor
      - IsUpdated=True            → marca que o registro foi tocado pelo form
    """
    uid = _new_uuid()
    prefix = f"Envolvidos[{uid}]"
    fields = [
        ("Envolvidos.Index", uid),
        (f"{prefix}._Index", prefix),
        (f"{prefix}.Id", ""),
        (f"{prefix}.ControleRecorrencia", ""),
        # ── campos fixos de comportamento ───────────────────────────────────
        (f"{prefix}.HasHorasTrabalhadas", "False"),
        (f"{prefix}.DisableEnvolvido", "False"),
        (f"{prefix}.IsResponsavelArea", "False"),
        (f"{prefix}.IsResponsavelAreaHidden", "False"),
        (f"{prefix}.IsSupervisor", "False"),
        (f"{prefix}.IsSupervisorHidden", "False"),
        (f"{prefix}.AddedAsResponsavelArea", "False"),
        (f"{prefix}.AddedAsSupervisor", "False"),
        (f"{prefix}.IsNotificarEnvolvidoEfetivo", "False"),
        (f"{prefix}.IsUpdated", "True"),
        # ── campos dinâmicos ────────────────────────────────────────────────
        (f"{prefix}.EnvolvidoEfetivoId", envolvido_id),
        (f"{prefix}.EnvolvidoText", envolvido_text),
        (f"{prefix}.EnvolvidoId", envolvido_id),
        # ── booleanos duplos (MVC hidden input pattern) ──────────────────────
        (f"{prefix}.IsSolicitante", _booljs(is_solicitante)),
        (f"{prefix}.IsSolicitante", "false"),
        (f"{prefix}.IsResponsavel", _booljs(is_responsavel)),
        (f"{prefix}.IsResponsavel", "false"),
        (f"{prefix}.IsExecutante", _booljs(is_executante)),
        (f"{prefix}.IsExecutante", "false"),
        (f"{prefix}.IsResponsavelArea", "false"),
        (f"{prefix}.IsSupervisor", "false"),
    ]
    return uid, fields


def _build_lembrete_block(
    envolvido_id: str,
    envolvido_text: str,
    numero_antecedencia: int,
    tipo_antecedencia: str,
) -> list[tuple[str, str]]:
    """
    Monta o bloco Lembretes[] com sub-bloco ConfiguracoesDeLembretes[].

    Ambos os níveis usam UUIDs independentes gerados em runtime.

    Campos fixos:
      - TipoCompromissoTarefa=1     → é tarefa (não compromisso)
      - TipoEnvolvimento=3          → tipo padrão de envolvimento
      - TipoNotificacaoLembrete=1   → notificação por e-mail
      - AcaoNotificacaoMomento=0    → sem ação no momento
      - TipoNotificacaoMomento=1    → e-mail no momento
      - TipoNotificacao=1           → e-mail
      - IsTodosEmailsMomento=false  → não envia para todos no momento
      - IsTodosEmails=true+false    → envia para todos (hidden input pattern)
      - IsAllEmailsDaily=false      → sem envio diário
      - NotificationTypeDaily=1     → tipo diário padrão

    Campos dinâmicos:
      - EnvolvidoId / EnvolvidoText         → referência ao envolvido
      - NumeroTempoAntecedencia             → quantos dias/horas antes
      - TipoTempoAntecedencia               → unidade (2=dias)
      - ControleRecorrencia                 → UUID gerado (controle interno)
    """
    lembrete_uid = _new_uuid()
    config_uid = _new_uuid()
    controle_uid = _new_uuid()   # UUID interno de controle de recorrência do lembrete
    lprefix = f"Lembretes[{lembrete_uid}]"
    cprefix = f"{lprefix}.ConfiguracoesDeLembretes[{config_uid}]"

    return [
        ("Lembretes.Index", lembrete_uid),
        (f"{lprefix}._Index", lprefix),
        # ── fixo: tipo = tarefa ──────────────────────────────────────────────
        (f"{lprefix}.TipoCompromissoTarefa", "1"),
        # ── dinâmicos: referência ao envolvido ──────────────────────────────
        (f"{lprefix}.EnvolvidoText", envolvido_text),
        (f"{lprefix}.EnvolvidoId", envolvido_id),
        # ── sub-bloco ConfiguracoesDeLembretes ──────────────────────────────
        (f"{lprefix}.ConfiguracoesDeLembretes.Index", config_uid),
        (f"{cprefix}._Index", cprefix),
        (f"{cprefix}.Id", ""),
        (f"{cprefix}.TipoEnvolvimento", "3"),
        (f"{cprefix}.CollectionName", "ConfiguracoesDeLembretes"),
        (f"{cprefix}.ControleRecorrencia", controle_uid),
        # ── fixos de notificação ─────────────────────────────────────────────
        (f"{cprefix}.TipoNotificacaoLembrete", "1"),
        (f"{cprefix}.AcaoNotificacaoMomento", "0"),
        (f"{cprefix}.IsTodosEmailsMomento", "false"),
        (f"{cprefix}.TipoNotificacaoMomento", "1"),
        # ── dinâmicos: antecedência ──────────────────────────────────────────
        (f"{cprefix}.NumeroTempoAntecedencia", str(numero_antecedencia)),
        (f"{cprefix}.TipoTempoAntecedencia", tipo_antecedencia),
        # ── fixos de notificação (continuação) ───────────────────────────────
        (f"{cprefix}.TipoNotificacao", "1"),
        (f"{cprefix}.IsTodosEmails", "true"),
        (f"{cprefix}.IsTodosEmails", "false"),
        (f"{cprefix}.IsAllEmailsDaily", "false"),
        (f"{cprefix}.NotificationTypeDaily", "1"),
    ]


def _build_recorrencia_block() -> list[tuple[str, str]]:
    """
    Bloco Recorrencia — completamente fixo.
    Representa uma tarefa sem recorrência (IsGerarRecorrencia=false).
    Os campos de frequência (diária, semanal, mensal, anual) são enviados
    com valores padrão porque o formulário sempre os inclui no submit,
    mesmo quando recorrência está desabilitada.
    """
    return [
        ("Recorrencia.Id", ""),
        ("Recorrencia.IsConfirmadoRecMensalMaior29Dias", "False"),
        ("Recorrencia.IsConfirmadoRecAnualMaior29Dias", "False"),
        ("Recorrencia.NomeCampoConfirmacao", ""),
        ("Recorrencia.TipoEdicaoObjeto", ""),
        ("Recorrencia.BotaoSubmit", "0"),
        ("Recorrencia.BloquearRecorrencia", "False"),
        ("Recorrencia.IsGerarRecorrenciaDesabilitado", "False"),
        ("Recorrencia.IsGerarRecorrenciaAoSalvar", "True"),
        ("Recorrencia.IsGerarRecorrencia", "false"),
        ("Recorrencia.TipoFrequencia", "0"),
        ("Recorrencia.IsTodosOsDias", "true"),
        ("Recorrencia.TaxaRepeticaoDiaria", "1"),
        ("Recorrencia.TaxaRepeticaoSemanal", "1"),
        ("Recorrencia.IsDomingo", "false"),
        ("Recorrencia.IsSegunda", "true"),
        ("Recorrencia.IsSegunda", "false"),
        ("Recorrencia.IsTerca", "false"),
        ("Recorrencia.IsQuarta", "false"),
        ("Recorrencia.IsQuinta", "false"),
        ("Recorrencia.IsSexta", "false"),
        ("Recorrencia.IsSabado", "false"),
        ("Recorrencia.IsOrdinalMensal", "false"),
        ("Recorrencia.DiaMensal", "6"),
        ("Recorrencia.TaxaRepeticaoMensal", "1"),
        ("Recorrencia.TipoTaxaRepeticaoOrdinalMensal", "0"),
        ("Recorrencia.DiaSemanaMensal", "1"),
        ("Recorrencia.TaxaRepeticaoOrdinalMensal", "1"),
        ("Recorrencia.TaxaRepeticaoAnual", "1"),
        ("Recorrencia.IsOrdinalAnual", "false"),
        ("Recorrencia.DiaAnual", "6"),
        ("Recorrencia.Mes", "4"),
        ("Recorrencia.TipoTaxaRepeticaoOrdinalAnual", "0"),
        ("Recorrencia.DiaSemanaAnual", "1"),
        ("Recorrencia.MesOrdinal", "1"),
        ("Recorrencia.DataInicio", ""),   # vazio: sem data de início de recorrência
        ("Recorrencia.TipoTermino", "0"),
        ("Recorrencia.NumeroRepeticoes", "1"),
    ]


def build_payload(data: TaskPayload) -> list[tuple[str, str]]:
    """
    Ponto de entrada do builder.

    Monta o form-data completo na ordem exata esperada pelo LegalOne,
    intercalando campos fixos e dinâmicos conforme o payload capturado.

    Ordem das seções:
      1. Campos raiz fixos de controle
      2. Campos raiz fixos do escritório (office)
      3. Campos raiz dinâmicos (descrição, datas, tipo)
      4. Kanban + status + prioridade (fixos)
      5. Datas dinâmicas de prazo
      6. Bloco Vinculos[] (1 item)
      7. Bloco Envolvidos[] (1+ itens)
      8. Bloco Lembretes[] (0+ itens)
      9. Bloco Recorrencia (fixo)
      10. Campos finais de controle
    """
    fields: list[tuple[str, str]] = []

    # ── 1. Controle do formulário (fixos) ────────────────────────────────────
    fields += [
        ("TagIds", "[]"),
        ("Id", ""),                              # vazio = criar novo registro
        ("CompromissoOuTarefa", "1"),            # 1 = tarefa, 0 = compromisso
        ("IsIgnorarConflitoDataPorStatus", "False"),
        ("TipoVinculo", "1"),
        ("VinculoId", data.processo_id),         # ID do processo pai
        ("VinculoParentId", data.processo_id),   # mesmo ID — referência duplicada do form
        ("IdProcedimento", ""),
        ("DisabledDescription", "False"),
        ("ContextTypeDescription", "processo"),
        ("IsSourceOfficeAreaRequired", "False"),
        ("IsLegalDepartmentRequired", "False"),
        ("IsResponsibleOfficeAreaRequired", "False"),
        ("IsJustificationMandatoryWhenFulfilling", "False"),
        ("OriginEnum", ""),
        ("CaActionName", "Processos.Pastas.CompromissosTarefas.CriarTarefa"),
        ("IsPreviewIa", "False"),
        ("RecoverySteps", "False"),
        ("ButtonSaveClick", "0"),
    ]

    # ── 2. Escritório (fixo — sempre o mesmo escritório) ─────────────────────
    fields += [
        ("SourceOfficeText", "AITH, BADARI E LUCHIN SOCIEDADE DE ADVOGADOS"),
        ("SourceOfficeId", "1"),
        ("ResponsibleOfficeText", "AITH, BADARI E LUCHIN SOCIEDADE DE ADVOGADOS"),
        ("ResponsibleOfficeId", "1"),
    ]

    # ── 3. Campos dinâmicos raiz ─────────────────────────────────────────────
    fields += [
        ("Descricao", data.descricao),
    ]

    # ── 4. Kanban + status + prioridade ──────────────────────────────────────
    fields += [
        ("ShowActivityInKanban", _booljs(data.show_activity_in_kanban)),
        ("ShowActivityInKanban", "false"),       # hidden input pattern
        ("KanbanBoardText", data.kanban_board_text),
        ("KanbanBoardId", data.kanban_board_id),
        ("KanbanBoardColumnText", data.kanban_column_text),
        ("KanbanBoardColumn", data.kanban_column_id),
        ("KanbanColumnPosition", "1"),
        ("PriorityId", "1"),
        ("StatusText", "Pendente"),
        ("StatusId", "0"),
        ("PrioridadeId", "1"),
    ]

    # ── 5. Tipo + datas dinâmicas ─────────────────────────────────────────────
    fields += [
        ("TipoText", data.tipo_text),
        ("TipoId", data.tipo_id),
        ("DeadlineCount", ""),
        ("DeadlineCountText", ""),
        ("DeadlineCountId", ""),
        ("AvailableDate", ""),
        ("DtPublicacao", ""),
        ("DtInicial", data.dt_inicial),
        ("HrInicio", data.hr_inicio),
        ("DtFinal", data.dt_final),
        ("HrFinal", data.hr_final),
        ("DeadLineDate", data.deadline_date),
        ("DeadLineTime", data.deadline_time),
        ("Local", ""),
        ("AreaText", ""),
        ("AreaId", ""),
        ("IsUseLinkToDeadlineCount", "False"),
    ]

    # ── 6. Bloco Vinculos[] — 1 item (o processo pai) ─────────────────────────
    fields += _build_vinculos_block(data.processo_id, data.num_pasta_processo)
    fields += [("CreateForEachLink", "false")]

    # ── 7. Bloco Envolvidos[] — 1 item por envolvido ─────────────────────────
    for envolvido in data.envolvidos:
        _, envolvido_fields = _build_envolvido_block(
            envolvido_id=envolvido.envolvido_id,
            envolvido_text=envolvido.envolvido_text,
            is_solicitante=envolvido.is_solicitante,
            is_responsavel=envolvido.is_responsavel,
            is_executante=envolvido.is_executante,
        )
        fields += envolvido_fields

    # ── 8. Bloco Lembretes[] — condicional (0+ itens) ───────────────────────
    if data.lembretes:
        for lembrete in data.lembretes:
            fields += _build_lembrete_block(
                envolvido_id=lembrete.envolvido_id,
                envolvido_text=lembrete.envolvido_text,
                numero_antecedencia=lembrete.numero_antecedencia,
                tipo_antecedencia=lembrete.tipo_antecedencia,
            )

    # ── 9. Bloco Recorrencia — condicional ────────────────────────────────────
    if data.incluir_recorrencia:
        fields += _build_recorrencia_block()

    # ── 10. Campos finais de controle (fixos) ────────────────────────────────
    fields += [
        ("Observacoes", data.observacoes),
        ("Maintain", "true"),
        ("Maintain", "false"),   # hidden input pattern
        ("ButtonSave", "0"),
    ]

    return fields
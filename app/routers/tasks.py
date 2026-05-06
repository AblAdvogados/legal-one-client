# filepath: app/routers/tasks.py
"""
Router FastAPI para a rota /tasks.

Responsabilidades:
  - Receber e validar o body JSON via CreateTaskRequest (schema Pydantic).
  - Converter o schema para os tipos de domínio (CreateTaskServiceInput).
  - Delegar toda a resolução de IDs ao TaskService.
  - Retornar CreateTaskResponse.

NÃO contém lógica de negócio nem acessa infraestrutura diretamente.
"""
from fastapi import APIRouter, Depends
import logging

from app.schemas.task_schemas import CreateTaskRequest, CreateTaskResponse
from core.errors import TarefaRejeitadaError
from services.task.dto import (
    CreateTaskServiceInput,
    KanbanInput,
    LembreteServiceInput,
    ResponsavelInput,
)
from services.task.task_service import TaskService

router = APIRouter()

logger = logging.getLogger(__name__)


# ── Dependency ────────────────────────────────────────────────────────────────

def get_task_service() -> TaskService:
    """
    Fornece uma instância de TaskService com sessão HTTP autenticada.
    Substituída por mock nos testes.
    """
    from app.dependencies import task_service
    return task_service


# ── Conversor schema → domain types ──────────────────────────────────────────

def _to_service_input(req: CreateTaskRequest) -> CreateTaskServiceInput:
    """Converte CreateTaskRequest (schema Pydantic) → CreateTaskServiceInput (domain)."""
    return CreateTaskServiceInput(
        numero_processo=req.numero_processo,
        responsaveis=[
            ResponsavelInput(
                nome=r.nome,
                cpf=r.cpf,
                is_solicitante=r.is_solicitante,
                is_responsavel=r.is_responsavel,
                is_executante=r.is_executante,
            )
            for r in req.responsaveis
        ],
        descricao=req.descricao,
        dt_inicial=req.dt_inicial,
        hr_inicio=req.hr_inicio,
        dt_final=req.dt_final,
        hr_final=req.hr_final,
        deadline_date=req.deadline_date,
        deadline_time=req.deadline_time,
        kanban=KanbanInput(
            board_name=req.kanban.board_name,
            column_name=req.kanban.column_name,
        ) if req.kanban else None,
        lembretes=[
            LembreteServiceInput(
                nome_envolvido=l.nome_envolvido,
                numero_antecedencia=l.numero_antecedencia,
                tipo_antecedencia=l.tipo_antecedencia,
            )
            for l in req.lembretes
        ],
        incluir_recorrencia=req.incluir_recorrencia,
        observacoes=req.observacoes,
    )


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "",
    response_model=CreateTaskResponse,
    summary="Criar tarefa vinculada a um processo",
    responses={
        200: {
            "description": (
                "Tarefa criada com sucesso (`success=true`) **ou** rejeitada pelo LegalOne "
                "(`success=false`, campo `errors` preenchido). Ambos os casos retornam HTTP 200."
            ),
        },
        422: {"description": "Payload inválido — falha na validação Pydantic (ex: campo obrigatório ausente)."},
        502: {"description": "Erro HTTP ao acessar o LegalOne (resposta 4xx/5xx inesperada)."},
        503: {"description": "Sessão expirada ou falha de autenticação com o LegalOne."},
    },
)
async def create_task(
    body: CreateTaskRequest,
    service: TaskService = Depends(get_task_service),
) -> CreateTaskResponse:
    """
    Cria uma nova tarefa no LegalOne vinculada a um processo.

    O caller envia **apenas dados de negócio** (número do processo, nomes, datas).
    Toda a resolução de IDs internos do LegalOne é feita internamente pelo service:

    1. `numero_processo` → ID interno do processo + número da pasta.
    2. `responsaveis[].cpf` ou `responsaveis[].nome` → ID do usuário.
    3. `kanban.board_name` + `kanban.column_name` → IDs do board e da coluna.

    **Nota sobre `success=false` com HTTP 200:** quando o LegalOne rejeita campos
    opcionais (ex: hora inválida), a tarefa pode ser criada parcialmente.
    Quando rejeita campos obrigatórios, `success=false` e `errors` é preenchido.

    **Implementação:** `app/routers/tasks.py` → `TaskService.create_task` →
    `TasksCrawler.post_create_task` → `interpret_create_task_response`.
    """
    input_data = _to_service_input(body)
    logger.info("POST /tasks: início numero_processo=%s", body.numero_processo)
    try:
        result = service.create_task(input_data)
    except TarefaRejeitadaError as exc:
        logger.warning(
            "POST /tasks: tarefa rejeitada numero_processo=%s erros=%s",
            body.numero_processo, exc.errors,
        )
        return CreateTaskResponse(success=False, errors=exc.errors)
    logger.info(
        "POST /tasks: concluído numero_processo=%s task_id=%s warnings=%d",
        body.numero_processo, result.task_id, len(result.warnings),
    )
    return CreateTaskResponse(success=result.success, task_id=result.task_id)
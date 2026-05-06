# filepath: app/error_handler.py
"""
Mapeamento de exceções do domínio para respostas HTTP padronizadas.

Formato único de resposta de erro:
    {"detail": "<mensagem>"}        — erros de string
    {"detail": ["msg1", "msg2"]}    — erros múltiplos (ContatoRejeitadoError)

Ordem de registro: subclasses antes das classes base.

O que NÃO passa por aqui:
  - ContactBuildError (EnderecoIncompletoError, MappingError e subclasses):
    capturadas dentro de build_dto() e convertidas em optional_field_errors
    no body 200. Registradas como fallback de segurança apenas.
  - SessionExpiredError: nunca escapa do BaseCrawler — resolvida por retry.
  - ValueError do Pydantic: tratada automaticamente pelo FastAPI antes do
    service ser chamado (gera 422 com formato de array do Pydantic).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from core.errors import (
    AmbiguousUserError,
    AuthenticationError,
    ContactBuildError,
    ContatoNaoEncontradoError,
    ContatoRejeitadoError,
    CrawlerError,
    DescriptionNotFoundError,
    KanbanBoardColumnNotFoundError,
    KanbanBoardNotFoundError,
    LegalOneError,
    ParseError,
    ProcessoNaoEncontradoError,
    SessionRefreshTimeoutError,
    UsuarioNaoEncontradoError,
)


def register_error_handlers(app: FastAPI) -> None:
    """
    Registra todos os handlers de exceção na instância FastAPI.
    Deve ser chamado em main.py antes de incluir os routers.
    """
    logger = logging.getLogger(__name__)

    # ── 404 — contato não encontrado ──────────────────────────────────────────

    @app.exception_handler(ContatoNaoEncontradoError)
    async def handle_contato_nao_encontrado(request: Request, exc: ContatoNaoEncontradoError):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    # ── 404 — processo não encontrado ─────────────────────────────────────────

    @app.exception_handler(ProcessoNaoEncontradoError)
    async def handle_processo_nao_encontrado(request: Request, exc: ProcessoNaoEncontradoError):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    # ── 404 — usuário não encontrado ──────────────────────────────────────────

    @app.exception_handler(UsuarioNaoEncontradoError)
    async def handle_usuario_nao_encontrado(request: Request, exc: UsuarioNaoEncontradoError):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    # ── 409 — nome ambíguo (mais de um usuário encontrado) ────────────────────

    @app.exception_handler(AmbiguousUserError)
    async def handle_ambiguous_user(request: Request, exc: AmbiguousUserError):
        return JSONResponse(
            status_code=409,
            content={"detail": str(exc)},
        )

    # ── 404 — board Kanban não encontrado ─────────────────────────────────────

    @app.exception_handler(KanbanBoardNotFoundError)
    async def handle_kanban_board_not_found(request: Request, exc: KanbanBoardNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    # ── 404 — coluna do board Kanban não encontrada ───────────────────────────

    @app.exception_handler(KanbanBoardColumnNotFoundError)
    async def handle_kanban_column_not_found(request: Request, exc: KanbanBoardColumnNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    # ── 404 — descrição não encontrada ────────────────────────────────────────

    @app.exception_handler(DescriptionNotFoundError)
    async def handle_description_not_found(request: Request, exc: DescriptionNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
        )

    # ── 422 — dados rejeitados pelo servidor LegalOne ─────────────────────────

    @app.exception_handler(ContatoRejeitadoError)
    async def handle_contato_rejeitado(request: Request, exc: ContatoRejeitadoError):
        # exc.errors é uma lista de mensagens — uma por campo rejeitado.
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors},
        )

    # ── 422 — erros de build que escaparam do build_dto() (fallback) ──────────
    # Na prática build_dto() os captura e converte em optional_field_errors.
    # Este handler existe como rede de segurança para novos caminhos de código.

    @app.exception_handler(ContactBuildError)
    async def handle_contact_build_error(request: Request, exc: ContactBuildError):
        return JSONResponse(
            status_code=422,
            content={"detail": str(exc)},
        )

    # ── 503 — falhas de sessão / autenticação ─────────────────────────────────

    @app.exception_handler(AuthenticationError)
    async def handle_authentication_error(request: Request, exc: AuthenticationError):
        logger.exception("AuthenticationError em %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=503,
            content={"detail": "Falha de autenticação com o LegalOne."},
        )

    @app.exception_handler(SessionRefreshTimeoutError)
    async def handle_session_refresh_timeout(request: Request, exc: SessionRefreshTimeoutError):
        logger.exception("SessionRefreshTimeoutError em %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=503,
            content={"detail": "Serviço temporariamente indisponível — tente novamente em instantes."},
        )

    # ── 502 — erros de comunicação com o LegalOne ────────────────────────────

    @app.exception_handler(CrawlerError)
    async def handle_crawler_error(request: Request, exc: CrawlerError):
        logger.exception("CrawlerError em %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=502,
            content={"detail": "Erro HTTP ao acessar o LegalOne."},
        )

    @app.exception_handler(ParseError)
    async def handle_parse_error(request: Request, exc: ParseError):
        logger.exception("ParseError em %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=502,
            content={"detail": "Resposta do LegalOne em formato inesperado."},
        )

    # ── 500 — fallback para qualquer LegalOneError não coberta acima ──────────

    @app.exception_handler(LegalOneError)
    async def handle_legalone_error(request: Request, exc: LegalOneError):
        logger.exception("LegalOneError não tratada em %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno inesperado."},
        )

    # ── 500 — fallback genérico para exceções NÃO-LegalOneError ──────────────
    # Garante que qualquer exceção inesperada (ex.: FileNotFoundError, KeyError,
    # TypeError) seja logada com traceback completo antes de virar 500.
    # Sem este handler, o Mangum/API Gateway retorna "Service Unavailable"
    # sem nenhum registro no CloudWatch.

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception):
        logger.critical(
            "Exceção não tratada em %s %s — %s: %s",
            request.method, request.url.path,
            type(exc).__name__, exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Erro interno inesperado."},
        )


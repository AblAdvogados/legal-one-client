# filepath: infrastructure/crawler/tasks.py
"""
TasksCrawler — executa requisições HTTP para o módulo de tarefas do LegalOne.

Herda de BaseCrawler para reutilizar sessão autenticada e headers padrão.
Inclui métodos de lookup para resolução de IDs usados pelo TaskService.

Headers HTTP:
  Todos os lookups usam ``self.headers_ajax`` (perfil AJAX / XHR do BaseCrawler),
  pois são chamadas assíncronas do formulário de criação de tarefa.
  Cookies e autenticação são gerenciados pelo SessionManager via BaseCrawler.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

from infrastructure.crawler.base_crawler import BaseCrawler
from core.errors import SessionExpiredError, TransientServerError
from infrastructure.crawler.lookup_responses import (
    DescricaoLookupResponse,
    KanbanBoardLookupResponse,
    KanbanColumnLookupResponse,
    LawsuitLookupResponse,
    UserLookupResponse,
)
from infrastructure.crawler.payload_builders.task_payload_builder import build_payload
from services.task.dto import TaskPayload

_TASKS_URL = "/processos/Tarefas/Edit"
_TASKS_LISTING_URL = "/processos/processos/DetailsCompromissosTarefas/{processo_id}"



# ── URLs dos endpoints de lookup (relativos ao base_url) ─────────────────────
_LOOKUP_LAWSUIT_URL = "/agenda/Compromissos/LookupLawSuit"
_LOOKUP_USER_URL = "/config/Usuarios/LookupGridUsuario"
_LOOKUP_KANBAN_BOARD_URL = "/agenda/CompromissoTarefa/LookupKanbanBoard"
_LOOKUP_KANBAN_COLUMN_URL = "/agenda/CompromissoTarefa/LookupKanbanColumn"
_LOOKUP_DESCRICAO_URL = "/config/ModeloDescricaoCompromissoTarefa/LookupModeloDescricaoTarefa"


class TasksCrawler(BaseCrawler):
    """Crawler para criação e manipulação de tarefas no LegalOne."""

    # ── Criação de tarefa ─────────────────────────────────────────────────────

    def post_create_task(self, data: TaskPayload) -> str:
        """
        Executa **um único POST** no endpoint de criação de tarefa.

        Responsabilidade exclusivamente HTTP:
          - Monta o payload e os parâmetros.
          - Envia o POST.
          - Trata ``SessionExpiredError`` com reautenticação (infraestrutura).
          - Propaga qualquer outro erro diretamente ao caller (service).

        Toda decisão sobre retry, verificação de listagem e política de
        tentativas é responsabilidade do ``TaskService``, não do crawler.

        Args:
            data: DTO com todos os campos já resolvidos.

        Returns:
            HTML da resposta (redirect de sucesso, listagem ou formulário com
            erros). O parser decide qual caso é.

        Raises:
            TransientServerError: erro transitório de infraestrutura (404+Erro, 502).
            CrawlerError: erro HTTP definitivo (4xx/5xx não transitório).
            AuthenticationError: sessão expirada mesmo após reautenticação.
        """
        payload = build_payload(data)
        params = {
            "returnUrl": f"/processos/processos/DetailsCompromissosTarefas/{data.processo_id}"
                         "?ajaxnavigation=true&renderOnlySection=True"
        }
        url = self.base_url + _TASKS_URL
        
        logger.info("post_create_task: POST processo_id=%s url=%s", data.processo_id, url)
        
        t0 = time.monotonic()
        response = self._post_task(url, data=payload, params=params)
        elapsed = time.monotonic() - t0
        
        logger.info(
            "post_create_task: concluído processo_id=%s status=%d elapsed=%.2fs html[:100]=%s",
            data.processo_id, response.status_code, elapsed, response.text[:100],
        )

        return response.text

    def fetch_task_listing(self, processo_id: str) -> str:
        """
        Faz GET na listagem de tarefas do processo com renderOnlySection=True.

        GET é idempotente — usa _request normal (com retry de sessão e transitório).

        Args:
            processo_id: ID interno do processo (ex: "19324").

        Returns:
            HTML da seção de compromissos/tarefas do processo.
        """
        url = self.base_url + _TASKS_LISTING_URL.format(processo_id=processo_id)
        params = {
            "ajaxnavigation": "true",
            "renderOnlySection": "True",
            "SortBy": "Id",
            "_SortDirection": "DESC",
        }

        logger.info("fetch_task_listing: GET processo_id=%s", processo_id)
        response = self._request("GET", url, params=params, headers=self.headers_ajax)
        logger.info(
            "fetch_task_listing: processo_id=%s status=%d html_len=%d",
            processo_id, response.status_code, len(response.text),
        )
        return response.text

    def _post_task(self, url: str, **kwargs):
        """
        Executa um POST HTTP para o endpoint de criação de tarefa.

        Tratamento de sessão (infraestrutura):
          - ``SessionExpiredError`` → reautenticação automática via ``_retry_after_reauth``.

        Tudo o mais (``TransientServerError``, ``CrawlerError``, etc.) é propagado
        diretamente ao ``TaskService``, que decide a política de retry.
        """
        kwargs.setdefault("headers", self.headers)
        response = self._session.request("POST", url, **kwargs)
        try:
            self._validate_response(response)
            return response
        except SessionExpiredError:
            return self._retry_after_reauth("POST", url, **kwargs)
        # TransientServerError, CrawlerError e qualquer outra exceção: propagar.

    # ══════════════════════════════════════════════════════════════════════════
    # Lookups — chamadas HTTP primitivas, sem lógica de negócio
    # ══════════════════════════════════════════════════════════════════════════
    #
    # Estes métodos fazem apenas a requisição HTTP e deserializam o JSON.
    # Toda a lógica de resolução (ex: "não encontrado", "ambíguo") é
    # responsabilidade do TaskService.

    def _ts(self) -> str:
        """Gera timestamp em milissegundos para o parâmetro ``_`` (cache-buster)."""
        return str(int(datetime.now().timestamp() * 1000))

    # ── Lookup de processo ────────────────────────────────────────────────────

    def lookup_lawsuit(self, termo_busca: str) -> LawsuitLookupResponse:
        """
        Busca processos por número do processo ou nome do envolvido.

        Endpoint: ``GET /agenda/Compromissos/LookupLawSuit``

        A busca é por continência: o termo é comparado contra número CNJ,
        número antigo, número da pasta e nome do cliente principal.

        Args:
            termo_busca: número do processo ou nome do cliente.

        Returns:
            :class:`LawsuitLookupResponse` com ``count`` e lista de
            :class:`LawsuitLookupRow`.
        """
        params = {
            "term": termo_busca,
            "tipoVinculo": "1",
            "pageSize": "100",
            "_": self._ts(),
        }
        url = f"{self.base_url}{_LOOKUP_LAWSUIT_URL}"
        response = self._request("GET", url, params=params, headers=self.headers_ajax)
        
        logger.info("lookup_lawsuit: termo=%s status=%d response[:20]=%s", termo_busca, response.status_code, response.text[:20])
        
        return LawsuitLookupResponse.from_dict(response.json())

    # ── Lookup de usuário ─────────────────────────────────────────────────────

    def lookup_user(self, cpf_or_name: str) -> UserLookupResponse:
        """
        Busca usuários ativos por CPF ou nome.

        Endpoint: ``GET /config/Usuarios/LookupGridUsuario``

        A busca é por continência no nome ou CPF. Se o termo for um CPF
        formatado (``###.###.###-##``), o match tende a ser exato (1 resultado).
        Se for um nome parcial, pode retornar múltiplos resultados.

        Args:
            cpf_or_name: CPF formatado ou nome (parcial ou completo) do usuário.

        Returns:
            :class:`UserLookupResponse` com ``count`` e lista de
            :class:`UserLookupRow` (contato_id, contato_nome, cpf).
        """
        params = {
            "ativosOnly": "True",
            "term": cpf_or_name,
            "pageSize": "100",
            "_": self._ts(),
        }
        url = f"{self.base_url}{_LOOKUP_USER_URL}"
        response = self._request("GET", url, params=params, headers=self.headers_ajax)
        
        logger.info("lookup_user: termo=%s status=%d response[:20]=%s", cpf_or_name, response.status_code, response.text[:20])

        return UserLookupResponse.from_dict(response.json())

    # ── Lookup de Kanban Board ────────────────────────────────────────────────

    def lookup_kanban_boards(self, term: str | None = None) -> KanbanBoardLookupResponse:
        """
        Lista boards Kanban, opcionalmente filtrados por nome.

        Endpoint: ``GET /agenda/CompromissoTarefa/LookupKanbanBoard``

        Args:
            term: filtro por nome do board (opcional; sem filtro retorna todos).

        Returns:
            :class:`KanbanBoardLookupResponse` com ``count`` e lista de
            :class:`KanbanBoardRow` (id, value).
        """
        params = {
            "term": term or "",
            "pageSize": "500",
            "_": self._ts(),
        }
        url = f"{self.base_url}{_LOOKUP_KANBAN_BOARD_URL}"
        response = self._request("GET", url, params=params, headers=self.headers_ajax)
        
        logger.info("lookup_kanban_boards: term=%s status=%d response[:20]=%s", term, response.status_code, response.text[:20])

        return KanbanBoardLookupResponse.from_dict(response.json())

    # ── Lookup de Kanban Column ───────────────────────────────────────────────

    def lookup_kanban_columns(
        self,
        board_id: str,
        term: str | None = None,
    ) -> KanbanColumnLookupResponse:
        """
        Lista colunas de um board Kanban, opcionalmente filtradas por nome.

        Endpoint: ``GET /agenda/CompromissoTarefa/LookupKanbanColumn``

        Args:
            board_id: ID do board Kanban (ex: ``"2"``).
            term: filtro por nome da coluna (opcional).

        Returns:
            :class:`KanbanColumnLookupResponse` com ``count`` e lista de
            :class:`KanbanColumnRow` (id, value).
        """
        params = {
            "term": term or "",
            "pageSize": "500",
            "_": self._ts(),
            "boardId": board_id,
        }
        url = f"{self.base_url}{_LOOKUP_KANBAN_COLUMN_URL}"
        response = self._request("GET", url, params=params, headers=self.headers_ajax)

        logger.info("lookup_kanban_columns: board_id=%s term=%s status=%d response[:20]=%s", board_id, term, response.status_code, response.text[:20])

        return KanbanColumnLookupResponse.from_dict(response.json())

    # ── Lookup de descrição de tarefa ─────────────────────────────────────────

    def lookup_descricao(self, descricao: str) -> DescricaoLookupResponse:
        """
        Busca descrições (modelos) de tarefa por termo.

        Endpoint: ``GET /config/ModeloDescricaoCompromissoTarefa/LookupModeloDescricaoTarefa``

        A busca é por continência no nome da descrição.

        Args:
            descricao: termo de busca (ex: ``"designar"``).

        Returns:
            :class:`DescricaoLookupResponse` com ``count`` e lista de
            :class:`DescricaoLookupRow` (id, value).
        """
        params = {
            "term": descricao,
            "pageSize": "500",
            "_": self._ts(),
        }
        url = f"{self.base_url}{_LOOKUP_DESCRICAO_URL}"
        response = self._request("GET", url, params=params, headers=self.headers_ajax)

        logger.info("lookup_descricao: term=%s status=%d response[:20]=%s", descricao, response.status_code, response.text[:20])

        return DescricaoLookupResponse.from_dict(response.json())

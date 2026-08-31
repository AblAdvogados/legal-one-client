# filepath: services/task/task_service.py
"""
TaskService — orquestra a criação de tarefas no LegalOne.

Responsabilidades:
  1. Resolver IDs dinâmicos chamando os lookups primitivos do crawler:
     - numero_processo → (processo_id, num_pasta_processo)
     - nome/cpf do responsável → (envolvido_id, envolvido_text)
     - kanban board/column names → IDs
     - nome do envolvido nos lembretes → IDs
  2. Montar o TaskPayload (DTO totalmente resolvido).
  3. Delegar ao TasksCrawler.create_task() (payload builder + POST HTTP).
  4. Retornar CreateTaskResult.

NÃO pertence ao service:
  - Montagem de tuplas form-data → task_payload_builder
  - Validação de formato de entrada → schemas Pydantic
  - Conversão schema → DTO de entrada → router
  - Chamadas HTTP primitivas → TasksCrawler
"""
from __future__ import annotations

import logging
import re
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.search_service import SearchService

logger = logging.getLogger(__name__)

from core.errors import (
    AmbiguousUserError,
    CrawlerError,
    KanbanBoardColumnNotFoundError,
    KanbanBoardNotFoundError,
    ProcessoNaoEncontradoError,
    TarefaRejeitadaError,
    TransientServerError,
    UsuarioNaoEncontradoError,
)
from infrastructure.crawler.tasks import TasksCrawler
from infrastructure.lookup.tipo_tarefa_mapper import map_tipo_tarefa
from parsers.task_parser import interpret_create_task_response
from services.task.dto import (
    CreateTaskResult,
    CreateTaskServiceInput,
    EnvolvidoPayload,
    LembretePayload,
    ResponsavelInput,
    TaskPayload,
)


class TaskService:

    # Número máximo de POSTs de retry após verificação na listagem.
    # 1 = tenta criar uma segunda vez se a listagem confirmar que não foi criada.
    _MAX_POST_RETRIES = 1
    _TIME_BETWEEN_HTTP_REQUESTS = 0.3  # Tempo fixo entre requisições para evitar sobrecarregar o servidor

    def __init__(self, crawler: TasksCrawler, search_service: "SearchService | None" = None) -> None:
        self._crawler = crawler
        # Busca global usada como fallback do lookup de processo (ver
        # _resolve_vinculo_via_busca_global). Opcional para não quebrar
        # instanciações existentes; sem ela o fallback fica desativado.
        self._search_service = search_service

    def _delay_between_requests(self):
        """Retorna o tempo de delay recomendado entre requisições para evitar sobrecarregar o servidor."""
        time.sleep(self._TIME_BETWEEN_HTTP_REQUESTS)

    # ── Ponto de entrada principal ────────────────────────────────────────────

    def create_task(self, req: CreateTaskServiceInput) -> CreateTaskResult:
        """
        Cria uma tarefa no LegalOne vinculada a um processo.

        Fluxo:
          1. Resolve processo_id + num_pasta via lookup de processo.
          2. Resolve cada responsável (CPF ou nome) → envolvido_id/text.
          3. Resolve Kanban board + coluna, se fornecido.
          4. Resolve envolvidos dos lembretes, se fornecidos.
          5. Monta TaskPayload completamente resolvido.
          6. Delega ao crawler para POST no LegalOne.

        Args:
            req: DTO de entrada do service (sem IDs resolvidos).

        Returns:
            CreateTaskResult com ``success=True`` e ``warnings`` com erros
            em campos opcionais retornados pelo servidor (se houver).

        Raises:
            TarefaRejeitadaError: servidor rejeitou campos obrigatórios.
            ProcessoNaoEncontradoError: processo não encontrado.
            UsuarioNaoEncontradoError: usuário não encontrado.
            AmbiguousUserError: nome ambíguo — informar CPF.
            KanbanBoardNotFoundError: board Kanban não encontrado.
            KanbanBoardColumnNotFoundError: coluna Kanban não encontrada.
            CrawlerError: erro HTTP do LegalOne.
            AuthenticationError: sessão expirada.
        """
        # 1. Resolver processo: numero → (processo_id, num_pasta_processo)
        logger.info("create_task: início numero_processo=%s", req.numero_processo)
        
        t0 = time.monotonic()
        
        vinculo_id, num_pasta = self._resolve_vinculo(req.numero_processo)
        time.sleep(self._TIME_BETWEEN_HTTP_REQUESTS)  # espera fixa para evitar sobrecarregar o servidor com lookups seguidos

        # 2. Resolver responsáveis → EnvolvidoPayload com IDs
        envolvidos = [
            self._resolve_responsavel(resp)
            for resp in req.responsaveis
        ]

        # 3. Resolver Kanban (se fornecido)
        show_kanban = False
        kb_text = kb_id = kc_text = kc_id = ""
        if req.kanban:
            kb_text, kb_id = self._lookup_kanban_board(req.kanban.board_name)
            self._delay_between_requests()  # espera fixa para evitar sobrecarregar o servidor com lookups seguidos
            
            kc_text, kc_id = self._lookup_kanban_column(req.kanban.column_name, kb_id)
            self._delay_between_requests()  # espera fixa para evitar sobrecarregar o servidor com lookups seguidos
            show_kanban = True

        # 4. Resolver lembretes (se fornecidos)
        lembretes = []
        # lembretes = [LembretePayload(
        #     envolvido_id=env_id,
        #     envolvido_text=env_text,
        #     numero_antecedencia=lem.numero_antecedencia,
        #     tipo_antecedencia=lem.tipo_antecedencia)
        #     for lem in req.lembretes for env_id, env_text in [self._lookup_usuario_por_nome(lem.nome_envolvido)]
        # ]

        # 5. Montar TaskPayload totalmente resolvido
        tipo_text, tipo_id = map_tipo_tarefa(req.tipo, req.subtipo)

        payload = TaskPayload(
            processo_id=vinculo_id,
            num_pasta_processo=num_pasta,
            descricao=req.descricao,
            dt_inicial=req.dt_inicial,
            hr_inicio=req.hr_inicio,
            dt_final=req.dt_final,
            hr_final=req.hr_final,
            deadline_date=req.deadline_date or "",
            deadline_time=req.deadline_time or "",
            tipo_text=tipo_text,
            tipo_id=tipo_id,
            show_activity_in_kanban=show_kanban,
            kanban_board_text=kb_text,
            kanban_board_id=kb_id,
            kanban_column_text=kc_text,
            kanban_column_id=kc_id,
            envolvidos=envolvidos,
            lembretes=lembretes,
            incluir_recorrencia=req.incluir_recorrencia,
            observacoes=req.observacoes,
        )

        # 6. Delegar ao crawler (POST) e interpretar resposta
        result = self._create_task_with_verification(payload)

        elapsed = time.monotonic() - t0
    
        logger.info(
            "create_task: parser resultado source=%s success=%s task_id=%s errors=%s tempo=%.2fs",
            result.source,
            result.success,
            result.task_id,
            [e.message for e in result.errors],
            elapsed,
        )

        if result.errors:
            raise TarefaRejeitadaError(errors=[e.message for e in result.errors])

        return CreateTaskResult(
            success=result.success,
            task_id=result.task_id,
        )

    # ── Criação com verificação e retry ─────────────────────────────────────

    def _create_task_with_verification(self, payload: TaskPayload):
        """
        Executa POST de criação da tarefa com verificação na listagem e retry controlado.

        Fluxo:
          1. POST via ``crawler.post_create_task`` → interpreta resposta.
          2. Se o POST lançar ``TransientServerError`` ou ``CrawlerError``:
             - Consulta a listagem para verificar se a tarefa foi criada mesmo assim.
             - Se encontrada: retorna resultado (evita duplicação).
          3. Caso contrário, faz retry (até ``_MAX_POST_RETRIES`` vezes) com
             espera incremental de 1.5 s.
          4. Se os retries se esgotarem, re-lança a última exceção.
        """
        last_exc: Exception | None = None

        for attempt in range(1 + self._MAX_POST_RETRIES):
            if attempt > 0:
                time.sleep(1.5 * attempt)

            try:
                html = self._crawler.post_create_task(payload)
                parsed = interpret_create_task_response(
                    html,
                    descricao=payload.descricao,
                    dt_inicial=payload.dt_inicial,
                    hr_inicio=payload.hr_inicio,
                    dt_final=payload.dt_final,
                )
                return parsed

            except (TransientServerError, CrawlerError) as exc:
                logger.warning(
                    "_create_task_with_verification: erro no POST attempt=%d exc=%s — verificando listagem",
                    attempt, exc,
                )
                last_exc = exc

                # Consulta a listagem para checar se a tarefa foi criada
                try:
                    listing_html = self._crawler.fetch_task_listing(payload.processo_id)
                    parsed = interpret_create_task_response(
                        listing_html,
                        descricao=payload.descricao,
                        dt_inicial=payload.dt_inicial,
                        hr_inicio=payload.hr_inicio,
                        dt_final=payload.dt_final,
                    )
                    if parsed.success:
                        logger.info(
                            "_create_task_with_verification: tarefa encontrada na listagem após erro — evitando duplicação"
                        )
                        return parsed
                except Exception as listing_exc:
                    logger.warning(
                        "_create_task_with_verification: falha ao consultar listagem exc=%s", listing_exc
                    )

        raise last_exc  # type: ignore[misc]

    # ── Resolução de vínculo ─────────────────────────────────────────────────

    def _resolve_vinculo(self, numero_processo: str) -> tuple[str, str]:
        """
        Dado o número do processo, retorna ``(vinculo_id, num_pasta_processo)``.

        Chama ``crawler.lookup_lawsuit`` e interpreta o resultado.
        O campo ``Id`` do JSON (ID interno do processo) é usado como
        RelationshipId/VinculoGridId no payload; o campo ``Pasta`` é
        usado como Description/VinculoGridText.

        Desde 28/08/2026 o LookupLawSuit do LegalOne deixou de casar o termo
        contra o campo "Número antigo" (onde fica o protocolo do INSS) — passou
        a encontrar apenas pelo número da pasta. Quando o lookup direto não
        encontra, este método usa a busca global (que ainda casa por número
        antigo) para descobrir a pasta e refaz o lookup por ela, validando o
        número por igualdade exata antes de aceitar o vínculo.

        Args:
            numero_processo: número do processo (ex: ``"0008579"``).

        Returns:
            Tupla ``(vinculo_id, num_pasta_processo)``,
            ex: ``("3004", "Proc - 0008579")``.

        Raises:
            ProcessoNaoEncontradoError: se nenhum processo for encontrado.
        """
        result = self._crawler.lookup_lawsuit(numero_processo)
        row = self._match_lookup_row(result, numero_processo)

        if row is None:
            row = self._resolve_vinculo_via_busca_global(numero_processo)

        if row is None:
            logger.warning("_resolve_vinculo: processo não encontrado numero_processo=%s", numero_processo)
            raise ProcessoNaoEncontradoError(numero_processo)

        logger.info("_resolve_vinculo: processo encontrado numero_processo=%s vinculo_id=%s", numero_processo, row.id)
        return str(row.id), row.nome_pasta_processo or ""

    @staticmethod
    def _match_lookup_row(result, numero_processo: str):
        """
        Retorna a primeira row cujo número casa EXATAMENTE com ``numero_processo``,
        ou ``None`` se nenhuma casar.

        A comparação é por igualdade exata (nunca substring) contra o
        ``ProcessNumber`` e o ``NumeroAntigo`` da row — assim um protocolo
        administrativo contido dentro do número de outro processo (ex: CNJ de
        um judicial) jamais é aceito por engano; já um processo judicial que
        guarda o protocolo no campo "Número antigo" é aceito corretamente.
        """
        for row in result.rows:
            if numero_processo in (row.numero_processo, row.numero_antigo):
                return row
        return None

    # Extrai o número da pasta de descrições como "Proc - 0020963".
    _PASTA_DESCRIPTION_RE = re.compile(r"Proc\s*-\s*(\S+)", re.IGNORECASE)

    def _resolve_vinculo_via_busca_global(self, numero_processo: str):
        """
        Fallback: resolve o vínculo via busca global quando o LookupLawSuit
        direto não encontra o processo.

        Fluxo:
          1. Busca global (``/shared/global/search``) pelo número — ela ainda
             casa por "Número antigo".
          2. Para cada resultado, extrai o número da pasta da description
             (ex: ``"Proc - 0020963"`` → ``"0020963"``).
          3. Refaz ``lookup_lawsuit`` pela pasta e valida o número retornado
             por igualdade exata (via :meth:`_match_lookup_row`).

        A busca global é por continência, então pode retornar processos cujo
        número apenas CONTÉM o termo — a validação exata do passo 3 descarta
        esses falsos positivos.

        Returns:
            A row validada, ou ``None`` se nenhum candidato casar.
        """
        if self._search_service is None:
            logger.warning(
                "_resolve_vinculo_via_busca_global: search_service não configurado — fallback indisponível"
            )
            return None

        try:
            resultado = self._search_service.search(term=numero_processo, contexts=["Processos"])
        except Exception as exc:
            logger.warning(
                "_resolve_vinculo_via_busca_global: erro na busca global numero_processo=%s erro=%s",
                numero_processo, exc,
            )
            return None

        grupo = next((g for g in resultado.groups if g.context == "Processos"), None)
        if grupo is None or not grupo.items:
            logger.info(
                "_resolve_vinculo_via_busca_global: busca global sem resultados numero_processo=%s",
                numero_processo,
            )
            return None

        pastas_testadas: set[str] = set()
        for item in grupo.items:
            match = self._PASTA_DESCRIPTION_RE.search(item.description or "")
            if not match:
                logger.info(
                    "_resolve_vinculo_via_busca_global: description sem número de pasta: %r",
                    item.description,
                )
                continue
            num_pasta = match.group(1)
            if num_pasta in pastas_testadas:
                continue
            pastas_testadas.add(num_pasta)

            self._delay_between_requests()
            lookup = self._crawler.lookup_lawsuit(num_pasta)
            row = self._match_lookup_row(lookup, numero_processo)
            if row is not None:
                logger.info(
                    "_resolve_vinculo_via_busca_global: processo resolvido via pasta=%s numero_processo=%s vinculo_id=%s",
                    num_pasta, numero_processo, row.id,
                )
                return row
            logger.info(
                "_resolve_vinculo_via_busca_global: pasta=%s não corresponde ao número %s (descartada)",
                num_pasta, numero_processo,
            )

        return None

    # ── Resolução de usuário ──────────────────────────────────────────────────

    def _lookup_usuario_por_cpf(self, cpf: str) -> tuple[str, str]:
        """
        Dado o CPF, retorna ``(envolvido_id, envolvido_text)``.

        O match por CPF é exato — espera-se 0 ou 1 resultado.

        Args:
            cpf: CPF do usuário (ex: ``"485.180.028-26"``).

        Returns:
            Tupla ``(envolvido_id, envolvido_text)``.

        Raises:
            UsuarioNaoEncontradoError: nenhum usuário encontrado.
        """
        result = self._crawler.lookup_user(cpf)
        if result.count == 0 or not result.rows:
            logger.warning("_lookup_usuario_por_cpf: usuário NÃO encontrado cpf=%s", cpf)
            raise UsuarioNaoEncontradoError(cpf)
        row = result.rows[0]
        logger.info("_lookup_usuario_por_cpf: usuário encontrado cpf=%s envolvido_id=%s nome=%r", cpf, row.contato_id, row.contato_nome)
        return str(row.contato_id), row.contato_nome

    def _lookup_usuario_por_nome(self, nome: str) -> tuple[str, str]:
        """
        Dado o nome, retorna ``(envolvido_id, envolvido_text)``.

        Se mais de um usuário for encontrado, lança ``AmbiguousUserError``
        para que o caller forneça o CPF para desambiguar.

        Args:
            nome: nome do usuário (ex: ``"Maria Souza"``).

        Returns:
            Tupla ``(envolvido_id, envolvido_text)``.

        Raises:
            UsuarioNaoEncontradoError: nenhum usuário encontrado.
            AmbiguousUserError: mais de um usuário encontrado.
        """
        result = self._crawler.lookup_user(nome)
        if result.count == 0 or not result.rows:
            logger.warning("_lookup_usuario_por_nome: usuário não encontrado nome=%r", nome)
            raise UsuarioNaoEncontradoError(nome)
        if result.count > 1:
            logger.warning("_lookup_usuario_por_nome: nome ambíguo nome=%r count=%d", nome, result.count)
            raise AmbiguousUserError(nome, result.count)
        row = result.rows[0]
        logger.info("_lookup_usuario_por_nome: encontrado nome=%r envolvido_id=%s", nome, row.contato_id)
        return str(row.contato_id), row.contato_nome

    def _resolve_responsavel(self, resp: ResponsavelInput) -> EnvolvidoPayload:
        """
        Resolve um ResponsavelInput (cpf e/ou nome) em EnvolvidoPayload com IDs.

        Regra:
          - Se CPF fornecido → lookup por CPF (match exato, sem ambiguidade).
          - Senão → lookup por nome (pode lançar AmbiguousUserError).
        """
        if resp.cpf:
            env_id, env_text = self._lookup_usuario_por_cpf(resp.cpf)
        else:
            env_id, env_text = self._lookup_usuario_por_nome(resp.nome)
        time.sleep(0.5)  # espera fixa para evitar sobrecarregar o servidor com lookups seguidos

        return EnvolvidoPayload(
            envolvido_id=env_id,
            envolvido_text=env_text,
            is_solicitante=resp.is_solicitante,
            is_responsavel=resp.is_responsavel,
            is_executante=resp.is_executante,
        )

    # ── Resolução de Kanban ───────────────────────────────────────────────────

    def _lookup_kanban_board(self, board_name: str) -> tuple[str, str]:
        """
        Dado o nome do board, retorna ``(kanban_board_text, kanban_board_id)``.

        Chama ``crawler.lookup_kanban_boards`` e extrai o primeiro resultado.
        O nome é comparado por continência pelo LegalOne.

        Args:
            board_name: nome do board (ex: ``"BACKOFFICE"``).

        Returns:
            Tupla ``(kanban_board_text, kanban_board_id)``,
            ex: ``("BACKOFFICE", "2")``.

        Raises:
            KanbanBoardNotFoundError: nenhum board encontrado.
        """
        result = self._crawler.lookup_kanban_boards(board_name)
        if result.count == 0 or not result.rows:
            logger.warning("_lookup_kanban_board: board não encontrado board_name=%r", board_name)
            raise KanbanBoardNotFoundError(board_name)
        row = result.rows[0]
        logger.info("_lookup_kanban_board: encontrado board_name=%r id=%s", board_name, row.id)
        return row.value, str(row.id)

    def _lookup_kanban_column(self, column_name: str, board_id: str) -> tuple[str, str]:
        """
        Dado o nome da coluna e o ID do board, retorna
        ``(kanban_column_text, kanban_column_id)``.

        Args:
            column_name: nome da coluna (ex: ``"A DESIGNAR"``).
            board_id: ID do board Kanban (ex: ``"2"``).

        Returns:
            Tupla ``(kanban_column_text, kanban_column_id)``,
            ex: ``("A DESIGNAR", "17")``.

        Raises:
            KanbanBoardColumnNotFoundError: nenhuma coluna encontrada.
        """
        result = self._crawler.lookup_kanban_columns(board_id, column_name)
        if result.count == 0 or not result.rows:
            logger.warning("_lookup_kanban_column: coluna não encontrada column_name=%r board_id=%s", column_name, board_id)
            raise KanbanBoardColumnNotFoundError(column_name, board_id)
        row = result.rows[0]
        logger.info("_lookup_kanban_column: encontrada column_name=%r id=%s", column_name, row.id)
        return row.value, str(row.id)

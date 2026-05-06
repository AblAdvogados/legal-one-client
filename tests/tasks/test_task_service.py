# filepath: tests/tasks/test_task_service.py
"""
Testes UNITÁRIOS para o TaskService.

Usa mocks do TasksCrawler para testar a orquestração de resolução de IDs
sem HTTP. Verifica:
  - Processo resolvido corretamente via crawler.lookup_lawsuit
  - Responsáveis resolvidos por CPF ou nome via crawler.lookup_user
  - AmbiguousUserError / UsuarioNaoEncontradoError / ProcessoNaoEncontradoError
  - Kanban resolvido via crawler.lookup_kanban_boards/columns
  - TaskPayload montado corretamente
  - Retry com verificação de listagem em caso de TransientServerError/CrawlerError
  - Sem duplicação: tarefa encontrada na listagem após erro não dispara novo POST
"""

import unittest
from unittest.mock import MagicMock, patch

from core.errors import (
    AmbiguousUserError,
    CrawlerError,
    KanbanBoardColumnNotFoundError,
    KanbanBoardNotFoundError,
    ProcessoNaoEncontradoError,
    TransientServerError,
    UsuarioNaoEncontradoError,
)
from infrastructure.crawler.lookup_responses import (
    KanbanBoardLookupResponse,
    KanbanBoardRow,
    KanbanColumnLookupResponse,
    KanbanColumnRow,
    LawsuitLookupResponse,
    LawsuitLookupRow,
    UserLookupResponse,
    UserLookupRow,
)
from infrastructure.crawler.tasks import TasksCrawler
from parsers.task_parser import CreateTaskParserResult
from services.task.dto import (
    CreateTaskServiceInput,
    KanbanInput,
    LembreteServiceInput,
    ResponsavelInput,
    TaskPayload,
)
from services.task.task_service import TaskService


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de fixture
# ─────────────────────────────────────────────────────────────────────────────

def _lawsuit_response(numero="0008579", vinculo_id=3004, pasta="Proc - 0008579"):
    return LawsuitLookupResponse(count=1, rows=[
        LawsuitLookupRow(id=vinculo_id, numero_processo=numero,
                         nome_pasta_processo=pasta, titulo=None,
                         nome_cliente_principal=None, id_cliente_principal=None),
    ])


def _user_response(contato_id=42, nome="JOÃO DA SILVA", cpf="123.456.789-00"):
    return UserLookupResponse(count=1, rows=[
        UserLookupRow(contato_id=contato_id, contato_nome=nome, cpf=cpf),
    ])


def _kanban_board_response(board_id=2, value="BACKOFFICE"):
    return KanbanBoardLookupResponse(count=1, rows=[KanbanBoardRow(id=board_id, value=value)])


def _kanban_column_response(col_id=17, value="A DESIGNAR"):
    return KanbanColumnLookupResponse(count=1, rows=[KanbanColumnRow(id=col_id, value=value)])


def _parser_success(task_id="102"):
    return CreateTaskParserResult(success=True, task_id=task_id, errors=[], source="post_success")


def _parser_not_found():
    return CreateTaskParserResult(success=False, task_id=None, errors=[], source="listing")


def _make_crawler_mock():
    crawler = MagicMock(spec=TasksCrawler)
    crawler.lookup_lawsuit.return_value = _lawsuit_response()
    crawler.lookup_user.return_value = _user_response()
    crawler.lookup_kanban_boards.return_value = _kanban_board_response()
    crawler.lookup_kanban_columns.return_value = _kanban_column_response()
    crawler.post_create_task.return_value = "<html>OK</html>"
    crawler.fetch_task_listing.return_value = "<html>listing</html>"
    return crawler


def _minimal_input():
    return CreateTaskServiceInput(
        numero_processo="0008579",
        responsaveis=[
            ResponsavelInput(nome="João da Silva", cpf="123.456.789-00",
                             is_solicitante=True, is_responsavel=True, is_executante=False),
        ],
        descricao="Audiência Inicial",
        dt_inicial="06/04/2026",
        hr_inicio="08:00:00",
        dt_final="06/04/2026",
        hr_final="09:00:00",
    )


_PARSER_PATH = "services.task.task_service.interpret_create_task_response"


# ══════════════════════════════════════════════════════════════════════════════
# 1. Happy path
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateTaskHappyPath(unittest.TestCase):

    def setUp(self):
        self.crawler = _make_crawler_mock()
        self.service = TaskService(crawler=self.crawler)
        self._p = patch(_PARSER_PATH, return_value=_parser_success())
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_sucesso_minimal(self):
        result = self.service.create_task(_minimal_input())
        self.assertTrue(result.success)

    def test_resolve_processo_via_lookup_lawsuit(self):
        self.service.create_task(_minimal_input())
        self.crawler.lookup_lawsuit.assert_called_once_with("0008579")

    def test_resolve_responsavel_por_cpf(self):
        self.service.create_task(_minimal_input())
        self.crawler.lookup_user.assert_called_once_with("123.456.789-00")

    def test_resolve_responsavel_por_nome(self):
        req = _minimal_input()
        req.responsaveis = [
            ResponsavelInput(nome="Maria Souza", cpf=None,
                             is_solicitante=True, is_responsavel=True, is_executante=False),
        ]
        self.service.create_task(req)
        self.crawler.lookup_user.assert_called_once_with("Maria Souza")

    def test_post_create_task_chamado_com_task_payload(self):
        self.service.create_task(_minimal_input())
        self.crawler.post_create_task.assert_called_once()
        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertIsInstance(payload, TaskPayload)
        self.assertEqual(payload.processo_id, "3004")
        self.assertEqual(payload.num_pasta_processo, "Proc - 0008579")
        self.assertEqual(payload.descricao, "Audiência Inicial")

    def test_envolvidos_resolvidos_no_payload(self):
        self.service.create_task(_minimal_input())
        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertEqual(len(payload.envolvidos), 1)
        env = payload.envolvidos[0]
        self.assertEqual(env.envolvido_id, "42")
        self.assertEqual(env.envolvido_text, "JOÃO DA SILVA")
        self.assertTrue(env.is_solicitante)

    def test_sem_kanban_no_payload(self):
        self.service.create_task(_minimal_input())
        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertFalse(payload.show_activity_in_kanban)
        self.assertEqual(payload.kanban_board_text, "")
        self.assertEqual(payload.kanban_board_id, "")

    def test_deadline_vazio_quando_nao_fornecido(self):
        self.service.create_task(_minimal_input())
        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertEqual(payload.deadline_date, "")
        self.assertEqual(payload.deadline_time, "")


# ══════════════════════════════════════════════════════════════════════════════
# 2. Kanban
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateTaskKanban(unittest.TestCase):

    def setUp(self):
        self.crawler = _make_crawler_mock()
        self.service = TaskService(crawler=self.crawler)
        self._p = patch(_PARSER_PATH, return_value=_parser_success())
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_kanban_resolvido(self):
        req = _minimal_input()
        req.kanban = KanbanInput(board_name="BACKOFFICE", column_name="A DESIGNAR")
        self.service.create_task(req)

        self.crawler.lookup_kanban_boards.assert_called_once_with("BACKOFFICE")
        self.crawler.lookup_kanban_columns.assert_called_once_with("2", "A DESIGNAR")

        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertTrue(payload.show_activity_in_kanban)
        self.assertEqual(payload.kanban_board_text, "BACKOFFICE")
        self.assertEqual(payload.kanban_board_id, "2")
        self.assertEqual(payload.kanban_column_text, "A DESIGNAR")
        self.assertEqual(payload.kanban_column_id, "17")

    def test_kanban_board_not_found_propaga(self):
        self.crawler.lookup_kanban_boards.return_value = KanbanBoardLookupResponse(count=0, rows=[])
        req = _minimal_input()
        req.kanban = KanbanInput(board_name="INVALIDO", column_name="COLUNA")
        with self.assertRaises(KanbanBoardNotFoundError):
            self.service.create_task(req)

    def test_kanban_column_not_found_propaga(self):
        self.crawler.lookup_kanban_columns.return_value = KanbanColumnLookupResponse(count=0, rows=[])
        req = _minimal_input()
        req.kanban = KanbanInput(board_name="BACKOFFICE", column_name="INVALIDA")
        with self.assertRaises(KanbanBoardColumnNotFoundError):
            self.service.create_task(req)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Lembretes
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateTaskLembretes(unittest.TestCase):

    def setUp(self):
        self.crawler = _make_crawler_mock()
        self.service = TaskService(crawler=self.crawler)
        self._p = patch(_PARSER_PATH, return_value=_parser_success())
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_sem_lembretes_payload_vazio(self):
        self.service.create_task(_minimal_input())
        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertEqual(payload.lembretes, [])


# ══════════════════════════════════════════════════════════════════════════════
# 4. Recorrência e observações
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateTaskRecorrencia(unittest.TestCase):

    def setUp(self):
        self.crawler = _make_crawler_mock()
        self.service = TaskService(crawler=self.crawler)
        self._p = patch(_PARSER_PATH, return_value=_parser_success())
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_recorrencia_propagada(self):
        req = _minimal_input()
        req.incluir_recorrencia = True
        self.service.create_task(req)
        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertTrue(payload.incluir_recorrencia)

    def test_sem_recorrencia_propagada(self):
        self.service.create_task(_minimal_input())
        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertFalse(payload.incluir_recorrencia)

    def test_observacoes_propagadas(self):
        req = _minimal_input()
        req.observacoes = "Nota importante"
        self.service.create_task(req)
        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertEqual(payload.observacoes, "Nota importante")


# ══════════════════════════════════════════════════════════════════════════════
# 5. Erros de resolução
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateTaskErrors(unittest.TestCase):

    def setUp(self):
        self.crawler = _make_crawler_mock()
        self.service = TaskService(crawler=self.crawler)

    def test_processo_nao_encontrado(self):
        self.crawler.lookup_lawsuit.return_value = LawsuitLookupResponse(count=0, rows=[])
        with self.assertRaises(ProcessoNaoEncontradoError):
            self.service.create_task(_minimal_input())

    def test_usuario_nao_encontrado_por_cpf(self):
        self.crawler.lookup_user.return_value = UserLookupResponse(count=0, rows=[])
        with self.assertRaises(UsuarioNaoEncontradoError):
            self.service.create_task(_minimal_input())

    def test_usuario_ambiguo_por_nome(self):
        self.crawler.lookup_user.return_value = UserLookupResponse(count=2, rows=[
            UserLookupRow(contato_id=1, contato_nome="Maria A", cpf=None),
            UserLookupRow(contato_id=2, contato_nome="Maria B", cpf=None),
        ])
        req = _minimal_input()
        req.responsaveis = [
            ResponsavelInput(nome="Maria", cpf=None,
                             is_solicitante=True, is_responsavel=True, is_executante=False),
        ]
        with self.assertRaises(AmbiguousUserError):
            self.service.create_task(req)


# ══════════════════════════════════════════════════════════════════════════════
# 6. Múltiplos responsáveis
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateTaskMultipleResponsaveis(unittest.TestCase):

    def setUp(self):
        self.crawler = _make_crawler_mock()
        self.crawler.lookup_user.side_effect = lambda t: (
            _user_response(42, "JOÃO DA SILVA", "123.456.789-00") if "." in t
            else _user_response(99, "MARIA SOUZA", None)
        )
        self.service = TaskService(crawler=self.crawler)
        self._p = patch(_PARSER_PATH, return_value=_parser_success())
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_dois_responsaveis(self):
        req = _minimal_input()
        req.responsaveis = [
            ResponsavelInput("João da Silva", "123.456.789-00", True, True, False),
            ResponsavelInput("Maria Souza", None, False, False, True),
        ]
        self.service.create_task(req)
        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertEqual(len(payload.envolvidos), 2)
        self.assertEqual(payload.envolvidos[0].envolvido_id, "42")
        self.assertTrue(payload.envolvidos[0].is_solicitante)
        self.assertEqual(payload.envolvidos[1].envolvido_id, "99")
        self.assertTrue(payload.envolvidos[1].is_executante)


# ══════════════════════════════════════════════════════════════════════════════
# 7. Deadline
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateTaskDeadline(unittest.TestCase):

    def setUp(self):
        self.crawler = _make_crawler_mock()
        self.service = TaskService(crawler=self.crawler)
        self._p = patch(_PARSER_PATH, return_value=_parser_success())
        self._p.start()

    def tearDown(self):
        self._p.stop()

    def test_deadline_preenchido(self):
        req = _minimal_input()
        req.deadline_date = "10/04/2026"
        req.deadline_time = "17:00:00"
        self.service.create_task(req)
        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertEqual(payload.deadline_date, "10/04/2026")
        self.assertEqual(payload.deadline_time, "17:00:00")

    def test_deadline_none_vira_vazio(self):
        self.service.create_task(_minimal_input())
        payload = self.crawler.post_create_task.call_args[0][0]
        self.assertEqual(payload.deadline_date, "")
        self.assertEqual(payload.deadline_time, "")


# ══════════════════════════════════════════════════════════════════════════════
# 8. Retry e verificação de listagem (_create_task_with_verification)
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateTaskWithVerification(unittest.TestCase):

    def setUp(self):
        self.crawler = _make_crawler_mock()
        self.service = TaskService(crawler=self.crawler)

    def _patch_parser(self, **kwargs):
        return patch(_PARSER_PATH, **kwargs)

    @patch("time.sleep")
    def test_transient_error_tarefa_encontrada_na_listagem(self, _sleep):
        """POST falha com 502 mas tarefa já está na listagem → sem novo POST."""
        self.crawler.post_create_task.side_effect = TransientServerError("502")
        result_listagem = CreateTaskParserResult(success=True, task_id="102", errors=[], source="listing")
        with self._patch_parser(return_value=result_listagem):
            result = self.service.create_task(_minimal_input())
        self.assertTrue(result.success)
        self.assertEqual(self.crawler.post_create_task.call_count, 1)
        self.crawler.fetch_task_listing.assert_called_once()

    @patch("time.sleep")
    def test_transient_error_tarefa_nao_encontrada_retry_sucesso(self, _sleep):
        """POST falha → listagem não confirma → retry tem sucesso."""
        self.crawler.post_create_task.side_effect = [
            TransientServerError("502"),
            "<html>OK retry</html>",
        ]
        with self._patch_parser(side_effect=[_parser_not_found(), _parser_success("55")]):
            result = self.service.create_task(_minimal_input())
        self.assertTrue(result.success)
        self.assertEqual(result.task_id, "55")
        self.assertEqual(self.crawler.post_create_task.call_count, 2)

    @patch("time.sleep")
    def test_retries_esgotados_propaga_excecao(self, _sleep):
        """Todos os POSTs falham e listagem nunca confirma → propaga exceção."""
        self.crawler.post_create_task.side_effect = TransientServerError("502 persistente")
        with self._patch_parser(return_value=_parser_not_found()):
            with self.assertRaises(TransientServerError):
                self.service.create_task(_minimal_input())
        self.assertEqual(
            self.crawler.post_create_task.call_count,
            1 + TaskService._MAX_POST_RETRIES,
        )

    @patch("time.sleep")
    def test_crawler_error_dispara_verificacao_listagem(self, _sleep):
        """CrawlerError (não só TransientServerError) também dispara verificação."""
        self.crawler.post_create_task.side_effect = CrawlerError("400")
        result_listagem = CreateTaskParserResult(success=True, task_id="77", errors=[], source="listing")
        with self._patch_parser(return_value=result_listagem):
            result = self.service.create_task(_minimal_input())
        self.assertTrue(result.success)
        self.crawler.fetch_task_listing.assert_called_once()

    @patch("time.sleep")
    def test_falha_na_listagem_nao_impede_retry(self, _sleep):
        """fetch_task_listing também falha → retry do POST prossegue normalmente."""
        self.crawler.post_create_task.side_effect = [
            TransientServerError("502"),
            "<html>OK retry</html>",
        ]
        self.crawler.fetch_task_listing.side_effect = CrawlerError("listagem inacessível")
        with self._patch_parser(return_value=_parser_success("88")):
            result = self.service.create_task(_minimal_input())
        self.assertTrue(result.success)
        self.assertEqual(self.crawler.post_create_task.call_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

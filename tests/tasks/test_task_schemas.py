# filepath: tests/tasks/test_task_schemas.py
"""
Testes UNITÁRIOS para os schemas Pydantic de tarefas.

Verifica validações de entrada:
  - Exatamente 1 solicitante
  - Ao menos cpf ou nome por responsável
  - Deadline date/time pareados
  - Bools obrigatórios (sem default)
  - Campos opcionais ausentes → defaults corretos

Offline, sem HTTP.
"""

import unittest

import pytest
from pydantic import ValidationError

from app.schemas.task_schemas import (
    CreateTaskRequest,
    CreateTaskResponse,
    KanbanSchema,
    LembreteSchema,
    ResponsavelSchema,
)


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

_RESPONSAVEL_SOLICITANTE = {
    "nome": "João da Silva",
    "cpf": "123.456.789-00",
    "is_solicitante": True,
    "is_responsavel": True,
    "is_executante": False,
}

_RESPONSAVEL_EXECUTOR = {
    "nome": "Maria Souza",
    "is_solicitante": False,
    "is_responsavel": False,
    "is_executante": True,
}

_MINIMAL_VALID_BODY = {
    "numero_processo": "0008579",
    "responsaveis": [_RESPONSAVEL_SOLICITANTE],
    "descricao": "Audiência Inicial",
    "dt_inicial": "06/04/2026",
    "hr_inicio": "08:00:00",
    "dt_final": "06/04/2026",
    "hr_final": "09:00:00",
}


# ══════════════════════════════════════════════════════════════════════════════
# ResponsavelSchema
# ══════════════════════════════════════════════════════════════════════════════

class TestResponsavelSchema(unittest.TestCase):

    def test_valid_com_cpf_e_nome(self):
        r = ResponsavelSchema(**_RESPONSAVEL_SOLICITANTE)
        self.assertEqual(r.cpf, "123.456.789-00")
        self.assertEqual(r.nome, "João da Silva")
        self.assertTrue(r.is_solicitante)

    def test_valid_somente_nome(self):
        r = ResponsavelSchema(**_RESPONSAVEL_EXECUTOR)
        self.assertIsNone(r.cpf)
        self.assertEqual(r.nome, "Maria Souza")

    def test_valid_somente_cpf(self):
        r = ResponsavelSchema(
            cpf="111.222.333-44",
            is_solicitante=False,
            is_responsavel=True,
            is_executante=False,
        )
        self.assertIsNone(r.nome)
        self.assertEqual(r.cpf, "111.222.333-44")

    def test_rejeita_sem_cpf_nem_nome(self):
        with self.assertRaises(ValidationError) as ctx:
            ResponsavelSchema(
                is_solicitante=False,
                is_responsavel=True,
                is_executante=False,
            )
        self.assertIn("cpf", str(ctx.exception).lower() + str(ctx.exception).lower())

    def test_bools_sao_obrigatorios(self):
        """Se is_solicitante/is_responsavel/is_executante estiverem faltando → erro."""
        with self.assertRaises(ValidationError):
            ResponsavelSchema(nome="Teste")

        with self.assertRaises(ValidationError):
            ResponsavelSchema(
                nome="Teste",
                is_solicitante=True,
                # is_responsavel ausente
                is_executante=False,
            )


# ══════════════════════════════════════════════════════════════════════════════
# KanbanSchema
# ══════════════════════════════════════════════════════════════════════════════

class TestKanbanSchema(unittest.TestCase):

    def test_valid(self):
        k = KanbanSchema(board_name="BACKOFFICE", column_name="A DESIGNAR")
        self.assertEqual(k.board_name, "BACKOFFICE")
        self.assertEqual(k.column_name, "A DESIGNAR")

    def test_rejeita_board_ausente(self):
        with self.assertRaises(ValidationError):
            KanbanSchema(column_name="A DESIGNAR")

    def test_rejeita_column_ausente(self):
        with self.assertRaises(ValidationError):
            KanbanSchema(board_name="BACKOFFICE")


# ══════════════════════════════════════════════════════════════════════════════
# LembreteSchema
# ══════════════════════════════════════════════════════════════════════════════

class TestLembreteSchema(unittest.TestCase):

    def test_valid_com_defaults(self):
        l = LembreteSchema(nome_envolvido="João da Silva")
        self.assertEqual(l.nome_envolvido, "João da Silva")
        self.assertEqual(l.numero_antecedencia, 1)
        self.assertEqual(l.tipo_antecedencia, "2")

    def test_override_defaults(self):
        l = LembreteSchema(
            nome_envolvido="Maria",
            numero_antecedencia=3,
            tipo_antecedencia="1",
        )
        self.assertEqual(l.numero_antecedencia, 3)
        self.assertEqual(l.tipo_antecedencia, "1")

    def test_rejeita_sem_nome(self):
        with self.assertRaises(ValidationError):
            LembreteSchema()


# ══════════════════════════════════════════════════════════════════════════════
# CreateTaskRequest — validadores
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateTaskRequest(unittest.TestCase):

    def test_minimal_valido(self):
        """Body mínimo (sem opcionais) deve ser aceito."""
        req = CreateTaskRequest(**_MINIMAL_VALID_BODY)
        self.assertEqual(req.numero_processo, "0008579")
        self.assertEqual(len(req.responsaveis), 1)
        self.assertIsNone(req.kanban)
        self.assertEqual(req.lembretes, [])
        self.assertFalse(req.incluir_recorrencia)
        self.assertEqual(req.observacoes, "")
        self.assertIsNone(req.deadline_date)
        self.assertIsNone(req.deadline_time)

    def test_completo_valido(self):
        """Body completo com todos os opcionais preenchidos."""
        body = {
            **_MINIMAL_VALID_BODY,
            "responsaveis": [_RESPONSAVEL_SOLICITANTE, _RESPONSAVEL_EXECUTOR],
            "deadline_date": "10/04/2026",
            "deadline_time": "17:00:00",
            "kanban": {"board_name": "BACKOFFICE", "column_name": "A DESIGNAR"},
            "lembretes": [{"nome_envolvido": "João da Silva"}],
            "incluir_recorrencia": True,
            "observacoes": "Obs de teste",
        }
        req = CreateTaskRequest(**body)
        self.assertEqual(len(req.responsaveis), 2)
        self.assertIsNotNone(req.kanban)
        self.assertEqual(len(req.lembretes), 1)
        self.assertTrue(req.incluir_recorrencia)

    # ── Exatamente 1 solicitante ──────────────────────────────────────────────

    def test_rejeita_zero_solicitantes(self):
        body = {
            **_MINIMAL_VALID_BODY,
            "responsaveis": [{
                "nome": "Teste",
                "is_solicitante": False,
                "is_responsavel": True,
                "is_executante": False,
            }],
        }
        with self.assertRaises(ValidationError) as ctx:
            CreateTaskRequest(**body)
        self.assertIn("solicitante", str(ctx.exception).lower())

    def test_rejeita_dois_solicitantes(self):
        sol1 = {**_RESPONSAVEL_SOLICITANTE}
        sol2 = {**_RESPONSAVEL_EXECUTOR, "is_solicitante": True}
        body = {**_MINIMAL_VALID_BODY, "responsaveis": [sol1, sol2]}
        with self.assertRaises(ValidationError) as ctx:
            CreateTaskRequest(**body)
        self.assertIn("solicitante", str(ctx.exception).lower())

    # ── Deadline pareado ──────────────────────────────────────────────────────

    def test_rejeita_deadline_date_sem_time(self):
        body = {**_MINIMAL_VALID_BODY, "deadline_date": "10/04/2026"}
        with self.assertRaises(ValidationError) as ctx:
            CreateTaskRequest(**body)
        self.assertIn("deadline_time", str(ctx.exception).lower())

    def test_rejeita_deadline_time_sem_date(self):
        body = {**_MINIMAL_VALID_BODY, "deadline_time": "17:00:00"}
        with self.assertRaises(ValidationError) as ctx:
            CreateTaskRequest(**body)
        self.assertIn("deadline_date", str(ctx.exception).lower())

    def test_aceita_deadline_completo(self):
        body = {
            **_MINIMAL_VALID_BODY,
            "deadline_date": "10/04/2026",
            "deadline_time": "17:00:00",
        }
        req = CreateTaskRequest(**body)
        self.assertEqual(req.deadline_date, "10/04/2026")
        self.assertEqual(req.deadline_time, "17:00:00")

    def test_aceita_sem_deadline(self):
        req = CreateTaskRequest(**_MINIMAL_VALID_BODY)
        self.assertIsNone(req.deadline_date)
        self.assertIsNone(req.deadline_time)

    # ── Responsáveis ≥ 1 ─────────────────────────────────────────────────────

    def test_rejeita_responsaveis_vazio(self):
        body = {**_MINIMAL_VALID_BODY, "responsaveis": []}
        with self.assertRaises(ValidationError):
            CreateTaskRequest(**body)


# ══════════════════════════════════════════════════════════════════════════════
# CreateTaskResponse
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateTaskResponse(unittest.TestCase):

    def test_sucesso(self):
        r = CreateTaskResponse(success=True, message="OK")
        self.assertTrue(r.success)

    def test_default_message(self):
        r = CreateTaskResponse(success=False)
        self.assertEqual(r.message, "")


if __name__ == "__main__":
    unittest.main(verbosity=2)

# filepath: tests/tasks/test_task_router_converter.py
"""
Testes UNITÁRIOS para o conversor _to_service_input() do router de tarefas.

Verifica que CreateTaskRequest (Pydantic) é convertido corretamente para
CreateTaskServiceInput (dataclass pura do domínio).

Offline, sem HTTP.
"""

import unittest

from app.schemas.task_schemas import CreateTaskRequest
from app.routers.tasks import _to_service_input
from services.task.dto import (
    CreateTaskServiceInput,
    KanbanInput,
    LembreteServiceInput,
    ResponsavelInput,
)


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

_MINIMAL_BODY = {
    "numero_processo": "0008579",
    "responsaveis": [{
        "nome": "João da Silva",
        "cpf": "123.456.789-00",
        "is_solicitante": True,
        "is_responsavel": True,
        "is_executante": False,
    }],
    "descricao": "Audiência Inicial",
    "dt_inicial": "06/04/2026",
    "hr_inicio": "08:00:00",
    "dt_final": "06/04/2026",
    "hr_final": "09:00:00",
}

_FULL_BODY = {
    **_MINIMAL_BODY,
    "responsaveis": [
        {
            "nome": "João da Silva",
            "cpf": "123.456.789-00",
            "is_solicitante": True,
            "is_responsavel": True,
            "is_executante": False,
        },
        {
            "nome": "Maria Souza",
            "is_solicitante": False,
            "is_responsavel": False,
            "is_executante": True,
        },
    ],
    "deadline_date": "10/04/2026",
    "deadline_time": "17:00:00",
    "kanban": {"board_name": "BACKOFFICE", "column_name": "A DESIGNAR"},
    "lembretes": [
        {"nome_envolvido": "João da Silva", "numero_antecedencia": 2, "tipo_antecedencia": "1"},
    ],
    "incluir_recorrencia": True,
    "observacoes": "Observação de teste",
}


# ══════════════════════════════════════════════════════════════════════════════
# Testes
# ══════════════════════════════════════════════════════════════════════════════

class TestToServiceInput(unittest.TestCase):

    def test_minimal_conversion(self):
        """Body mínimo deve produzir DTO com defaults corretos."""
        req = CreateTaskRequest(**_MINIMAL_BODY)
        dto = _to_service_input(req)

        self.assertIsInstance(dto, CreateTaskServiceInput)
        self.assertEqual(dto.numero_processo, "0008579")
        self.assertEqual(dto.descricao, "Audiência Inicial")
        self.assertEqual(dto.dt_inicial, "06/04/2026")
        self.assertEqual(dto.hr_inicio, "08:00:00")
        self.assertEqual(dto.dt_final, "06/04/2026")
        self.assertEqual(dto.hr_final, "09:00:00")
        self.assertIsNone(dto.deadline_date)
        self.assertIsNone(dto.deadline_time)
        self.assertIsNone(dto.kanban)
        self.assertEqual(dto.lembretes, [])
        self.assertFalse(dto.incluir_recorrencia)
        self.assertEqual(dto.observacoes, "")

    def test_responsaveis_conversion(self):
        """Cada ResponsavelSchema deve virar ResponsavelInput."""
        req = CreateTaskRequest(**_MINIMAL_BODY)
        dto = _to_service_input(req)

        self.assertEqual(len(dto.responsaveis), 1)
        r = dto.responsaveis[0]
        self.assertIsInstance(r, ResponsavelInput)
        self.assertEqual(r.nome, "João da Silva")
        self.assertEqual(r.cpf, "123.456.789-00")
        self.assertTrue(r.is_solicitante)
        self.assertTrue(r.is_responsavel)
        self.assertFalse(r.is_executante)

    def test_full_conversion(self):
        """Body completo deve converter todos os campos corretamente."""
        req = CreateTaskRequest(**_FULL_BODY)
        dto = _to_service_input(req)

        # Responsáveis
        self.assertEqual(len(dto.responsaveis), 2)
        self.assertTrue(dto.responsaveis[0].is_solicitante)
        self.assertFalse(dto.responsaveis[1].is_solicitante)
        self.assertTrue(dto.responsaveis[1].is_executante)
        self.assertIsNone(dto.responsaveis[1].cpf)

        # Deadline
        self.assertEqual(dto.deadline_date, "10/04/2026")
        self.assertEqual(dto.deadline_time, "17:00:00")

        # Kanban
        self.assertIsNotNone(dto.kanban)
        self.assertIsInstance(dto.kanban, KanbanInput)
        self.assertEqual(dto.kanban.board_name, "BACKOFFICE")
        self.assertEqual(dto.kanban.column_name, "A DESIGNAR")

        # Lembretes
        self.assertEqual(len(dto.lembretes), 1)
        lem = dto.lembretes[0]
        self.assertIsInstance(lem, LembreteServiceInput)
        self.assertEqual(lem.nome_envolvido, "João da Silva")
        self.assertEqual(lem.numero_antecedencia, 2)
        self.assertEqual(lem.tipo_antecedencia, "1")

        # Flags
        self.assertTrue(dto.incluir_recorrencia)
        self.assertEqual(dto.observacoes, "Observação de teste")

    def test_kanban_none_when_absent(self):
        """Se kanban não fornecido, dto.kanban deve ser None."""
        req = CreateTaskRequest(**_MINIMAL_BODY)
        dto = _to_service_input(req)
        self.assertIsNone(dto.kanban)


if __name__ == "__main__":
    unittest.main(verbosity=2)

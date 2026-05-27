# filepath: tests/tasks/test_tipo_tarefa_mapper.py
"""
Testes unitários para tipo_tarefa_mapper.

Offline — apenas lê tipos_tarefa.json via @cache.
"""

import unittest

from core.errors import TipoTarefaNaoEncontradoError
from infrastructure.lookup.tipo_tarefa_mapper import (
    DEFAULT_TIPO_ID,
    DEFAULT_TIPO_TEXT,
    map_tipo_tarefa,
)


class TestMapTipoTarefa(unittest.TestCase):

    def test_tipo_none_retorna_defaults(self):
        text, id_ = map_tipo_tarefa(None)
        self.assertEqual(text, DEFAULT_TIPO_TEXT)
        self.assertEqual(id_, DEFAULT_TIPO_ID)

    def test_tipo_none_subtipo_none_retorna_defaults(self):
        text, id_ = map_tipo_tarefa(None, None)
        self.assertEqual(text, DEFAULT_TIPO_TEXT)
        self.assertEqual(id_, DEFAULT_TIPO_ID)

    def test_tipo_valido_retorna_path_e_id(self):
        text, id_ = map_tipo_tarefa("BACKOFFICE")
        self.assertEqual(text, "BACKOFFICE")
        self.assertTrue(id_.startswith("tipo_"))

    def test_tipo_case_insensitive(self):
        text_upper, id_upper = map_tipo_tarefa("BACKOFFICE")
        text_lower, id_lower = map_tipo_tarefa("backoffice")
        self.assertEqual(text_upper, text_lower)
        self.assertEqual(id_upper, id_lower)

    def test_tipo_com_strip(self):
        text_plain, id_plain = map_tipo_tarefa("BACKOFFICE")
        text_spaces, id_spaces = map_tipo_tarefa("  BACKOFFICE  ")
        self.assertEqual(text_plain, text_spaces)
        self.assertEqual(id_plain, id_spaces)

    def test_tipo_e_subtipo_validos(self):
        text, id_ = map_tipo_tarefa("BACKOFFICE", "ANALISE DE CASO")
        self.assertIn("BACKOFFICE", text)
        self.assertTrue(id_.startswith("subtipo_"))

    def test_tipo_e_subtipo_case_insensitive(self):
        text_upper, id_upper = map_tipo_tarefa("BACKOFFICE", "ANALISE DE CASO")
        text_lower, id_lower = map_tipo_tarefa("backoffice", "analise de caso")
        self.assertEqual(text_upper, text_lower)
        self.assertEqual(id_upper, id_lower)

    def test_tipo_sem_acento_encontra_com_acento(self):
        """'ANALISE DE CASO' (sem acento) deve encontrar 'ANÁLISE DE CASO' (com acento)."""
        text_sem, id_sem = map_tipo_tarefa("BACKOFFICE", "ANALISE DE CASO")
        text_com, id_com = map_tipo_tarefa("BACKOFFICE", "ANÁLISE DE CASO")
        self.assertEqual(text_sem, text_com)
        self.assertEqual(id_sem, id_com)

    def test_tipo_com_strip_e_subtipo_com_strip(self):
        text_plain, id_plain = map_tipo_tarefa("BACKOFFICE", "ANALISE DE CASO")
        text_spaces, id_spaces = map_tipo_tarefa("  BACKOFFICE  ", "  ANALISE DE CASO  ")
        self.assertEqual(text_plain, text_spaces)
        self.assertEqual(id_plain, id_spaces)

    def test_tipo_invalido_lanca_erro(self):
        with self.assertRaises(TipoTarefaNaoEncontradoError) as ctx:
            map_tipo_tarefa("TIPO_INEXISTENTE_XYZ")
        self.assertIn("TIPO_INEXISTENTE_XYZ", str(ctx.exception))

    def test_subtipo_invalido_lanca_erro(self):
        with self.assertRaises(TipoTarefaNaoEncontradoError) as ctx:
            map_tipo_tarefa("BACKOFFICE", "SUBTIPO_INEXISTENTE_XYZ")
        self.assertIn("SUBTIPO_INEXISTENTE_XYZ", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)

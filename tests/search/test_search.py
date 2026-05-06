# filepath: tests/search/test_search.py
"""
Testes para o caso de uso de busca global.

Dois grupos:

  TestParseSearchResults  — testes UNITÁRIOS, offline, sem HTTP.
    Verifica que parse_search_results() converte corretamente um dict JSON
    para GlobalSearchResult, incluindo casos de grupos vazios e campos null.

  TestSearchIntegration   — testes de INTEGRAÇÃO, HTTP real.
    Faz uma única requisição real ao LegalOne e verifica que os resultados
    batem com os marcadores conhecidos do contato/processo de referência.
"""

import unittest

from parsers.search_parser import (
    GlobalSearchResult,
    SearchResultGroup,
    SearchResultItem,
    parse_search_results,
)
from infrastructure.crawler.search import GlobalSearchCrawler
from services.search_service import SearchService
from tests.helpers import make_session_manager, assert_not_login_page


# ── Fixtures para testes unitários ───────────────────────────────────────────

_SAMPLE_RESPONSE = {
    "Groups": [
        {
            "Items": [
                {
                    "Description": "Proc - 0003965",
                    "ExtraInformation": "Titulo AUXILIO ACIDENTE",
                    "Url": "/processos/Processos/Details/24195",
                },
                {
                    "Description": "Proc - 0016779",
                    "ExtraInformation": "Titulo AUXÍLIO-ACIDENTE",
                    "Url": "/processos/Processos/Details/22358",
                },
            ],
            "Count": 2,
            "Name": "Processos",
            "CompleteSearchUrl": "/processos/Processos/Search?Search=ELIZABETE",
            "IsCompleteSearchUrlExternal": False,
        },
        {
            "Items": [
                {
                    "Description": "ELIZABETE RIBEIRO DA SILVA SANTOS",
                    "ExtraInformation": None,
                    "Url": "/contatos/Pessoas/Details/86797",
                }
            ],
            "Count": 1,
            "Name": "Contatos",
            "CompleteSearchUrl": "/contatos/Contatos/Search?Search=ELIZABETE",
            "IsCompleteSearchUrlExternal": False,
        },
    ],
    "Unauthorized": False,
    "UseRules": True,
}

_EMPTY_RESPONSE = {"Groups": [], "Unauthorized": False, "UseRules": True}


# ══════════════════════════════════════════════════════════════════════════════
# 1. Testes UNITÁRIOS — parse offline
# ══════════════════════════════════════════════════════════════════════════════

class TestParseSearchResults(unittest.TestCase):
    """Testa parse_search_results() contra fixtures de dict sem HTTP."""

    @classmethod
    def setUpClass(cls):
        cls.result = parse_search_results(_SAMPLE_RESPONSE)

    def test_retorna_global_search_result(self):
        self.assertIsInstance(self.result, GlobalSearchResult)

    def test_dois_grupos(self):
        self.assertEqual(len(self.result.groups), 2)

    def test_grupo_processos(self):
        g = self.result.groups[0]
        self.assertIsInstance(g, SearchResultGroup)
        self.assertEqual(g.context, "Processos")
        self.assertEqual(g.count, 2)
        self.assertEqual(len(g.items), 2)

    def test_grupo_contatos(self):
        g = self.result.groups[1]
        self.assertEqual(g.context, "Contatos")
        self.assertEqual(g.count, 1)
        self.assertEqual(len(g.items), 1)

    def test_item_com_extra_information(self):
        item = self.result.groups[0].items[0]
        self.assertIsInstance(item, SearchResultItem)
        self.assertEqual(item.description, "Proc - 0003965")
        self.assertEqual(item.url, "/processos/Processos/Details/24195")
        self.assertEqual(item.extra_information, "Titulo AUXILIO ACIDENTE")

    def test_item_sem_extra_information_e_none(self):
        """ExtraInformation: null no JSON deve virar None no objeto."""
        item = self.result.groups[1].items[0]
        self.assertEqual(item.description, "ELIZABETE RIBEIRO DA SILVA SANTOS")
        self.assertIsNone(item.extra_information)

    def test_resposta_vazia_retorna_lista_vazia(self):
        result = parse_search_results(_EMPTY_RESPONSE)
        self.assertEqual(result.groups, [])

    def test_resposta_sem_chave_groups_retorna_lista_vazia(self):
        result = parse_search_results({})
        self.assertEqual(result.groups, [])


# ══════════════════════════════════════════════════════════════════════════════
# 2. Testes de INTEGRAÇÃO — HTTP real
# ══════════════════════════════════════════════════════════════════════════════

# Marcadores conhecidos do contato 86797 (ELIZABETE RIBEIRO DA SILVA SANTOS)
_SEARCH_TERM    = "ELIZABETE RIBEIRO DA SILVA SANTOS"
_EXPECTED_NOME  = "ELIZABETE RIBEIRO DA SILVA SANTOS"
_EXPECTED_URL   = "/contatos/Pessoas/Details/86797"


def _make_service() -> SearchService:
    sm = make_session_manager()
    crawler = GlobalSearchCrawler(session_manager=sm)
    return SearchService(crawler=crawler)


class TestSearchIntegration(unittest.TestCase):
    """
    Integração: GlobalSearchCrawler + parse_search_results() com HTTP real.

    Busca pelo contato de referência (ELIZABETE) e verifica que:
      - O grupo "Contatos" contém o contato esperado.
      - O grupo "Processos" retorna ao menos um resultado.
    """

    @classmethod
    def setUpClass(cls):
        service = _make_service()
        cls.result = service.search(term=_SEARCH_TERM, contexts=["Processos", "Contatos"])

    def test_retorna_dois_grupos(self):
        self.assertEqual(len(self.result.groups), 2)

    def test_grupo_contatos_contem_referencia(self):
        contatos = next(
            (g for g in self.result.groups if g.context == "Contatos"), None
        )
        self.assertIsNotNone(contatos, "Grupo 'Contatos' ausente na resposta")
        urls = [item.url for item in contatos.items]
        self.assertIn(_EXPECTED_URL, urls)

    def test_grupo_processos_tem_resultados(self):
        processos = next(
            (g for g in self.result.groups if g.context == "Processos"), None
        )
        self.assertIsNotNone(processos, "Grupo 'Processos' ausente na resposta")
        self.assertGreater(processos.count, 0)

    def test_busca_so_contatos(self):
        """Busca restrita a Contatos deve retornar apenas um grupo."""
        service = _make_service()
        result = service.search(term=_SEARCH_TERM, contexts=["Contatos"])
        self.assertEqual(len(result.groups), 1)
        self.assertEqual(result.groups[0].context, "Contatos")

    def test_contexto_invalido_levanta_value_error(self):
        """Contexto desconhecido deve levantar ValueError antes de qualquer HTTP."""
        service = _make_service()
        with self.assertRaises(ValueError):
            service.search(term=_SEARCH_TERM, contexts=["Invalido"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

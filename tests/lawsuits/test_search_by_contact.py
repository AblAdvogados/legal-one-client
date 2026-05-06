"""
Teste de INTEGRAÇÃO para LawsuitsCrawler.search_by_contact().

Faz requisições HTTP REAIS ao site LegalOne.
Mocka APENAS os métodos do SessionManager que tocam o DynamoDB.
O Authenticator faz login real, obtém os cookies e os injeta na sessão.
As asserções verificam marcadores estáveis extraídos do HTML de referência
gravado em tests/results/search_by_contact_result.html.
"""

import unittest

from infrastructure.crawler.lawsuits import LawsuitsCrawler
from tests.helpers import make_session_manager, assert_not_login_page

# ── Contato a ser buscado ────────────────────────────────────────────────────
CONTACT_NAME = "JOSELI CARNEIRO DA SILVA"
CONTACT_ID   = "60444"

# ── Marcadores estáveis extraídos do HTML de referência ─────────────────────
EXPECTED_MARKERS = [
    # Módulo de processos carregado corretamente
    'NavigationContext="lawsuits"',
    # Filtro de contato ecoado pelo servidor na página de resultados
    '"Id":60444',
    f'"Value":"{CONTACT_NAME}"',
    # Escritório autenticado corretamente
    'AITH, BADARI E LUCHIN SOCIEDADE DE ADVOGADOS',
]


class TestSearchByContactIntegration(unittest.TestCase):
    """
    Teste de integração com HTTP real.
    Faz login verdadeiro, chama search_by_contact() e verifica os marcadores
    estáveis presentes no HTML de referência.
    """

    @classmethod
    def setUpClass(cls):
        """
        Roda uma única vez: faz login real e instancia o crawler.
        Todos os testes da classe reusam a mesma sessão autenticada.
        """
        sm = make_session_manager()
        cls.crawler = LawsuitsCrawler(session_manager=sm)

        cls.html = cls.crawler.search_by_contact(CONTACT_NAME, CONTACT_ID)

    def test_html_contem_marcadores_esperados(self):
        """
        Verifica todos os marcadores estáveis do HTML de referência em um
        único teste, usando subTest para identificar qual falhou.
        """
        for marker in EXPECTED_MARKERS:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.html)

    def test_nao_e_pagina_de_login(self):
        """O resultado NÃO deve ser a página de login do BrowserHawk."""
        assert_not_login_page(self, self.html)


if __name__ == "__main__":
    unittest.main(verbosity=2)

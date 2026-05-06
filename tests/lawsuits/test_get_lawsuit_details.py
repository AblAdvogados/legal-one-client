"""
Teste de INTEGRAÇÃO para LawsuitsCrawler.get_lawsuit_details().

Faz requisições HTTP REAIS ao site LegalOne.
Mocka APENAS os métodos do SessionManager que tocam o DynamoDB.
O Authenticator faz login real, obtém os cookies e os injeta na sessão.
As asserções verificam marcadores estáveis extraídos do HTML de referência
gravado em tests/results/detalhes_processo.html.
"""

import unittest

from infrastructure.crawler.lawsuits import LawsuitsCrawler
from tests.helpers import make_session_manager, assert_not_login_page

# ── Processo a ser buscado ───────────────────────────────────────────────────
# ID e número extraídos do HTML de referência (tests/results/detalhes_processo.html)
PROCESSO_ID     = "2"
PROCESSO_NUMERO = "5002160-11.2023.4.02.5109"

# ── Marcadores estáveis extraídos do HTML de referência ─────────────────────
EXPECTED_MARKERS = [
    
    # Expressão presente no título da página de detalhes do processo
    "Visualizando processo: Proc - 0000002 - Legal One",
    
    # Número do processo presente na página de detalhes
    PROCESSO_NUMERO,

    # Escritório autenticado corretamente
    'AITH, BADARI E LUCHIN SOCIEDADE DE ADVOGADOS',
]


class TestGetLawsuitDetailsIntegration(unittest.TestCase):
    """
    Teste de integração com HTTP real.
    Faz login verdadeiro, chama get_lawsuit_details() e verifica os marcadores
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

        cls.html = cls.crawler.get_lawsuit_details(PROCESSO_ID)

        # with open("tests/lawsuits/results/lawsuit_details.html", "w", encoding="utf-8") as f:
        #     f.write(cls.html)

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

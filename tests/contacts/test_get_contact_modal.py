"""
Teste de INTEGRAÇÃO para ContactsCrawler.get_contact_modal().

Faz requisições HTTP REAIS ao site LegalOne.
Mocka APENAS os métodos do SessionManager que tocam o DynamoDB.
O Authenticator faz login real, obtém os cookies e os injeta na sessão.
As asserções verificam marcadores estáveis extraídos do HTML de referência
gravado em tests/contacts/results/contact_modal.html.
"""

import unittest

from infrastructure.crawler.contacts import ContactsCrawler
from tests.helpers import make_session_manager, assert_not_login_page

# ── Contato a ser consultado ─────────────────────────────────────────────────
# ID extraído do HTML de referência (tests/contacts/results/contact_modal.html)
CONTATO_ID = "60444"

# ── Marcadores estáveis extraídos do HTML de referência ─────────────────────
EXPECTED_MARKERS = [
    # ID do contato presente no atributo do <form>
    f'id="{CONTATO_ID}"',

    # Nome do contato
    'JOSELI CARNEIRO DA SILVA',

    # CPF do contato
    '654.873.627-34',

    # Logradouro do endereço
    'RUA BELA VISTA',

    # Celular registrado
    '(24) 99267-1158',

    # Rota de submissão presente na modal
    'action="/contatos/Contatos/VisualizeContactCardView"',
]


class TestGetContactModalIntegration(unittest.TestCase):
    """
    Teste de integração com HTTP real.
    Faz login verdadeiro, chama get_contact_modal() e verifica os marcadores
    estáveis presentes no HTML de referência.
    """

    @classmethod
    def setUpClass(cls):
        """
        Roda uma única vez: faz login real e instancia o crawler.
        Todos os testes da classe reusam a mesma sessão autenticada.
        """
        sm = make_session_manager()
        cls.crawler = ContactsCrawler(session_manager=sm)

        cls.html = cls.crawler.get_contact_modal(CONTATO_ID)

        # Descomente para atualizar o HTML de referência:
        # with open("tests/contacts/results/contact_modal.html", "w", encoding="utf-8") as f:
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

# filepath: tests/contacts/test_get_contact.py
"""
Testes para a rota de consulta de contatos.

Dois grupos:

  TestParseContactModal   — testes UNITÁRIOS, offline, sem HTTP.
    Verifica que parse_contact_modal() extrai corretamente os campos do
    HTML de referência gravado em logs/customer_details_modal.html.

  TestParseContactDetails — testes UNITÁRIOS, offline, sem HTTP.
    Verifica que parse_contact_details() extrai corretamente os campos do
    HTML de referência gravado em logs/customer_main_details.html.

  TestGetContactSummaryIntegration  ─┐  testes de INTEGRAÇÃO, HTTP real.
  TestGetContactDetailsIntegration  ─┘
    Fazem uma única requisição real ao LegalOne e verificam que os
    dados retornados batem com os marcadores do HTML de referência.
"""

import unittest
from pathlib import Path

from parsers.contact_parser import parse_contact_modal, parse_contact_details
from domain.contact import ContactSummary, ContactDetails
from infrastructure.crawler.contacts import ContactsCrawler
from services.contact.service import ContactService
from tests.helpers import make_session_manager, assert_not_login_page

# ── Contato dos HTMLs de referência ──────────────────────────────────────────
# Extraído de logs/customer_details_modal.html (id do <form>)
CONTATO_ID_MODAL   = "60444"
# Extraído de logs/customer_main_details.html (link /Pessoas/Edit/{id})
CONTATO_ID_DETAILS = "86797"

# ── Caminhos para os HTMLs de referência ─────────────────────────────────────
_ROOT = Path(__file__).parents[2]
_MODAL_HTML_PATH   = _ROOT / "logs" / "customer_details_modal.html"
_DETAILS_HTML_PATH = _ROOT / "logs" / "customer_main_details.html"


# ══════════════════════════════════════════════════════════════════════════════
# 1. Testes UNITÁRIOS — parse da modal (summary=True)
# ══════════════════════════════════════════════════════════════════════════════

class TestParseContactModal(unittest.TestCase):
    """
    Testa parse_contact_modal() contra o HTML de referência offline.
    Não faz nenhuma requisição HTTP.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = _MODAL_HTML_PATH.read_text(encoding="utf-8")
        cls.result = parse_contact_modal(cls.html)

    def test_retorna_contact_summary(self):
        self.assertIsInstance(self.result, ContactSummary)

    def test_extrai_contact_id(self):
        self.assertEqual(self.result.contact_id, CONTATO_ID_MODAL)

    def test_extrai_nome(self):
        self.assertIn("JOSELI CARNEIRO DA SILVA", self.result.dados_pessoais.nome)

    def test_extrai_cpf(self):
        self.assertEqual(self.result.dados_pessoais.cpf, "654.873.627-34")

    def test_extrai_logradouro(self):
        self.assertIsNotNone(self.result.endereco)
        self.assertEqual(self.result.endereco.logradouro, "RUA BELA VISTA")

    def test_extrai_numero(self):
        self.assertIsNotNone(self.result.endereco)
        self.assertEqual(self.result.endereco.numero, "143")

    def test_extrai_bairro(self):
        self.assertIsNotNone(self.result.endereco)
        self.assertEqual(self.result.endereco.bairro, "PENEDO")

    def test_extrai_cep(self):
        self.assertIsNotNone(self.result.endereco)
        self.assertEqual(self.result.endereco.cep, "27580-000")

    def test_extrai_cidade(self):
        self.assertIsNotNone(self.result.endereco)
        self.assertEqual(self.result.endereco.cidade, "Itatiaia")

    def test_extrai_uf(self):
        self.assertIsNotNone(self.result.endereco)
        self.assertEqual(self.result.endereco.uf, "Rio de Janeiro")

    def test_extrai_celular(self):
        self.assertIsNotNone(self.result.telefone)
        self.assertEqual(self.result.telefone.celular, "(24) 99267-1158")

    def test_extrai_observacao(self):
        # Observação contém texto de acesso com caracteres especiais
        self.assertIsNotNone(self.result.dados_pessoais.observacao)
        self.assertIn("ACESSO MEU.INSS", self.result.dados_pessoais.observacao)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Testes UNITÁRIOS — parse dos detalhes completos (summary=False)
# ══════════════════════════════════════════════════════════════════════════════

class TestParseContactDetails(unittest.TestCase):
    """
    Testa parse_contact_details() contra o HTML de referência offline.
    Não faz nenhuma requisição HTTP.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = _DETAILS_HTML_PATH.read_text(encoding="utf-8")
        cls.result = parse_contact_details(cls.html)

    def test_retorna_contact_details(self):
        self.assertIsInstance(self.result, ContactDetails)

    def test_extrai_contact_id(self):
        self.assertEqual(self.result.contact_id, CONTATO_ID_DETAILS)

    def test_extrai_nome(self):
        self.assertIn("ELIZABETE RIBEIRO DA SILVA SANTOS", self.result.dados_pessoais.nome)

    def test_extrai_cpf(self):
        self.assertEqual(self.result.dados_pessoais.cpf, "587.275.234-20")

    def test_extrai_data_nascimento(self):
        self.assertEqual(self.result.dados_pessoais.data_nascimento, "13/08/1968")

    def test_extrai_campo_personalizado_tag(self):
        self.assertIsNotNone(self.result.custom_fields)
        self.assertEqual(self.result.custom_fields.tag, "ABRO35NA65SSVN")

    def test_campos_ausentes_sao_none(self):
        # Na fixture esses campos estão vazios no painel "Personalizados"
        self.assertIsNotNone(self.result.custom_fields)
        self.assertIsNone(self.result.custom_fields.link_drive)
        self.assertIsNone(self.result.custom_fields.cid)
        self.assertIsNone(self.result.custom_fields.classificacao_backoffice)


# ══════════════════════════════════════════════════════════════════════════════
# Utilitário de integração
# ══════════════════════════════════════════════════════════════════════════════

def _make_service() -> ContactService:
    """Instancia ContactService com sessão autenticada real."""
    sm = make_session_manager()
    crawler = ContactsCrawler(session_manager=sm)
    return ContactService(crawler=crawler)


class _GetContactIntegrationBase(unittest.TestCase):
    """
    Classe base para testes de integração de get_contact().

    Subclasses definem:
        CONTACT_ID : str   — ID do contato a consultar
        SUMMARY    : bool  — True para modal, False para página completa

    setUpClass() faz login real, chama get_contact() e guarda em cls.result
    e cls.html (HTML bruto) para asserções.
    """
    __test__ = False

    CONTACT_ID: str
    SUMMARY: bool

    @classmethod
    def setUpClass(cls):
        service = _make_service()
        if cls.SUMMARY:
            crawler = service._crawler
            cls.html = crawler.get_contact_modal(cls.CONTACT_ID)
            from parsers.contact_parser import parse_contact_modal as _parse
            cls.result = _parse(cls.html)
        else:
            crawler = service._crawler
            cls.html = crawler.get_contact_details(cls.CONTACT_ID)
            from parsers.contact_parser import parse_contact_details as _parse
            cls.result = _parse(cls.html)

    def test_nao_e_pagina_de_login(self):
        assert_not_login_page(self, self.html)

    def test_contact_id_correto(self):
        self.assertEqual(self.result.contact_id, self.CONTACT_ID)

    def test_nome_preenchido(self):
        self.assertTrue(self.result.dados_pessoais.nome.strip())

    def test_cpf_preenchido(self):
        self.assertTrue(self.result.dados_pessoais.cpf)


class TestGetContactSummaryIntegration(_GetContactIntegrationBase):
    """Integração: get_contact_modal() + parse_contact_modal() com HTTP real."""
    __test__ = True
    CONTACT_ID = CONTATO_ID_MODAL
    SUMMARY = True

    def test_marcadores_da_fixture(self):
        """Os dados devem bater com o HTML de referência gravado."""
        with self.subTest("nome"):
            self.assertIn("JOSELI CARNEIRO DA SILVA", self.result.dados_pessoais.nome)
        with self.subTest("cpf"):
            self.assertEqual(self.result.dados_pessoais.cpf, "654.873.627-34")
        with self.subTest("celular"):
            self.assertIsNotNone(self.result.telefone)
            self.assertEqual(self.result.telefone.celular, "(24) 99267-1158")


class TestGetContactDetailsIntegration(_GetContactIntegrationBase):
    """Integração: get_contact_details() + parse_contact_details() com HTTP real."""
    __test__ = True
    CONTACT_ID = CONTATO_ID_DETAILS
    SUMMARY = False

    def test_marcadores_da_fixture(self):
        """Os dados devem bater com o HTML de referência gravado."""
        with self.subTest("nome"):
            self.assertIn("ELIZABETE RIBEIRO DA SILVA SANTOS", self.result.dados_pessoais.nome)
        with self.subTest("cpf"):
            self.assertEqual(self.result.dados_pessoais.cpf, "587.275.234-20")
        with self.subTest("data_nascimento"):
            self.assertEqual(self.result.dados_pessoais.data_nascimento, "13/08/1968")
        with self.subTest("tag"):
            self.assertIsNotNone(self.result.custom_fields)
            self.assertEqual(self.result.custom_fields.tag, "ABRO35NA65SSVN")


if __name__ == "__main__":
    unittest.main(verbosity=2)

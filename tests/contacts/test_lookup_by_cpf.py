# filepath: tests/contacts/test_lookup_by_cpf.py
"""
Testes para ContactService.lookup_by_cpf() e GET /contacts/{cpf}.

Dois grupos:

  TestLookupByCpfUnit  — testes UNITÁRIOS, sem HTTP.
    Verifica o comportamento de lookup_by_cpf() usando mocks para
    SearchService e ContactService.get_contact(). Cobre:
      - Retorno de ContactSummary (summary=True) e ContactDetails (summary=False).
      - ContatoNaoEncontradoError quando a busca não retorna resultados.
      - Extração correta do contact_id a partir da URL do resultado.
      - Propagação de exceções do SearchService.

  TestLookupRouterUnit — testes UNITÁRIOS do endpoint GET /contacts/{cpf}.
    Usa TestClient com o serviço sobrescrito por mock.
    Cobre retorno 200, retorno 404 e query param summary.

  TestLookupByCpfIntegration — testes de INTEGRAÇÃO, HTTP real.
    Faz login verdadeiro, busca pelo contato de referência (JOSELI)
    via CPF e verifica que os dados retornados batem com os esperados.
"""

import unittest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from core.errors import ContatoNaoEncontradoError
from domain.contact import (
    Address,
    ContactDetails,
    ContactSummary,
    CustomFields,
    PersonalData,
    Phone,
)
from parsers.search_parser import GlobalSearchResult, SearchResultGroup, SearchResultItem
from services.contact.service import ContactService
from services.search_service import SearchService


# ── Fixtures ──────────────────────────────────────────────────────────────────

_CPF_REFERENCIA   = "654.873.627-34"    # JOSELI — contato 60444
_CONTACT_ID       = "60444"
_CONTACT_URL      = f"/contatos/Pessoas/Details/{_CONTACT_ID}"
_NOME_REFERENCIA  = "JOSELI CARNEIRO DA SILVA"


def _make_search_result_com_contato(
    contact_id: str = _CONTACT_ID,
    cpf: str = _CPF_REFERENCIA,
) -> GlobalSearchResult:
    """Fixture: resultado de busca com um item no grupo Contatos."""
    item = SearchResultItem(
        description=_NOME_REFERENCIA,
        extra_information=cpf,
        url=f"/contatos/Pessoas/Details/{contact_id}",
    )
    group = SearchResultGroup(
        context="Contatos",
        count=1,
        items=[item],
        complete_search_url="",
    )
    return GlobalSearchResult(groups=[group])


def _make_search_result_vazio() -> GlobalSearchResult:
    """Fixture: resultado de busca sem grupo Contatos."""
    return GlobalSearchResult(groups=[])


def _make_contact_summary(contact_id: str = _CONTACT_ID) -> ContactSummary:
    """Fixture mínima de ContactSummary."""
    return ContactSummary(
        contact_id=contact_id,
        dados_pessoais=PersonalData(cpf=_CPF_REFERENCIA, nome=_NOME_REFERENCIA),
        telefone=Phone(celular="(24) 99999-0000"),
        email=None,
        endereco=None,
    )


def _make_contact_details(contact_id: str = _CONTACT_ID) -> ContactDetails:
    """Fixture mínima de ContactDetails."""
    return ContactDetails(
        contact_id=contact_id,
        dados_pessoais=PersonalData(
            cpf=_CPF_REFERENCIA,
            nome=_NOME_REFERENCIA,
            data_nascimento="01/01/1980",
        ),
        telefone=Phone(celular="(24) 99999-0000"),
        email=None,
        endereco=Address(logradouro="RUA BELA VISTA", cidade="Volta Redonda", uf="RJ"),
        custom_fields=None,
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. Testes UNITÁRIOS — lookup_by_cpf() sem HTTP
# ══════════════════════════════════════════════════════════════════════════════

class TestLookupByCpfUnit(unittest.TestCase):
    """Testa ContactService.lookup_by_cpf() com SearchService e get_contact() mockados."""

    def _make_service(
        self,
        search_result: GlobalSearchResult,
        contact_return=None,
    ) -> ContactService:
        """Cria ContactService com dependências mockadas."""
        mock_crawler = MagicMock()
        mock_search  = MagicMock(spec=SearchService)
        mock_search.search.return_value = search_result

        service = ContactService(crawler=mock_crawler, search_service=mock_search)
        if contact_return is not None:
            service.get_contact = MagicMock(return_value=contact_return)
        return service

    # ── summary=True ──────────────────────────────────────────────────────────

    def test_retorna_contact_summary_quando_summary_true(self):
        expected = _make_contact_summary()
        service = self._make_service(
            search_result=_make_search_result_com_contato(),
            contact_return=expected,
        )
        result = service.lookup_by_cpf(cpf=_CPF_REFERENCIA, summary=True)
        self.assertIsInstance(result, ContactSummary)
        self.assertIs(result, expected)

    def test_get_contact_chamado_com_id_correto_summary_true(self):
        expected = _make_contact_summary()
        service = self._make_service(
            search_result=_make_search_result_com_contato(),
            contact_return=expected,
        )
        service.lookup_by_cpf(cpf=_CPF_REFERENCIA, summary=True)
        service.get_contact.assert_called_once_with(
            contact_id=_CONTACT_ID, summary=True
        )

    # ── summary=False ─────────────────────────────────────────────────────────

    def test_retorna_contact_details_quando_summary_false(self):
        expected = _make_contact_details()
        service = self._make_service(
            search_result=_make_search_result_com_contato(),
            contact_return=expected,
        )
        result = service.lookup_by_cpf(cpf=_CPF_REFERENCIA, summary=False)
        self.assertIsInstance(result, ContactDetails)
        self.assertIs(result, expected)

    def test_get_contact_chamado_com_id_correto_summary_false(self):
        expected = _make_contact_details()
        service = self._make_service(
            search_result=_make_search_result_com_contato(),
            contact_return=expected,
        )
        service.lookup_by_cpf(cpf=_CPF_REFERENCIA, summary=False)
        service.get_contact.assert_called_once_with(
            contact_id=_CONTACT_ID, summary=False
        )

    # ── Extração de ID da URL ─────────────────────────────────────────────────

    def test_extrai_id_de_url_com_trailing_slash(self):
        """URL com barra final deve ser tratada corretamente."""
        result_com_slash = GlobalSearchResult(groups=[
            SearchResultGroup(
                context="Contatos",
                count=1,
                items=[SearchResultItem(
                    description=_NOME_REFERENCIA,
                    extra_information=None,
                    url=f"/contatos/Pessoas/Details/{_CONTACT_ID}/",
                )],
                complete_search_url="",
            )
        ])
        expected = _make_contact_summary()
        service = self._make_service(
            search_result=result_com_slash,
            contact_return=expected,
        )
        service.lookup_by_cpf(cpf=_CPF_REFERENCIA, summary=True)
        service.get_contact.assert_called_once_with(
            contact_id=_CONTACT_ID, summary=True
        )

    def test_search_service_chamado_com_contexto_contatos(self):
        """SearchService.search deve ser chamado com contexts=["Contatos"]."""
        expected = _make_contact_summary()
        service = self._make_service(
            search_result=_make_search_result_com_contato(),
            contact_return=expected,
        )
        service.lookup_by_cpf(cpf=_CPF_REFERENCIA, summary=True)
        service._search_service.search.assert_called_once_with(
            term=_CPF_REFERENCIA, contexts=["Contatos"]
        )

    # ── Contato não encontrado ────────────────────────────────────────────────

    def test_levanta_contato_nao_encontrado_quando_grupos_vazios(self):
        service = self._make_service(search_result=_make_search_result_vazio())
        with self.assertRaises(ContatoNaoEncontradoError) as ctx:
            service.lookup_by_cpf(cpf=_CPF_REFERENCIA, summary=True)
        self.assertEqual(ctx.exception.cpf, _CPF_REFERENCIA)

    def test_levanta_contato_nao_encontrado_quando_grupo_contatos_sem_itens(self):
        """Grupo Contatos presente mas com lista vazia deve levantar erro."""
        result_sem_itens = GlobalSearchResult(groups=[
            SearchResultGroup(
                context="Contatos",
                count=0,
                items=[],
                complete_search_url="",
            )
        ])
        service = self._make_service(search_result=result_sem_itens)
        with self.assertRaises(ContatoNaoEncontradoError):
            service.lookup_by_cpf(cpf=_CPF_REFERENCIA, summary=True)

    def test_mensagem_erro_contem_cpf(self):
        service = self._make_service(search_result=_make_search_result_vazio())
        with self.assertRaises(ContatoNaoEncontradoError) as ctx:
            service.lookup_by_cpf(cpf=_CPF_REFERENCIA, summary=True)
        self.assertIn(_CPF_REFERENCIA, str(ctx.exception))

    def test_get_contact_nao_chamado_quando_nao_encontrado(self):
        """get_contact NÃO deve ser chamado se a busca não retornar resultados."""
        mock_crawler = MagicMock()
        mock_search  = MagicMock(spec=SearchService)
        mock_search.search.return_value = _make_search_result_vazio()

        service = ContactService(crawler=mock_crawler, search_service=mock_search)
        service.get_contact = MagicMock()

        with self.assertRaises(ContatoNaoEncontradoError):
            service.lookup_by_cpf(cpf=_CPF_REFERENCIA, summary=True)

        service.get_contact.assert_not_called()


# ══════════════════════════════════════════════════════════════════════════════
# 2. Testes UNITÁRIOS do endpoint POST /contacts/lookup
# ══════════════════════════════════════════════════════════════════════════════

def _make_test_client(service: ContactService) -> TestClient:
    """Cria TestClient com ContactService sobrescrito."""
    from app.main import app
    from app.routers.contacts import get_contact_service
    app.dependency_overrides[get_contact_service] = lambda: service
    client = TestClient(app, raise_server_exceptions=False)
    return client


class TestLookupRouterUnit(unittest.TestCase):
    """Testa o endpoint GET /contacts/{cpf} com mocks — sem HTTP real."""

    def tearDown(self):
        # Limpa os overrides após cada teste
        from app.main import app
        app.dependency_overrides.clear()

    def _make_service_mock(self, return_value=None, side_effect=None) -> ContactService:
        mock_crawler = MagicMock()
        mock_search  = MagicMock(spec=SearchService)
        service = ContactService(crawler=mock_crawler, search_service=mock_search)
        if side_effect is not None:
            service.lookup_by_cpf = MagicMock(side_effect=side_effect)
        else:
            service.lookup_by_cpf = MagicMock(return_value=return_value)
        return service

    def test_retorna_200_com_summary_response(self):
        summary = _make_contact_summary()
        service = self._make_service_mock(return_value=summary)
        client  = _make_test_client(service)

        resp = client.get(f"/contacts/{_CPF_REFERENCIA}?summary=true")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["contact_id"], _CONTACT_ID)
        self.assertEqual(data["dados_pessoais"]["cpf"], _CPF_REFERENCIA)
        self.assertEqual(data["dados_pessoais"]["nome"], _NOME_REFERENCIA)

    def test_retorna_200_com_details_response(self):
        details = _make_contact_details()
        service = self._make_service_mock(return_value=details)
        client  = _make_test_client(service)

        resp = client.get(f"/contacts/{_CPF_REFERENCIA}?summary=false")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["contact_id"], _CONTACT_ID)
        self.assertIn("data_nascimento", data["dados_pessoais"])

    def test_retorna_404_quando_nao_encontrado(self):
        service = self._make_service_mock(
            side_effect=ContatoNaoEncontradoError(cpf=_CPF_REFERENCIA)
        )
        client = _make_test_client(service)

        resp = client.get(f"/contacts/{_CPF_REFERENCIA}")
        self.assertEqual(resp.status_code, 404)
        self.assertIn(_CPF_REFERENCIA, resp.json()["detail"])

    def test_summary_default_true(self):
        """Quando summary não é enviado, deve usar True por padrão."""
        summary = _make_contact_summary()
        service = self._make_service_mock(return_value=summary)
        client  = _make_test_client(service)

        resp = client.get(f"/contacts/{_CPF_REFERENCIA}")  # sem ?summary
        self.assertEqual(resp.status_code, 200)
        service.lookup_by_cpf.assert_called_once_with(
            cpf=_CPF_REFERENCIA, summary=True
        )

    def test_lookup_by_cpf_chamado_com_summary_false(self):
        details = _make_contact_details()
        service = self._make_service_mock(return_value=details)
        client  = _make_test_client(service)

        client.get(f"/contacts/{_CPF_REFERENCIA}?summary=false")
        service.lookup_by_cpf.assert_called_once_with(
            cpf=_CPF_REFERENCIA, summary=False
        )


# ══════════════════════════════════════════════════════════════════════════════
# 3. Testes de INTEGRAÇÃO — HTTP real
# ══════════════════════════════════════════════════════════════════════════════

# Contato de referência (mesmos dados usados em test_get_contact_modal.py)
_CPF_INTEGRACAO  = "654.873.627-34"
_ID_INTEGRACAO   = "60444"
_NOME_INTEGRACAO = "JOSELI CARNEIRO DA SILVA"


def _make_real_service() -> ContactService:
    from infrastructure.crawler.contacts import ContactsCrawler
    from infrastructure.crawler.search import GlobalSearchCrawler
    from tests.helpers import make_session_manager

    sm = make_session_manager()
    contacts_crawler = ContactsCrawler(session_manager=sm)
    search_crawler   = GlobalSearchCrawler(session_manager=sm)
    search_svc       = SearchService(crawler=search_crawler)
    return ContactService(crawler=contacts_crawler, search_service=search_svc)


class _LookupIntegrationBase(unittest.TestCase):
    """
    Base para testes de integração de lookup_by_cpf.
    Subclasses definem `summary` e o tipo de retorno esperado.
    """

    __test__ = False   # não coletar esta classe diretamente

    summary: bool = True

    @classmethod
    def setUpClass(cls):
        service = _make_real_service()
        cls.result = service.lookup_by_cpf(
            cpf=_CPF_INTEGRACAO, summary=cls.summary
        )

    def test_contact_id_correto(self):
        self.assertEqual(self.result.contact_id, _ID_INTEGRACAO)

    def test_nome_correto(self):
        self.assertEqual(self.result.dados_pessoais.nome, _NOME_INTEGRACAO)

    def test_cpf_correto(self):
        self.assertEqual(self.result.dados_pessoais.cpf, _CPF_INTEGRACAO)


class TestLookupByCpfSummaryIntegration(_LookupIntegrationBase):
    """Integração: lookup_by_cpf com summary=True → ContactSummary."""

    __test__ = True
    summary  = True

    def test_retorna_contact_summary(self):
        self.assertIsInstance(self.result, ContactSummary)


class TestLookupByCpfDetailsIntegration(_LookupIntegrationBase):
    """Integração: lookup_by_cpf com summary=False → ContactDetails."""

    __test__ = True
    summary  = False

    def test_retorna_contact_details(self):
        self.assertIsInstance(self.result, ContactDetails)

    def test_data_nascimento_presente(self):
        """ContactDetails deve conter data_nascimento."""
        self.assertIsNotNone(self.result.dados_pessoais.data_nascimento)


class TestLookupNaoEncontradoIntegration(unittest.TestCase):
    """Integração: CPF inexistente deve levantar ContatoNaoEncontradoError."""

    __test__ = True

    def test_cpf_inexistente_levanta_erro(self):
        service = _make_real_service()
        cpf_fake = "000.000.000-00"
        with self.assertRaises(ContatoNaoEncontradoError) as ctx:
            service.lookup_by_cpf(cpf=cpf_fake, summary=True)
        self.assertEqual(ctx.exception.cpf, cpf_fake)


if __name__ == "__main__":
    unittest.main(verbosity=2)

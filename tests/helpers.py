# filepath: tests/helpers.py
"""
Utilitários compartilhados entre os testes de integração.
"""

from core.config import settings
from infrastructure.crawler.session_manager import SessionManager


class SessionManagerMock(SessionManager):
    """
    SessionManager com DynamoDB completamente neutralizado.
    get_valid_cookies() e refresh() fazem login HTTP real via Authenticator,
    sem tocar em nenhuma tabela do DynamoDB.
    """
    def get_valid_cookies(self) -> dict:
        return self._do_login()

    def refresh(self) -> dict:
        return self._do_login()


def make_session_manager() -> SessionManagerMock:
    """
    Instancia SessionManagerMock com credenciais lidas de .env /
    variáveis de ambiente.
    """
    return SessionManagerMock(
        username=settings.legalone_username,
        password=settings.legalone_password,
        table_name="session-store-fake",  # nunca será acessada de fato
        region=settings.aws_region,
    )


def assert_not_login_page(test_case, html: str):
    """Asserção reutilizável: garante que o HTML não é a página de login BrowserHawk."""
    test_case.assertNotIn("bhcp=1", html)
    test_case.assertNotIn("signon.thomsonreuters.com", html)

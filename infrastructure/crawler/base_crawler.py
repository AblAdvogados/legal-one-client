# filepath: infrastructure/crawler/base_crawler.py
import logging

import requests

from core.config import settings
from infrastructure.crawler.constants import LegalOneConstants
from core.errors import AuthenticationError, CrawlerError, SessionExpiredError, TransientServerError
from infrastructure.crawler.session_manager import SessionManager

logger = logging.getLogger(__name__)

# Marcadores presentes na página de login do BrowserHawk.
# O site retorna status 200 mesmo quando a sessão expirou;
# esses strings identificam que o conteúdo é a tela de login, não a resposta esperada.
_BROWSERHAWK_MARKERS = [
    'bhcp=1',
    'BrowserHawk',
    'signon.thomsonreuters.com',
]


class BaseCrawler:
    """
    Classe base para todos os crawlers do site LegalOne.

    Responsabilidades:
      - Manter os headers HTTP comuns a todas as rotas.
      - Validar respostas HTTP detectando sessão expirada ou erros HTTP.
      - Centralizar o mecanismo de retry com reautenticação:
          se SessionExpiredError → chama session_manager.refresh() → tenta 1x mais.
          se CrawlerError (4xx/5xx) → propaga sem retry.
          se o segundo retry também falhar → propaga AuthenticationError.

    Uso:
        class ContactsCrawler(BaseCrawler):
            def get_details(self, contact_id):
                return self._request('GET', f'{self.base_url}/contatos/Pessoas/Details/{contact_id}')
    """

    def __init__(self, session_manager: SessionManager, cookies: dict = None):
        """
        Args:
            session_manager: instância de SessionManager — fornece cookies válidos
                             e expõe refresh() para forçar novo login.
        """
        self._session_manager = session_manager
        self.base_url = settings.legalone_base_url

        self._session = requests.Session()

        if not cookies:
            cookies = session_manager.get_valid_cookies()
        self._session.cookies.update(cookies)

        _c = LegalOneConstants
        # ── Headers compartilhados por todos os perfis ───────────────────────
        _common = {
            'Accept-Language':    'pt-BR,pt;q=0.9',
            'Cache-Control':      'no-cache',
            'Connection':         'keep-alive',
            'Pragma':             'no-cache',
            'Sec-Fetch-Site':     'same-origin',
            'User-Agent':         _c.user_agent,
            'sec-ch-ua':          _c.sec_ch_ua,
            'sec-ch-ua-mobile':   '?0',
            'sec-ch-ua-platform': _c.sec_ch_ua_platform,
        }

        # ── Perfil 1 — navigate ──────────────────────────────────────────────
        # Usado em: GET Details, POST busca de processos/contatos, GET detalhes do processo.
        # O browser envia uma navegação completa de página; requests segue redirects.
        self.headers = {
            **_common,
            'Accept': (
                'text/html,application/xhtml+xml,application/xml;'
                'q=0.9,image/avif,image/webp,image/apng,*/*;'
                'q=0.8,application/signed-exchange;v=b3;q=0.7'
            ),
            'Origin':                    self.base_url,
            'Sec-Fetch-Dest':            'document',
            'Sec-Fetch-Mode':            'navigate',
            'Sec-Fetch-User':            '?1',
            'Upgrade-Insecure-Requests': '1',
        }

        # ── Perfil 2 — ajax (seções parciais / XHR) ──────────────────────────
        # Usado em: GET detailsenderecos, detailsfones, detailsenvolvimentos
        #           (com renderOnlySection=True & ajaxnavigation=true).
        # O browser envia uma requisição XHR para carregar apenas um fragmento HTML.
        self.headers_ajax = {
            **_common,
            'Accept':            'text/html, */*; q=0.01',
            'Sec-Fetch-Dest':    'empty',
            'Sec-Fetch-Mode':    'cors',
            'X-Requested-With':  'XMLHttpRequest',
        }

        # ── Perfil 3 — modal (XHR para modais / JSON leve) ───────────────────
        # Usado em: GET ModalPersonInvolveds e endpoints similares que retornam
        # fragmentos HTML ou JSON via chamada assíncrona de modal.
        self.headers_modal = {
            **_common,
            'Accept':            '*/*',
            'Content-Type':      'application/x-www-form-urlencoded; charset=UTF-8',
            'Sec-Fetch-Dest':    'empty',
            'Sec-Fetch-Mode':    'cors',
            'X-Requested-With':  'XMLHttpRequest',
        }

    # ──────────────────────────────────────────────────────────
    # Ponto central de todas as requisições HTTP dos crawlers
    # ──────────────────────────────────────────────────────────
    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Executa uma requisição HTTP com retry automático em caso de sessão expirada.

        Args:
            method: 'GET', 'POST', etc.
            url: URL completa do endpoint.
            **kwargs: argumentos extras repassados ao requests (data, params, headers, etc.).
                      Se 'headers' não for fornecido, usa self.headers (perfil navigate).
                      Para rotas AJAX passe headers=self.headers_ajax;
                      para modais passe headers=self.headers_modal.

        Returns:
            requests.Response com a resposta bem-sucedida.

        Raises:
            AuthenticationError: se o retry após reautenticação também falhar.
            CrawlerError: se a resposta retornar status 4xx/5xx.
        """
        kwargs.setdefault('headers', self.headers)

        response = self._session.request(method, url, **kwargs)

        try:
            self._validate_response(response)
            return response
        except SessionExpiredError:
            return self._retry_after_reauth(method, url, **kwargs)
        except TransientServerError:
            import time
            time.sleep(2)  # espera fixa antes de tentar o retry para erros transitórios
            return self._retry_transient(method, url, **kwargs)

    def _retry_after_reauth(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Força novo login via session_manager.refresh() e tenta a requisição por mais quatro vezes.
        Se falhar por mais de quatro vezes, levanta AuthenticationError.
        """
        for n_try in range(1, 4):
            logger.info("_retry_after_reauth (tentativa: %d): sessão expirada detectada — reautenticando antes de repetir %s %s", n_try, method, url)
            
            new_cookies = self._session_manager.refresh()
            self._session.cookies.clear()
            self._session.cookies.update(new_cookies)
            response = self._session.request(method, url, **kwargs)
            try:
                self._validate_response(response)
                logger.info("_retry_after_reauth (tentativa: %d): bem-sucedido — %s %s", n_try, method, url)
                return response
            except SessionExpiredError:
                espera = n_try - 0.5
                logger.error("_retry_after_reauth (tentativa: %d): sessão ainda expirada após reautenticação — %s %s -  aguardando %s segundos antes de tentar novamente.", n_try, method, url, str(espera))
                import time
                time.sleep(espera)  # espera incremental: 0.5s, 1.5s, 2.5s

        raise AuthenticationError(
            "Sessão expirada mesmo após 4 reautenticações. "
            "Verifique as credenciais ou se a conta está bloqueada."
        )

    def _retry_transient(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Repete a requisição até 2 vezes com espera incremental para erros
        transitórios do servidor (404 + <title>Erro</title>).
        Não força novo login — os cookies permanecem os mesmos.
        Se todas as tentativas falharem, propaga CrawlerError.
        """
        import time as _time
        for n_try in range(1, 3):
            espera = n_try * 1.0
            logger.warning(
                "_retry_transient (tentativa %d/2): erro transitório em %s %s — aguardando %.1fs",
                n_try, method, url, espera,
            )
            _time.sleep(espera)
            response = self._session.request(method, url, **kwargs)
            try:
                self._validate_response(response)
                logger.info("_retry_transient (tentativa %d/2): sucesso — %s %s", n_try, method, url)
                return response
            except TransientServerError:
                continue

        logger.error(
            "_retry_transient: todas as tentativas falharam para %s %s",
            method, url,
        )
        raise CrawlerError(
            "Erro transitório persistente no servidor LegalOne após 2 tentativas.",
            status_code=404,
            url=url,
        )

    # ──────────────────────────────────────────────────────────
    # Valida a resposta HTTP lançando as exceções adequadas
    # ──────────────────────────────────────────────────────────
    def _validate_response(self, response: requests.Response) -> None:
        """
        Analisa a resposta e levanta a exceção correta quando necessário.

        - SessionExpiredError: sessão expirada detectada por dois padrões:
            1. Status 200 + body contendo marcadores BrowserHawk (página de login).
            2. Status 403 + body contendo "You do not have permission to view this
               directory or page" (comportamento de certos endpoints do LegalOne).
          → ambos disparam retry com reautenticação no _request().

        - CrawlerError: a resposta retornou status HTTP de erro (4xx/5xx) sem
          indicativo de sessão expirada → propagada diretamente, sem retry.

        Raises:
            SessionExpiredError
            CrawlerError
        """
        if any(marker in response.text for marker in _BROWSERHAWK_MARKERS):
            logger.warning(
                "_validate_response: BrowserHawk detectado em %s %s (status=%d) — sessão expirada",
                response.request.method if response.request else "?",
                response.url,
                response.status_code,
            )
            raise SessionExpiredError(
                "Sessão expirada: o site retornou a página de login (BrowserHawk)."
            )

        if response.status_code == 403 and "You do not have permission to view this directory or page" in response.text:
            # O LegalOne retorna 403 + mensagem de permissão quando os cookies
            # estão expirados em certos endpoints (ex: LookupLawSuit).
            # Distinguimos do 403 "legítimo" (recurso realmente proibido) pelo
            # conteúdo do body para não mascarar erros reais de autorização.
            logger.warning(
                "_validate_response: HTTP 403 com marcador de sessão expirada em %s — acionando retry",
                response.url,
            )
            raise SessionExpiredError(
                "Sessão expirada: o site retornou 403 com mensagem de permissão negada."
            )
        
        # O LegalOne retorna uma página de erro genérica com status 404 e título "Erro"
        # quando ocorre uma falha transitória do lado do servidor (não "recurso inexistente").
        # Disparamos TransientServerError para acionar retry sem forçar novo login.
        if response.status_code == 404 and '<title>Erro</title>' in response.text:
            logger.warning(
                "_validate_response: HTTP 404 com <title>Erro</title> em %s — erro transitório, acionando retry",
                response.url,
            )
            raise TransientServerError(
                "Erro transitório do servidor LegalOne (404 + página de erro genérica)."
            )

        # 502 Bad Gateway indica falha de infraestrutura do servidor (proxy/balanceador),
        # não erro de lógica. Tratamos como TransientServerError para acionar retry
        # sem reenviar o POST (evitar duplicata de tarefa).
        if response.status_code == 502:
            logger.warning(
                "_validate_response: HTTP 502 em %s — erro transitório de infraestrutura, acionando retry",
                response.url,
            )
            raise TransientServerError(
                "Erro transitório do servidor LegalOne (502 Bad Gateway)."
            )

        if response.status_code != 200:
            # Dica: prefira sempre usar %s/%d com argumentos separados em vez de f-string (f"HTTP {code}"),
            # porque o logging adia a interpolação — se o nível ERROR estiver desabilitado, a string 
            # nunca é montada e não há custo de CPU.
            logger.error(
                "_validate_response: HTTP %d em %s — body: %s",
                response.status_code,
                response.url,
                response.text[:200],
            )
            raise CrawlerError(
                f"Erro HTTP ao acessar o site LegalOne.",
                status_code=response.status_code,
                url=response.url,
                response_html=response.text[:200],
            )

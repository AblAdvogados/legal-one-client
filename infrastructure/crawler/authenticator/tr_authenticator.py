# =============================================================================
# new_authenticator.py
# =============================================================================
#
# Autenticador do LegalOne via Auth0 (OIDC / Authorization Code Flow).
#
# HISTÓRICO DE MUDANÇAS
# ---------------------
# O fluxo original usava OnePass — um sistema SSO proprietário da Thomson Reuters
# onde o próprio signon.thomsonreuters.com validava e-mail + senha diretamente
# (endpoints /v2/migrate/start, /v2/migrate/oidc, etc.) e emitia o JWT.
#
# Em 2026 a TR migrou as contas para o Auth0 (auth.thomsonreuters.com).
# O fluxo legado parava com "Erro geral" porque o endpoint /v2/migrate/start
# apagava ativamente o cookie COSISOSession (Set-Cookie: expires=1970) para
# contas já migradas. O diagnóstico mostrou que:
#
#   1. O servidor exige o cookie CIAMMigrationUserMigrated=True no domínio
#      signon.thomsonreuters.com ANTES de iniciar o fluxo OIDC.
#   2. Com esse cookie presente, o próprio passo de BrowserHawk (/v2?bhcp=1)
#      já redireciona direto para auth.thomsonreuters.com/u/login/identifier.
#   3. Após a senha, o Auth0 devolve um Authorization Code para o signon via
#      redirect (OAuth2 Authorization Code Flow). O signon precisa de mais um
#      GET com BrowserHawk + code para trocar o code por JWT.
#
# CONCEITOS NECESSÁRIOS
# ---------------------
#
# BrowserHawk
#   Middleware do signon que detecta o browser do cliente. O primeiro GET (/v2)
#   entrega um HTML + script JS que coleta dados do browser (resolução, timezone,
#   idioma…). O cliente deve reenviar esses dados como query-params (?bhcp=1&bh*=…)
#   para que o servidor prossiga. O crawler simula essa etapa injetando os valores
#   manualmente nos params, sem executar o JS.
#
# COSISOSession
#   Cookie de sessão emitido pelo signon no primeiro GET /v2. É obrigatório em
#   todas as requisições subsequentes ao signon. Sem ele, o servidor rejeita
#   qualquer tentativa de login.
#
# CIAMMigrationUserMigrated=True
#   Cookie que o servidor define para contas já migradas do OnePass para o Auth0.
#   Sua presença instrui o signon a iniciar o fluxo OIDC em vez do OnePass legado.
#   Como o crawler nunca fez login "de verdade" para receber esse cookie, ele é
#   injetado manualmente na sessão — contas legadas (sem migração) não são
#   suportadas nesta versão.
#
# OAuth2 Authorization Code Flow (OIDC)
#   1. O signon redireciona o browser para auth.thomsonreuters.com/authorize?…
#   2. O Auth0 exibe as telas de e-mail e senha.
#   3. Após autenticação bem-sucedida, o Auth0 redireciona de volta para o signon
#      com ?code=…&state=… (Authorization Code).
#   4. O signon usa esse code para trocar com o Auth0 por tokens (access_token,
#      id_token) — essa troca acontece server-side, invisível ao crawler.
#   5. O signon emite o JWT proprietário do LegalOne e redireciona para
#      firm.legalone.com.br/?jwt=…&nonce=…
#
# state (CSRF token)
#   Parâmetro opaco gerado pelo signon no início do fluxo OIDC. Deve ser
#   ecoado em cada etapa para que o Auth0 e o signon validem que a requisição
#   faz parte da mesma sessão (proteção contra CSRF).
#
# JWT do LegalOne
#   Token proprietário emitido pelo firm.legalone.com.br após o login.
#   Não é o id_token do Auth0 — é um token próprio da plataforma, usado
#   em todas as chamadas subsequentes à API do LegalOne.
#
# subscriptionKey (PubNub)
#   Chave de assinatura do canal de eventos real-time (PubNub) embutida no
#   bundle JS principal (main.*.js) do LegalOne. Extraída via regex.
#
# =============================================================================

import re
import sys
import logging
sys.path.append('.')
import requests
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

from infrastructure.crawler.constants import LegalOneConstants
from core.errors import AuthenticationError

BASE_URL  = 'https://signon.thomsonreuters.com'
RETURN_TO = 'https://login.novajus.com.br/OnePass/LoginOnePass/'

_C = LegalOneConstants
logger = logging.getLogger(__name__)


class TRAuthenticator:
    """
    Authenticador do LegalOne via Auth0 (OIDC Authorization Code Flow).

    Uso:
        auth = Authenticator(username, password)
        jwt_token, subscription_key, cookies = auth.authenticate()

    Fluxo interno (ver docstrings de cada método para detalhes):

      Passo 1 — _trigger_browserhawk()
        GET signon/v2  →  obtém COSISOSession (cookie obrigatório para os passos seguintes).

      Passo 2 — _simulate_browserhawk()
        GET signon/v2?bhcp=1&bh*=…  →  simula a detecção do browser.
        Com CIAMMigrationUserMigrated=True na sessão, o signon redireciona direto
        para auth.thomsonreuters.com/u/login/identifier?state=…  (início do OIDC).

      Passo 3 — _submit_email()
        POST auth/u/login/identifier  →  envia o e-mail; Auth0 retorna a tela de senha.

      Passo 4 — _submit_password()
        POST auth/u/login/password  →  envia a senha; Auth0 redireciona para
        signon/?code=…&state=…  (Authorization Code de volta ao signon).

      Passo 5 — _complete_oidc_callback()
        GET signon/?code=…&bhcp=1&bh*=…  →  signon troca o code por JWT internamente
        e redireciona para firm.legalone.com.br/?jwt=…&nonce=…

      Passo 6 — _extract_jwt_from_redirect()
        Extrai jwt, nonce, redirectTo e js_url da URL/HTML da página final.

      Passo 7 — _get_subscription_key()
        GET firm.legalone.com.br/main.*.js  →  extrai subscribeKey via regex.
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.session = self._new_session()
        self._headers_base = {
            'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'no-cache',
            'pragma': 'no-cache',
            'priority': 'u=0, i',
            'sec-ch-ua': _C.sec_ch_ua,
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': _C.sec_ch_ua_platform,
            'sec-fetch-dest': 'document',
            'sec-fetch-mode': 'navigate',
            'sec-fetch-site': 'none',
            'sec-fetch-user': '?1',
            'upgrade-insecure-requests': '1',
            'user-agent': _C.user_agent,
        }

    def _new_session(self):
        """
        Cria a sessão HTTP e pré-popula os cookies necessários.

        Por que injetar cookies manualmente?
        -------------------------------------
        Em um browser real, os cookies são acumulados ao longo de logins anteriores.
        O crawler parte do zero a cada execução, então precisamos simular o estado
        que um usuário já migrado teria:

        - CIAMMigrationUserMigrated=True (signon.thomsonreuters.com)
            Indica ao signon que a conta usa Auth0 em vez do OnePass legado.
            Sem ele, /v2 redireciona para o fluxo OnePass, que está desativado
            para contas migradas — resultado: "Erro geral".

        - Cookies de preferência do LegalOne (login.novajus.com.br)
            Evitam modais/popups de boas-vindas e configuram o método de login
            (cookie_login_method=2 = login por e-mail/senha, não SSO externo).
        """
        session = requests.Session()

        for name, value in [
            ('CIAMMigrationUserMigrated', 'True'),
        ]:
            session.cookies.set(name, value, domain='signon.thomsonreuters.com', path='/')

        for name, value in [
            ('cookie_login_method',    '2'),
            ('PingIdIdentifier',       'UserInformationSavedInDbIdentifier=False'),
            ('lembrar-usuario',        ''),
            ('cookieAvisoPendencias',  'ShowAlert=false'),
            ('ContractResponse',       ''),
        ]:
            session.cookies.set(name, value, domain='login.novajus.com.br', path='/')

        logger.debug("Sessão iniciada. Cookies: %s", list(session.cookies.keys()))
        return session

    # ──────────────────────────────────────────────────
    # PASSO 1: Inicia sessão e obtém COSISOSession
    # ──────────────────────────────────────────────────
    def _trigger_browserhawk(self) -> None:
        """
        GET /v2 sem parâmetros de browser (bhcp ausente).

        Por quê este passo existe?
        --------------------------
        O signon.thomsonreuters.com usa o middleware BrowserHawk para identificar
        o cliente. O fluxo tem duas etapas:

          1. GET /v2 sem bhcp  →  servidor emite COSISOSession e devolve um HTML
             com um script JS que coleta dados do browser (resolução, timezone…).
          2. GET /v2?bhcp=1&bh*=… →  cliente reenvia os dados coletados; servidor
             valida e prossegue para o fluxo de autenticação.

        Este método executa apenas a etapa 1. O objetivo é obter o cookie
        COSISOSession, que o servidor exige em todas as requisições subsequentes.
        Sem ele, qualquer tentativa de avançar no fluxo resulta em erro 400/403.

        O HTML retornado não é usado — apenas os cookies são aproveitados.
        """
        self.session.get(
            f'{BASE_URL}/v2',
            params={'productid': 'L1NJ', 'returnto': RETURN_TO},
            headers=self._headers_base,
        )
        logger.debug("Passo 1 concluído. Cookies: %s", list(self.session.cookies.keys()))

    # ──────────────────────────────────────────────────
    # PASSO 2: Simula detecção do browser (BrowserHawk)
    # ──────────────────────────────────────────────────
    def _simulate_browserhawk(self) -> tuple[str, str]:
        """
        GET /v2?bhcp=1&bh*=… — simula o envio dos dados de browser coletados pelo JS.

        Por que simular em vez de executar o JS?
        ----------------------------------------
        Em um browser real, o script BrowserHawk.js roda no cliente e coleta dados
        como resolução de tela, fuso horário e idioma. O crawler não tem browser,
        então injeta valores fixos plausíveis (resolução 1920×1080, UTC-3, pt-br).
        O servidor não valida a consistência dos valores — apenas exige que os
        parâmetros ?bh*=… estejam presentes.

        Por que este passo já chega em auth.thomsonreuters.com?
        -------------------------------------------------------
        Com o cookie CIAMMigrationUserMigrated=True presente na sessão, o signon
        detecta que a conta usa Auth0 e inicia o fluxo OIDC automaticamente:

          signon/v2?bhcp=1  →  302  →  signon/v2/migrate/oidc
                             →  302  →  auth.thomsonreuters.com/authorize?…
                             →  302  →  auth.thomsonreuters.com/u/login/identifier?state=…

        Retorna (html_final, url_final). A url_final deve conter '/u/login/identifier'.
        """
        params = {
            'productId': 'L1NJ',
            'returnto':  RETURN_TO,
            'bhcp': '1',
            'bhav': '',
            'bhsh': '1080',
            'bhsw': '1920',
            'bhiw': '1920',
            'bhih': '1080',
            'bhtz': '-3',
            'bhlu': 'pt-br',
            'bhsp': '0',
            'bhqs': '1',
        }
        headers = {
            **self._headers_base,
            'sec-fetch-site': 'same-origin',
            'referer': f'{BASE_URL}/v2?productId=L1NJ&returnto={RETURN_TO}&bhcp=1',
        }
        response = self.session.get(f'{BASE_URL}/v2', params=params, headers=headers, allow_redirects=True)
        response.raise_for_status()
        logger.debug("Passo 2 concluído. URL final: %s", response.url)
        return response.text, response.url

    # ──────────────────────────────────────────────────
    # PASSO 3: Submete e-mail no Auth0
    # ──────────────────────────────────────────────────
    def _submit_email(self, email_entry_url: str) -> tuple[str, str]:
        """
        POST para auth.thomsonreuters.com/u/login/identifier com o e-mail.
        O `state` é extraído da URL da página de entrada de e-mail.

        Retorna (html_da_pagina_de_senha, url_da_pagina_de_senha)
        """
        parsed = urlparse(email_entry_url)
        state = parse_qs(parsed.query).get('state', [None])[0]
        if not state:
            raise AuthenticationError("Parâmetro 'state' não encontrado na URL da página de e-mail.")

        auth_base = f'{parsed.scheme}://{parsed.netloc}'  # https://auth.thomsonreuters.com

        headers = {
            **self._headers_base,
            'content-type': 'application/x-www-form-urlencoded',
            'origin': auth_base,
            'referer': email_entry_url,
            'sec-fetch-site': 'same-origin',
        }

        data = {
            'state': state,
            'username': self.username,
            'js-available': 'true',
            'webauthn-available': 'true',
            'is-brave': 'false',
            'webauthn-platform-available': 'false',
            'action': 'default',
        }

        response = self.session.post(
            f'{auth_base}/u/login/identifier',
            headers=headers,
            data=data,
            allow_redirects=True,
        )
        response.raise_for_status()
        return response.text, response.url

    # ──────────────────────────────────────────────────
    # PASSO 4: Submete senha no Auth0
    # ──────────────────────────────────────────────────
    def _submit_password(self, password_page_url: str) -> requests.Response:
        """
        POST para auth.thomsonreuters.com/u/login/password com a senha.
        O `state` é extraído da URL da página de senha.

        Retorna a Response final (já com redirects seguidos até o JWT)
        """
        parsed = urlparse(password_page_url)
        state = parse_qs(parsed.query).get('state', [None])[0]
        if not state:
            raise AuthenticationError("Parâmetro 'state' não encontrado na URL da página de senha.")

        auth_base = f'{parsed.scheme}://{parsed.netloc}'

        headers = {
            **self._headers_base,
            'content-type': 'application/x-www-form-urlencoded',
            'origin': auth_base,
            'referer': password_page_url,
            'sec-fetch-site': 'same-origin',
        }

        data = {
            'state': state,
            'username': self.username,
            'password': self.password,
            'action': 'default',
        }

        response = self.session.post(
            f'{auth_base}/u/login/password',
            headers=headers,
            data=data,
            allow_redirects=True,
        )
        response.raise_for_status()
        return response

    # ──────────────────────────────────────────────────
    # PASSO 5: Completa o callback OIDC no signon.thomsonreuters.com
    # ──────────────────────────────────────────────────
    def _complete_oidc_callback(self, callback_response: requests.Response) -> requests.Response:
        """
        Troca o Authorization Code por JWT completando o callback OIDC no signon.

        Por que este passo é necessário?
        --------------------------------
        No OAuth2 Authorization Code Flow, após o usuário autenticar no Auth0,
        o Auth0 redireciona o browser de volta para a URL de callback do signon:

            signon.thomsonreuters.com/?code=ABC123&state=XYZ

        Nesse ponto, o signon precisaria fazer uma requisição server-to-server para
        o Auth0 trocando o code por tokens. Porém o signon usa BrowserHawk: antes
        de processar o code, exige que o cliente (browser) reenvie os parâmetros
        ?bhcp=1&bh*=… (etapa 2 do BrowserHawk), desta vez também passando code e
        state de volta.

        Sem este segundo round de BrowserHawk, o signon ignora o code e não emite
        o JWT — a sessão fica presa na tela de BrowserHawk.

        Fluxo deste método:
            GET signon/?code=…&state=…&bhcp=1&bh*=…
              →  302  →  firm.legalone.com.br/authentication/auth/?jwt=…&nonce=…

        Retorna a Response final com jwt= na URL.
        """
        parsed = urlparse(callback_response.url)
        qs = parse_qs(parsed.query)

        code         = qs.get('code',        [None])[0]
        state        = qs.get('state',       [None])[0]
        session_type = qs.get('sessionType', ['1'])[0]
        productid    = qs.get('productid',   ['L1NJ'])[0]
        returnto     = qs.get('returnto',    [RETURN_TO])[0]

        if not code:
            raise AuthenticationError(
                f"'code' não encontrado na URL de callback OIDC: {callback_response.url}"
            )

        # Parâmetros BrowserHawk + os params originais do callback
        params = {
            'sessionType': session_type,
            'productid':   productid,
            'returnto':    returnto,
            'code':        code,
            'state':       state,
            'bhcp':        '1',
            'bhav':        '',
            'bhsh':        '1080',
            'bhsw':        '1920',
            'bhiw':        '1920',
            'bhih':        '1080',
            'bhtz':        '-3',
            'bhlu':        'pt-br',
            'bhsp':        '0',
            'bhqs':        '1',
        }

        headers = {
            **self._headers_base,
            'referer':          'https://auth.thomsonreuters.com/',
            'sec-fetch-site':   'cross-site',
        }

        response = self.session.get(
            f'{BASE_URL}/',
            params=params,
            headers=headers,
            allow_redirects=True,
        )
        response.raise_for_status()
        logger.debug("Passo 5 concluído. URL: %s", response.url)
        return response

    # ──────────────────────────────────────────────────
    # PASSO 6: Extrai JWT e nonce da URL de redirect
    # ──────────────────────────────────────────────────
    def _extract_jwt_from_redirect(self, response: requests.Response) -> tuple[str, str, str, str]:
        """
        Extrai jwt, nonce, redirectTo e js_url da página final do LegalOne.

        Após o signon emitir o JWT, o browser é redirecionado para:
            firm.legalone.com.br/authentication/auth/?jwt=…&nonce=…&redirectTo=…

        O JWT é um token proprietário do LegalOne (não é o id_token do Auth0).
        O nonce é usado pelo frontend para validar que o JWT não foi reutilizado.
        O redirectTo indica para qual módulo do sistema o usuário deve ser enviado.

        Além dos query-params da URL, também extrai a URL do bundle JS principal
        (main.*.js) do HTML da página, necessário para o passo 7.

        Retorna (jwt_token, nonce, redirect_to, js_url).
        """
        parsed = urlparse(response.url)
        params = parse_qs(parsed.query)

        jwt_token   = params.get('jwt', [None])[0]
        nonce       = params.get('nonce', [None])[0]
        redirect_to = params.get('redirectTo', ['home'])[0]

        if not jwt_token:
            raise AuthenticationError(
                "JWT não encontrado na URL de redirect. Verifique as credenciais."
            )

        js_url_match = re.search(r'<script src="(main\..*?\.js)" type="module"></script>', response.text)
        if js_url_match:
            js_url = js_url_match.group(1)
        else:
            raise AuthenticationError(
                "URL do JavaScript não encontrada na página de redirect. O formato da página pode ter mudado."
            )

        return jwt_token, nonce, redirect_to, js_url

    # ──────────────────────────────────────────────────
    # PASSO 7: Extrai subscriptionKey do bundle JS
    # ──────────────────────────────────────────────────
    def _get_subscription_key(self, js_url: str, jwt: str, nonce: str, redirect_to: str) -> str:
        """
        Obtém a subscriptionKey do PubNub a partir do bundle JS do LegalOne.

        O LegalOne usa PubNub para eventos real-time (notificações, atualizações
        de processos…). A chave de assinatura do canal (subscribeKey) fica
        embutida no bundle JS principal — não é servida por API.

        O bundle é requisitado com os headers corretos de referer/origin para
        evitar bloqueios por CORS ou verificação de origem.

        A chave é extraída via regex: subscribeKey:"<valor>".
        """
        headers = {
            **self._headers_base,
            'accept':           '*/*',
            'origin':           'https://firm.legalone.com.br',
            'referer':          f'https://firm.legalone.com.br/authentication/auth/?jwt={jwt}&redirectTo={redirect_to}&nonce={nonce}',
            'sec-fetch-dest':   'script',
            'sec-fetch-mode':   'cors',
            'sec-fetch-site':   'same-origin',
        }

        response = self.session.get(f'https://firm.legalone.com.br/{js_url}', headers=headers)
        response.raise_for_status()

        match = re.search(r'subscribeKey:"([^"]+)"', response.text)
        if match:
            return match.group(1)
        raise AuthenticationError(
            "Subscription key não encontrada no JavaScript. O formato do JS pode ter mudado."
        )

    # ──────────────────────────────────────────────────
    # PÚBLICO: Executa o fluxo completo de autenticação
    # ──────────────────────────────────────────────────
    def authenticate(self) -> tuple[str, str, dict]:
        """
        Executa o fluxo OIDC completo e retorna (jwt_token, subscription_key, cookies).

        Lança AuthenticationError em qualquer falha de fluxo (credenciais inválidas,
        formato de página inesperado, ausência de JWT ou subscriptionKey).

        O dict de cookies contém todos os cookies acumulados na sessão ao final do
        fluxo — inclui .ASPXAUTH, login-session e culture do LegalOne, que podem
        ser usados diretamente em chamadas subsequentes à API.
        """
        self._trigger_browserhawk()

        _, email_entry_url = self._simulate_browserhawk()

        if 'login/identifier' not in email_entry_url:
            raise AuthenticationError(
                f"Passo 2 não chegou em /u/login/identifier. URL: {email_entry_url}"
            )

        _, password_page_url = self._submit_email(email_entry_url)

        response = self._submit_password(password_page_url)

        if 'code=' in response.url and 'jwt=' not in response.url:
            response = self._complete_oidc_callback(response)

        jwt_token, nonce, redirect_to, js_url = self._extract_jwt_from_redirect(response)
        logger.info("JWT obtido com sucesso. js_url=%s", js_url)

        subscription_key = self._get_subscription_key(js_url, jwt_token, nonce, redirect_to)

        return jwt_token, subscription_key, self.session.cookies.get_dict()


if __name__ == "__main__":
    pass
    # logging.basicConfig(level=logging.DEBUG, format='%(levelname)s %(name)s: %(message)s')

    # import os
    # username = os.environ.get('LEGALONE_USER', 'thomas.maia@abladvogados.com')
    # password = os.environ.get('LEGALONE_PASS', '')

    # auth = TRAuthenticator(username, password)

    # try:
    #     jwt_token, subscription_key, cookies = auth.authenticate()
    #     print(f"\n✓ JWT obtido:           {jwt_token[:40]}...")
    #     print(f"✓ Subscription key:     {subscription_key}")
    #     print(f"✓ Cookies de sessão:    {list(cookies.keys())}")
    # except AuthenticationError as exc:
    #     print(f"\n✗ Falha na autenticação: {exc}")
    #     raise SystemExit(1)

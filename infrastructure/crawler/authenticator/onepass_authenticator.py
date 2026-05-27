import sys
sys.path.append('.')
import math
import requests
from datetime import datetime, time
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

from infrastructure.crawler.constants import LegalOneConstants
from core.errors import AuthenticationError

BASE_URL = 'https://signon.thomsonreuters.com'
RETURN_TO = 'https%3a%2f%2flogin.novajus.com.br%2fOnePass%2fLoginOnePass%2f'

_C = LegalOneConstants


class OnePassAuthenticator:
    """
    Authenticator for LegalOne platform.
    Fluxo:
      1. GET  → aciona BrowserHawk
      2. GET  → simula detecção do browser (BrowserHawk params)
      3. POST → submete credenciais
      4. GET  → troca JWT por sessão autenticada
    """

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.session = requests.Session()

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

    # ──────────────────────────────────────────────────
    # PASSO 1: Primeira requisição (aciona BrowserHawk)
    # ──────────────────────────────────────────────────
    def _trigger_browserhawk(self):
        self.session.get(
            f'{BASE_URL}/?productId=L1NJ&returnto={RETURN_TO}&bhcp=1',
            headers=self._headers_base,
        )

    # ──────────────────────────────────────────────────
    # PASSO 2: Simula detecção do browser e obtém HTML
    # ──────────────────────────────────────────────────
    def _simulate_browserhawk(self) -> str:
        params = {
            'productId': 'L1NJ',
            'returnto': 'https://login.novajus.com.br/OnePass/LoginOnePass/',
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
            'referer': f'{BASE_URL}/?productId=L1NJ&returnto={RETURN_TO}&bhcp=1',
        }

        response = self.session.get(f'{BASE_URL}/', params=params, headers=headers)
        response.raise_for_status()
        return response.text

    # ──────────────────────────────────────────────────
    # PASSO 3: Extrai campos ocultos do HTML de login
    # ──────────────────────────────────────────────────
    def _extract_login_fields(self, html: str) -> dict:
        soup = BeautifulSoup(html, 'html.parser')

        def get_field(name, fallback=''):
            tag = soup.find('input', {'name': name})
            return tag['value'] if tag and tag.get('value') else fallback

        now = datetime.now()
        midnight = datetime.combine(now.date(), time(0, 0))
        minutes_to_midnight = math.floor((midnight - now).seconds / 60)
    
        return {
            '__RequestVerificationToken': get_field('__RequestVerificationToken'),
            'IsCDNAvailable':             get_field('IsCDNAvailable', 'False'),
            'IsCloudAccessible':          get_field('IsCloudAccessible', 'False'),
            'OIDCStartUrl':               get_field('OIDCStartUrl'),
            'ViewProductCode':            get_field('ViewProductCode', 'L1NJ'),
            'TraceToken':                 get_field('TraceToken'),
            'SiteKey':                    get_field('SiteKey'),
            'MinutesToMidnight':          str(minutes_to_midnight),
        }

    # ──────────────────────────────────────────────────
    # PASSO 4: Submete credenciais e obtém redirect JWT
    # ──────────────────────────────────────────────────
    def _submit_credentials(self, login_fields: dict) -> requests.Response:
        headers = {
            **self._headers_base,
            'content-type': 'application/x-www-form-urlencoded',
            'origin': BASE_URL,
            'referer': f'{BASE_URL}/?productId=L1NJ&returnto={RETURN_TO}&bhcp=1',
            'sec-fetch-site': 'same-origin',
        }

        data = {
            **login_fields,
            'Username':             self.username,
            'Password':             self.password,
            'Password-clone':       self.password,
            'SaveUsername':         'false',
            'SaveUsernamePassword': 'false',
            'CultureCode':          'pt-BR',
            'OverrideCaptchaFlags': 'False',
            'SignIn':               'submit',
        }

        response = self.session.post(
            f'{BASE_URL}/?productId=L1NJ&returnto={RETURN_TO}&bhcp=1',
            headers=headers,
            data=data,
        )
        response.raise_for_status()
        return response

    # ──────────────────────────────────────────────────
    # PASSO 5: Extrai JWT e nonce da URL de redirect
    # ──────────────────────────────────────────────────
    def _extract_jwt_from_redirect(self, response: requests.Response) -> tuple[str, str, str]:
        parsed = urlparse(response.url)
        params = parse_qs(parsed.query)

        jwt_token   = params.get('jwt', [None])[0]
        nonce       = params.get('nonce', [None])[0]
        redirect_to = params.get('redirectTo', ['home'])[0]

        if not jwt_token:
            raise AuthenticationError(
                "JWT não encontrado na URL de redirect. Verifique as credenciais."
            )
        import re
        # main.4efaf74b896de650.js
        js_url = re.search(r'<script src="(main\..*\.js)" type="module"></script>', response.text)
        if js_url:
            js_url = js_url.group(1)
        else:
            raise AuthenticationError("URL do JavaScript não encontrada na página de redirect. O formato da página pode ter mudado.")

        return jwt_token, nonce, redirect_to, js_url

    # ──────────────────────────────────────────────────
    # PASSO 6: Troca JWT por sessão autenticada
    # ──────────────────────────────────────────────────
    def _exchange_jwt(self, jwt_token: str, nonce: str, redirect_to: str):
        headers = {
            **self._headers_base,
            'referer': 'https://signon.thomsonreuters.com/',
            'sec-fetch-site': 'cross-site',
        }

        self.session.get(
            'https://firm.legalone.com.br/authentication/auth/',
            params={'jwt': jwt_token, 'redirectTo': redirect_to, 'nonce': nonce},
            headers=headers,
        )

    def _get_subscription_key(self, js_url, jwt, nonce, redirect_to) -> str:
        headers = {
            'accept': '*/*',
            'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
            'cache-control': 'no-cache',
            'origin': 'https://firm.legalone.com.br',
            'pragma': 'no-cache',
            'priority': 'u=1',
            'referer': f'https://firm.legalone.com.br/authentication/auth/?jwt={jwt}&redirectTo={redirect_to}&nonce={nonce}',
            'sec-ch-ua': '"Google Chrome";v="147", "Not.A/Brand";v="8", "Chromium";v="147"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'script',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36',
        }

        response = self.session.get(f'https://firm.legalone.com.br/{js_url}', headers=headers)
        # print(response.text)
        import re
        # subscribeKey:"b1159d90df8d45148b4f5721e2752efc"}...
        regex = r'subscribeKey:"([^"]+)"'
        subscription_key_match = re.search(regex, response.text)
        if subscription_key_match:
            return subscription_key_match.group(1)
        else:
            raise AuthenticationError("Subscription key não encontrada no JavaScript. O formato do JS pode ter mudado.")

    # ──────────────────────────────────────────────────
    # PÚBLICO: Executa o fluxo completo de autenticação
    # ──────────────────────────────────────────────────
    def authenticate(self) -> dict:
        """
        Executa todos os passos de autenticação e retorna os cookies da sessão.

        Fluxo ativo:
          1. GET  → aciona BrowserHawk
          2. GET  → simula detecção do browser
          3. POST → submete credenciais (com redirect automático pelo requests)
          4. Cookies de sessão já estão disponíveis após o redirect

        Passos 5 e 6 (JWT explícito) estão desativados: o requests segue os
        redirects automaticamente e os cookies são definidos sem precisar
        extrair o JWT manualmente.
        """
        self._trigger_browserhawk()

        login_page_html = self._simulate_browserhawk()

        login_fields = self._extract_login_fields(login_page_html)

        response = self._submit_credentials(login_fields)

        with open('response_after_login.html', 'w', encoding='utf-8') as f:
            f.write(response.text)  # salva o HTML para análise posterior, se necessário

        # Passo 5 e 6 desativados — o requests segue os redirects automaticamente
        # e deposita os cookies de sessão sem intervenção manual.
        jwt_token, nonce, redirect_to, js_url = self._extract_jwt_from_redirect(response)
        print(f"JWT extraído: {jwt_token[:30]}...")  # log parcial do JWT para depuração, sem expor o token completo
        print(f"js_url extraído: {js_url}")  # log do JS URL para depuração

        self._exchange_jwt(jwt_token, nonce, redirect_to)

        subscription_key = self._get_subscription_key(js_url, jwt_token, nonce, redirect_to)

        return jwt_token, subscription_key, self.session.cookies.get_dict()


if __name__ == "__main__":
    # Exemplo de uso
    auth = OnePassAuthenticator('thomas.maia@abladvogados.com', 'senha_exemplo')
    jwt, subscription_key, cookies = auth.authenticate()
    print("JWT:", jwt)
    print("Subscription Key:", subscription_key)
    print("Cookies:", cookies)

"""
Script de diagnóstico do fluxo de autenticação LegalOne/OnePass → Auth0.
Executa cada etapa individualmente, imprimindo cookies, headers e redirects.
"""
import sys
sys.path.append('.')
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs, urlencode, urljoin

BASE_URL = 'https://signon.thomsonreuters.com'
RETURN_TO_RAW = 'https://login.novajus.com.br/OnePass/LoginOnePass/'
RETURN_TO = 'https%3a%2f%2flogin.novajus.com.br%2fOnePass%2fLoginOnePass%2f'

HEADERS_BASE = {
    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'accept-language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'cache-control': 'no-cache',
    'pragma': 'no-cache',
    'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'document',
    'sec-fetch-mode': 'navigate',
    'sec-fetch-site': 'none',
    'sec-fetch-user': '?1',
    'upgrade-insecure-requests': '1',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
}


def print_sep(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


def print_response_info(label, response, show_redirects=True):
    print(f"\n[{label}]")
    print(f"  URL final    : {response.url}")
    print(f"  Status       : {response.status_code}")
    if show_redirects and response.history:
        print(f"  Redirects    :")
        for r in response.history:
            loc = r.headers.get('Location', '')
            print(f"    {r.status_code} → {loc}")
    print(f"  Cookies sessão: {dict(session.cookies)}")
    resp_cookies = response.cookies.get_dict()
    if resp_cookies:
        print(f"  Cookies resp .: {resp_cookies}")


def save_html(filename, html):
    path = f'/Users/thomas/Documents/projetos/legal-one-client/debug_{filename}'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  [salvo em debug_{filename}]")


# ── Cria sessão ──────────────────────────────────────────────
session = requests.Session()

print_sep("PASSO 1a: GET /v2 sem bhcp (deve setar CIAMMigrationUserMigrated)")
r1a = session.get(
    f'{BASE_URL}/v2',
    params={'productid': 'L1NJ', 'returnto': RETURN_TO_RAW},
    headers=HEADERS_BASE,
    allow_redirects=True,
)
print_response_info("passo 1a", r1a)
save_html("1a_trigger.html", r1a.text)

print_sep("PASSO 1b: GET /v2 com bhcp=1 (BrowserHawk)")
r1b = session.get(
    f'{BASE_URL}/v2',
    params={
        'productId': 'L1NJ',
        'returnto': RETURN_TO_RAW,
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
    },
    headers={
        **HEADERS_BASE,
        'sec-fetch-site': 'same-origin',
        'referer': f'{BASE_URL}/v2?productId=L1NJ&returnto={RETURN_TO}&bhcp=1',
    },
    allow_redirects=True,
)
print_response_info("passo 1b", r1b)
save_html("1b_simulate_bh.html", r1b.text)

# Extrair OIDCStartUrl
soup = BeautifulSoup(r1b.text, 'html.parser')
oidc_input = soup.find('input', {'id': 'OIDCStartUrl'})
if not oidc_input or not oidc_input.get('value'):
    print("\n[ERRO] OIDCStartUrl não encontrado na página 1b!")
    sys.exit(1)

oidc_url = oidc_input['value']
if not oidc_url.startswith('http'):
    oidc_url = BASE_URL + oidc_url
print(f"\nOIDCStartUrl extraído: {oidc_url}")

# Extrair campos do form
form = soup.find('form', {'id': 'form0'})
form_action = form['action'] if form else None
form_fields = {}
if form:
    for inp in form.find_all('input', {'type': 'hidden'}):
        if inp.get('name'):
            form_fields[inp['name']] = inp.get('value', '')
    print(f"Form action: {form_action}")
    print(f"Form fields: {list(form_fields.keys())}")

print_sep("PASSO 2a: GET para OIDCStartUrl (abordagem atual — sem follow manual)")
r2a = session.get(
    oidc_url,
    headers={
        **HEADERS_BASE,
        'referer': f'{BASE_URL}/v2?productId=L1NJ&returnto={RETURN_TO_RAW}&bhcp=1',
        'sec-fetch-site': 'same-origin',
    },
    allow_redirects=False,  # Sem seguir redirects para ver o que retorna
)
print_response_info("passo 2a (sem redirect)", r2a, show_redirects=False)
print(f"  Location header: {r2a.headers.get('Location', '(nenhum)')}")
save_html("2a_oidc_get_no_redirect.html", r2a.text)

print_sep("PASSO 2b: GET para OIDCStartUrl (seguindo todos os redirects)")
r2b = session.get(
    oidc_url,
    headers={
        **HEADERS_BASE,
        'referer': f'{BASE_URL}/v2?productId=L1NJ&returnto={RETURN_TO_RAW}&bhcp=1',
        'sec-fetch-site': 'same-origin',
    },
    allow_redirects=True,
)
print_response_info("passo 2b (com redirect)", r2b)
save_html("2b_oidc_get_with_redirect.html", r2b.text)

# Se tiver migrate/start no fluxo, tentar processar o form auto-submit
if 'migrate/start' in r2b.url or 'migrate/start' in r2b.text:
    print("\n[INFO] Detectado migrate/start — tentando processar form auto-submit...")
    soup2 = BeautifulSoup(r2b.text, 'html.parser')
    form2 = soup2.find('form')
    if form2:
        action2 = form2.get('action', '')
        if not action2.startswith('http'):
            action2 = urljoin(r2b.url, action2)
        fields2 = {i['name']: i.get('value', '') for i in form2.find_all('input') if i.get('name')}
        method2 = form2.get('method', 'get').upper()
        print(f"  Form action  : {action2}")
        print(f"  Form method  : {method2}")
        print(f"  Form fields  : {list(fields2.keys())}")

        r_migrate = session.request(
            method2,
            action2,
            data=fields2 if method2 == 'POST' else None,
            params=fields2 if method2 == 'GET' else None,
            headers={
                **HEADERS_BASE,
                'content-type': 'application/x-www-form-urlencoded',
                'origin': f'{urlparse(r2b.url).scheme}://{urlparse(r2b.url).netloc}',
                'referer': r2b.url,
                'sec-fetch-site': 'same-origin',
            },
            allow_redirects=True,
        )
        print_response_info("migrate/start form submit", r_migrate)
        save_html("2c_migrate_start_result.html", r_migrate.text)

print_sep("PASSO 2c: POST form (action do form da login_page) com campos hidden")
if form_action and form_fields:
    full_action = form_action if form_action.startswith('http') else BASE_URL + form_action
    r2c = session.post(
        full_action,
        data=form_fields,
        headers={
            **HEADERS_BASE,
            'content-type': 'application/x-www-form-urlencoded',
            'origin': BASE_URL,
            'referer': f'{BASE_URL}/v2?productId=L1NJ&returnto={RETURN_TO_RAW}&bhcp=1',
            'sec-fetch-site': 'same-origin',
        },
        allow_redirects=True,
    )
    print_response_info("passo 2c (POST form)", r2c)
    save_html("2c_form_post.html", r2c.text)
    print(f"  'state' na URL: {'state=' in r2c.url}")
else:
    print("  [SKIP] Sem form para postar")

print("\nDiagnóstico concluído.")

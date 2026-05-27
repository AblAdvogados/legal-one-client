"""
Diagnóstico v4 — descobre como obter CIAMMigrationUserMigrated=True legitimamente.

Testa múltiplos endpoints e parâmetros para ver qual deles define o cookie.
"""
import sys, requests
from bs4 import BeautifulSoup

BASE_URL = 'https://signon.thomsonreuters.com'
RETURN_TO_RAW = 'https://login.novajus.com.br/OnePass/LoginOnePass/'

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


def check_cookies(session, label):
    c = session.cookies.get_dict()
    migrated = c.get('CIAMMigrationUserMigrated', '(não presente)')
    print(f"  [{label}] CIAMMigrationUserMigrated={migrated}")
    print(f"           todos cookies: {list(c.keys())}")


def test_endpoint(label, session, method, url, **kwargs):
    print(f"\n--- {label} ---")
    print(f"  {method} {url}")
    r = getattr(session, method.lower())(url, allow_redirects=False, **kwargs)
    print(f"  status={r.status_code}")
    migrated_set = False
    for k, v in r.headers.items():
        if k.lower() == 'set-cookie':
            print(f"  Set-Cookie: {v[:130]}")
            if 'CIAMMigration' in v:
                migrated_set = True
    check_cookies(session, label)
    if migrated_set:
        print(f"  *** CIAMMigrationUserMigrated SETADO AQUI! ***")
    return r, migrated_set


# ──────────────────────────────────────────────────────────
# Sessão comum para todos os testes
# ──────────────────────────────────────────────────────────
session = requests.Session()

# Passo base: pegar COSISOSession
session.get(f'{BASE_URL}/v2', params={'productid': 'L1NJ', 'returnto': RETURN_TO_RAW}, headers=HEADERS_BASE)
r_bh = session.get(f'{BASE_URL}/v2', params={
    'productId': 'L1NJ', 'returnto': RETURN_TO_RAW, 'bhcp': '1',
    'bhav': '', 'bhsh': '1080', 'bhsw': '1920', 'bhiw': '1920',
    'bhih': '1080', 'bhtz': '-3', 'bhlu': 'pt-br', 'bhsp': '0', 'bhqs': '1',
}, headers={**HEADERS_BASE, 'sec-fetch-site': 'same-origin'})

soup = BeautifulSoup(r_bh.text, 'html.parser')
rvt = soup.find('input', {'name': '__RequestVerificationToken'})
token = rvt['value'] if rvt else ''
check_cookies(session, "após BH")

# Candidatos para setar CIAMMigrationUserMigrated:

# 1. GET /v2/migrate/oidc (o próprio endpoint de início do OIDC — NÃO tem o cookie)
test_endpoint("GET /v2/migrate/oidc", session, 'GET',
    f'{BASE_URL}/v2/migrate/oidc',
    params={'sessionType': '1', 'productid': 'L1NJ', 'returnto': RETURN_TO_RAW},
    headers={**HEADERS_BASE, 'sec-fetch-site': 'same-origin'})

# Reinicia sessão após o teste acima (o COSISOSession foi deletado)
session2 = requests.Session()
session2.get(f'{BASE_URL}/v2', params={'productid': 'L1NJ', 'returnto': RETURN_TO_RAW}, headers=HEADERS_BASE)
session2.get(f'{BASE_URL}/v2', params={
    'productId': 'L1NJ', 'returnto': RETURN_TO_RAW, 'bhcp': '1',
    'bhav': '', 'bhsh': '1080', 'bhsw': '1920', 'bhiw': '1920',
    'bhih': '1080', 'bhtz': '-3', 'bhlu': 'pt-br', 'bhsp': '0', 'bhqs': '1',
}, headers={**HEADERS_BASE, 'sec-fetch-site': 'same-origin'})
r_bh2 = session2.get(f'{BASE_URL}/v2', params={
    'productId': 'L1NJ', 'returnto': RETURN_TO_RAW, 'bhcp': '1',
    'bhav': '', 'bhsh': '1080', 'bhsw': '1920', 'bhiw': '1920',
    'bhih': '1080', 'bhtz': '-3', 'bhlu': 'pt-br', 'bhsp': '0', 'bhqs': '1',
}, headers={**HEADERS_BASE, 'sec-fetch-site': 'same-origin'})
soup2 = BeautifulSoup(r_bh2.text, 'html.parser')
rvt2_el = soup2.find('input', {'name': '__RequestVerificationToken'})
token2 = rvt2_el['value'] if rvt2_el else ''
check_cookies(session2, "sessão2 após BH")

# 2. GET /v2 com parâmetro sessionType=1
test_endpoint("GET /v2?sessionType=1", session2, 'GET',
    f'{BASE_URL}/v2',
    params={'productId': 'L1NJ', 'returnto': RETURN_TO_RAW, 'sessionType': '1'},
    headers={**HEADERS_BASE, 'sec-fetch-site': 'same-origin'})

# 3. GET /v2/keepalive
test_endpoint("GET /v2/keepalive", session2, 'GET',
    f'{BASE_URL}/v2/keepalive',
    params={'productid': 'L1NJ', 'returnto': RETURN_TO_RAW},
    headers={**HEADERS_BASE, 'sec-fetch-site': 'same-origin'})

# 4. POST para o form action com OIDCStartUrl preenchido
print("\n--- POST form action (rota de credenciais) com campos hidden ---")
soup_bh = BeautifulSoup(r_bh2.text, 'html.parser')
form = soup_bh.find('form', {'id': 'form0'})
if form:
    action = form['action']
    if not action.startswith('http'):
        action = BASE_URL + action
    fields = {i['name']: i.get('value', '') for i in form.find_all('input', {'type': 'hidden'}) if i.get('name')}
    print(f"  POST {action}")
    print(f"  fields: {list(fields.keys())}")
    r_post, found = test_endpoint("POST form0", session2, 'POST', action,
        data=fields,
        headers={**HEADERS_BASE, 'content-type': 'application/x-www-form-urlencoded',
                 'origin': BASE_URL, 'referer': r_bh2.url, 'sec-fetch-site': 'same-origin'})

# 5. GET /v2/migrate/check ou /v2/migrate/status
for ep in ['/v2/migrate/check', '/v2/migrate/status', '/v2/migrate']:
    test_endpoint(f"GET {ep}", session2, 'GET',
        f'{BASE_URL}{ep}',
        params={'productid': 'L1NJ', 'returnto': RETURN_TO_RAW},
        headers={**HEADERS_BASE, 'sec-fetch-site': 'same-origin'})

print("\nFim do diagnóstico v4.")

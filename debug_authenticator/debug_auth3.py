"""
Diagnóstico v3 — testa duas hipóteses:

A) Definir o cookie CIAMMigrationUserMigrated=True manualmente antes do fluxo OIDC
B) Seguir o fluxo do login.novajus.com.br para ver o que ele envia ao signon.thomsonreuters.com

Também testa: POST para /v2/migrate/start (em vez de GET)
"""
import sys, requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

BASE_URL = 'https://signon.thomsonreuters.com'
RETURN_TO_RAW = 'https://login.novajus.com.br/OnePass/LoginOnePass/'
NOVAJUS_LOGIN = 'https://login.novajus.com.br/OnePass/LoginOnePass/'

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


def save(name, html):
    path = f'/Users/thomas/Documents/projetos/legal-one-client/{name}'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  → {name}")


def hop_by_hop(session, start_url, headers, max_hops=15, label=''):
    """Segue redirects hop a hop e imprime cada etapa."""
    url = start_url
    for i in range(max_hops):
        print(f"  [{'GET':4s} hop {i:2d}] {url[:100]}")
        r = session.get(url, headers=headers, allow_redirects=False)
        print(f"           status={r.status_code}  cookies={list(session.cookies.keys())}")
        for k, v in r.headers.items():
            if k.lower() == 'set-cookie':
                print(f"           Set-Cookie: {v[:120]}")
        if r.status_code in (301, 302, 303, 307, 308):
            loc = r.headers.get('Location', '')
            if not loc.startswith('http'):
                p = urlparse(url)
                loc = f"{p.scheme}://{p.netloc}{loc}"
            url = loc
        else:
            return url, r
    return url, None


# ─────────────────────────────────────────────────────────
# HIPÓTESE A: Definir CIAMMigrationUserMigrated=True antes do fluxo
# ─────────────────────────────────────────────────────────
print("\n" + "="*70)
print("HIPÓTESE A — CIAMMigrationUserMigrated=True injetado manualmente")
print("="*70)

sA = requests.Session()

# Passo normal
sA.get(f'{BASE_URL}/v2', params={'productid': 'L1NJ', 'returnto': RETURN_TO_RAW}, headers=HEADERS_BASE)
sA.get(f'{BASE_URL}/v2', params={
    'productId': 'L1NJ', 'returnto': RETURN_TO_RAW, 'bhcp': '1',
    'bhav': '', 'bhsh': '1080', 'bhsw': '1920', 'bhiw': '1920',
    'bhih': '1080', 'bhtz': '-3', 'bhlu': 'pt-br', 'bhsp': '0', 'bhqs': '1',
}, headers={**HEADERS_BASE, 'sec-fetch-site': 'same-origin'})

# Injetar o cookie que supostamente habilita o OIDC
sA.cookies.set('CIAMMigrationUserMigrated', 'True', domain='signon.thomsonreuters.com')
print(f"Cookies antes do OIDC: {list(sA.cookies.keys())}")

oidc_url = f'{BASE_URL}/v2/migrate/oidc?sessionType=1&productid=L1NJ&returnto={RETURN_TO_RAW}'
final_url_A, final_resp_A = hop_by_hop(
    sA, oidc_url,
    {**HEADERS_BASE, 'sec-fetch-site': 'same-origin', 'referer': f'{BASE_URL}/v2'},
    label='A'
)
print(f"\nResultado A: url={final_url_A}")
if final_resp_A:
    html_A = final_resp_A.text
    print(f"  Erro geral: {'Erro geral' in html_A}")
    print(f"  state= na URL: {'state=' in final_url_A}")
    print(f"  login/identifier: {'login/identifier' in final_url_A}")
    save('diagA_result.html', html_A)


# ─────────────────────────────────────────────────────────
# HIPÓTESE B: Seguir login.novajus.com.br para capturar o que
#             ele passa ao signon.thomsonreuters.com
# ─────────────────────────────────────────────────────────
print("\n" + "="*70)
print("HIPÓTESE B — Seguir fluxo via login.novajus.com.br")
print("="*70)

sB = requests.Session()

print(f"\n  GET {NOVAJUS_LOGIN}")
rB = sB.get(NOVAJUS_LOGIN, headers=HEADERS_BASE, allow_redirects=False)
print(f"  status={rB.status_code}")
for k, v in rB.headers.items():
    if k.lower() in ('location', 'set-cookie'):
        print(f"  {k}: {v[:150]}")
print(f"  cookies novajus: {list(sB.cookies.keys())}")

# Seguir até signon.thomsonreuters.com hop a hop
if rB.status_code in (301, 302, 303):
    loc = rB.headers.get('Location', '')
    if 'signon.thomsonreuters.com' in loc or loc.startswith('/'):
        print(f"\n  Redirect para: {loc}")
        # Agora pegar a página de login do signon com os cookies do novajus
        final_url_B, final_resp_B = hop_by_hop(
            sB, loc,
            {**HEADERS_BASE, 'referer': NOVAJUS_LOGIN, 'sec-fetch-site': 'cross-site'},
            label='B'
        )
        print(f"\nResultado B: url={final_url_B}")
        if final_resp_B:
            html_B = final_resp_B.text
            print(f"  Erro geral: {'Erro geral' in html_B}")
            print(f"  OIDCStartUrl no HTML: {'OIDCStartUrl' in html_B}")
            print(f"  state= na URL: {'state=' in final_url_B}")
            print(f"  auth.thomsonreuters.com: {'auth.thomsonreuters.com' in final_url_B}")
            print(f"  cookies após redirect: {list(sB.cookies.keys())}")
            save('diagB_result.html', html_B)
    else:
        print(f"  Redirect não vai para signon: {loc}")
else:
    print(f"  novajus não fez redirect (status {rB.status_code}). Seguindo com allow_redirects=True...")
    rB2 = sB.get(NOVAJUS_LOGIN, headers=HEADERS_BASE, allow_redirects=True)
    print(f"  URL final: {rB2.url}")
    print(f"  status: {rB2.status_code}")
    print(f"  cookies: {list(sB.cookies.keys())}")
    print(f"  Erro geral: {'Erro geral' in rB2.text}")
    print(f"  OIDCStartUrl: {'OIDCStartUrl' in rB2.text}")
    print(f"  auth.thomsonreuters.com: {'auth.thomsonreuters.com' in rB2.url}")
    save('diagB_result.html', rB2.text)


# ─────────────────────────────────────────────────────────
# HIPÓTESE C: POST para /v2/migrate/start em vez de GET
# ─────────────────────────────────────────────────────────
print("\n" + "="*70)
print("HIPÓTESE C — POST para /v2/migrate/start")
print("="*70)

sC = requests.Session()
sC.get(f'{BASE_URL}/v2', params={'productid': 'L1NJ', 'returnto': RETURN_TO_RAW}, headers=HEADERS_BASE)
r_bh = sC.get(f'{BASE_URL}/v2', params={
    'productId': 'L1NJ', 'returnto': RETURN_TO_RAW, 'bhcp': '1',
    'bhav': '', 'bhsh': '1080', 'bhsw': '1920', 'bhiw': '1920',
    'bhih': '1080', 'bhtz': '-3', 'bhlu': 'pt-br', 'bhsp': '0', 'bhqs': '1',
}, headers={**HEADERS_BASE, 'sec-fetch-site': 'same-origin'})

# Extrair __RequestVerificationToken
soup = BeautifulSoup(r_bh.text, 'html.parser')
rvt = soup.find('input', {'name': '__RequestVerificationToken'})
token = rvt['value'] if rvt else ''
print(f"  __RequestVerificationToken: {token[:40]}...")

migrate_start_url = f'{BASE_URL}/v2/migrate/start?productid=L1NJ&returnto={RETURN_TO_RAW}'
print(f"\n  POST {migrate_start_url}")
rC = sC.post(
    migrate_start_url,
    data={'__RequestVerificationToken': token},
    headers={
        **HEADERS_BASE,
        'content-type': 'application/x-www-form-urlencoded',
        'origin': BASE_URL,
        'referer': f'{BASE_URL}/v2',
        'sec-fetch-site': 'same-origin',
    },
    allow_redirects=False,
)
print(f"  status={rC.status_code}")
for k, v in rC.headers.items():
    if k.lower() in ('location', 'set-cookie', 'content-type'):
        print(f"  {k}: {v[:150]}")
print(f"  cookies: {list(sC.cookies.keys())}")
save('diagC_result.html', rC.text)

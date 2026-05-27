"""
Diagnóstico detalhado: rastreia Set-Cookie em cada hop do redirect.
Chama /v2/migrate/oidc UMA SÓ VEZ, manualmente seguindo os redirects
para inspecionar cada resposta intermediária.
"""
import sys
sys.path.append('.')
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

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


def save_html(filename, html):
    path = f'/Users/thomas/Documents/projetos/legal-one-client/{filename}'
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  → salvo em {filename}")


def follow_manually(session, start_url, headers, max_hops=10):
    """
    Segue redirects manualmente, imprimindo Set-Cookie em cada hop.
    Retorna (url_final, html_final)
    """
    url = start_url
    for hop in range(max_hops):
        print(f"\n  [HOP {hop}] GET {url}")
        r = session.get(url, headers=headers, allow_redirects=False)
        print(f"    Status : {r.status_code}")
        print(f"    Cookies sessão: {dict(session.cookies)}")
        set_cookie = r.headers.get('Set-Cookie', '')
        if set_cookie:
            print(f"    Set-Cookie: {set_cookie}")
        all_set = r.headers.get_all('Set-Cookie') if hasattr(r.headers, 'get_all') else [set_cookie]
        # requests usa CaseInsensitiveDict; iterar diretamente
        for k, v in r.headers.items():
            if k.lower() == 'set-cookie':
                print(f"    Set-Cookie (raw): {v}")

        if r.status_code in (301, 302, 303, 307, 308):
            location = r.headers.get('Location', '')
            print(f"    Location: {location}")
            if not location.startswith('http'):
                parsed = urlparse(url)
                location = f"{parsed.scheme}://{parsed.netloc}{location}"
            url = location
        else:
            # chegamos na resposta final
            print(f"    [FIM] URL final: {url}")
            return url, r.text

    return url, ""


session = requests.Session()

print("=" * 60)
print("PASSO 1: GET /v2 sem bhcp")
print("=" * 60)
r1 = session.get(
    f'{BASE_URL}/v2',
    params={'productid': 'L1NJ', 'returnto': RETURN_TO_RAW},
    headers=HEADERS_BASE,
)
print(f"Status: {r1.status_code}")
print(f"Cookies: {dict(session.cookies)}")
for k, v in r1.headers.items():
    if k.lower() == 'set-cookie':
        print(f"Set-Cookie: {v}")

print("\n" + "=" * 60)
print("PASSO 2: GET /v2 com bhcp=1 (BrowserHawk)")
print("=" * 60)
r2 = session.get(
    f'{BASE_URL}/v2',
    params={
        'productId': 'L1NJ', 'returnto': RETURN_TO_RAW, 'bhcp': '1',
        'bhav': '', 'bhsh': '1080', 'bhsw': '1920',
        'bhiw': '1920', 'bhih': '1080', 'bhtz': '-3',
        'bhlu': 'pt-br', 'bhsp': '0', 'bhqs': '1',
    },
    headers={**HEADERS_BASE, 'sec-fetch-site': 'same-origin'},
)
print(f"Status: {r2.status_code}")
print(f"Cookies: {dict(session.cookies)}")
for k, v in r2.headers.items():
    if k.lower() == 'set-cookie':
        print(f"Set-Cookie: {v}")
save_html("diag2_login_page.html", r2.text)

# Extrair OIDCStartUrl
soup = BeautifulSoup(r2.text, 'html.parser')
oidc_input = soup.find('input', {'id': 'OIDCStartUrl'})
if not oidc_input or not oidc_input.get('value'):
    print("[ERRO] OIDCStartUrl não encontrado!")
    sys.exit(1)

oidc_path = oidc_input['value']
oidc_url = BASE_URL + oidc_path if not oidc_path.startswith('http') else oidc_path
print(f"\nOIDCStartUrl: {oidc_url}")

print("\n" + "=" * 60)
print("PASSO 3: Seguindo OIDCStartUrl manualmente (hop a hop)")
print("=" * 60)

nav_headers = {**HEADERS_BASE, 'referer': r2.url, 'sec-fetch-site': 'same-origin'}
final_url, final_html = follow_manually(session, oidc_url, nav_headers)

print(f"\n[RESULTADO]")
print(f"  URL final : {final_url}")
print(f"  Cookies   : {dict(session.cookies)}")
print(f"  'state=' na URL: {'state=' in final_url}")
print(f"  'Erro geral' no HTML: {'Erro geral' in final_html}")
print(f"  'login/identifier' na URL: {'login/identifier' in final_url}")
print(f"  'authorize' na URL: {'authorize' in final_url}")
save_html("diag3_oidc_result.html", final_html)

# Se chegou em migrate/start, mostrar conteúdo relevante
if 'migrate/start' in final_url:
    print("\n[INFO] Chegou em migrate/start. Conteúdo relevante:")
    soup3 = BeautifulSoup(final_html, 'html.parser')
    forms = soup3.find_all('form')
    print(f"  Forms encontrados: {len(forms)}")
    for form in forms:
        print(f"    action={form.get('action')}, method={form.get('method')}")
    scripts = soup3.find_all('script')
    for s in scripts:
        if s.string and ('submit' in s.string.lower() or 'location' in s.string.lower() or 'auth' in s.string.lower()):
            print(f"  JS relevante: {s.string[:300]}")

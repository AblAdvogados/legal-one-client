"""
Testa isoladamente o lookup_lawsuit com o processo que deu 403 em produção.
Faz login fresco (sem DynamoDB) e exibe a resposta completa.
"""
import logging
import sys
import time

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
for noisy in ("boto3", "botocore", "urllib3", "s3transfer"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

from core.config import settings
from infrastructure.crawler.authenticator import Authenticator
from infrastructure.crawler.tasks import TasksCrawler


class _LocalSessionManager:
    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._cookies = None

    def get_valid_cookies(self):
        if not self._cookies:
            self._cookies = self.refresh()
        return self._cookies

    def refresh(self):
        logging.info("refresh: autenticando no LegalOne...")
        t0 = time.monotonic()
        cookies = Authenticator(self._username, self._password).authenticate()
        logging.info("refresh: login OK em %.2fs", time.monotonic() - t0)
        self._cookies = cookies
        return cookies


session_manager = _LocalSessionManager(
    username=settings.legalone_username,
    password=settings.legalone_password,
)
crawler = TasksCrawler(session_manager=session_manager)

# ── Processo dos logs de produção ─────────────────────────────────────────────
PROCESSO = "5003103-08.2023.4.03.6109"

print("=" * 60)
print(f"lookup_lawsuit: '{PROCESSO}'")
print("=" * 60)

try:
    t0 = time.monotonic()
    result = crawler.lookup_lawsuit(PROCESSO)
    elapsed = time.monotonic() - t0

    print(f"\n  count   : {result.count}")
    print(f"  elapsed : {elapsed:.2f}s")
    print(f"  rows    : {len(result.rows)}")

    for i, row in enumerate(result.rows):
        print(f"\n  row[{i}]:")
        print(f"    id                  = {row.id!r}")
        print(f"    numero_processo     = {row.numero_processo!r}")
        print(f"    nome_pasta_processo = {row.nome_pasta_processo!r}")
        print(f"    titulo              = {getattr(row, 'titulo', '?')!r}")
        print(f"    nome_cliente_principal = {getattr(row, 'nome_cliente_principal', '?')!r}")

except Exception as e:
    logging.exception("Erro no lookup_lawsuit: %s", e)
    sys.exit(1)

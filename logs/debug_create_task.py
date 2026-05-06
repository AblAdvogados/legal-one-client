"""
Script de diagnóstico — executa create_task com dados reais e salva o HTML
retornado pelo crawler para inspeção.

Uso:
    python debug_create_task.py
"""
import logging
import sys

# ── Logging para o terminal ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stdout,
)
# Silencia libs barulhentas
for noisy in ("boto3", "botocore", "urllib3", "s3transfer"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

# ── Patch: salvar HTML antes de retornar ─────────────────────────────────────
import infrastructure.crawler.tasks as _tasks_mod

_original_create_task = _tasks_mod.TasksCrawler.create_task

def _patched_create_task(self, data):
    html = _original_create_task(self, data)
    out = "debug_create_task_response.html"
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅  HTML salvo em: {out}  ({len(html)} bytes)\n")
    return html

_tasks_mod.TasksCrawler.create_task = _patched_create_task

# ── Importa service (após o patch) ───────────────────────────────────────────
from core.config import settings
from infrastructure.crawler.authenticator import Authenticator
from infrastructure.crawler.tasks import TasksCrawler
from services.task.task_service import TaskService


class _LocalSessionManager:
    """SessionManager simplificado: faz login direto, sem DynamoDB."""
    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._cookies: dict | None = None

    def get_valid_cookies(self) -> dict:
        if not self._cookies:
            self._cookies = self.refresh()
        return self._cookies

    def refresh(self) -> dict:
        logging.info("_LocalSessionManager.refresh: autenticando no LegalOne...")
        cookies = Authenticator(self._username, self._password).authenticate()
        self._cookies = cookies
        logging.info("_LocalSessionManager.refresh: login OK")
        return cookies


_session_manager = _LocalSessionManager(
    username=settings.legalone_username,
    password=settings.legalone_password,
)
task_service = TaskService(crawler=TasksCrawler(session_manager=_session_manager))

from services.task.dto import (
    CreateTaskServiceInput,
    LembreteServiceInput,
    ResponsavelInput,
)

# ── Dados de teste ────────────────────────────────────────────────────────────
req = CreateTaskServiceInput(
    numero_processo="5003103-08.2023.4.03.6109",
    responsaveis=[
        ResponsavelInput(
            cpf="484.805.758-24",
            nome="BEATRIZ HELENA",
            is_solicitante=True,
            is_responsavel=True,
            is_executante=True,
        )
    ],
    descricao="(ADVBOX) TESTE DEBUG",
    dt_inicial="25/04/2026",
    hr_inicio="00:01:00",
    dt_final="25/04/2026",
    hr_final="23:59:00",
    deadline_date="",
    deadline_time="",
    observacoes="RVT - Julgamento desfavorável\r\nSeguir com habilitação?",
)

# ── Executa ───────────────────────────────────────────────────────────────────
print("=" * 60)
print("Executando TaskService.create_task()...")
print("=" * 60)

try:
    result = task_service.create_task(req)
    print(f"\nResultado:")
    print(f"  success  = {result.success}")
    print(f"  task_id  = {result.task_id}")
    print(f"  warnings = {result.warnings}")
    print(f"  message  = {result.message!r}")
except Exception as e:
    logging.exception("Erro durante create_task: %s", e)
    sys.exit(1)

# ── Analisa o HTML salvo ──────────────────────────────────────────────────────
import re

print("\n" + "=" * 60)
print("Análise do HTML salvo:")
print("=" * 60)

with open("debug_create_task_response.html", encoding="utf-8") as f:
    html = f.read()

# Título
m = re.search(r"<title>([^<]+)</title>", html)
print(f"  <title>  : {m.group(1) if m else 'NÃO ENCONTRADO'}")

# Padrão task_id atual
m_id = re.search(r"DetailsCompromissoTarefa/(\d+)[/?]", html)
print(f"  task_id  : {m_id.group(1) if m_id else 'NÃO ENCONTRADO — regex não casou'}")

# Todas as ocorrências de DetailsCompromissoTarefa
ocorrencias = re.findall(r"DetailsCompromissoTarefa[^\s\"'<]{0,60}", html)
print(f"\n  Ocorrências de 'DetailsCompromissoTarefa' ({len(ocorrencias)}):")
for o in ocorrencias[:10]:
    print(f"    {o}")

# Erros de validação
block = re.search(r'<div[^>]*class="validation-summary-errors"[^>]*>(.*?)</div>', html, re.DOTALL)
if block:
    items = re.findall(r"<li>(.*?)</li>", block.group(1), re.DOTALL)
    print(f"\n  ⚠️  Erros de validação ({len(items)}):")
    for item in items:
        print(f"    - {re.sub(r'<[^>]+>', '', item).strip()}")
else:
    print("\n  Sem erros de validação.")

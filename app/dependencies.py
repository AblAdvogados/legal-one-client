# filepath: app/dependencies.py
"""
Instanciação dos services e crawlers compartilhados pela aplicação.

Centralizado aqui para que os routers importem de um único lugar e
para facilitar a substituição por mocks nos testes.
"""

from core.config import settings
from infrastructure.crawler.contacts import ContactsCrawler
from infrastructure.crawler.lawsuits import LawsuitsCrawler
from infrastructure.crawler.search import GlobalSearchCrawler
from infrastructure.crawler.session_manager import SessionManager
from services.contact.service import ContactService
from services.lawsuit.lawsuit_service import LawsuitService
from services.search_service import SearchService
from infrastructure.crawler.tasks import TasksCrawler
from services.task.task_service import TaskService


# ── Sessão compartilhada ──────────────────────────────────────────────────────
_session_manager = SessionManager(
    username=settings.legalone_username,
    password=settings.legalone_password,
    table_name=settings.dynamodb_table,
    region=settings.aws_region,
)

# ── Crawlers ──────────────────────────────────────────────────────────────────
_contacts_crawler = ContactsCrawler(session_manager=_session_manager)
_lawsuits_crawler = LawsuitsCrawler(session_manager=_session_manager)
_search_crawler   = GlobalSearchCrawler(session_manager=_session_manager)
_tasks_crawler = TasksCrawler(session_manager=_session_manager)

# ── Services (importados pelos routers via Depends) ───────────────────────────
search_service  = SearchService(crawler=_search_crawler)
contact_service = ContactService(crawler=_contacts_crawler)
lawsuit_service = LawsuitService(lawsuits_crawler=_lawsuits_crawler, contacts_crawler=_contacts_crawler)
task_service = TaskService(crawler=_tasks_crawler)

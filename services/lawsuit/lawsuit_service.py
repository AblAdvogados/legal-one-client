# filepath: services/lawsuit_service.py
"""
LawsuitService — wrapper de negócio sobre LawsuitsCrawler.

Por enquanto delega diretamente ao crawler sem transformação adicional.
A camada de serviço existe para:
  - Isolar os routers FastAPI do crawler.
  - Facilitar adição futura de validação, cache ou parsers de HTML.
"""
from infrastructure.crawler.lawsuits import LawsuitsCrawler
from infrastructure.crawler.contacts import ContactsCrawler
from core.errors import ContatoNaoEncontradoError
from services.lawsuit.dto import LawsuitSummary
from bs4 import BeautifulSoup
from typing import List
import re


def parse_list_of_lawsuits(html: str) -> List[LawsuitSummary]:
    """
    Parser de HTML para extrair dados estruturados da página de resultados de busca por contato.

    Args:
        html: string HTML da página de resultados.

    Returns:
        list[LawsuitSummary]: Lista de resumos de processos encontrados.
    """
    resultado = []
    soup = BeautifulSoup(html, 'html.parser')
    rows = soup.select('table tbody tr.webgrid-row-style')
    for row in rows:
        
        # Número do processo: primeiro link dentro de grid-main-text
        main_text = row.select_one('.grid-main-text a')
        if not main_text:
            continue
        numero_processo = main_text.get_text(strip=True)

        # ID do processo: extraído da URL do link acima
        href = main_text.get('href', '')
        match_id = re.search(r'/processos/processos/details/(\d+)', href, re.IGNORECASE)
        if not match_id:
            continue
        processo_id = match_id.group(1)

        # Assunto: décimo td (índice 9) da linha 
        assunto = row.find_all('td')[9].get_text(strip=True)

        resultado.append(LawsuitSummary(numero_processo, assunto or '', processo_id))

    return resultado

class LawsuitService:
    """
    Wrapper de negócio sobre LawsuitsCrawler.

    Uso:
        service = LawsuitService(crawler)
        html = service.search_by_contact(nome, id_contato)
        html = service.get_lawsuit_details(processo_id)
    """

    def __init__(self, lawsuits_crawler: LawsuitsCrawler, 
                 contacts_crawler: ContactsCrawler,
                 ) -> None:
        self._lawsuits_crawler = lawsuits_crawler
        self._contacts_crawler = contacts_crawler

    def list_lawsuits_by_cpf(self, cpf: str) -> List[LawsuitSummary]:
        """
        Lista processos vinculados a um CPF.

        Args:
            cpf: CPF do contato no formato ###.###.###-##.

        Returns:
            list[LawsuitSummary]: Lista de processos encontrados.

        Raises:
            ContatoNaoEncontradoError: se o lookup por CPF/nome não retornar resultados.
        """
        lookup_results = self._contacts_crawler.lookup_grid_contact(termo=cpf)
        if lookup_results.get('Count') < 1:
            raise ContatoNaoEncontradoError(cpf=cpf)

        nome_contato = lookup_results["Rows"][0]["ContatoNome"]
        id_contato = lookup_results["Rows"][0]["ContatoId"]

        html = self._lawsuits_crawler.search_by_contact(nome_contato, id_contato)

        return parse_list_of_lawsuits(html)

    def get_lawsuit_details(self, processo_id: str) -> str:
        """
        Retorna a página de detalhes de um processo.

        Args:
            processo_id: ID interno do processo no LegalOne.

        Returns:
            HTML da página de detalhes.
        """
        return self._lawsuits_crawler.get_lawsuit_details(processo_id)

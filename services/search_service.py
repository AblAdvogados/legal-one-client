# filepath: services/search_service.py
"""
SearchService — orquestra a busca global no LegalOne.

Responsabilidades:
  - Delegar a requisição HTTP ao GlobalSearchCrawler.
  - Parsear a resposta com parse_search_results().
  - Isolar o router de detalhes de infraestrutura.

NÃO pertence ao service:
  - Mapeamento de contextos para IDs internos  → GlobalSearchCrawler
  - Decodificação e validação do JSON           → GlobalSearchCrawler
  - Mapeamento do dict para tipos estruturados  → parse_search_results()
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrastructure.crawler.search import GlobalSearchCrawler

from infrastructure.crawler.search import VALID_CONTEXTS
from parsers.search_parser import GlobalSearchResult, parse_search_results


class SearchService:
    """
    Wrapper de negócio sobre GlobalSearchCrawler.

    Fluxo:
      1. crawler.search() — GET /shared/global/search → dict JSON.
      2. parse_search_results() — dict → GlobalSearchResult.
    """

    def __init__(self, crawler: "GlobalSearchCrawler") -> None:
        self._crawler = crawler

    def search(
        self,
        term: str,
        contexts: list[str] | None = None,
    ) -> GlobalSearchResult:
        """
        Busca global no LegalOne por termo livre.

        Args:
            term: texto a buscar (nome, CPF, número de processo, etc.).
            contexts: lista de contextos. Padrão: todos (Processos + Contatos).
                      Valores aceitos: "Processos", "Contatos".

        Returns:
            GlobalSearchResult com os grupos de resultados encontrados.

        Raises:
            ValueError: contexto inválido.
            ParseError: resposta inesperada do LegalOne.
            CrawlerError: erro HTTP retornado pelo LegalOne.
            AuthenticationError: falha de sessão.
        """
        if contexts is None:
            contexts = VALID_CONTEXTS

        data = self._crawler.search(term=term, contexts=contexts)
        return parse_search_results(data)

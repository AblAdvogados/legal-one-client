# filepath: infrastructure/crawler/search.py
"""
GlobalSearchCrawler — requisição HTTP para a busca global do LegalOne.

Endpoint: GET /shared/global/search
Retorna JSON (não HTML) — sem parse aqui, apenas a resposta bruta como dict.
"""

from datetime import datetime

from infrastructure.crawler.base_crawler import BaseCrawler
from core.errors import ParseError

# Mapeamento de nomes de contexto para IDs internos da API do LegalOne.
# Detalhe de implementação da API — não exposto fora deste módulo.
_CONTEXT_IDS: dict[str, str] = {
    "Processos": "1",
    "Contatos":  "3",
}

VALID_CONTEXTS = list(_CONTEXT_IDS.keys())


class GlobalSearchCrawler(BaseCrawler):
    """
    Crawler para o endpoint de busca global do LegalOne.

    Usa o perfil headers_ajax (XHR + Accept: JSON) — idêntico ao que o
    browser envia ao digitar na barra de busca do LegalOne.
    """

    def search(self, term: str, contexts: list[str]) -> dict:
        """
        Executa a busca global no LegalOne.

        Args:
            term: texto a buscar (nome, CPF, número de processo, etc.).
            contexts: lista de contextos a pesquisar. Valores aceitos:
                      "Processos" e/ou "Contatos".

        Returns:
            dict com o JSON bruto retornado pelo LegalOne.

        Raises:
            ValueError: se algum contexto não estiver em VALID_CONTEXTS.
            ParseError: se a resposta não puder ser decodificada como JSON
                        ou indicar acesso não autorizado.
            CrawlerError: para erros HTTP retornados pelo LegalOne.
            AuthenticationError: falhas de sessão.
        """
        unknown = [c for c in contexts if c not in _CONTEXT_IDS]
        if unknown:
            raise ValueError(
                f"Contexto(s) inválido(s): {unknown}. "
                f"Valores aceitos: {VALID_CONTEXTS}."
            )

        params = {
            "term":              term,
            "limit":             "20",
            "useRules":          "true",
            "tipo":              "1",
            "searchContextsIds": [_CONTEXT_IDS[c] for c in contexts],
            "_":                 int(datetime.now().timestamp() * 1000),
        }

        url = f"{self.base_url}/shared/global/search"
        response = self._request("GET", url, params=params, headers=self.headers_ajax)

        try:
            data = response.json()
        except Exception as exc:
            raise ParseError(
                f"Resposta da busca global não é JSON válido: {response.text[:200]}"
            ) from exc

        if data.get("Unauthorized"):
            raise ParseError(
                "Busca global retornou Unauthorized=true. "
                "Verifique se a conta tem permissão de acesso."
            )

        return data

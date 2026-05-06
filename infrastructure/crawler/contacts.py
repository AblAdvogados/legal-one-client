# filepath: infrastructure/crawler/contacts.py
"""
ContactsCrawler — métodos HTTP puros para a rota /contatos do LegalOne.

Responsabilidades:
  - Receber um ContactPayload com valores já resolvidos pelo service.
  - Delegar a montagem do payload para contact_payload_builder.
  - Executar o POST HTTP.

NÃO conhece: dataclasses de entrada públicas, mapeamentos de IDs,
lógica de negócio nem montagem de tuplas multipart.
"""

import logging
import time

from infrastructure.crawler.base_crawler import BaseCrawler
from services.contact.dto import ContactPayload
from infrastructure.crawler.payload_builders.contact_payload_builder import build_contact_payload
from datetime import datetime

logger = logging.getLogger(__name__)

class ContactsCrawler(BaseCrawler):
    """
    Crawler para a rota /contatos do site LegalOne.
    Herda headers, _validate_response() e mecanismo de retry de BaseCrawler.
    """

    # ──────────────────────────────────────────────────
    # Consultas de contato
    # ──────────────────────────────────────────────────

    def get_contact_details(self, contato_id: str) -> str:
        url = f"{self.base_url}/contatos/Pessoas/Details/{contato_id}"
        response = self._request("GET", url, headers=self.headers)
        return response.text

    def get_contact_lawsuits(self, contato_id: str) -> str:
        url = f"{self.base_url}/contatos/Pessoas/detailsenvolvimentos/{contato_id}"
        params = {"ajaxnavigation": "true", "renderOnlySection": "True"}
        response = self._request("GET", url, params=params, headers=self.headers_ajax)
        return response.text

    def get_contact_modal(self, contato_id: str) -> str:
        url = f"{self.base_url}/contatos/Contatos/ModalPersonInvolveds"
        params = {
            "idPerson": contato_id,
            "tipoContato": "1",
            "_": int(datetime.now().timestamp() * 1000),
        }
        response = self._request("GET", url, params=params, headers=self.headers_modal)
        return response.text

    # ──────────────────────────────────────────────────
    # Cadastro de contato — POST HTTP
    # ──────────────────────────────────────────────────

    def create_contact(self, payload: ContactPayload) -> str:
        """
        Delega a montagem do payload ao contact_payload_builder e executa o POST.

        Returns:
            HTML da resposta (interpretado por parsers/contact_parser.py).
        """
        files = build_contact_payload(payload)
        url = f"{self.base_url}/contatos/Pessoas/Edit"
        params = {"returnUrl": "/contatos/contatos/search?ajaxnavigation=true"}

        logger.info("create_contact: POST %s iniciado", url)
        t0 = time.perf_counter()

        response = self._request("POST", url, params=params, files=files, headers=self.headers)

        elapsed = time.perf_counter() - t0
        logger.info(
            "create_contact: POST concluído — status=%d, len=%d, elapsed=%.2fs",
            response.status_code, len(response.text), elapsed,
        )

        return response.text

    def lookup_grid_contact(self, termo: str) -> dict:
        """
        Busca contatos pelo CPF ou nome no grid de contatos.
        Observação: Retorna correspondência por continência do termo de busca no nome ou CPF do contato.
        Exemplo: termo "marcos" retorna contatos com nome "Marcos Silva" e CPF "123.456.789-00".

        Returns:
            Dict com a estrutura da resposta JSON do endpoint de lookup, por exemplo:
            {
                'Count': 1, 
                'Rows': [
                    {
                        'Id': 60444, 
                        'ContatoId': 60444, 
                        'ContatoNome': 'JOSELI CARNEIRO DA SILVA', 
                        'ContatoCPF_CNPJ': '654.873.627-34', 
                        'Value': 'JOSELI CARNEIRO DA SILVA', 
                        'TipoContato': 1, 'ContatoCargo': None, 
                        'ContactPosition': None, 
                        'QuantidadeEmails': 0, 'Login': None, 
                        'TipoExecutanteRegraCobrancaHoraTrabalahdaId': None, 
                        'DataBankId': None, 
                        'DataBankName': None, 
                        'DataBankAccountNumber': None, 
                        'DataBankAccountCheckDigit': None, 
                        'DataBankAgencyNumber': None, 
                        'DataBankAgencyCheckDigit': None, 
                        'IBGECodeInvoiceAddress': 3302254, 
                        'Email': None, 
                        'IsRequester': False, 
                        'IsPerformer': False, 
                        'IsResponsible': False
                    }
                ], 
                'Columns': [], 
                'ColumnsHeaders': [], 
                'CustomErrorMessage': None
            }
        """
        params = {
            'term': termo,
            'pageSize': '10',
            '_': int(datetime.now().timestamp() * 1000),
        }
        url = f'{self.base_url}/contatos/Contatos/LookupGridContato'
        response = self._request("GET", url, params=params, headers=self.headers)

        return response.json()

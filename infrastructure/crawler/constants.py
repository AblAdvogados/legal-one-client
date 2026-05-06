# filepath: infrastructure/crawler/constants.py
"""
Constantes HTTP do cliente LegalOne.

Centraliza User-Agent e hints de browser (sec-ch-ua) usados em todas as
requisições — tanto no Authenticator quanto no BaseCrawler.

A URL base do sistema (`base_url`) é uma configuração de ambiente e está
em config.Settings.legalone_base_url.
"""


class LegalOneConstants:
    """Constantes HTTP compartilhadas entre Authenticator e BaseCrawler."""
    user_agent         = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
    sec_ch_ua          = '"Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"'
    sec_ch_ua_platform = '"macOS"'

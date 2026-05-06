# filepath: infrastructure/crawler/dto.py
"""
DTOs de saída dos crawlers — estruturas retornadas aos services.

Separados dos DTOs de domínio (services/task/dto.py) para manter
a separação entre camada de infraestrutura e camada de serviço.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class CrawlerTaskResult:
    """
    Resultado retornado por TasksCrawler.create_task() ao TaskService.

    Atributos:
        html:
            HTML da resposta. O conteúdo varia conforme ``source``:
            - ``"post_response"``: HTML do redirect de sucesso do POST
              (contém ``showMessage`` com o link para a tarefa criada).
            - ``"listing_verification"``: HTML da listagem de tarefas
              do processo (contém linhas com ``data-val-id`` / ``data-val-text``).
        source:
            Indica a origem do HTML, determinando qual parser o service deve usar:
            - ``"post_response"``      → ``interpret_create_task_response``
            - ``"listing_verification"`` → ``find_task_in_listing``
    """
    html: str
    source: Literal["post_response", "listing_verification"]

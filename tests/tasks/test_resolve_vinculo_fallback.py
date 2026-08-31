# filepath: tests/tasks/test_resolve_vinculo_fallback.py
"""
Testes UNITÁRIOS do fallback de resolução de vínculo via busca global.

Contexto: desde 28/08/2026 o LookupLawSuit do LegalOne deixou de casar o
termo contra o campo "Número antigo" (onde fica o protocolo do INSS) — passou
a encontrar apenas pelo número da pasta. O fallback usa a busca global (que
ainda casa por número antigo) para descobrir a pasta e refaz o lookup por ela.

Cenários cobertos (os dois primeiros foram pedidos explicitamente na revisão):
  1. Protocolo administrativo CONTIDO no número de outro processo (judicial)
     não pode ser aceito por engano — igualdade exata, nunca substring.
  2. Fluxo feliz: lookup direto vazio → global acha a pasta → lookup pela
     pasta valida o número → vínculo resolvido.
  3. Múltiplos candidatos na global: descarta o errado, aceita o certo.
  4. Judicial que guarda o protocolo no campo "Número antigo" é aceito.
  5. Lookup direto ainda funcionando → fallback nem é acionado.
  6. Global sem resultados → ProcessoNaoEncontradoError.
  7. Sem search_service injetado → comportamento antigo (erro direto).
"""

import unittest
from unittest.mock import MagicMock

from core.errors import ProcessoNaoEncontradoError
from infrastructure.crawler.lookup_responses import (
    LawsuitLookupResponse,
    LawsuitLookupRow,
)
from parsers.search_parser import (
    GlobalSearchResult,
    SearchResultGroup,
    SearchResultItem,
)
from services.task.task_service import TaskService


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de fixture
# ─────────────────────────────────────────────────────────────────────────────

def _row(vinculo_id, numero, pasta, numero_antigo=None):
    return LawsuitLookupRow(
        id=vinculo_id,
        numero_processo=numero,
        nome_pasta_processo=pasta,
        titulo=None,
        nome_cliente_principal=None,
        id_cliente_principal=None,
        numero_antigo=numero_antigo,
    )


def _lookup(rows):
    return LawsuitLookupResponse(count=len(rows), rows=rows)


_LOOKUP_VAZIO = _lookup([])


def _global_result(descriptions):
    """Monta um GlobalSearchResult de Processos a partir das descriptions."""
    return GlobalSearchResult(groups=[
        SearchResultGroup(
            context="Processos",
            count=len(descriptions),
            items=[
                SearchResultItem(description=d, url=f"/processos/Details/{i}")
                for i, d in enumerate(descriptions, start=1)
            ],
        ),
    ])


def _service(lookup_por_termo, global_result=None, search_service="auto"):
    """
    Monta um TaskService com crawler e busca global mockados.

    Args:
        lookup_por_termo: dict termo → LawsuitLookupResponse do lookup.
        global_result: GlobalSearchResult devolvido pela busca global.
        search_service: "auto" cria mock; None desativa o fallback.
    """
    crawler = MagicMock()
    crawler.lookup_lawsuit.side_effect = (
        lambda termo: lookup_por_termo.get(termo, _LOOKUP_VAZIO)
    )

    if search_service == "auto":
        search_service = MagicMock()
        search_service.search.return_value = (
            global_result if global_result is not None
            else GlobalSearchResult(groups=[])
        )

    svc = TaskService(crawler=crawler, search_service=search_service)
    svc._TIME_BETWEEN_HTTP_REQUESTS = 0  # sem sleep nos testes
    return svc, crawler, search_service


# ─────────────────────────────────────────────────────────────────────────────
# Testes
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveVinculoFallback(unittest.TestCase):

    # 1 ── protocolo contido em outro número NÃO pode casar (pedido na revisão)
    def test_protocolo_contido_em_processo_judicial_nao_casa(self):
        """
        Protocolo "123456" está contido no CNJ "0123456-78.2026.8.26.0001" de
        um processo judicial que a busca global retorna por continência.
        O lookup da pasta desse judicial devolve o CNJ como ProcessNumber e
        outro número antigo — igualdade exata falha e o vínculo é recusado.
        """
        svc, _, _ = _service(
            lookup_por_termo={
                # lookup direto pelo protocolo: vazio (comportamento pós-28/08)
                "123456": _LOOKUP_VAZIO,
                # lookup da pasta do judicial: números NÃO batem exatamente
                "0099999": _lookup([
                    _row(555, "0123456-78.2026.8.26.0001", "Proc - 0099999",
                         numero_antigo="998877"),
                ]),
            },
            global_result=_global_result(["Proc - 0099999"]),
        )
        with self.assertRaises(ProcessoNaoEncontradoError):
            svc._resolve_vinculo("123456")

    # 2 ── fluxo feliz do fallback
    def test_fallback_resolve_pela_pasta(self):
        """Lookup direto vazio → global acha a pasta → lookup valida → resolve."""
        svc, crawler, search = _service(
            lookup_por_termo={
                "1234567890": _LOOKUP_VAZIO,
                "0020963": _lookup([
                    _row(32427, "1234567890", "Proc - 0020963",
                         numero_antigo="1234567890"),
                ]),
            },
            global_result=_global_result(["Proc - 0020963"]),
        )
        vinculo_id, pasta = svc._resolve_vinculo("1234567890")
        self.assertEqual(vinculo_id, "32427")
        self.assertEqual(pasta, "Proc - 0020963")
        search.search.assert_called_once_with(
            term="1234567890", contexts=["Processos"]
        )
        # dois lookups: o direto (vazio) e o da pasta
        self.assertEqual(crawler.lookup_lawsuit.call_count, 2)

    # 3 ── múltiplos candidatos: descarta o errado, aceita o certo
    def test_multiplos_candidatos_global_aceita_apenas_o_exato(self):
        svc, _, _ = _service(
            lookup_por_termo={
                "123456": _LOOKUP_VAZIO,
                # candidato 1: judicial cujo número apenas contém o termo
                "0011111": _lookup([
                    _row(111, "0123456-78.2026.8.26.0001", "Proc - 0011111"),
                ]),
                # candidato 2: o processo certo (ProcessNumber exato)
                "0022222": _lookup([
                    _row(222, "123456", "Proc - 0022222"),
                ]),
            },
            global_result=_global_result(["Proc - 0011111", "Proc - 0022222"]),
        )
        vinculo_id, pasta = svc._resolve_vinculo("123456")
        self.assertEqual(vinculo_id, "222")
        self.assertEqual(pasta, "Proc - 0022222")

    # 4 ── judicial que guarda o protocolo no "Número antigo" é aceito
    def test_judicial_com_numero_antigo_igual_ao_protocolo_casa(self):
        svc, _, _ = _service(
            lookup_por_termo={
                "934458734": _LOOKUP_VAZIO,
                "0045740": _lookup([
                    _row(777, "5001234-56.2026.4.03.6183", "Proc - 0045740",
                         numero_antigo="934458734"),
                ]),
            },
            global_result=_global_result(["Proc - 0045740"]),
        )
        vinculo_id, pasta = svc._resolve_vinculo("934458734")
        self.assertEqual(vinculo_id, "777")
        self.assertEqual(pasta, "Proc - 0045740")

    # 5 ── lookup direto ainda funciona → fallback não é acionado
    def test_lookup_direto_funcionando_nao_aciona_fallback(self):
        svc, crawler, search = _service(
            lookup_por_termo={
                "0008579": _lookup([_row(3004, "0008579", "Proc - 0008579")]),
            },
        )
        vinculo_id, pasta = svc._resolve_vinculo("0008579")
        self.assertEqual(vinculo_id, "3004")
        self.assertEqual(pasta, "Proc - 0008579")
        search.search.assert_not_called()
        self.assertEqual(crawler.lookup_lawsuit.call_count, 1)

    # 6 ── busca global sem resultados → erro
    def test_global_sem_resultados_lanca_erro(self):
        svc, _, _ = _service(
            lookup_por_termo={"999999": _LOOKUP_VAZIO},
            global_result=_global_result([]),
        )
        with self.assertRaises(ProcessoNaoEncontradoError):
            svc._resolve_vinculo("999999")

    # 7 ── sem search_service: comportamento antigo preservado
    def test_sem_search_service_mantem_comportamento_antigo(self):
        svc, _, _ = _service(
            lookup_por_termo={"888888": _LOOKUP_VAZIO},
            search_service=None,
        )
        with self.assertRaises(ProcessoNaoEncontradoError):
            svc._resolve_vinculo("888888")

    # extra ── erro na busca global não derruba: vira ProcessoNaoEncontrado
    def test_erro_na_busca_global_vira_processo_nao_encontrado(self):
        search = MagicMock()
        search.search.side_effect = RuntimeError("busca global fora do ar")
        svc, _, _ = _service(
            lookup_por_termo={"777777": _LOOKUP_VAZIO},
            search_service=search,
        )
        with self.assertRaises(ProcessoNaoEncontradoError):
            svc._resolve_vinculo("777777")

    # extra ── pastas duplicadas na global geram um único lookup
    def test_pastas_duplicadas_na_global_sao_testadas_uma_vez(self):
        svc, crawler, _ = _service(
            lookup_por_termo={"666666": _LOOKUP_VAZIO, "0033333": _LOOKUP_VAZIO},
            global_result=_global_result(["Proc - 0033333", "Proc - 0033333"]),
        )
        with self.assertRaises(ProcessoNaoEncontradoError):
            svc._resolve_vinculo("666666")
        # 1 lookup direto + 1 único lookup da pasta (sem repetição)
        self.assertEqual(crawler.lookup_lawsuit.call_count, 2)


if __name__ == "__main__":
    unittest.main()

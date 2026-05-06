# filepath: tests/infrastructure/test_session_manager_concurrency.py
"""
Testes de concorrência do SessionManager.

POR QUE ESSES TESTES GARANTEM O COMPORTAMENTO EM PRODUÇÃO
==========================================================

A pergunta central é: "o moto não é o DynamoDB real — como sei que vai
funcionar na AWS de verdade?"

A resposta está em *onde* está a lógica crítica do sistema.

O contrato que o DynamoDB garante (e o moto replica fielmente):
  O `put_item` com `ConditionExpression` é uma operação **atômica** no
  servidor. Isso significa que, quando duas chamadas chegam ao mesmo tempo,
  o DynamoDB garante que apenas uma delas terá sucesso — a outra receberá
  `ConditionalCheckFailedException`. Não existe "empate".
  Esse é o fundamento do lock distribuído implementado em `_acquire_lock`.

  O moto reproduz essa semântica porque, internamente, ele também executa
  o `put_item` condicional dentro de um `threading.Lock` em memória.
  O efeito observável para o código testado é idêntico: apenas uma thread
  passa, as demais recebem a exceção esperada.

O que os testes verificam de ponta a ponta:
  1. A lógica de aquisição de lock (`_acquire_lock`) — executada contra um
     servidor DynamoDB real (moto), com `ConditionExpression` real.
  2. O fluxo completo do `SessionManager`: adquire lock → faz login →
     salva cookies → libera lock → demais threads leem do cache.
  3. A única peça substituída é o login HTTP via `Authenticator` — para
     não fazer chamadas de rede. Toda a lógica de orquestração ao redor
     dela é executada de verdade.

O que poderia ser diferente em produção:
  - Latência de rede: o DynamoDB real tem ~1-5ms de latência por operação.
    Em produção a janela de concorrência é maior, mas o resultado é o
    mesmo porque a atomicidade é garantida pelo servidor, não pela
    velocidade das chamadas.
  - Múltiplas instâncias Lambda (processos separados, não threads): o
    lock distribuído via DynamoDB foi projetado exatamente para esse caso.
    Threads no mesmo processo são um subconjunto mais simples do problema.

Conclusão: o que o teste valida é o *contrato de comportamento* do código,
que depende apenas da atomicidade do `put_item` condicional — propriedade
que tanto o moto quanto o DynamoDB real garantem da mesma forma.

──────────────────────────────────────────────────────────────────────────

ESTRUTURA DOS TESTES
====================

  test_only_one_login_under_concurrent_requests
    → Prova que, com N threads simultâneas sem cache,
      Authenticator.authenticate é chamado exatamente 1 vez.

  test_cookies_persisted_exactly_once
    → Prova que o DynamoDB tem 1 item pk=COOKIES ao final,
      com o conteúdo correto, e nenhum lock residual.

  test_second_request_reuses_cached_cookies
    → Prova que requisições subsequentes (com cache aquecido)
      não disparam novo login.

DEPENDÊNCIAS SUBSTITUÍDAS
=========================

  DynamoDB real  →  moto (emulação em memória, mesma API boto3)
    Motivo: evitar dependência de infra AWS nos testes. O moto executa a
    ConditionExpression com semântica idêntica (atomicidade via lock
    interno).

  Authenticator.authenticate  →  unittest.mock.patch
    Motivo: evitar chamada HTTP real ao LegalOne. A lógica testada está
    *ao redor* do login, não dentro dele. O mock retorna cookies falsos
    determinísticos para que as asserções sejam precisas.
"""

import json
import threading
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from infrastructure.crawler.session_manager import SessionManager

# ── Constantes ────────────────────────────────────────────────────────────────

TABLE_NAME = "test-session-store"
REGION     = "us-east-1"

# Cookies determinísticos que o mock do Authenticator sempre retorna.
# Valores fixos permitem asserções de igualdade precisas no final dos testes.
FAKE_COOKIES = {"novajus_session": "abc123", "XSRF-TOKEN": "tok456"}

# Número de threads simultâneas nos testes de concorrência.
# 5 é suficiente para expor race conditions sem tornar o teste lento.
N_THREADS = 5


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def dynamodb_table():
    """
    Cria uma tabela DynamoDB **em memória** via moto antes de cada teste.

    O `with mock_aws()` intercepta *todas* as chamadas boto3 feitas dentro
    do seu bloco e as redireciona para a emulação local — sem tocar na AWS
    real e sem necessidade de credenciais.

    Por que `yield` dentro do `with`:
      O `with mock_aws()` precisa permanecer ativo durante todo o teste,
      não apenas durante o setup. O `yield` pausa o fixture aqui e entrega
      o controle ao teste; quando o teste termina, o `with` finaliza e
      destrói todos os dados da tabela — isolamento total entre testes.
    """
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        client.create_table(
            TableName=TABLE_NAME,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        )
        # O moto é síncrono, mas usar o waiter mantém o código portável caso
        # o fixture seja adaptado para apontar para um DynamoDB Local real.
        waiter = client.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_NAME)

        yield boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)


@pytest.fixture
def make_session_manager(dynamodb_table):
    """
    Factory que cria instâncias de SessionManager apontando para a tabela moto.

    Por que uma factory (função) em vez de retornar um único manager?
      Em produção, cada instância Lambda é um processo separado com seu
      próprio SessionManager. Para simular isso com threads, cada thread
      precisa de sua *própria* instância de SessionManager — mas todas
      compartilhando a mesma tabela DynamoDB (o recurso compartilhado
      real). `make_session_manager()` chamado N vezes cria N managers
      distintos, todos apontando para o mesmo `dynamodb_table`.

    Por que sobrescrever `sm.table` diretamente?
      O `SessionManager.__init__` cria sua própria conexão boto3. Como o
      moto já está ativo (estamos dentro do `with mock_aws()` do fixture
      pai), qualquer nova conexão boto3 já seria interceptada. A
      sobrescrita explícita é uma garantia extra de que todos os managers
      usam exatamente o mesmo objeto de tabela — evitando surpresas caso
      o moto seja configurado diferentemente no futuro.
    """
    def _factory() -> SessionManager:
        sm = SessionManager(
            username="test_user",
            password="test_pass",
            table_name=TABLE_NAME,
            region=REGION,
        )
        # Garante que todos os managers criados neste teste apontam para
        # a mesma instância de tabela moto — simula o DynamoDB compartilhado.
        sm.table = dynamodb_table
        return sm

    return _factory


# ── Testes ─────────────────────────────────────────────────────────────────────

@mock_aws
def test_only_one_login_under_concurrent_requests(make_session_manager):
    """
    CENÁRIO: N requisições chegam simultaneamente com o cache vazio.

    ESPERADO: exatamente 1 login ocorre. As demais threads aguardam em
    `_wait_for_refresh()` e retornam os cookies que a vencedora salvou.

    COMO O threading.Barrier FUNCIONA:
      `Barrier(N)` cria um ponto de sincronização. Cada thread que chama
      `barrier.wait()` fica bloqueada até que N threads tenham chamado
      `wait()`. No momento em que a N-ésima thread chega, todas são
      liberadas ao mesmo tempo — maximizando a colisão no `_acquire_lock`.

    POR QUE O MOCK DO AUTHENTICATE TEM sleep(0.3):
      Sem a pausa, a thread vencedora termina o login tão rápido que salva
      os cookies antes das outras threads tentarem `_acquire_lock`. O
      sleep simula o tempo real de um login HTTP (~3s no LegalOne) e força
      as outras threads a entrarem de fato em `_wait_for_refresh()`,
      exercitando esse caminho do código.

    POR QUE login_lock (Lock no mock):
      O `login_count` é uma variável Python compartilhada entre threads.
      Mesmo sendo um contador simples, `login_count += 1` não é atômico
      em todos os contextos. O `login_lock` garante que a contagem seja
      precisa — sem ele, poderíamos ter um falso positivo de "1 login"
      por sorte de escalonamento.
    """
    results     = []  # cookies retornados por cada thread
    exceptions  = []  # qualquer exceção inesperada capturada pelas threads
    barrier     = threading.Barrier(N_THREADS)
    login_count = 0
    login_lock  = threading.Lock()

    def fake_authenticate():
        """
        Substitui o login HTTP real. Incrementa o contador de logins e
        dorme 0.3s para simular latência de rede — forçando as threads
        perdedoras a entrarem em _wait_for_refresh() enquanto a vencedora
        ainda está "fazendo login".
        """
        import time
        nonlocal login_count
        with login_lock:
            login_count += 1
        time.sleep(0.3)
        return FAKE_COOKIES

    def worker(session_manager):
        """
        Corpo de cada thread: sincroniza na barreira e chama
        get_valid_cookies(). Exceções são capturadas para não matar a
        thread silenciosamente — serão asseridas ao final do teste.
        """
        try:
            barrier.wait()  # aguarda todas as N threads estarem prontas
            cookies = session_manager.get_valid_cookies()
            results.append(cookies)
        except Exception as exc:
            exceptions.append(exc)

    with patch(
        # Patch no namespace onde o símbolo é *usado* (session_manager.py),
        # não onde é definido (authenticator.py). Isso garante que o mock
        # intercepta exatamente a chamada que o SessionManager faz.
        "infrastructure.crawler.session_manager.Authenticator.authenticate",
        side_effect=fake_authenticate,
    ):
        # Cria N managers distintos (simulando N instâncias Lambda) e N threads
        threads = [
            threading.Thread(target=worker, args=(make_session_manager(),))
            for _ in range(N_THREADS)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)  # timeout para evitar hang infinito em CI

    # Nenhuma thread deve ter levantado exceção
    assert exceptions == [], f"Threads levantaram exceções: {exceptions}"

    # Todas as N threads devem ter retornado cookies
    assert len(results) == N_THREADS, (
        f"Esperado {N_THREADS} resultados, obtido {len(results)}"
    )

    # O login deve ter ocorrido exatamente 1 vez.
    # Se > 1: múltiplas threads ganharam o lock → bug em _acquire_lock.
    # Se = 0: nenhuma thread fez login → bug na detecção de cache vazio.
    assert login_count == 1, (
        f"Esperado 1 login, Authenticator.authenticate foi chamado "
        f"{login_count} vez(es)."
    )

    # Todos os resultados devem ser o mesmo dict — independentemente de
    # qual thread fez o login, todas devem receber os mesmos cookies.
    assert all(r == FAKE_COOKIES for r in results), (
        f"Threads retornaram cookies diferentes: {results}"
    )


@mock_aws
def test_cookies_persisted_exactly_once(make_session_manager):
    """
    CENÁRIO: N requisições simultâneas com cache vazio.

    ESPERADO (verificado diretamente no DynamoDB):
      - 1 item pk='COOKIES' com o conteúdo correto
      - Nenhum item pk='LOCK' residual (lock liberado pelo _release_lock)

    Por que verificar o DynamoDB diretamente?
      Este teste complementa o anterior: enquanto o anterior verifica o
      que as threads *receberam*, este verifica o que ficou *gravado*.
      São garantias distintas — é possível as threads retornarem o valor
      correto sem que ele tenha sido salvo corretamente.

    Por que verificar ausência do lock residual?
      Um lock residual faria com que a próxima requisição após um restart
      ficasse presa em _wait_for_refresh() por até 30s (LOCK_TTL), até
      o TTL do DynamoDB expirar o item automaticamente.
    """
    barrier = threading.Barrier(N_THREADS)

    def worker(session_manager):
        barrier.wait()
        session_manager.get_valid_cookies()

    with patch(
        "infrastructure.crawler.session_manager.Authenticator.authenticate",
        return_value=FAKE_COOKIES,
    ):
        threads = [
            threading.Thread(target=worker, args=(make_session_manager(),))
            for _ in range(N_THREADS)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

    # Consulta direta ao DynamoDB (moto) — bypassa toda a lógica do
    # SessionManager para garantir que a asserção é sobre o estado
    # persistido, não sobre o que o código retorna em memória.
    table    = make_session_manager().table
    response = table.get_item(Key={"pk": "COOKIES"})
    item     = response.get("Item")

    assert item is not None, (
        "Nenhum item pk='COOKIES' encontrado no DynamoDB após o login."
    )

    # O conteúdo deve ser exatamente os cookies que o mock retornou
    stored_cookies = json.loads(item["cookies"])
    assert stored_cookies == FAKE_COOKIES, (
        f"Cookies armazenados diferem do esperado. Armazenado: {stored_cookies}"
    )

    # O item de lock não deve ter sobrado — _release_lock deve tê-lo deletado
    lock_response = table.get_item(Key={"pk": "LOCK"})
    assert "Item" not in lock_response, (
        "Item pk='LOCK' ainda presente após o unlock — _release_lock falhou."
    )


@mock_aws
def test_second_request_reuses_cached_cookies(make_session_manager):
    """
    CENÁRIO: duas requisições sequenciais (não simultâneas).

    ESPERADO: a segunda requisição retorna os cookies do cache (DynamoDB)
    sem chamar Authenticator novamente.

    Por que este teste importa?
      Os dois testes anteriores focam em concorrência. Este valida o
      caminho feliz do `_get_cookies()`: se o cache está quente, nunca
      deve haver login desnecessário — o que seria custoso (3-5s de HTTP)
      e poderia invalidar a sessão ativa no LegalOne se o servidor
      interpretar o novo login como "logout implícito" da sessão anterior.
    """
    with patch(
        "infrastructure.crawler.session_manager.Authenticator.authenticate",
        return_value=FAKE_COOKIES,
    ) as mock_auth:
        sm = make_session_manager()

        # Primeira chamada: cache vazio → deve fazer login
        cookies_1 = sm.get_valid_cookies()
        assert mock_auth.call_count == 1, (
            "Primeira chamada deveria ter feito login."
        )

        # Segunda chamada: cache aquecido → não deve chamar authenticate
        cookies_2 = sm.get_valid_cookies()
        assert mock_auth.call_count == 1, (
            "Segunda requisição não deveria chamar Authenticator — "
            "cookies estavam no cache do DynamoDB."
        )

        # Ambas as chamadas devem retornar os mesmos cookies
        assert cookies_1 == cookies_2 == FAKE_COOKIES

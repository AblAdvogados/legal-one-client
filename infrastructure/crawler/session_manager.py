import time
import json
import uuid
import logging
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

from infrastructure.crawler.authenticator.tr_authenticator import TRAuthenticator
from core.errors import AuthenticationError, SessionRefreshTimeoutError

LOCK_TTL = 30       # segundos
COOKIES_TTL = 3 * 3600  # 3 hora


class SessionManager:
    def __init__(
        self,
        username: str,
        password: str,
        table_name: str = "legal-one-session-store",
        region: str = "us-east-1",
    ):
        self.username = username
        self.password = password
        self._region = region
        self.table = self._dynamodb(table_name)
        self.jwt = None  # opcional: armazenar o JWT para depuração ou uso futuro, embora não seja necessário para os cookies
        self.subscription_key = None  # opcional: armazenar a subscription key para depuração ou uso futuro, embora não seja necessário para os cookies

    def _dynamodb(self, table_name):
        return boto3.resource("dynamodb", region_name=self._region).Table(table_name)

    # ──────────────────────────────────────────
    # Obter cookies válidos (ponto de entrada)
    # ──────────────────────────────────────────
    def get_valid_cookies(self) -> dict:
        logger.debug("get_valid_cookies: verificando cache no DynamoDB")
        cookies = self._get_cookies()
        if cookies:
            logger.debug("get_valid_cookies: cookies válidos encontrados no cache")
            return cookies
        logger.info("get_valid_cookies: cache vazio ou expirado, iniciando refresh")
        return self._refresh_with_lock()

    # ──────────────────────────────────────────
    # Força novo login e atualiza o cache
    # Chamado pelo BaseCrawler no mecanismo de retry
    # ──────────────────────────────────────────
    def refresh(self) -> dict:
        logger.info("refresh: forçado pelo BaseCrawler (sessão expirada detectada)")
        return self._refresh_with_lock()

    # ──────────────────────────────────────────
    # Tenta fazer refresh com lock distribuído
    # ──────────────────────────────────────────
    def _refresh_with_lock(self) -> dict:
        lock_value = str(uuid.uuid4())
        lock_expires_at = int((datetime.now(timezone.utc) + timedelta(seconds=LOCK_TTL)).timestamp())

        logger.info("_refresh_with_lock: tentando adquirir lock (lock_value=%s)", lock_value)
        acquired = self._acquire_lock(lock_value, lock_expires_at)

        if acquired:
            logger.info("_refresh_with_lock: lock adquirido, iniciando login")
            try:
                cookies = self._do_login()
                self._save_cookies(cookies)
                logger.info("_refresh_with_lock: login concluído e cookies salvos")
                return cookies
            finally:
                self._release_lock(lock_value)
        else:
            logger.info("_refresh_with_lock: lock não adquirido, aguardando outra instância")
            return self._wait_for_refresh()

    # ──────────────────────────────────────────
    # Tenta adquirir o lock
    # ──────────────────────────────────────────
    def _acquire_lock(self, lock_value: str, lock_expires_at: int) -> bool:
        try:
            self.table.put_item(
                Item={
                    "pk": "LOCK",
                    "lock_value": lock_value,   # "value" é palavra reservada do DynamoDB;
                    "expires_at": lock_expires_at,  # usar "lock_value" evita erros de syntax
                },
                # Só grava se:
                # 1. O item não existe (nenhum lock ativo)
                # OU
                # 2. O lock existente já expirou (instância anterior morreu ou TTL limpou)
                ConditionExpression=(
                    "attribute_not_exists(pk) OR expires_at < :now"
                ),
                ExpressionAttributeValues={
                    ":now": int(datetime.now(timezone.utc).timestamp())
                },
            )
            return True  # ganhou o lock
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                return False  # perdeu o lock, outra instância ganhou
            raise  # outro erro inesperado (permissão, tabela inexistente), propaga

    # ──────────────────────────────────────────
    # Libera o lock somente se ainda for o dono
    # ──────────────────────────────────────────
    def _release_lock(self, lock_value: str):
        try:
            self.table.delete_item(
                Key={"pk": "LOCK"},
                # Só deleta se o atributo lock_value ainda bate com o desta instância.
                # Usa ExpressionAttributeNames porque "lock_value" poderia colidir com
                # palavras reservadas em futuras versões; aqui é seguro mas mantemos
                # o padrão de alias para consistência e clareza.
                ConditionExpression="#lv = :lock_value",
                ExpressionAttributeNames={"#lv": "lock_value"},
                ExpressionAttributeValues={":lock_value": lock_value},
            )
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "ConditionalCheckFailedException":
                # O lock já foi substituído por outra instância (ou expirou via TTL
                # do DynamoDB antes de chegarmos aqui). Não há nada a liberar — ok.
                logger.debug(
                    "Lock já não pertence a esta instância ao tentar liberar "
                    "(lock_value=%s). Ignorando.", lock_value
                )
            else:
                # Qualquer outro erro (permissão IAM, tabela não encontrada, etc.)
                # é logado e re-lançado para não mascarar problemas de infraestrutura.
                logger.error(
                    "Erro inesperado ao liberar lock no DynamoDB (code=%s): %s",
                    code, e
                )
                raise

    # ──────────────────────────────────────────
    # Aguarda outra instância terminar o refresh
    # ──────────────────────────────────────────
    def _wait_for_refresh(self, timeout: int = 30) -> dict:
        """
        Aguarda que outra instância (que adquiriu o lock) termine o login e grave
        cookies *mais novos* do que o momento em que esta instância começou a esperar.

        Motivo do ``wait_start``:
          Sem esse filtro, a instância poderia pegar cookies "velhos" já gravados
          no DynamoDB — que o LegalOne acabou de expirar — e retorná-los como
          válidos, resultando em 403 imediato na próxima requisição.
          Ao exigir ``updated_at >= wait_start`` garantimos que só aceitamos
          cookies gravados *após* a detecção da sessão expirada por esta instância.
        """
        wait_start = datetime.now(timezone.utc)
        start = time.time()
        attempt = 0

        while time.time() - start < timeout:
            time.sleep(0.5)
            attempt += 1
            cookies, updated_at = self._get_cookies_with_timestamp()
            if cookies and updated_at and updated_at >= wait_start:
                logger.info(
                    "_wait_for_refresh: cookies frescos disponíveis após %d tentativa(s) (%.1fs) updated_at=%s",
                    attempt, time.time() - start, updated_at.isoformat(),
                )
                return cookies
            if cookies and updated_at:
                logger.debug(
                    "_wait_for_refresh: cookies encontrados mas são anteriores ao início da espera "
                    "(updated_at=%s wait_start=%s) — aguardando cookies mais novos",
                    updated_at.isoformat(), wait_start.isoformat(),
                )

        elapsed = time.time() - start
        logger.error("_wait_for_refresh: timeout após %.1fs (%d tentativas) — outra instância não concluiu o login", elapsed, attempt)
        raise SessionRefreshTimeoutError(
                "Timeout aguardando refresh dos cookies. "
                "Outra instância demorou mais de 30s para concluir o login."
            )

    # ──────────────────────────────────────────
    # Simula login no site externo
    # ──────────────────────────────────────────
    def _do_login(self) -> dict:
        logger.info("_do_login: iniciando autenticação no LegalOne")
        t0 = time.time()
        jwt, subscription_key, cookies = TRAuthenticator(self.username, self.password).authenticate()

        self.jwt = jwt  # opcional: armazenar o JWT para depuração ou uso futuro, embora não seja necessário para os cookies
        self.subscription_key = subscription_key  # opcional: armazenar a subscription key para depuração ou uso futuro, embora não seja necessário para os cookies

        if not cookies:
            logger.error("_do_login: authenticate() retornou cookies vazios")
            raise AuthenticationError("Login retornou cookies vazios. Verifique as credenciais.")
        logger.info("_do_login: autenticação concluída em %.2fs", time.time() - t0)
        return cookies

    # ──────────────────────────────────────────
    # Helpers DynamoDB
    # ──────────────────────────────────────────
    def _get_cookies(self) -> dict | None:
        cookies, _ = self._get_cookies_with_timestamp()
        return cookies

    def _get_cookies_with_timestamp(self) -> tuple[dict | None, datetime | None]:
        """Retorna (cookies, updated_at) ou (None, None) se ausentes/expirados."""
        response = self.table.get_item(Key={"pk": "COOKIES"})
        item = response.get("Item")

        if not item:
            return None, None

        # Verifica se os cookies ainda são válidos pelo expires_at
        if int(datetime.now(timezone.utc).timestamp()) > item["expires_at"]:
            return None, None

        updated_at = None
        if "updated_at" in item:
            try:
                updated_at = datetime.fromisoformat(item["updated_at"])
                # Garante que o datetime é timezone-aware para comparação com wait_start
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        return json.loads(item["cookies"]), updated_at

    def _save_cookies(self, cookies: dict):
        expires_at = int((datetime.now(timezone.utc) + timedelta(seconds=COOKIES_TTL)).timestamp())

        self.table.put_item(Item={
            "pk": "COOKIES",
            "cookies": json.dumps(cookies),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": expires_at,  # usado para validar + TTL automático do DynamoDB
        })
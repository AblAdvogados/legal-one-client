# filepath: core/config.py
"""
Configurações globais da aplicação — fonte de verdade única.

Estratégia de resolução de segredos:
  - Localmente: lê variáveis de ambiente ou arquivo .env na raiz do projeto.
  - Em produção (Lambda): recebe paths SSM via env vars (SSM_*_PATH) e busca
    os valores em runtime via boto3. Isso contorna a limitação do CloudFormation
    que não suporta {{resolve:ssm-secure:...}} em Lambda Environment.Variables.

Consumido por:
  - tests/helpers.py          → credenciais do SessionManager
  - app/main.py               → instancia services e session manager
"""

import os
import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


def _get_ssm_value(path_env_var: str, fallback_env_var: str, default: str) -> str:
    """
    Resolve um segredo: primeiro tenta a env var direta (desenvolvimento/testes),
    depois o caminho SSM indicado pela env var de path, depois o default.
    """
    # Valor direto tem precedência (desenvolvimento local, .env, testes)
    direct = os.environ.get(fallback_env_var)
    if direct:
        return direct

    # Caminho SSM — usado em produção
    ssm_path = os.environ.get(path_env_var)
    if ssm_path:
        try:
            import boto3
            client = boto3.client("ssm", region_name=os.environ.get("AWS_REGION", "us-east-1"))
            resp = client.get_parameter(Name=ssm_path, WithDecryption=True)
            return resp["Parameter"]["Value"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Falha ao buscar %s no SSM (%s): %s", ssm_path, path_env_var, exc)

    return default


class Settings(BaseSettings):
    # Credenciais do LegalOne — resolvidas via SSM em produção
    legalone_username: str = ""
    legalone_password: str = ""
    legalone_base_url: str = "https://abladv.novajus.com.br"

    dynamodb_table: str = "session-store"
    aws_region: str = "us-east-1"   # Lambda injeta AWS_REGION automaticamente

    # Autenticação JWT da própria API — resolvidas via SSM em produção
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    api_key: str = "change-me"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    def model_post_init(self, __context: object) -> None:
        """Substitui placeholders pelos valores reais do SSM quando necessário."""
        if not self.legalone_username or self.legalone_username == "":
            object.__setattr__(
                self, "legalone_username",
                _get_ssm_value("SSM_USERNAME_PATH", "LEGALONE_USERNAME", "")
            )
        if not self.legalone_password or self.legalone_password == "":
            object.__setattr__(
                self, "legalone_password",
                _get_ssm_value("SSM_PASSWORD_PATH", "LEGALONE_PASSWORD", "")
            )
        if self.jwt_secret == "change-me":
            object.__setattr__(
                self, "jwt_secret",
                _get_ssm_value("SSM_JWT_SECRET_PATH", "JWT_SECRET", "change-me")
            )
        if self.api_key == "change-me":
            object.__setattr__(
                self, "api_key",
                _get_ssm_value("SSM_API_KEY_PATH", "API_KEY", "change-me")
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna instância cacheada de Settings (SSM consultado apenas uma vez por cold start)."""
    return Settings()


# Instância global para compatibilidade com imports existentes
settings = get_settings()

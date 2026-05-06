# filepath: app/auth.py
"""
Autenticação JWT da API.

Fluxo normal (token temporário):
  1. Cliente chama POST /auth/token com { "api_key": "<segredo>" }
  2. Se a api_key bater, devolve um JWT assinado com exp (1 hora por padrão)
  3. Nos demais endpoints o cliente envia Authorization: Bearer <token>
  4. A dependency `require_auth` valida o token e injeta o payload

Tokens permanentes (sem exp):
  Gerados manualmente (ver deploy/README.md) e distribuídos às aplicações
  clientes internas. Não têm data de expiração — válidos enquanto o
  JWT_SECRET não for rotacionado no SSM.

Segredos configurados via variáveis de ambiente (SSM no Lambda):
  JWT_SECRET — chave de assinatura do JWT
  API_KEY    — segredo compartilhado para obter tokens temporários via /auth/token
"""

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from core.config import settings

# ── Utilitários ───────────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)   # auto_error=False → 401 customizado


def _verify_api_key(plain: str) -> bool:
    """Compara a api_key recebida com a configurada (comparação em tempo constante)."""
    return secrets.compare_digest(plain, settings.api_key)


def create_access_token(permanent: bool = False) -> str:
    """
    Gera um JWT assinado com o jwt_secret.

    permanent=False (padrão) → inclui `exp` (expira em jwt_expire_minutes)
    permanent=True           → omite `exp` (token não expira nunca)
    """
    payload: dict = {"sub": "api-client"}
    if not permanent:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
        payload["exp"] = expire
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def _decode_token(token: str) -> dict:
    """
    Decodifica e valida o JWT.

    Tokens sem `exp` são aceitos normalmente — python-jose só verifica
    expiração se o campo `exp` estiver presente no payload.
    Lança HTTPException 401 em caso de assinatura inválida.
    """
    try:
        # options={"verify_exp": False} não é necessário: jose só verifica exp
        # quando ele existe. Passamos explicitamente para deixar o comportamento
        # documentado no código.
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": True},   # verifica se existir, ignora se ausente
        )
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Dependency FastAPI ────────────────────────────────────────────────────────

def require_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """
    Dependency que valida o Bearer token.

    Use como parâmetro em qualquer endpoint que precise de autenticação:
        @router.get("/contacts")
        def list_contacts(_: dict = Depends(require_auth)):
            ...

    Ou aplique a um router inteiro em include_router(..., dependencies=[...]).
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token(credentials.credentials)

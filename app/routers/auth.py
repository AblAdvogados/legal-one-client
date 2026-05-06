# filepath: app/routers/auth.py
"""
Router de autenticação.

  POST /auth/token  →  troca api_key por JWT Bearer
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.auth import _verify_api_key, create_access_token
from core.config import settings

router = APIRouter()


class TokenRequest(BaseModel):
    api_key: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Obtém um JWT de acesso",
    description=(
        "Troca a `api_key` (segredo compartilhado) por um JWT Bearer. "
        "O token deve ser enviado no header `Authorization: Bearer <token>` "
        "em todas as demais chamadas à API."
    ),
)
def get_token(body: TokenRequest) -> TokenResponse:
    if not _verify_api_key(body.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="api_key inválida.",
        )
    token = create_access_token()
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
    )

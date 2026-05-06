# filepath: app/main.py
"""
Entrypoint da aplicação FastAPI.

Registra routers e error handlers.
Exporta `handler = Mangum(app)` para AWS Lambda.
"""

import logging

from fastapi import FastAPI, Depends
from mangum import Mangum

from app.auth import require_auth
from app.error_handler import register_error_handlers
from app.routers import contacts, lawsuits, search, auth, tasks

# ── Configuração de logging ───────────────────────────────────────────────────
# No Lambda, a AWS pré-configura o root logger com nível WARNING e um handler
# próprio. O basicConfig() é no-op quando o root já tem handlers — por isso
# os INFO estavam sendo silenciosamente descartados.
#
# A solução é configurar o root logger diretamente, forçando o nível INFO.
# Os handlers existentes (colocados pela AWS) são preservados e continuam
# enviando para o CloudWatch — só o nível mínimo muda.
logging.getLogger().setLevel(logging.INFO)

# Silencia bibliotecas muito verbosas em INFO
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


app = FastAPI(
    title="LegalOne Client API",
    description="API para automação de cadastros e consultas no LegalOne.",
    version="1.0.0",
)

register_error_handlers(app)

# Rota pública — emite o token
app.include_router(auth.router, prefix="/auth", tags=["auth"])

# Rotas protegidas — exigem Bearer token válido
_auth = [Depends(require_auth)]
app.include_router(contacts.router, prefix="/contacts", tags=["contacts"], dependencies=_auth)
app.include_router(lawsuits.router, prefix="/lawsuits", tags=["lawsuits"], dependencies=_auth)
app.include_router(search.router,   prefix="/search",   tags=["search"],   dependencies=_auth)
app.include_router(tasks.router, prefix="/tasks", tags=["tasks"], dependencies=_auth)

# Entrypoint AWS Lambda
# api_gateway_base_path="/prod" normaliza o root_path que o HTTP API v2 injeta,
# evitando que o FastAPI procure "/prod/contacts/..." em vez de "/contacts/..."
# O fix final foi Mangum(app, lifespan="off", api_gateway_base_path="/prod") — sem 
# o api_gateway_base_path o HTTP API Gateway v2 estava enviando o stage /prod como parte do path, e o FastAPI não encontrava as rotas.
# O Mangum(app) está sem lifespan e sem api_gateway_base_path. O API Gateway HTTP API v2 envia o path sem o stage (/prod), mas o Mangum precisa saber que é um HTTP API v2. O problema é que o Mangum por padrão tenta detectar o tipo do evento — mas com HTTP API v2 às vezes o root_path fica como /prod, fazendo o FastAPI procurar /prod/contacts/... e não encontrar.
handler = Mangum(app, lifespan="off", api_gateway_base_path="/prod")

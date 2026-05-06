## Conceitos básicos

---

### Os 3 segredos

**`JWT_SECRET`**
É como um "carimbo particular" do servidor. Qualquer token JWT só é considerado verdadeiro se tiver sido assinado com esse carimbo. Se alguém tentar forjar um token, vai falhar porque não conhece o segredo.

**`API_KEY`**
É uma senha compartilhada entre o servidor e quem quer obter um token. Funciona como o "código de acesso" para chegar à portaria e pegar um crachá.

**Token JWT**
É o "crachá" em si. Uma vez emitido, você o apresenta em toda requisição para provar quem você é — sem precisar digitar senha toda hora.

---

### O fluxo completo

```
OBTER CRACHÁ (uma vez só):
  Cliente → POST /auth/token  {"api_key": "segredo"}
  Servidor → verifica se a api_key bate
  Servidor → gera e assina um JWT com o jwt_secret
  Servidor → devolve o token JWT

USAR O CRACHÁ (em cada requisição):
  Cliente → GET /contacts/...  Authorization: Bearer <token>
  Servidor → verifica assinatura do token com o jwt_secret
  Servidor → se válido, executa e retorna o resultado
             se inválido, retorna 401 Unauthorized
```

---

### Como o JWT é estruturado

Um token JWT tem 3 partes separadas por `.`:

```
eyJhbGci...   →  HEADER:  algoritmo usado (ex: HS256)
eyJzdWIi...   →  PAYLOAD: dados (ex: {"sub": "api-client"})
FDfqmRea...   →  ASSINATURA: hash do header+payload usando o jwt_secret
```

A assinatura é o que garante autenticidade. Qualquer alteração no payload invalida a assinatura.

---

### O papel do FastAPI nisso

O FastAPI não sabe nada de JWT por padrão. No seu projeto, foi configurado manualmente:

1. **`HTTPBearer`** — extrai o token do header `Authorization: Bearer <token>`
2. **`require_auth`** — é uma *dependency*: função que o FastAPI executa automaticamente antes de qualquer endpoint protegido
3. **`jose.jwt.decode`** — verifica a assinatura usando o `jwt_secret` e retorna o payload

```python
# Simplificando o que acontece em cada requisição protegida:

1. FastAPI recebe a requisição
2. Executa require_auth automaticamente (dependency)
3. require_auth extrai o token do header
4. jose.jwt.decode verifica: "essa assinatura bate com meu jwt_secret?"
   → Sim: libera o endpoint
   → Não: retorna 401
```

---

### Por que deu 401 localmente

O token permanente no seu notebook foi assinado com o `jwt_secret` do SSM de produção. Localmente o .env não tinha `JWT_SECRET`, então usava `"change-me"` — uma secret diferente. Assinaturas diferentes = token inválido = 401.

A solução foi colocar o mesmo `jwt_secret` do SSM no .env local, fazendo os dois ambientes usarem o mesmo "carimbo".
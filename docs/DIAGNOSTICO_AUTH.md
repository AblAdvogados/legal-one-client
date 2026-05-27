# Diagnóstico do Fluxo de Autenticação — LegalOne / Auth0

> Documento técnico sobre **como** foram identificadas as causas raízes do bug de autenticação
> e **quais técnicas** de diagnóstico foram usadas. Útil para depurar regressões futuras.

---

## O problema inicial

O `Authenticator` legado parava com `"Erro geral"` na tela do signon.
O traceback não dizia muita coisa — a requisição chegava no servidor, recebia HTTP 200,
mas o HTML de resposta continha a mensagem de erro da TR em vez de redirecionar para o Auth0.

```
AuthenticationError: Passo de autenticação retornou "Erro geral".
```

**Primeira pergunta:** o erro é na requisição, nos cookies, no fluxo, ou nas credenciais?

---

## Técnica 1 — Separar o fluxo em passos atômicos

O ponto de partida é **nunca debugar um fluxo inteiro de uma vez**.

O fluxo original (`authenticate()`) encadeava 6+ requisições em sequência.
Qualquer falha intermediária era mascarada pela seguinte, ou o estado da sessão
já estava corrompido quando o erro aparecia.

**Solução:** criar um script de diagnóstico (`debug_auth.py`) que executa
**cada requisição individualmente**, com `allow_redirects=False`, e imprime
após cada uma:

```python
def print_response_info(label, response):
    print(f"  URL final    : {response.url}")
    print(f"  Status       : {response.status_code}")
    print(f"  Redirects    :")
    for r in response.history:
        loc = r.headers.get('Location', '')
        print(f"    {r.status_code} → {loc}")
    print(f"  Cookies sessão: {dict(session.cookies)}")
    print(f"  Set-Cookie resp: {response.cookies.get_dict()}")
```

Isso revelou que o **passo 1b** (BrowserHawk com `bhcp=1`) retornava 200
com HTML de "Erro geral" em vez de redirecionar para o Auth0 — os passos
seguintes nunca chegavam a executar.

---

## Técnica 2 — Seguir redirects hop a hop

O passo 1b envolvia uma cadeia de redirects (302 → 302 → 302…).
Com `allow_redirects=True` (padrão do requests), a biblioteca segue
tudo automaticamente e você só vê a URL final — os redirects intermediários
ficam ocultos.

**Solução:** função `hop_by_hop()` que desativa redirects automáticos
e segue manualmente, imprimindo cada etapa:

```python
def hop_by_hop(session, start_url, headers, max_hops=15):
    url = start_url
    for i in range(max_hops):
        print(f"  [GET hop {i}] {url}")
        r = session.get(url, headers=headers, allow_redirects=False)
        print(f"    status={r.status_code}")

        # Imprime todos os Set-Cookie — isso é crítico
        for k, v in r.headers.items():
            if k.lower() == 'set-cookie':
                print(f"    Set-Cookie: {v}")

        if r.status_code in (301, 302, 303, 307, 308):
            url = r.headers['Location']
        else:
            return url, r
```

**O que isso revelou:**

No hop do endpoint `/v2/migrate/start`, o servidor enviava:

```
Set-Cookie: COSISOSession=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/
```

O servidor estava **apagando ativamente** o cookie de sessão — isso explicava
por que os passos seguintes falhavam mesmo com a sessão aparentemente válida.
Sem `COSISOSession`, qualquer requisição ao signon resulta em erro.

> **Insight fundamental:** inspecionar `Set-Cookie` com `expires=1970` é a
> assinatura de um cookie sendo deletado pelo servidor, não de uma falha de rede.

---

## Técnica 3 — Isolar variáveis via hipóteses formais

Com a causa do `COSISOSession` sendo apagado confirmada, a pergunta seguinte era:
**por quê?** E o que o servidor esperava receber para não apagar o cookie?

Isso exigiu testar hipóteses isoladas, uma por vez (`debug_auth3.py`):

### Hipótese A — O cookie `CIAMMigrationUserMigrated=True` é o gatilho

**Raciocínio:** o nome do cookie sugere que o servidor tem dois caminhos:
contas migradas para Auth0 e contas legadas (OnePass). Talvez o servidor
apague o `COSISOSession` apenas para contas **não** marcadas como migradas,
por segurança.

**Teste:** injetar o cookie manualmente antes do fluxo e observar se o
comportamento muda.

```python
session.cookies.set('CIAMMigrationUserMigrated', 'True',
                    domain='signon.thomsonreuters.com', path='/')
```

**Resultado:** ✅ Confirmado. Com o cookie presente, o hop_by_hop mostrou:

```
[GET hop 0] https://signon.thomsonreuters.com/v2/migrate/oidc?...
  status=302  →  https://auth.thomsonreuters.com/authorize?...
[GET hop 1] https://auth.thomsonreuters.com/authorize?...
  status=302  →  https://auth.thomsonreuters.com/u/login/identifier?state=eyJ...
[GET hop 2] https://auth.thomsonreuters.com/u/login/identifier?state=eyJ...
  status=200
```

Sem o cookie:
```
[GET hop 0] https://signon.thomsonreuters.com/v2/migrate/oidc?...
  status=200   ← não redireciona, devolve HTML de "Erro geral"
  Set-Cookie: COSISOSession=; expires=1970...
```

### Hipótese B — O fluxo real do browser passa algum outro header/cookie

Como controle, também testamos seguir o fluxo partindo do `login.novajus.com.br`
(o portal real) para ver se ele passava algo diferente ao signon.

**Resultado:** o portal novajus redireciona para o signon com exatamente os
mesmos parâmetros que o crawler já usava — nenhum header secreto.
Isso **confirmou** que a diferença era apenas o cookie de migração.

---

## Técnica 4 — Salvar HTML de cada etapa em arquivo

Para inspecionar o conteúdo das páginas sem logs gigantes no terminal:

```python
def save_html(filename, html):
    with open(f'debug_{filename}.html', 'w', encoding='utf-8') as f:
        f.write(html)
```

Arquivos como `diagA_result.html`, `password_page.html` e
`response_after_oidc_callback.html` foram abertos no browser para
inspecionar visualmente o DOM — útil quando o servidor devolve 200 com
uma página de erro em vez de um status de erro HTTP.

> **Armadilha comum:** o Auth0 retorna HTTP 400 para senha errada, mas
> retorna HTTP 200 com HTML de erro para e-mail inexistente. Olhar apenas
> o status code não basta — é necessário verificar a URL final e o conteúdo
> do HTML também.

---

## Técnica 5 — Comparar sessão local vs. produção via SSM

Quando o erro `400 /u/login/password` apareceu em produção (mas não localmente),
o diagnóstico foi:

1. **Descartar código** — o mesmo código rodava OK localmente. Código igual, ambiente diferente → problema de configuração.
2. **Isolar a variável** — a única diferença entre local e Lambda era a fonte das credenciais: local usa `.env`, Lambda usa SSM.
3. **Verificar o SSM diretamente:**

```bash
aws ssm get-parameter --name "/legal-one/username" \
  --with-decryption --query "Parameter.Value" --output text
```

Resultado: `thomas.maia@advogados.com` — domínio incorreto (faltava `abl`).

> **Regra:** `400` no endpoint de senha (não de e-mail) significa que o e-mail
> foi aceito mas a senha foi rejeitada. `400` no endpoint de e-mail significa
> que o e-mail não existe. Isso permitiu localizar o problema em uma linha
> específica do fluxo.

---

## Técnica 6 — Verificar o `.env` vs. SSM vs. `__main__`

Um padrão recorrente em bugs de credencial é a **divergência entre ambientes**.
A tabela abaixo é o checklist mental usado:

| Fonte | Valor no momento do bug |
|---|---|
| `.env` local | `thomas.maia` (incompleto, sem domínio) |
| SSM `/legal-one/username` | `thomas.maia@advogados.com` (domínio errado) |
| `__main__` hardcoded | `thomas.maia@abladvogados.com` (correto) |

A lógica em `_get_ssm_value()` dá precedência à env var direta — por isso
localmente (com `.env`) o bug não aparecia, mas na Lambda (sem `.env`, só SSM) sim.

---

## Resumo: checklist de diagnóstico para regressões futuras

```
1. O erro é HTTP 4xx/5xx ou HTTP 200 com conteúdo de erro?
   → 4xx: problema de protocolo (cookie ausente, parâmetro faltando, credencial errada)
   → 200 com HTML de erro: problema de estado/fluxo (sessão corrompida, cookie apagado)

2. Em qual passo do fluxo o erro ocorre?
   → Separar com allow_redirects=False e inspecionar cada hop

3. O servidor está apagando algum cookie?
   → Checar Set-Cookie com expires=1970 na resposta

4. O problema é local ou só em produção?
   → Sim: divergência de configuração — comparar .env, SSM e variáveis de ambiente

5. O erro é no e-mail ou na senha?
   → /u/login/identifier 400: e-mail não existe
   → /u/login/password 400: e-mail aceito, senha rejeitada (ou e-mail errado na segunda chamada)

6. Há cookies sendo injetados manualmente? Estão no domínio correto?
   → session.cookies.set(name, value, domain='signon.thomsonreuters.com', path='/')
   → Um cookie sem domain explícito pode não ser enviado para o domínio correto
```

---

## Arquivos de diagnóstico

Os scripts e HTMLs usados no diagnóstico estão preservados em `debug_authenticator/`:

| Arquivo | O que faz |
|---|---|
| `debug_auth.py` | Primeira iteração — passos atômicos com print de cookies/redirects |
| `debug_auth2.py` | Testa variações de parâmetros do BrowserHawk |
| `debug_auth3.py` | Testa Hipótese A (cookie de migração) e Hipótese B (fluxo do novajus) |
| `debug_auth4.py` | Testa o callback OIDC (passo 5) após confirmar a Hipótese A |
| `*.html` | HTMLs salvos de cada etapa para inspeção visual no browser |

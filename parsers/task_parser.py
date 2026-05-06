# filepath: parsers/task_parser.py
"""
Parser puro para respostas HTML do endpoint de criação de tarefas do LegalOne.

Não faz I/O — recebe HTML como string e retorna tipos Python estruturados.
Testável offline com HTMLs de fixture sem precisar de sessão HTTP.

Padrão de resposta do LegalOne para criação de tarefa:
  - Título começa com "Criando nova tarefa do processo" → formulário exibido
    (pode ter erros de validação ou ser o estado inicial do form).
  - Se houver erros → <div class="validation-summary-errors"> com <li>s.
  - Se a tarefa foi criada com sucesso → o servidor redireciona e retorna
    o HTML da seção de compromissos/tarefas (título diferente).
"""
import sys
sys.path.append('.')
import logging
import re
import html as _html_mod
from dataclasses import dataclass, field
from typing import Literal

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

from core.errors import ParseError
from parsers.contact_parser import FieldError


# ── Marcador de título do formulário de criação ───────────────────────────────
# O título começa com esse prefixo quando o formulário está sendo exibido,
# seja na renderização inicial (GET) ou após rejeição (POST com erros).
_TITLE_FORM_PREFIX = "Criando nova tarefa do processo"

# Regex que extrai o nome do campo de uma mensagem de erro do LegalOne.
# Formato esperado: "... campo 'NomeDoCampo' ..."
_FIELD_NAME_RE = re.compile(r"campo '([^']+)'")

# Regex que extrai o ID da tarefa criada a partir do HTML de resposta de sucesso.
# O LegalOne emite um showMessage() com um link do tipo:
#   /agenda/Tarefas/DetailsCompromissoTarefa/102?parentId=...
_TASK_ID_RE = re.compile(r"DetailsCompromissoTarefa/(\d+)[/?]")

# Campos cujos erros são considerados bloqueantes para a criação da tarefa.
# Todos os outros são tratados como warnings (opcionais).
_BLOCKING_FIELDS = {
    "Hora de início previsto/efetivo",
    "Hora de conclusão prevista/efetiva",
    "Data de início prevista/efetiva",
    "Data de conclusão prevista/efetiva",
    "Envolvidos",
    "Vínculo",
}


# ── Tipo de retorno ───────────────────────────────────────────────────────────

@dataclass
class CreateTaskParserResult:
    """
    Resultado interpretado da resposta HTML do endpoint de criação de tarefa.

    Atributos:
        success:
            True quando a tarefa foi criada com sucesso.
            False quando o formulário foi retornado com erros ou quando o HTML
            era da listagem mas a tarefa não foi encontrada.
        task_id:
            ID interno da tarefa criada. ``None`` quando ``success=False`` ou
            quando o padrão não for encontrado no HTML.
        errors:
            Erros bloqueantes retornados pelo servidor (campos obrigatórios,
            envolvidos, etc.). Quando não-vazio, ``success=False`` e o service
            lança ``TarefaRejeitadaError``.
        source:
            Origem do HTML que gerou este resultado — informacional, para logging.
            ``"form_error"``   → formulário de criação retornado com erros.
            ``"listing"``      → HTML era a listagem de tarefas do processo.
            ``"post_success"`` → redirect de sucesso do POST (showMessage).
    """
    success: bool
    task_id: str | None = None
    errors: list[FieldError] = field(default_factory=list)
    source: Literal["form_error", "listing", "post_success"] | None = None


# ── Funções auxiliares (privadas) ─────────────────────────────────────────────

def _extract_title(html: str) -> str:
    """
    Extrai o conteúdo da tag <title>, sem o sufixo ' - Legal One'.

    Raises:
        ParseError: se a tag <title> não for encontrada.
    """
    match = re.search(r"<title>([^<]+)</title>", html)
    if not match:
        logger.error(
            "Tag <title> não encontrada no HTML de create_task(). html[:200]=%r",
            html[:200],
        )
        raise ParseError(
            "Tag <title> não encontrada no HTML de resposta do create_task(). "
            "A estrutura do site pode ter mudado."
        )
    return match.group(1).replace(" - Legal One", "").strip()


def _extract_validation_errors(html: str) -> list[FieldError]:
    """
    Extrai todos os erros do bloco <div class="validation-summary-errors">.

    Para cada <li>, tenta extrair o nome do campo com a regex
    ``campo '([^']+)'``. Se não encontrar o padrão, usa ``'desconhecido'``
    como ``field_name`` mas preserva a mensagem completa.

    Retorna lista vazia se o bloco não existir.
    """
    block_match = re.search(
        r'<div[^>]*class="validation-summary-errors"[^>]*>(.*?)</div>',
        html,
        re.DOTALL,
    )
    if not block_match:
        return []

    raw_items = re.findall(r"<li>(.*?)</li>", block_match.group(1), re.DOTALL)

    errors: list[FieldError] = []
    for raw in raw_items:
        message = _strip_tags(raw).strip()
        message = _decode_html_entities(message)

        field_match = _FIELD_NAME_RE.search(message)
        field_name = field_match.group(1) if field_match else "desconhecido"

        errors.append(FieldError(field_name=field_name, message=message))

    return errors


def _strip_tags(text: str) -> str:
    """Remove todas as tags HTML de uma string."""
    return re.sub(r"<[^>]+>", "", text)


def _decode_html_entities(text: str) -> str:
    """Decodifica todas as entidades HTML usando a stdlib.
    Exemplo: "Data de início prevista/efetiva é obrigat&#243;rio." → "Data de início prevista/efetiva é obrigatório."
    """
    return _html_mod.unescape(text)


def _extract_task_id(html: str) -> str | None:
    """
    Extrai o ID da tarefa criada a partir do HTML de resposta de sucesso.

    Procura pelo padrão ``DetailsCompromissoTarefa/<id>`` dentro da chamada
    ``showMessage(...)`` gerada pelo LegalOne após a criação bem-sucedida.

    Retorna o ID como string (ex: ``"102"``) ou ``None`` se não encontrado.
    """
    match = _TASK_ID_RE.search(html)
    return match.group(1) if match else None


# ── Função pública ────────────────────────────────────────────────────────────

def interpret_create_task_response(
    html: str,
    descricao: str,
    dt_inicial: str,
    hr_inicio: str,
    dt_final: str,
) -> CreateTaskParserResult:
    """
    Interpreta qualquer HTML retornado pelo fluxo de criação de tarefa.

    O LegalOne pode responder com três tipos diferentes de HTML após o POST:

    1. **Formulário com erros** — ``<title>`` começa com ``"Criando nova tarefa
       do processo"``: extrai os erros do ``validation-summary-errors``.
       → ``success=False, source="form_error"``

    2. **showMessage com DetailsCompromissoTarefa** — presença do padrão
       ``DetailsCompromissoTarefa/<id>`` no HTML (gerado pelo ``showMessage``
       do LegalOne após POST bem-sucedido). Verificado ANTES da listagem porque
       o HTML do POST contém ambos simultaneamente, e a listagem é paginada
       podendo não conter a tarefa recém-criada.
       → ``success=True, task_id=..., source="post_success"``

    3. **Página de listagem sem showMessage** — presença de
       ``compromisso-tarefa-cumprir-action`` mas sem ``showMessage``: ocorre
       no GET manual de verificação (``fetch_task_listing``). Busca a tarefa
       pelos critérios fornecidos na página retornada.
       → ``success=True, task_id=..., source="listing"`` se encontrada
       → ``success=False, source="listing"`` se não encontrada

    Args:
        html: HTML completo da resposta (POST ou GET de verificação).
        descricao: descrição da tarefa — usado na busca na listagem.
        dt_inicial: data de início (dd/MM/yyyy) — usado na busca na listagem.
        hr_inicio: hora de início (HH:mm ou HH:mm:ss) — usado na busca.
        dt_final: data de término (dd/MM/yyyy) — usado na busca na listagem.

    Returns:
        CreateTaskParserResult.

    Raises:
        ParseError: se o HTML for do formulário mas sem tag ``<title>``.
    """
    # ── Caso 1: formulário de criação (com ou sem erros) ─────────────────────
    # Verificamos o título apenas quando o HTML parece ser o do formulário
    # (evitamos chamar _extract_title em HTMLs que não têm o prefixo esperado).
    title_match = re.search(r"<title>([^<]+)</title>", html)
    if title_match:
        title = title_match.group(1).replace(" - Legal One", "").strip()
        if title.startswith(_TITLE_FORM_PREFIX):
            all_errors = _extract_validation_errors(html)
            if all_errors:
                logger.error(
                    "interpret_create_task_response: servidor rejeitou a tarefa com %d erro(s): %s",
                    len(all_errors),
                    [e.message for e in all_errors],
                )
            else:
                logger.warning(
                    "interpret_create_task_response: formulário retornado sem erros visíveis — html=%r",
                    html,
                )
            return CreateTaskParserResult(
                success=False,
                errors=all_errors,
                source="form_error",
            )

    # ── Caso 2: showMessage com DetailsCompromissoTarefa (POST bem-sucedido) ──
    # Verificado ANTES da listagem: o HTML do POST bem-sucedido contém ambos
    # (showMessage + listagem). O showMessage é a evidência mais direta e
    # confiável — a listagem é paginada e pode não conter a tarefa recém-criada.
    task_id = _extract_task_id(html)
    if task_id is not None:
        logger.debug(
            "interpret_create_task_response: sucesso via post_success task_id=%s", task_id,
        )
        return CreateTaskParserResult(
            success=True,
            task_id=task_id,
            source="post_success",
        )

    # ── Caso 3: página de listagem sem showMessage (GET de verificação) ───────
    # Chegamos aqui apenas quando não há showMessage — ou seja, é um GET manual
    # de verificação (fetch_task_listing), não a resposta direta do POST.
    if "compromisso-tarefa-cumprir-action" in html:
        logger.info(
            "interpret_create_task_response: HTML identificado como listagem de tarefas — buscando tarefa "
            "descricao=%r dt_inicial=%s hr_inicio=%s dt_final=%s",
            descricao, dt_inicial, hr_inicio, dt_final,
        )
        task_id = _find_task_in_listing(
            html=html,
            descricao=descricao,
            dt_inicial=dt_inicial,
            hr_inicio=hr_inicio,
            dt_final=dt_final,
        )
        if task_id is not None:
            return CreateTaskParserResult(
                success=True,
                task_id=task_id,
                source="listing",
            )
        # Listagem obtida mas tarefa não encontrada — cadastro não efetivado
        logger.warning(
            "interpret_create_task_response: listagem obtida mas tarefa não encontrada "
            "descricao=%r dt_inicial=%s dt_final=%s",
            descricao, dt_inicial, dt_final,
        )

        # with open("debug_create_task_listing.html", "w") as f:
        #     f.write(html)

        return CreateTaskParserResult(
            success=False,
            source="listing",
        )

    # ── Fallback: HTML não reconhecido ────────────────────────────────────────
    logger.warning(
        "interpret_create_task_response: HTML não reconhecido (sem showMessage, sem listagem, sem formulário). "
        "html=%r",
        html,
    )
    return CreateTaskParserResult(
        success=False,
        source=None,
    )

# if __name__ == "__main__":
    # from pprint import pprint
    # with open('/Users/thomas/Documents/projetos/legal-one-client/task_creation_response.html', 'r') as f:
    #     html = f.read()
    # r = interpret_create_task_response(html)
    # pprint(r)


# ── Busca na listagem de tarefas ──────────────────────────────────────────────

def _find_task_in_listing(html: str, descricao: str, dt_inicial: str, hr_inicio: str, dt_final: str) -> str | None:
    """
    Busca uma tarefa na listagem de tarefas do processo.

    Função auxiliar privada — chamada apenas por ``interpret_create_task_response``
    quando o HTML é identificado como a página de listagem de tarefas.
      - <a class="compromisso-tarefa-cumprir-action" data-val-id="<id>" data-val-text="<descricao>">
      - <td> com Data início no formato dd/MM/yyyy
      - <td> com Hora início no formato HH:mm:ss
      - <td> com Data término no formato dd/MM/yyyy

    Critérios de correspondência (todos devem ser satisfeitos):
      1. data-val-text (descrição) — comparação case-insensitive sem espaços extras.
      2. Data de início (dt_inicial) — formato dd/MM/yyyy.
      3. Hora de início (hr_inicio) — formato HH:mm:ss (comparação apenas HH:mm).
      4. Data de término (dt_final) — formato dd/MM/yyyy.

    Em caso de colisão (múltiplos matches), retorna o de maior data-val-id (mais recente).

    Args:
        html: HTML completo da listagem.
        descricao: descrição da tarefa (ex: "Reunião de equipe").
        dt_inicial: data de início no formato dd/MM/yyyy (ex: "20/04/2026").
        hr_inicio: hora de início no formato HH:mm ou HH:mm:ss (ex: "09:00" ou "09:00:00").
        dt_final: data de término no formato dd/MM/yyyy (ex: "20/04/2026").

    Returns:
        task_id como string (ex: "130") ou None se não encontrado.
    """
    soup = BeautifulSoup(html, "lxml")

    descricao_norm = descricao.strip().lower()
    # normalizar hora de início: comparar apenas HH:mm
    hr_inicio_norm = hr_inicio.strip()[:5]  # "09:00:00" → "09:00" / "09:00" → "09:00"

    candidates: list[tuple[int, str]] = []  # (task_id_int, task_id_str)

    for anchor in soup.select("a.compromisso-tarefa-cumprir-action"):
        val_text = _html_mod.unescape(anchor.get("data-val-text", "")).strip().lower()
        val_id_str = anchor.get("data-val-id", "")

        if val_text != descricao_norm:
            continue

        # Percorrer as células <td> da linha (<tr>) para extrair datas/hora
        row = anchor.find_parent("tr")
        if row is None:
            continue

        tds = row.find_all("td", recursive=False)
        # Estrutura da tabela (posições 0-based):
        #   0: checkbox/check
        #   1: status
        #   2: ação cumprir (âncora data-val-id)
        #   3: (vazio)
        #   4: Id (numérico)
        #   5: ID recorrência
        #   6: (vazio)
        #   7: Office 365
        #   8: Google
        #   9: Descrição (link)
        #  10: Tipo
        #  11: Prioridade
        #  12: Tipo/subtipo
        #  13: Data publicação
        #  14: Data início
        #  15: Hora início
        #  16: Data término/conclusão
        if len(tds) < 17:
            logger.debug("find_task_in_listing: linha com menos de 17 colunas, ignorando val_id=%s", val_id_str)
            continue

        td_dt_inicio = tds[14].get_text(separator=" ", strip=True)
        td_hr_inicio = tds[15].get_text(separator=" ", strip=True)
        td_dt_final  = tds[16].get_text(separator=" ", strip=True)

        # Comparar data de início
        if td_dt_inicio != dt_inicial.strip():
            logger.debug(
                "find_task_in_listing: dt_inicial não coincide val_id=%s esperado=%r encontrado=%r",
                val_id_str, dt_inicial.strip(), td_dt_inicio,
            )
            continue

        # Comparar hora de início (apenas HH:mm)
        if td_hr_inicio[:5] != hr_inicio_norm:
            logger.debug(
                "find_task_in_listing: hr_inicio não coincide val_id=%s esperado=%r encontrado=%r",
                val_id_str, hr_inicio_norm, td_hr_inicio[:5],
            )
            continue

        # Comparar data de término
        if td_dt_final != dt_final.strip():
            logger.debug(
                "find_task_in_listing: dt_final não coincide val_id=%s esperado=%r encontrado=%r",
                val_id_str, dt_final.strip(), td_dt_final,
            )
            continue

        try:
            candidates.append((int(val_id_str), val_id_str))
        except ValueError:
            logger.warning("find_task_in_listing: data-val-id não numérico: %r", val_id_str)

    if not candidates:
        logger.info(
            "find_task_in_listing: tarefa não encontrada descricao=%r dt_inicial=%s hr_inicio=%s dt_final=%s",
            descricao, dt_inicial, hr_inicio, dt_final,
        )
        return None

    # Em caso de colisão, retorna o de maior ID (mais recente)
    best_id_int, best_id_str = max(candidates, key=lambda c: c[0])
    if len(candidates) > 1:
        logger.warning(
            "find_task_in_listing: %d candidatos com mesma descrição+datas — usando o mais recente task_id=%s",
            len(candidates), best_id_str,
        )
    else:
        logger.info("find_task_in_listing: tarefa encontrada task_id=%s", best_id_str)

    return best_id_str

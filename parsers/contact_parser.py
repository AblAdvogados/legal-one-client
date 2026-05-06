# filepath: parsers/contact_parser.py
"""
Parser puro para respostas HTML do endpoint de cadastro de contatos do LegalOne.

Não faz I/O — recebe HTML como string e retorna tipos Python estruturados.
Testável offline com HTMLs de fixture sem precisar de sessão HTTP.
"""

import re
import html as _html_mod
import logging
from dataclasses import dataclass, field
from typing import Optional

from bs4 import BeautifulSoup

from core.errors import ParseError
from domain.contact import (
    Address,
    ContactDetails,
    ContactSummary,
    CustomFields,
    PersonalData,
    Phone,
)

logger = logging.getLogger(__name__)


# ── Campos obrigatórios cujo erro bloqueia a criação ─────────────────────────
# O LegalOne inclui o nome do campo entre aspas simples na mensagem de erro,
# ex.: "O conteúdo informado no campo 'CPF' não é válido."
_REQUIRED_FIELDS = {"CPF", "Nome"}

# Título retornado quando a criação foi aceita pelo servidor (sem erros obrigatórios)
_TITLE_SUCCESS = "Pesquisa de pessoas"

# Título retornado quando o formulário é exibido novamente (criação rejeitada OU
# criada com erros em campos opcionais)
_TITLE_FORM = "Criando nova pessoa"

# Regex que extrai o nome do campo de uma mensagem de erro do LegalOne.
# Formato esperado: "... campo 'NomeDoCampo' ..."
_FIELD_NAME_RE = re.compile(r"campo '([^']+)'")


# ── Tipos de retorno ──────────────────────────────────────────────────────────

@dataclass
class FieldError:
    """Erro de validação associado a um campo do formulário LegalOne."""
    field_name: str   # ex.: "CPF", "Nome", "Data de nascimento"
    message: str      # texto exato retornado pelo LegalOne


@dataclass
class CreateContactResult:
    """
    Resultado interpretado da resposta HTML do endpoint de criação de contato.

    Atributos:
        success:
            True quando o contato foi criado.
            False quando campos obrigatórios foram rejeitados.
        errors:
            Erros em campos obrigatórios (CPF, Nome) ou de duplicidade que
            impedem a criação do contato. Quando não-vazio, success=False
            e o service lança ContatoRejeitadoError.
        warnings:
            Erros em campos opcionais (ex.: data de nascimento, endereço).
            O contato foi criado mesmo assim — são informativos.
            O service combina os warnings de mapeamento local (build_payload)
            com os warnings opcionais retornados pelo servidor.
    """
    success: bool
    errors: list[FieldError] = field(default_factory=list)
    warnings: list[FieldError] = field(default_factory=list)


# ── Funções auxiliares ────────────────────────────────────────────────────────

def _extract_title(html: str) -> str:
    """Extrai o conteúdo da tag <title>, sem o sufixo ' - Legal One'."""
    match = re.search(r"<title>([^<]+)</title>", html)
    if not match:
        logger.error(
            "_extract_title: <title> não encontrada — html[:500]=%s",
            html[:500],
        )
        raise ParseError(
            "Tag <title> não encontrada no HTML de resposta do create_contact(). "
            "A estrutura do site pode ter mudado."
        )
    return match.group(1).replace(" - Legal One", "").strip()


def _extract_validation_errors(html: str) -> list[FieldError]:
    """
    Extrai todos os erros do bloco <div class="validation-summary-errors">.

    Para cada <li>, tenta extrair o nome do campo com a regex
    `campo '([^']+)'`. Se não encontrar o padrão, usa 'desconhecido'
    como field_name mas preserva a mensagem completa.

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
        # Remove tags HTML internas (ex.: <span>) e decodifica entidades básicas
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
    """Decodifica todas as entidades HTML usando a stdlib."""
    return _html_mod.unescape(text)


# ── Função pública ────────────────────────────────────────────────────────────

def interpret_create_response(html: str) -> CreateContactResult:
    """
    Interpreta o HTML retornado pelo endpoint POST /contatos/Pessoas/Edit.

    Lógica:
      - Extrai todos os erros do bloco validation-summary-errors.
      - Erros nos campos obrigatórios (CPF, Nome) sinalizam que a criação foi
        bloqueada: retorna success=False com esses erros em ``errors``
        para que o service lance ContatoRejeitadoError.
      - Erros nos demais campos são opcionais: o contato foi criado mesmo assim
        e são retornados em ``warnings``.
      - success=True quando nenhum erro obrigatório está presente.

    Args:
        html: HTML completo da resposta do servidor.

    Returns:
        CreateContactResult.
          - ``errors``   — erros bloqueantes (campos obrigatórios rejeitados).
          - ``warnings`` — erros em campos opcionais (informativos).

    Raises:
        ParseError: se a tag <title> não for encontrada no HTML.
    """
    _extract_title(html)  # valida que o HTML é da página esperada
    all_errors = _extract_validation_errors(html)

    logger.debug(
        "interpret_create_response: validation_errors=%d — fields=%s",
        len(all_errors), [e.field_name for e in all_errors],
    )

    required_errors = [
        e for e in all_errors if e.field_name in _REQUIRED_FIELDS
    ]
    optional_errors = [
        e for e in all_errors if e.field_name not in _REQUIRED_FIELDS
    ]

    if required_errors:
        # Contato NÃO foi criado — campos obrigatórios rejeitados.
        return CreateContactResult(
            success=False,
            errors=required_errors,
            warnings=optional_errors,
        )

    return CreateContactResult(
        success=True,
        errors=[],
        warnings=optional_errors,
    )


# ── Helpers de parse para lookup ─────────────────────────────────────────────

def _panel_value(soup: BeautifulSoup, label_text: str) -> Optional[str]:
    """
    Localiza um bloco .value dentro de um .row que contenha um .header com
    o texto `label_text` (case-insensitive, espaços normalizados).

    Retorna None se o bloco não existir ou se o texto for vazio.
    """
    target = label_text.strip().lower()
    for header in soup.select(".header"):
        header_text = header.get_text(strip=True).lower()
        if header_text == target:
            value_div = header.find_next_sibling(class_="value")
            if value_div:
                text = value_div.get_text(separator=" ", strip=True)
                return text or None
    return None


def _panel_first_value(soup: BeautifulSoup, panel_title: str) -> Optional[str]:
    """
    Localiza um painel pelo seu .panel-title e retorna o texto do primeiro
    .value encontrado dentro dele.

    Usado para painéis como "Observações" onde o .header está vazio.
    """
    target = panel_title.strip().lower()
    for panel in soup.select(".edit-panel-responsive-wrapper"):
        title_el = panel.select_one(".panel-title")
        if title_el and title_el.get_text(strip=True).lower() == target:
            value_el = panel.select_one(".value")
            if value_el:
                text = value_el.get_text(separator="\n", strip=True)
                return text or None
    return None


def _contact_id_from_form(soup: BeautifulSoup) -> str:
    """Extrai o id do contato do atributo `id` do <form> principal."""
    form = soup.find("form", id=True)
    if not form:
        raise ParseError(
            "Tag <form id='...'> nao encontrada no HTML da modal. "
            "A estrutura do site pode ter mudado."
        )
    return form["id"]


# ── Funcoes publicas de lookup ────────────────────────────────────────────────

def parse_contact_modal(html: str) -> ContactSummary:
    """
    Extrai dados resumidos do HTML retornado por
    GET /contatos/Contatos/ModalPersonInvolveds.

    Paineis esperados: "Dados principais", "Endereco", "Telefone e e-mail",
    "Observacoes".

    Args:
        html: HTML completo da resposta.

    Returns:
        ContactSummary com os campos disponiveis preenchidos.

    Raises:
        ParseError: se o <form id="..."> nao for encontrado.
    """
    soup = BeautifulSoup(html, "html.parser")
    contact_id = _contact_id_from_form(soup)

    # ── Dados pessoais ────────────────────────────────────────────────────────
    dados_pessoais = PersonalData(
        cpf=_panel_value(soup, "CPF") or "",
        nome=_panel_value(soup, "Nome") or "",
        observacao=_panel_first_value(soup, "Observações") or "",
    )

    # ── Telefone ──────────────────────────────────────────────────────────────
    celular = _panel_value(soup, "Celular")
    telefone = Phone(celular=celular) if celular else None

    # ── E-mail ────────────────────────────────────────────────────────────────
    email = _panel_value(soup, "E-mail")

    # ── Endereço ──────────────────────────────────────────────────────────────
    addr_fields = {
        "logradouro": _panel_value(soup, "Logradouro"),
        "numero": _panel_value(soup, "Número"),
        "bairro": _panel_value(soup, "Bairro"),
        "cep": _panel_value(soup, "CEP"),
        "cidade": _panel_value(soup, "Cidade"),
        "uf": _panel_value(soup, "UF"),
        "pais": _panel_value(soup, "País"),
    }
    endereco = Address(**addr_fields) if any(addr_fields.values()) else None

    return ContactSummary(
        contact_id=contact_id,
        dados_pessoais=dados_pessoais,
        telefone=telefone,
        email=email,
        endereco=endereco,
    )


def parse_contact_details(html: str) -> ContactDetails:
    """
    Extrai dados completos do HTML retornado por
    GET /contatos/Pessoas/Details/{id}.

    Inclui campos personalizados alem do que o modal expoe.
    O ID do contato e inferido do link de edicao na barra lateral
    (/contatos/Pessoas/Edit/{id}).

    Args:
        html: HTML completo da resposta.

    Returns:
        ContactDetails com os campos disponiveis preenchidos.

    Raises:
        ParseError: se o ID do contato nao puder ser extraido do HTML.
    """
    soup = BeautifulSoup(html, "html.parser")

    edit_link = soup.find("a", href=lambda h: h and "/Pessoas/Edit/" in h)
    if not edit_link:
        raise ParseError(
            "Link de edicao (/Pessoas/Edit/{id}) nao encontrado no HTML de detalhes. "
            "A estrutura do site pode ter mudado."
        )
    contact_id = edit_link["href"].split("/Pessoas/Edit/")[1].split("?")[0]

    # ── Dados pessoais ────────────────────────────────────────────────────────
    nome = (_panel_value(soup, "Nome") or "").strip()

    data_nascimento = _panel_value(soup, "Data de nascimento")
    if data_nascimento:
        data_nascimento = data_nascimento.split("\n")[0].strip() or None

    dados_pessoais = PersonalData(
        cpf=_panel_value(soup, "CPF") or "",
        nome=nome,
        data_nascimento=data_nascimento or "",
    )

    # ── Telefone ──────────────────────────────────────────────────────────────
    celular = _panel_value(soup, "Celular")
    telefone = Phone(celular=celular) if celular else None

    # ── E-mail ────────────────────────────────────────────────────────────────
    email = _panel_value(soup, "E-mail")

    # ── Endereço ──────────────────────────────────────────────────────────────
    addr_fields = {
        "logradouro": _panel_value(soup, "Logradouro"),
        "numero": _panel_value(soup, "Número"),
        "complemento": _panel_value(soup, "Complemento"),
        "bairro": _panel_value(soup, "Bairro"),
        "cep": _panel_value(soup, "CEP"),
        "cidade": _panel_value(soup, "Cidade"),
        "uf": _panel_value(soup, "UF"),
        "pais": _panel_value(soup, "País"),
    }
    endereco = Address(**addr_fields) if any(addr_fields.values()) else None

    # ── Campos personalizados ─────────────────────────────────────────────────
    custom: dict[str, Optional[str]] = {}
    for row in soup.select(".custom-panel .row"):
        label_el = row.select_one(".label label.word-breaker")
        field_el = row.select_one(".field.custom-field")
        if label_el and field_el:
            key = label_el.get_text(strip=True)
            value = field_el.get_text(separator=" ", strip=True) or None
            if value:
                value = re.sub(r"\s*\$\.\s*datepicker.*", "", value, flags=re.DOTALL).strip() or None
            custom[key] = value

    custom_fields = CustomFields(
        tag=custom.get("Tag"),
        cid=custom.get("CID"),
        referencia=custom.get("Referência"),
        link_drive=custom.get("Link da pasta"),
        data_vencimento_kit=custom.get("Data Vencimento Kit"),
        data_vencimento_comprovante=custom.get("Data Vencimento Comprovante"),
        classificacao_backoffice=custom.get("Classificação Backoffice"),
        natureza_do_acidente=custom.get("Natureza do acidente"),
        tratamento_da_lesao=custom.get("Tratamento da Lesão"),
        tramitacao_prioritaria=custom.get("Tramitação prioritária"),
    ) if custom else None

    return ContactDetails(
        contact_id=contact_id,
        dados_pessoais=dados_pessoais,
        telefone=telefone,
        email=email,
        endereco=endereco,
        custom_fields=custom_fields,
    )

"""
service.py — orquestra a criação de contatos no LegalOne.

Responsabilidades:
  - Resolver mapeamentos delegando para infrastructure/lookup/.
  - Produzir um ContactPayload com todos os valores já resolvidos.
  - Degradar graciosamente blocos opcionais (endereço, campos personalizados):
    falha no mapeamento → omite o bloco + registra FieldError, sem impedir o cadastro.
  - Delegar a chamada HTTP ao ContactsCrawler.
  - Interpretar a resposta HTML com interpret_create_response().
  - Lançar ContatoRejeitadoError quando o servidor rejeitar campos obrigatórios.

NÃO pertence ao service:
  - Montagem de tuplas multipart/form-data  → ContactsCrawler
  - Bloco fixo de monitoramento             → ContactsCrawler
  - Nomes internos do LegalOne              → infrastructure/lookup/select_mapper.py
  - I/O de JSONs de mapeamento              → infrastructure/lookup/
"""

from typing import Optional, Union, List # , TYPE_CHECKING

import logging
import time

from infrastructure.crawler.contacts import ContactsCrawler

from core.errors import (
    ContatoNaoEncontradoError,
    ContatoRejeitadoError,
    EnderecoIncompletoError,
    MappingError,
)
from domain.contact import ContactDetails, ContactSummary, CreateContactInput
from infrastructure.lookup.city_mapper import map_cidade_to_id
from infrastructure.lookup.state_mapper import map_uf_to_id
from infrastructure.lookup.select_mapper import (
    FN_CLASS_BACK,
    FN_NAT_ACIDENTE,
    FN_TRAT_LESAO,
    FN_TRAMIT_PRIOR,
    map_select_to_id,
)
from parsers.contact_parser import (
    CreateContactResult,
    FieldError,
    interpret_create_response,
    parse_contact_modal,
    parse_contact_details,
)
from services.contact.dto import (
    ContactPayload,
    ResolvedAddress,
    ResolvedPhone,
    ResolvedSelectField,
    ResolvedTextField,
)
from services.search_service import SearchService
from services.contact.dto import GridContact, RowGridContact

logger = logging.getLogger(__name__)

# ── Nomes internos dos campos de texto livre ──────────────────────────────────
_FN_TAG        = "Tag_PessoaFisicaEntitySchema_p3699_o"
_FN_LINK_DRIVE = "LinkDaPasta_PessoaFisicaEntitySchema_p3700_o"
_FN_DT_KIT     = "DataVencimentoKit_PessoaFisicaEntitySchema_p3701_o"
_FN_DT_COMP    = "DataVencimentoComprovante_PessoaFisicaEntitySchema_p3702_o"
_FN_CID        = "CID_PessoaFisicaEntitySchema_p3706_o"
_FN_REFERENCIA = "Referencia_PessoaFisicaEntitySchema_p3716_o"


# ── Helpers privados ──────────────────────────────────────────────────────────

def _resolve_sexo(sexo: Optional[str]) -> str:
    if not sexo:
        return ""
    s = sexo.lower()
    if s in ("m", "masculino"):
        return "0"
    if s in ("f", "feminino"):
        return "1"
    return ""


# ── Construção do DTO ─────────────────────────────────────────────────────────

def build_payload(dados: CreateContactInput) -> tuple[ContactPayload, list[FieldError]]:
    """
    Converte um CreateContactInput num ContactPayload com todos os valores
    já resolvidos (IDs internos do LegalOne).

    Blocos opcionais que falharem no mapeamento são omitidos do payload e
    registrados como FieldError em warnings — sem impedir o cadastro.

    Returns:
        (payload, warnings)
    """
    warnings: list[FieldError] = []

    dp = dados.dados_pessoais
    payload = ContactPayload(
        cpf=dp.cpf,
        nome=dp.nome,
        sexo=_resolve_sexo(dp.sexo),
        data_nascimento=dp.data_nascimento or "",
        observacao=dp.observacao or "",
    )

    # ── Telefones (nunca falham) ──────────────────────────────────────────────
    if dados.telefones:
        t = dados.telefones
        if t.celular:
            payload.telefones.append(ResolvedPhone(tipo_id="3", numero=t.celular))
        if t.telefone_residencial:
            payload.telefones.append(ResolvedPhone(tipo_id="1", numero=t.telefone_residencial))

    # ── Endereço (opcional — degrada se mapeamento falhar) ────────────────────
    if dados.endereco:
        e = dados.endereco
        try:
            if not all([e.cep, e.logradouro, e.cidade, e.uf, e.pais]):
                raise EnderecoIncompletoError()
            
            # Após a validação acima, os campos obrigatórios são str (não None).
            assert e.cep and e.logradouro and e.cidade and e.uf and e.pais
            
            payload.endereco = ResolvedAddress(
                cep=e.cep,
                logradouro=e.logradouro,
                numero=e.numero or "",
                complemento=e.complemento or "",
                bairro=e.bairro or "",
                cidade_texto=e.cidade,
                cidade_id=map_cidade_to_id(e.cidade),
                uf_texto=e.uf.upper(),
                uf_id=map_uf_to_id(e.uf),
                pais_texto=e.pais or "Brasil",
                pais_id="31",
            )
        except (MappingError, EnderecoIncompletoError) as exc:
            logger.info("build_payload: campo opcional degradado — field=Endereço reason=%s", exc)
            warnings.append(FieldError(field_name="Endereço", message=str(exc)))

    # ── Campos personalizados (opcional — cada um degrada individualmente) ────
    if dados.custom_fields:
        pf = dados.custom_fields

        text_fields = [
            (pf.tag,                         _FN_TAG,        "tag"),
            (pf.cid,                         _FN_CID,        "cid"),
            (pf.referencia,                  _FN_REFERENCIA, "referencia"),
            (pf.link_drive,                  _FN_LINK_DRIVE, "link_drive"),
            (pf.data_vencimento_kit,         _FN_DT_KIT,     "data_vencimento_kit"),
            (pf.data_vencimento_comprovante, _FN_DT_COMP,    "data_vencimento_comprovante"),
        ]
        for value, field_name, _ in text_fields:
            if value is not None:
                payload.campos_texto.append(ResolvedTextField(field_name=field_name, value=value))

        select_fields = [
            (pf.classificacao_backoffice, FN_CLASS_BACK,   "classificacao_backoffice"),
            (pf.natureza_do_acidente,     FN_NAT_ACIDENTE, "natureza_do_acidente"),
            (pf.tratamento_da_lesao,      FN_TRAT_LESAO,   "tratamento_da_lesao"),
            (pf.tramitacao_prioritaria,   FN_TRAMIT_PRIOR, "tramitacao_prioritaria"),
        ]
        for value, field_name, attr_name in select_fields:
            if value is not None:
                try:
                    option_id = map_select_to_id(field_name, value)
                    payload.campos_select.append(
                        ResolvedSelectField(
                            field_name=field_name,
                            label=value,
                            option_id=option_id,
                        )
                    )
                except MappingError as exc:
                    logger.info("build_payload: campo opcional degradado — field=%s reason=%s", attr_name, exc)
                    warnings.append(FieldError(field_name=attr_name, message=str(exc)))

    return payload, warnings


# ── Classe de serviço ─────────────────────────────────────────────────────────

class ContactService:
    """
    Orquestra a criação de contatos no LegalOne.

    Fluxo:
      1. build_payload() — resolve mapeamentos via infrastructure/lookup/; coleta warnings.
      2. crawler.create_contact(payload) — executa o POST HTTP.
      3. interpret_create_response() — interpreta o HTML de resposta.
      4. Combina warnings locais (build_payload) + warnings do servidor.
      5. Lança ContatoRejeitadoError se CPF ou Nome foram rejeitados.
    """

    def __init__(self, crawler: ContactsCrawler) -> None:
        self._crawler = crawler

    def create_contact(self, dados: CreateContactInput) -> CreateContactResult:
        """
        Cria um novo contato (pessoa física) no LegalOne.

        Returns:
            CreateContactResult com warnings contendo tanto os avisos de
            mapeamento local quanto os erros opcionais retornados pelo servidor.

        Raises:
            ContatoRejeitadoError: quando o servidor rejeita CPF ou Nome.
            CrawlerError: para erros HTTP retornados pelo LegalOne.
            AuthenticationError: falhas de sessão.
        """
        cpf_mascarado = dados.dados_pessoais.cpf[:3] + ".***.***-**"
        logger.info("create_contact iniciado — cpf=%s", cpf_mascarado)
        t0 = time.perf_counter()

        payload, build_warnings = build_payload(dados)

        logger.debug("create_contact: payload montado, %d warning(s) de build", len(build_warnings))

        html = self._crawler.create_contact(payload)

        elapsed_crawler = time.perf_counter() - t0
        logger.info(
            "create_contact: crawler respondeu em %.2fs — html_len=%d",
            elapsed_crawler, len(html),
        )

        result = interpret_create_response(html)

        if result.errors:
            logger.warning(
                "create_contact: contato rejeitado pelo LegalOne — cpf=%s errors=%s",
                cpf_mascarado, [e.field_name for e in result.errors],
            )
            raise ContatoRejeitadoError(
                errors=[e.message for e in result.errors]
            )

        elapsed_total = time.perf_counter() - t0
        logger.info(
            "create_contact: sucesso — cpf=%s warnings=%d tempo_total=%.2fs",
            cpf_mascarado, len(build_warnings) + len(result.warnings), elapsed_total,
        )

        return CreateContactResult(
            success=result.success,
            errors=[],
            warnings=build_warnings + result.warnings,
        )

    def lookup_grid_contact(self, term: str) -> GridContact:
        """
        Busca contatos pelo nome ou CPF.
        Observação: Retorna correspondência por continência do termo de busca no nome ou CPF do contato.
        Exemplo: termo "marcos" retorna contatos com nome "Marcos Silva" e CPF "123.456.789-00".

        Args:
            term: Nome ou CPF do contato a ser buscado.

        Returns:
            Lista de LookupResult com os contatos encontrados.
        """
        results = self._crawler.lookup_grid_contact(term)
        return GridContact(
            contacts=[
                RowGridContact(contact_id=r['ContatoId'], cpf=r['ContatoCPF_CNPJ'], name=r['ContatoNome'])
                for r in results.get('Rows', [])
            ],
            count=results.get('Count')
        )

    def get_contact_info_by_cpf(
        self, cpf: str, summary: bool = True
    ) -> Union[ContactSummary, ContactDetails]:
        """
        Busca um contato pelo CPF usando a busca global e retorna seus dados.

        Internamente:
          1. Chama ContactsCrawler.lookup_grid_contact(cpf) para obter o contact_id.
          2. Extrai o contact_id do dicionário do primeiro resultado.
          3. Delega para get_contact(contact_id, summary).
          4. Faz o parse do HTML retornado para extrair os dados estruturados.

        Args:
            cpf: CPF do contato no formato ###.###.###-##.
            summary: True  → retorna ContactSummary (modal).
                     False → retorna ContactDetails (página completa).

        Returns:
            ContactSummary ou ContactDetails dependendo do parâmetro `summary`.

        Raises:
            ContatoNaoEncontradoError: se nenhum contato for encontrado para o CPF.
            ParseError: se a estrutura do HTML retornado for inesperada.
            CrawlerError: para erros HTTP retornados pelo LegalOne.
            AuthenticationError: falhas de sessão.
        """
        # adicionar uma validação simples do formato do CPF antes de chamar o crawler 
        # para evitar de pesquisar por CPFs inválidos ou por nome de contato, 
        # já que o lookup_grid_contact faz busca por continência no nome e CPF.

        result = self._crawler.lookup_grid_contact(cpf)

        if result.get('Count') < 1:
            raise ContatoNaoEncontradoError(cpf=cpf)
        contact_id = result.get('Rows')[0].get('ContatoId')

        if summary:
            html = self._crawler.get_contact_modal(contact_id)
            return parse_contact_modal(html)
        else:
            html = self._crawler.get_contact_details(contact_id)
            return parse_contact_details(html)

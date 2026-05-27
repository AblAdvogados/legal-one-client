# filepath: app/routers/contacts.py
"""
Router FastAPI para a rota /contacts.

Responsabilidades:
  - Receber e validar o body JSON via CreateContactRequest (schema Pydantic).
  - Converter o schema para os tipos de domínio (CreateContactInput).
  - Chamar ContactService.create_contact().
  - Converter CreateContactResult → CreateContactResponse.
  - Retornar 200 mesmo quando há warnings (erros em campos opcionais).

NÃO contém lógica de negócio nem acessa infraestrutura diretamente.
"""

from fastapi import APIRouter, Depends, Query
from typing import Union
import logging

from app.schemas.contact_schemas import (
    AddressResponse,
    ContactDetailsResponse,
    ContactSummaryResponse,
    CreateContactRequest,
    CreateContactResponse,
    CustomFieldsResponse,
    FieldErrorDetail,
    GridContactResponse,
    PersonalDataResponse,
    PhoneResponse,
    RowGridContactResponse,
)
from services.contact.service import ContactService
from services.lawsuit.lawsuit_service import LawsuitService
from domain.contact import (
    Address,
    CreateContactInput,
    CustomFields,
    PersonalData,
    Phone,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Dependency ────────────────────────────────────────────────────────────────

def get_contact_service() -> ContactService:
    """
    Fornece uma instância de ContactService com sessão HTTP autenticada.
    Substituída por mock nos testes.
    """
    from app.dependencies import contact_service
    return contact_service


def get_lawsuit_service() -> LawsuitService:
    """
    Fornece uma instância de LawsuitService com sessão HTTP autenticada.
    Substituída por mock nos testes.
    """
    from app.dependencies import lawsuit_service
    return lawsuit_service


# ── Conversor schema → domain types ──────────────────────────────────────────

def _to_service_input(req: CreateContactRequest) -> CreateContactInput:
    """Converte CreateContactRequest (schema Pydantic) → CreateContactInput (domain)."""
    dp = req.dados_pessoais
    dados_pessoais = PersonalData(
        cpf=dp.cpf,
        nome=dp.nome,
        data_nascimento=dp.data_nascimento or "",
        sexo=dp.sexo or "",
        observacao=dp.observacao or "",
        email=dp.email,
        rg=dp.rg,
        estado_civil=dp.estado_civil,
        profissao=dp.profissao,
    )

    telefones = None
    if req.telefones:
        telefones = Phone(
            celular=req.telefones.celular,
            telefone_residencial=req.telefones.telefone_residencial,
        )

    endereco = None
    if req.endereco:
        e = req.endereco
        endereco = Address(
            cep=e.cep,
            logradouro=e.logradouro,
            cidade=e.cidade,
            uf=e.uf,
            bairro=e.bairro,
            pais=e.pais,
            numero=e.numero,
            complemento=e.complemento,
        )

    custom_fields = None
    if req.custom_fields:
        pf = req.custom_fields
        custom_fields = CustomFields(
            tag=pf.tag,
            cid=pf.cid,
            referencia=pf.referencia,
            link_drive=pf.link_drive,
            data_vencimento_kit=pf.data_vencimento_kit,
            data_vencimento_comprovante=pf.data_vencimento_comprovante,
            classificacao_backoffice=pf.classificacao_backoffice,
            natureza_do_acidente=pf.natureza_do_acidente,
            tratamento_da_lesao=pf.tratamento_da_lesao,
            tramitacao_prioritaria=pf.tramitacao_prioritaria,
        )

    return CreateContactInput(
        dados_pessoais=dados_pessoais,
        telefones=telefones,
        endereco=endereco,
        custom_fields=custom_fields,
    )


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("", response_model=CreateContactResponse)
async def create_contact(
    body: CreateContactRequest,
    service: ContactService = Depends(get_contact_service),
) -> CreateContactResponse:
    """
    Cria um novo contato (pessoa física) no LegalOne.

    - **200** — contato criado; `warnings` lista campos opcionais
      que foram ignorados pelo servidor (ex.: endereço com UF inválida).
    - **422** — dados obrigatórios inválidos (CPF, Nome) ou erro de mapeamento
      detectado antes do POST.
    - **502** — erro HTTP ao acessar o LegalOne.
    - **503** — falha de sessão ou autenticação.
    """
    input_data = _to_service_input(body)
    result = service.create_contact(input_data)

    logger.info(
        "POST /contacts concluído — success=%s, warnings=%d",
        result.success, len(result.warnings),
    )

    return CreateContactResponse(
        success=result.success,
        warnings=[
            FieldErrorDetail(field_name=e.field_name, message=e.message)
            for e in result.warnings
        ],
    )

@router.get(
    "/lookup",
    response_model=GridContactResponse,
    summary="Busca contatos por nome ou CPF via LookupGridContato",
)
async def lookup_grid_contact(
    term: str = Query(description="Nome ou CPF do contato (busca por continência)"),
    service: ContactService = Depends(get_contact_service),
) -> GridContactResponse:
    """
    Busca contatos no LegalOne usando o endpoint interno `LookupGridContato`.

    Diferente de uma listagem padrão, este endpoint consulta o grid de lookup
    do LegalOne — a busca é por **continência**: `term=marcos` retorna todos
    os contatos cujo nome ou CPF contenha "marcos".

    - **200** — lista (possivelmente vazia) de contatos encontrados.
    - **502** — erro HTTP ao acessar o LegalOne.
    - **503** — falha de sessão ou autenticação.
    """
    result = service.lookup_grid_contact(term=term)
    return GridContactResponse(
        total=result.count,
        contacts=[
            RowGridContactResponse(
                contact_id=c.contact_id,
                name=c.name,
                cpf=c.cpf,
            )
            for c in result.contacts
        ],
    )


@router.get(
    "/{cpf}",
    response_model=Union[ContactSummaryResponse, ContactDetailsResponse],
    summary="Retorna dados de um contato pelo CPF",
)
async def get_contact(
    cpf: str,
    summary: bool = Query(
        default=True,
        description=(
            "True → retorna resumo via modal (mais rápido, menos campos). "
            "False → retorna dados completos via página de detalhes."
        ),
    ),
    service: ContactService = Depends(get_contact_service),
) -> Union[ContactSummaryResponse, ContactDetailsResponse]:
    """
    Localiza um contato no LegalOne pelo CPF.

    O CPF deve estar no formato ###.###.###-## (URL-encoded: `654.873.627-34`
    → `/contacts/654.873.627-34`).

    - **200 / summary=true**  — ContactSummaryResponse.
    - **200 / summary=false** — ContactDetailsResponse.
    - **404** — nenhum contato encontrado para o CPF informado.
    - **502** — erro HTTP ao acessar o LegalOne ou HTML inesperado.
    - **503** — falha de sessão ou autenticação.
    """
    result = service.get_contact_info_by_cpf(cpf=cpf, summary=summary)
    return _contact_to_response(result, summary)


# ── Conversor domain → response (compartilhado pelos dois endpoints) ──────────

def _contact_to_response(
    result,
    summary: bool,
) -> Union[ContactSummaryResponse, ContactDetailsResponse]:
    """Converte ContactSummary ou ContactDetails → schema de resposta."""
    if summary:
        from domain.contact import ContactSummary
        assert isinstance(result, ContactSummary)
        return ContactSummaryResponse(
            contact_id=result.contact_id,
            dados_pessoais=PersonalDataResponse(
                cpf=result.dados_pessoais.cpf,
                nome=result.dados_pessoais.nome,
                observacao=result.dados_pessoais.observacao or None,
            ),
            telefones=PhoneResponse(
                celular=result.telefone.celular,
            ) if result.telefone else None,
            email=result.email,
            endereco=AddressResponse(
                cep=result.endereco.cep,
                logradouro=result.endereco.logradouro,
                cidade=result.endereco.cidade,
                uf=result.endereco.uf,
                bairro=result.endereco.bairro,
                pais=result.endereco.pais,
                numero=result.endereco.numero,
            ) if result.endereco else None,
        )
    else:
        from domain.contact import ContactDetails
        assert isinstance(result, ContactDetails)
        return ContactDetailsResponse(
            contact_id=result.contact_id,
            dados_pessoais=PersonalDataResponse(
                cpf=result.dados_pessoais.cpf,
                nome=result.dados_pessoais.nome,
                data_nascimento=result.dados_pessoais.data_nascimento or None,
            ),
            telefones=PhoneResponse(
                celular=result.telefone.celular,
            ) if result.telefone else None,
            email=result.email,
            endereco=AddressResponse(
                cep=result.endereco.cep,
                logradouro=result.endereco.logradouro,
                complemento=result.endereco.complemento,
                cidade=result.endereco.cidade,
                uf=result.endereco.uf,
                bairro=result.endereco.bairro,
                pais=result.endereco.pais,
                numero=result.endereco.numero,
            ) if result.endereco else None,
            custom_fields=CustomFieldsResponse(
                tag=result.custom_fields.tag,
                cid=result.custom_fields.cid,
                referencia=result.custom_fields.referencia,
                link_drive=result.custom_fields.link_drive,
                data_vencimento_kit=result.custom_fields.data_vencimento_kit,
                data_vencimento_comprovante=result.custom_fields.data_vencimento_comprovante,
                classificacao_backoffice=result.custom_fields.classificacao_backoffice,
                natureza_do_acidente=result.custom_fields.natureza_do_acidente,
                tratamento_da_lesao=result.custom_fields.tratamento_da_lesao,
                tramitacao_prioritaria=result.custom_fields.tramitacao_prioritaria,
            ) if result.custom_fields else None,
        )

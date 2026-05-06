# filepath: app/schemas/contact_schemas.py
"""
Schemas Pydantic para a rota /contacts.

Independentes dos dataclasses de domain/ — são o contrato público da API.
Validam formato antes de qualquer lógica de negócio.
"""

import re
from pydantic import BaseModel, field_validator


# ── Request ───────────────────────────────────────────────────────────────────

class PersonalDataSchema(BaseModel):
    cpf: str
    nome: str
    data_nascimento: str | None = None
    sexo: str | None = None        # 'M' | 'F' (case-insensitive)
    observacao: str | None = None

    @field_validator("cpf")
    @classmethod
    def validar_cpf(cls, v: str) -> str:
        if not re.fullmatch(r"\d{3}\.\d{3}\.\d{3}-\d{2}", v.strip()):
            raise ValueError("CPF deve estar no formato ###.###.###-##.")
        return v.strip()

    @field_validator("nome")
    @classmethod
    def validar_nome(cls, v: str) -> str:
        partes = v.strip().split()
        if len(partes) < 2:
            raise ValueError("Nome deve conter pelo menos duas palavras.")
        return v.strip()

    @field_validator("sexo")
    @classmethod
    def validar_sexo(cls, v: str | None) -> str | None:
        if v is None or v.strip() == "":
            return v
        if v.upper().strip() not in ("M", "F", "MASCULINO", "FEMININO", ""):
            raise ValueError("Sexo, se informado, deve ser 'M', 'Masculino', 'F' ou 'Feminino'. Mayúsculas e minúsculas são ignoradas.")
        return v.upper()


class PhonesSchema(BaseModel):
    celular: str | None = None
    telefone_residencial: str | None = None


class AddressSchema(BaseModel):
    cep: str
    logradouro: str
    cidade: str
    uf: str
    bairro: str = ""
    pais: str = "Brasil"
    numero: str = ""
    complemento: str = ""

    # @field_validator("uf")
    # @classmethod
    # def validar_uf(cls, v: str) -> str:
    #     if not re.fullmatch(r"[A-Za-z]{2}", v.strip()):
    #         raise ValueError("UF deve conter exatamente 2 letras (ex.: 'SP').")
    #     return v.strip().upper()


class CustomFieldsSchema(BaseModel):
    """
    Campos personalizados — cada atributo é opcional (None = não enviar).

    Texto livre:
        tag, cid, referencia, link_drive,
        data_vencimento_kit, data_vencimento_comprovante

    SelectOne (valores aceitos definidos em infrastructure/lookup/select_mapper.py):
        classificacao_backoffice : '0' | '1' | '2' | '3'
        natureza_do_acidente     : 'Trabalho' | 'Qualquer natureza'
        tratamento_da_lesao      : 'Cirúrgico' | 'Conservador'
        tramitacao_prioritaria   : 'Sim' | 'Não'
    """
    tag: str | None = None
    cid: str | None = None
    referencia: str | None = None
    link_drive: str | None = None
    data_vencimento_kit: str | None = None
    data_vencimento_comprovante: str | None = None
    classificacao_backoffice: str | None = None
    natureza_do_acidente: str | None = None
    tratamento_da_lesao: str | None = None
    tramitacao_prioritaria: str | None = None


class CreateContactRequest(BaseModel):
    dados_pessoais: PersonalDataSchema
    telefones: PhonesSchema | None = None
    endereco: AddressSchema | None = None
    custom_fields: CustomFieldsSchema | None = None


# ── Response ──────────────────────────────────────────────────────────────────

class FieldErrorDetail(BaseModel):
    """Erro de validação associado a um campo específico — espelha FieldError do parser."""
    field_name: str
    message: str


class CreateContactResponse(BaseModel):
    """
    Resposta de POST /contacts.

    Sempre retorna 200. Campos opcionais com erro são listados em
    warnings — o contato foi criado mesmo assim.
    """
    success: bool
    warnings: list[FieldErrorDetail] = []


# ── Lookup responses ──────────────────────────────────────────────────────────

class AddressResponse(BaseModel):
    """Endereço extraído do LegalOne."""
    cep: str | None = None
    logradouro: str | None = None
    cidade: str | None = None
    uf: str | None = None
    bairro: str | None = None
    pais: str | None = None
    numero: str | None = None
    complemento: str | None = None


class PhoneResponse(BaseModel):
    """Telefones extraídos do LegalOne."""
    celular: str | None = None
    telefone_residencial: str | None = None


class PersonalDataResponse(BaseModel):
    """Dados pessoais extraídos do LegalOne."""
    cpf: str
    nome: str
    data_nascimento: str | None = None
    sexo: str | None = None
    observacao: str | None = None


class CustomFieldsResponse(BaseModel):
    """Campos personalizados extraídos do LegalOne."""
    tag: str | None = None
    cid: str | None = None
    referencia: str | None = None
    link_drive: str | None = None
    data_vencimento_kit: str | None = None
    data_vencimento_comprovante: str | None = None
    classificacao_backoffice: str | None = None
    natureza_do_acidente: str | None = None
    tratamento_da_lesao: str | None = None
    tramitacao_prioritaria: str | None = None


class ContactSummaryResponse(BaseModel):
    """
    Resposta de GET /contacts/{id}?summary=true e de POST /lookup

    Dados extraídos da modal do LegalOne (mais rápido, menos campos).
    """
    contact_id: str
    dados_pessoais: PersonalDataResponse
    telefones: PhoneResponse | None = None
    email: str | None = None
    endereco: AddressResponse | None = None


class ContactDetailsResponse(BaseModel):
    """
    Resposta de GET /contacts/{id}?summary=false e de POST /lookup

    Dados completos extraídos da página de detalhes do LegalOne.
    Inclui campos personalizados e data de nascimento.
    """
    contact_id: str
    dados_pessoais: PersonalDataResponse
    telefones: PhoneResponse | None = None
    email: str | None = None
    endereco: AddressResponse | None = None
    custom_fields: CustomFieldsResponse | None = None


# ── Grid lookup responses ─────────────────────────────────────────────────────

class RowGridContactResponse(BaseModel):
    """Item de resultado da busca por grade — espelha RowGridContact do DTO."""
    contact_id: int
    name: str | None
    cpf: str | None


class GridContactResponse(BaseModel):
    """Resposta de GET /contacts/lookup?term=... — lista de contatos encontrados."""
    total: int
    contacts: list[RowGridContactResponse]

# filepath: domain/contact.py
"""
Value objects de domínio para o caso de uso de contatos.

Definidos como dataclasses simples, sem dependência de framework.
Usados tanto pelo schema de entrada (router) quanto pelo service.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class PersonalData:
    """Dados pessoais de um contato (pessoa física)."""
    cpf: str
    nome: str
    data_nascimento: Optional[str] = ""
    sexo: Optional[str] = ""   # 'm'/'masculino' → '0'; 'f'/'feminino' → '1'
    observacao: Optional[str] = ""
    email: Optional[str] = None
    rg: Optional[str] = None
    estado_civil: Optional[str] = None
    profissao: Optional[str] = None


@dataclass
class Address:
    """
    Endereço de um contato.

    Todos os campos são opcionais para suportar tanto criação (onde o service
    valida obrigatoriedade) quanto consulta (onde nem todo campo está presente).
    """
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    cidade: Optional[str] = None
    uf: Optional[str] = None
    bairro: Optional[str] = None
    pais: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None


@dataclass
class Phone:
    """Telefones de um contato."""
    celular: Optional[str] = None
    telefone_residencial: Optional[str] = None


@dataclass
class CustomFields:
    """
    Campos personalizados do formulário LegalOne com atributos nomeados.

    None significa "não enviar o campo" (criação) ou "campo vazio" (consulta).

    Campos de texto livre:
        tag, cid, referencia, link_drive,
        data_vencimento_kit, data_vencimento_comprovante

    Campos SelectOne (recebem o label exibido; o service resolve o ID interno):
        classificacao_backoffice : '0' | '1' | '2' | '3'
        natureza_do_acidente     : 'Trabalho' | 'Qualquer natureza'
        tratamento_da_lesao      : 'Cirúrgico' | 'Conservador'
        tramitacao_prioritaria   : 'Sim' | 'Não'
    """
    tag: Optional[str] = None
    cid: Optional[str] = None
    referencia: Optional[str] = None
    link_drive: Optional[str] = None
    data_vencimento_kit: Optional[str] = None
    data_vencimento_comprovante: Optional[str] = None
    classificacao_backoffice: Optional[str] = None
    natureza_do_acidente: Optional[str] = None
    tratamento_da_lesao: Optional[str] = None
    tramitacao_prioritaria: Optional[str] = None


@dataclass
class CreateContactInput:
    """Entrada do caso de uso de criação de contato."""
    dados_pessoais: PersonalData
    telefones: Optional[Phone] = None
    endereco: Optional[Address] = None
    custom_fields: Optional[CustomFields] = None


# ── Value objects de saída (lookup) ──────────────────────────────────────────

@dataclass
class ContactSummary:
    """
    Dados resumidos de um contato, extraídos do modal do LegalOne
    (GET /contatos/Contatos/ModalPersonInvolveds).

    Compõe com os value objects de domínio para manter consistência
    estrutural com o input de criação.
    """
    contact_id: str
    dados_pessoais: PersonalData
    telefone: Optional[Phone] = None
    email: Optional[str] = None
    endereco: Optional[Address] = None


@dataclass
class ContactDetails:
    """
    Dados completos de um contato, extraídos da página de detalhes do LegalOne
    (GET /contatos/Pessoas/Details/{id}).

    Inclui campos personalizados e data de nascimento além do que o modal expõe.
    """
    contact_id: str
    dados_pessoais: PersonalData
    telefone: Optional[Phone] = None
    email: Optional[str] = None
    endereco: Optional[Address] = None
    custom_fields: Optional[CustomFields] = None

"""
dto.py — tipos internos resolvidos do caso de uso de contatos.

Dois grupos:
  1. Tipos RESOLVIDOS (service → crawler) — produzidos pelo service após resolver
     mapeamentos; consumidos pelo ContactsCrawler via ContactPayload.
  2. ContactPayload — envelope que agrega todos os valores resolvidos e
     trafega entre ContactService → ContactsCrawler.

Os tipos de ENTRADA (PersonalData, Address, etc.) vivem em domain/contact.py.
"""

from dataclasses import dataclass, field
from typing import Optional, List


# ══════════════════════════════════════════════════════════════════════════════
# 1. Tipos RESOLVIDOS  (service → crawler)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ResolvedAddress:
    """Endereço com UFId e CidadeId já resolvidos."""
    cep: str
    logradouro: str
    numero: str
    complemento: str
    bairro: str
    cidade_texto: str
    cidade_id: str
    uf_texto: str
    uf_id: str
    pais_texto: str = "Brasil"
    pais_id: str = "31"


@dataclass
class ResolvedPhone:
    tipo_id: str   # '3' = celular, '1' = residencial
    numero: str


@dataclass
class ResolvedTextField:
    """Campo de texto livre com field_name interno do LegalOne já mapeado."""
    field_name: str
    value: str


@dataclass
class ResolvedSelectField:
    """Campo SelectOne com label e ID interno do LegalOne já resolvidos."""
    field_name: str
    label: str
    option_id: str


# ══════════════════════════════════════════════════════════════════════════════
# 2. ContactPayload — envelope service → crawler
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class ContactPayload:
    """
    Envelope produzido pelo ContactService após resolver todos os mapeamentos.
    Recebido pelo ContactsCrawler, que o converte em tuplas multipart/form-data.
    """
    cpf: str
    nome: str
    sexo: str = ""
    data_nascimento: str = ""
    observacao: str = ""

    telefones: list[ResolvedPhone] = field(default_factory=list)
    endereco: Optional[ResolvedAddress] = None
    campos_texto: list[ResolvedTextField] = field(default_factory=list)
    campos_select: list[ResolvedSelectField] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════════════════════
# 3. RowGridContact e GridContact  — tipos de resultado da busca de contatos para lookup
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class RowGridContact:
    contact_id: int
    name: str
    cpf: str

@dataclass
class GridContact:
    contacts: List[RowGridContact]
    count: int

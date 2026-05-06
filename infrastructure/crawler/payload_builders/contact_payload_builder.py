"""
contact_payload_builder.py — monta as tuplas multipart/form-data do formulário
de criação de contato do LegalOne.

Responsabilidade única: receber um ContactPayload com todos os valores
já resolvidos e produzir a lista de tuplas pronta para o requests.post(files=).

Não faz HTTP, não conhece sessão, não resolve IDs — é uma função de montagem pura.
"""

import json
import uuid
from functools import cache
from pathlib import Path

from services.contact.dto import (
    ContactPayload,
    ResolvedAddress,
)

_DATA_DIR = Path(__file__).parent.parent / "data"


@cache
def _load_diarios() -> list[dict]:
    """Carrega os diários de monitoramento do JSON — executado uma única vez."""
    path = _DATA_DIR / "diarios_monitoramento.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)["diarios"]


def build_contact_payload(dto: ContactPayload) -> list:
    """
    Constrói a lista de tuplas multipart/form-data para criação de contato.

    Args:
        dto: ContactPayloadDTO com todos os valores já resolvidos.

    Returns:
        Lista de tuplas no formato aceito por requests (files=).
    """
    files: list = []
    _add_personal_data(files, dto)
    _add_telefones(files, dto)
    if dto.endereco:
        _add_endereco(files, dto.endereco)
    _add_campos_texto(files, dto)
    _add_campos_select(files, dto)
    _add_monitoramento(files)
    _add_form_footer(files)
    return files


# ── Seções do payload ─────────────────────────────────────────────────────────

def _add_personal_data(files: list, dto: ContactPayload) -> None:
    files.extend([
        ("Id",                                               (None, "")),
        ("IsJustificativaObrigatoria",                       (None, "False")),
        ("HasPermissaoAlterarEmailPrincipal",                (None, "True")),
        ("HasInvolvementESocial",                            (None, "False")),
        ("IdArquivoNovajusTemp",                             (None, "")),
        ("CPF",                                              (None, dto.cpf)),
        ("DataDeNascimento",                                 (None, dto.data_nascimento)),
        ("Nome",                                             (None, dto.nome)),
        ("Sexo",                                             (None, dto.sexo)),
        ("Tratamento",                                       (None, "")),
        ("TratamentoId",                                     (None, "")),
        ("ProfissaoText",                                    (None, "")),
        ("ProfissaoId",                                      (None, "")),
        ("EstadoCivilText",                                  (None, "")),
        ("EstadoCivilId",                                    (None, "")),
        ("NivelEducacionalText",                             (None, "")),
        ("NivelEducacionalId",                               (None, "")),
        ("MatriculaCodigo",                                  (None, "")),
        ("NacionalidadeText",                                (None, "")),
        ("NacionalidadeId",                                  (None, "")),
        ("TipoIdentidadeText",                               (None, "")),
        ("TipoIdentidadeId",                                 (None, "")),
        ("TipoIdentidadeHasUF",                              (None, "False")),
        ("TipoIdentidadeUFText",                             (None, "")),
        ("TipoIdentidadeUFId",                               (None, "")),
        ("NITPISPASEP",                                      (None, "")),
        ("RG",                                               (None, "")),
        ("CTPS",                                             (None, "")),
        ("Serie",                                            (None, "")),
        ("TituloEleitor",                                    (None, "")),
        ("Zona",                                             (None, "")),
        ("Secao",                                            (None, "")),
        ("TaxIdentificationNumberData.TaxIdentificationNumber", (None, "")),
        ("TaxIdentificationNumberData.NifNotInformReason",  (None, "")),
        ("Observacao",                                       (None, dto.observacao)),
    ])


def _add_telefones(files: list, dto: ContactPayload) -> None:
    for tel in dto.telefones:
        _id = str(uuid.uuid4())
        is_principal = "true" if tel.tipo_id == "3" else "false"
        files.extend([
            ("Telefones.Index",               (None, _id)),
            (f"Telefones[{_id}]._Index",      (None, f"Telefones[{_id}]")),
            (f"Telefones[{_id}].Id",          (None, "")),
            (f"Telefones[{_id}].TipoId",      (None, tel.tipo_id)),
            (f"Telefones[{_id}].Numero",      (None, tel.numero)),
            (f"Telefones[{_id}].IsPrincipal", (None, is_principal)),
            (f"Telefones[{_id}].IsPrincipal", (None, "false")),
        ])


def _add_endereco(files: list, e: ResolvedAddress) -> None:
    _id = str(uuid.uuid4())
    files.extend([
        ("Enderecos.Index",                         (None, _id)),
        (f"Enderecos[{_id}]._Index",                (None, f"Enderecos[{_id}]")),
        (f"Enderecos[{_id}].Id",                    (None, "")),
        (f"Enderecos[{_id}].TipoId",                (None, "0")),
        (f"Enderecos[{_id}].Descricao",             (None, "")),
        (f"Enderecos[{_id}].IsPrincipal",           (None, "true")),
        (f"Enderecos[{_id}].IsPrincipal",           (None, "false")),
        (f"Enderecos[{_id}].IsCobranca",            (None, "true")),
        (f"Enderecos[{_id}].IsCobranca",            (None, "false")),
        (f"Enderecos[{_id}].IsFaturamento",         (None, "true")),
        (f"Enderecos[{_id}].IsFaturamento",         (None, "false")),
        (f"Enderecos[{_id}].CEP",                   (None, e.cep)),
        (f"Enderecos[{_id}].PaisText",              (None, e.pais_texto)),
        (f"Enderecos[{_id}].PaisId",                (None, e.pais_id)),
        (f"Enderecos[{_id}].UFText",                (None, e.uf_texto)),
        (f"Enderecos[{_id}].UFId",                  (None, e.uf_id)),
        (f"Enderecos[{_id}].CidadeText",            (None, e.cidade_texto)),
        (f"Enderecos[{_id}].CidadeId",              (None, e.cidade_id)),
        (f"Enderecos[{_id}].Logradouro",            (None, e.logradouro)),
        (f"Enderecos[{_id}].Numero",                (None, e.numero)),
        (f"Enderecos[{_id}].Complemento",           (None, e.complemento)),
        (f"Enderecos[{_id}].Bairro",                (None, e.bairro)),
    ])


def _add_campos_texto(files: list, dto: ContactPayload) -> None:
    for campo in dto.campos_texto:
        files.append((campo.field_name, (None, campo.value)))


def _add_campos_select(files: list, dto: ContactPayload) -> None:
    for campo in dto.campos_select:
        files.extend([
            (f"{campo.field_name}.Value", (None, campo.label)),
            (f"{campo.field_name}.Id",    (None, campo.option_id)),
        ])


def _add_monitoramento(files: list) -> None:
    """Adiciona o bloco de Diários Oficiais monitorados ao payload."""
    for d in _load_diarios():
        _id = d["id"]
        files.extend([
            ("Diarios.Index",            (None, _id)),
            (f"Diarios[{_id}].Id",       (None, _id)),
            (f"Diarios[{_id}].Selected", (None, "false")),
            (f"Diarios[{_id}].Estado",   (None, d["estado"])),
            (f"Diarios[{_id}].Diario",   (None, d["diario"])),
        ])


def _add_form_footer(files: list) -> None:
    """Adiciona campos fixos de encerramento do formulário de contato."""
    files.extend([
        ("MonitorarRex",                               (None, "false")),
        ("ConfiguracoesFatura.NotaDebitoText",          (None, "")),
        ("ConfiguracoesFatura.NotaDebitoId",            (None, "")),
        ("ConfiguracoesFatura.NotaFiscalText",          (None, "")),
        ("ConfiguracoesFatura.NotaFiscalId",            (None, "")),
        ("ConfiguracoesFatura.NotaFiscalServicoText",   (None, "")),
        ("ConfiguracoesFatura.NotaFiscalServicoId",     (None, "")),
        ("ConfiguracoesFatura.NotaHonorarioText",       (None, "")),
        ("ConfiguracoesFatura.NotaHonorarioId",         (None, "")),
        ("ConfiguracoesFatura.ModeloExtratoFaturaText", (None, "")),
        ("ConfiguracoesFatura.ModeloExtratoFaturaId",   (None, "")),
        ("FileAzure.FieldPrefix",                       (None, "")),
        ("FileAzure.FileItemMaxSizeLimitInBytes",       (None, "2000000")),
        ("FileAzure.HasFile",                           (None, "False")),
        ("FileAzure.MultipleFiles",                     (None, "False")),
        ("FileAzure.DragText",                          (None, "Arraste ou selecione o arquivo que deseja importar")),
        ("FileAzure.MaxUploadFiles",                    (None, "1")),
        ("FileAzure.AllowedFileExtensions[0]",          (None, "jpg")),
        ("FileAzure.AllowedFileExtensions[1]",          (None, "jpeg")),
        ("FileAzure.AllowedFileExtensions[2]",          (None, "png")),
        ("FileAzure.AllowedFileExtensions[3]",          (None, "bmp")),
        ("FileAzure.CustomOnCompleteCallbackJS",        (None, "")),
        ("FileAzure.CustomOnDeleteCallbackJS",          (None, "")),
        ("FileAzure.CustomOnReadyCallbackJS",           (None, "")),
        ("qqfile",                                      ("", "", "application/octet-stream")),
        ("UserSiteAdvogado",                            (None, "")),
        ("Maintain",                                    (None, "true")),
        ("Maintain",                                    (None, "false")),
        ("ButtonSave",                                  (None, "0")),
    ])

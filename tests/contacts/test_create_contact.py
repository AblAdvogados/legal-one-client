# filepath: tests/contacts/test_create_contact.py
"""
Testes para o caso de uso de criação de contato.

Dois grupos:

  TestBuildPayload  — testes UNITÁRIOS, offline, sem HTTP.
    Verifica que build_payload() resolve corretamente os campos a partir de
    um CreateContactInput, incluindo campos personalizados e degradação
    graceful de valores inválidos.

  TestCadastroCompleto       ─┐
  TestCadastroSemEndereco    ├─ testes de INTEGRAÇÃO, HTTP real.
  TestCadastroComCpfInvalido ─┘
    Cada classe faz um único POST real ao LegalOne e verifica o resultado.
    ATENÇÃO: os testes "Completo" e "SemEndereco" criam contatos reais —
    apague-os no LegalOne após cada execução.

Comportamento do servidor LegalOne
───────────────────────────────────
  Campos OBRIGATÓRIOS (CPF, Nome):
    • Inválidos → servidor rejeita; ContactService lança ContatoRejeitadoError.

  Campos OPCIONAIS (endereço, telefone, custom_fields):
    • Com erro → servidor CRIA o contato, mas devolve warnings.
    • Ausentes  → servidor CRIA sem warnings.
"""

import unittest

from infrastructure.crawler.contacts import ContactsCrawler
from services.contact.service import ContactService, build_payload
from domain.contact import (
    Address,
    CreateContactInput,
    CustomFields,
    PersonalData,
    Phone,
)
from core.errors import ContatoRejeitadoError
from tests.helpers import make_session_manager, assert_not_login_page


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures compartilhadas
# ══════════════════════════════════════════════════════════════════════════════

_DADOS_PESSOAIS = PersonalData(
    cpf='083.863.794-99',
    nome='TESTE AUTOMATIZADO NOVO',
    sexo='M',
    observacao='Criado por teste automatizado — pode ser deletado.',
)

_TELEFONE = Phone(celular='(11) 99999-0001')

_ENDERECO = Address(
    cep='12916-070',
    logradouro='Alameda Noruega',
    numero='119',
    bairro='Jardim Europa',
    cidade='Atibaia',
    uf='SP',
    pais='Brasil',
)

_CUSTOM_FIELDS_VALIDOS = CustomFields(
    tag='tag-teste',
    cid='M54',
    referencia='REF-001',
    classificacao_backoffice='1',
    natureza_do_acidente='Trabalho',
    tratamento_da_lesao='Conservador',
    tramitacao_prioritaria='Sim',
)

# CreateContactInput completo — endereço + campos personalizados válidos
INPUT_COMPLETO = CreateContactInput(
    dados_pessoais=_DADOS_PESSOAIS,
    telefones=_TELEFONE,
    endereco=_ENDERECO,
    custom_fields=_CUSTOM_FIELDS_VALIDOS,
)

# CreateContactInput com dados reais para o teste de integração
INPUT_CADASTRO_REAL = CreateContactInput(
    dados_pessoais=PersonalData(
        cpf='039.726.028-80',
        nome='FULANO DA SILVA',
        sexo='M',
        data_nascimento='04/07/1980',
        rg='154424028',
        email='email@gmail.com',
        estado_civil='Divorciado',
        profissao='tratorista',
    ),
    telefones=Phone(celular='(11) 91230-2380'),
    endereco=Address(
        pais='Brasil',
        uf='MG',
        cidade='MUNHOZ',
        logradouro='RURAL RESIDENCIAL SANTO EXPEDITO',
        numero='0',
        complemento='CX 2',
        bairro='RIBEIRAO FUNDO',
        cep='37620-000',
    ),
)

# CreateContactInput mínimo — só dados obrigatórios + telefone, sem endereço
INPUT_SEM_ENDERECO = CreateContactInput(
    dados_pessoais=_DADOS_PESSOAIS,
    telefones=_TELEFONE,
)

# CreateContactInput com CPF inválido — deve ser rejeitado pelo servidor
INPUT_CPF_INVALIDO = CreateContactInput(
    dados_pessoais=PersonalData(
        cpf='000.000.000-00',
        nome='TESTE AUTOMATIZADO INVALIDO',
    ),
)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Testes UNITÁRIOS — offline, sem HTTP
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildPayload(unittest.TestCase):
    """
    Testa build_payload() diretamente, sem nenhuma chamada HTTP.
    Executa em qualquer ambiente — não requer credenciais nem rede.
    """

    def test_inclui_cpf_e_nome(self):
        """Campos obrigatórios devem aparecer no payload."""
        payload, warnings = build_payload(INPUT_COMPLETO)
        self.assertEqual(payload.cpf,  _DADOS_PESSOAIS.cpf)
        self.assertEqual(payload.nome, _DADOS_PESSOAIS.nome)

    def test_resolve_sexo(self):
        """Sexo 'M' deve ser convertido para '0'."""
        payload, _ = build_payload(INPUT_COMPLETO)
        self.assertEqual(payload.sexo, '0')

    def test_inclui_telefone_celular(self):
        """Celular deve ser mapeado com tipo_id '3'."""
        payload, _ = build_payload(INPUT_COMPLETO)
        self.assertEqual(len(payload.telefones), 1)
        self.assertEqual(payload.telefones[0].tipo_id, '3')
        self.assertEqual(payload.telefones[0].numero, '(11) 99999-0001')

    def test_resolve_uf_e_cidade(self):
        """Endereço válido deve ter uf_id e cidade_id preenchidos sem warnings."""
        payload, warnings = build_payload(INPUT_COMPLETO)
        self.assertIsNotNone(payload.endereco)
        self.assertEqual(payload.endereco.uf_id,     '26')    # SP → 26
        self.assertEqual(payload.endereco.cidade_id, '4830')  # Atibaia → 4830
        self.assertEqual(warnings, [])

    def test_sem_endereco_nao_gera_warning(self):
        """Input sem endereço não deve gerar warnings."""
        payload, warnings = build_payload(INPUT_SEM_ENDERECO)
        self.assertIsNone(payload.endereco)
        self.assertEqual(warnings, [])

    def test_inclui_campos_texto_personalizados(self):
        """Campos de texto de custom_fields devem aparecer em campos_texto."""
        payload, _ = build_payload(INPUT_COMPLETO)
        values = [c.value for c in payload.campos_texto]
        # Três campos de texto foram preenchidos: tag, cid, referencia
        self.assertIn('tag-teste', values)
        self.assertIn('M54',       values)
        self.assertIn('REF-001',   values)
        self.assertEqual(len(payload.campos_texto), 3)

    def test_inclui_campos_select_personalizados(self):
        """Campos SelectOne de custom_fields devem aparecer em campos_select com IDs corretos."""
        payload, _ = build_payload(INPUT_COMPLETO)
        by_label = {c.label: c.option_id for c in payload.campos_select}
        self.assertEqual(by_label.get('Trabalho'),    '5')
        self.assertEqual(by_label.get('Conservador'), '8')
        self.assertEqual(by_label.get('Sim'),         '9')
        self.assertEqual(by_label.get('1'),           '2')  # classificacao_backoffice='1' → id '2'

    def test_campo_select_invalido_gera_warning_nao_excecao(self):
        """Valor inválido num campo SelectOne deve gerar warning, não lançar exceção."""
        input_invalido = CreateContactInput(
            dados_pessoais=_DADOS_PESSOAIS,
            custom_fields=CustomFields(natureza_do_acidente='OPCAO_INEXISTENTE'),
        )
        payload, warnings = build_payload(input_invalido)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].field_name, 'natureza_do_acidente')
        self.assertEqual(payload.campos_select, [])

    def test_endereco_incompleto_gera_warning_nao_excecao(self):
        """Endereço sem campos obrigatórios deve gerar warning, não lançar exceção."""
        input_incompleto = CreateContactInput(
            dados_pessoais=_DADOS_PESSOAIS,
            endereco=Address(
                cep='',
                logradouro='',
                cidade='Atibaia',
                uf='SP',
                bairro='',
            ),
        )
        payload, warnings = build_payload(input_incompleto)
        self.assertIsNone(payload.endereco)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].field_name, 'Endereço')

    # ── Novos campos pessoais ─────────────────────────────────────────────────

    def test_inclui_rg(self):
        """RG informado deve aparecer no payload."""
        inp = CreateContactInput(dados_pessoais=PersonalData(
            cpf=_DADOS_PESSOAIS.cpf, nome=_DADOS_PESSOAIS.nome, rg='15442486',
        ))
        payload, warnings = build_payload(inp)
        self.assertEqual(payload.rg, '15442486')
        self.assertEqual(warnings, [])

    def test_inclui_email(self):
        """Email informado deve gerar ResolvedEmail com tipo_id='1' e is_principal=True."""
        inp = CreateContactInput(dados_pessoais=PersonalData(
            cpf=_DADOS_PESSOAIS.cpf, nome=_DADOS_PESSOAIS.nome,
            email='joao@example.com',
        ))
        payload, warnings = build_payload(inp)
        self.assertIsNotNone(payload.email)
        self.assertEqual(payload.email.email, 'joao@example.com')
        self.assertEqual(payload.email.tipo_id, '1')
        self.assertTrue(payload.email.is_principal)
        self.assertEqual(warnings, [])

    def test_profissao_valida_resolve_id(self):
        """Profissão conhecida deve preencher profissao_texto e profissao_id sem warnings."""
        inp = CreateContactInput(dados_pessoais=PersonalData(
            cpf=_DADOS_PESSOAIS.cpf, nome=_DADOS_PESSOAIS.nome,
            profissao='tratorista',
        ))
        payload, warnings = build_payload(inp)
        self.assertEqual(payload.profissao_id, '49')
        self.assertNotEqual(payload.profissao_texto, '')
        self.assertEqual(warnings, [])

    def test_profissao_case_insensitive(self):
        """'TRATORISTA' deve resolver para o mesmo ID que 'tratorista'."""
        inp = CreateContactInput(dados_pessoais=PersonalData(
            cpf=_DADOS_PESSOAIS.cpf, nome=_DADOS_PESSOAIS.nome,
            profissao='TRATORISTA',
        ))
        payload, _ = build_payload(inp)
        self.assertEqual(payload.profissao_id, '49')

    def test_profissao_invalida_gera_warning(self):
        """Profissão desconhecida deve gerar warning e deixar profissao_id vazio."""
        inp = CreateContactInput(dados_pessoais=PersonalData(
            cpf=_DADOS_PESSOAIS.cpf, nome=_DADOS_PESSOAIS.nome,
            profissao='INEXISTENTE',
        ))
        payload, warnings = build_payload(inp)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].field_name, 'profissao')
        self.assertEqual(payload.profissao_id, '')
        self.assertEqual(payload.profissao_texto, '')

    def test_estado_civil_valido_resolve_id(self):
        """Estado civil conhecido deve preencher texto e id sem warnings."""
        inp = CreateContactInput(dados_pessoais=PersonalData(
            cpf=_DADOS_PESSOAIS.cpf, nome=_DADOS_PESSOAIS.nome,
            estado_civil='Divorciado',
        ))
        payload, warnings = build_payload(inp)
        self.assertEqual(payload.estado_civil_id, '4')
        self.assertEqual(payload.estado_civil_texto, 'Divorciado')
        self.assertEqual(warnings, [])

    def test_estado_civil_case_insensitive(self):
        """'divorciado' deve resolver para o mesmo ID que 'Divorciado'."""
        inp = CreateContactInput(dados_pessoais=PersonalData(
            cpf=_DADOS_PESSOAIS.cpf, nome=_DADOS_PESSOAIS.nome,
            estado_civil='divorciado',
        ))
        payload, _ = build_payload(inp)
        self.assertEqual(payload.estado_civil_id, '4')

    def test_estado_civil_invalido_gera_warning(self):
        """Estado civil desconhecido deve gerar warning e deixar os campos vazios."""
        inp = CreateContactInput(dados_pessoais=PersonalData(
            cpf=_DADOS_PESSOAIS.cpf, nome=_DADOS_PESSOAIS.nome,
            estado_civil='Casamentado',
        ))
        payload, warnings = build_payload(inp)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(warnings[0].field_name, 'estado_civil')
        self.assertEqual(payload.estado_civil_id, '')
        self.assertEqual(payload.estado_civil_texto, '')

    def test_sem_novos_campos_nao_altera_comportamento(self):
        """Input sem os novos campos deve manter rg/email/profissao/estado_civil zerados."""
        payload, warnings = build_payload(INPUT_SEM_ENDERECO)
        self.assertEqual(payload.rg, '')
        self.assertIsNone(payload.email)
        self.assertEqual(payload.profissao_id, '')
        self.assertEqual(payload.profissao_texto, '')
        self.assertEqual(payload.estado_civil_id, '')
        self.assertEqual(payload.estado_civil_texto, '')
        self.assertEqual(warnings, [])


# ══════════════════════════════════════════════════════════════════════════════
# Utilitários de integração
# ══════════════════════════════════════════════════════════════════════════════

def _make_service() -> ContactService:
    """Instancia ContactService com sessão autenticada real."""
    sm = make_session_manager()
    crawler = ContactsCrawler(session_manager=sm)
    return ContactService(crawler)


def _save_html(filename: str, html: str) -> None:
    """Persiste o HTML de resposta para inspeção manual."""
    with open(f"tests/contacts/results/{filename}", "w", encoding="utf-8") as f:
        f.write(html)


# ══════════════════════════════════════════════════════════════════════════════
# 2. Testes de INTEGRAÇÃO — HTTP real
# ══════════════════════════════════════════════════════════════════════════════

class TestCadastroCompleto(unittest.TestCase):
    """
    Cenário: cadastro com dados reais — email, RG, estado civil, profissão e endereço.
    Expectativa: success=True, warnings=[].
    ATENÇÃO: cria contato real — apague no LegalOne após o teste.
    """

    @classmethod
    def setUpClass(cls):
        service = _make_service()
        crawler = service._crawler
        original = crawler.create_contact

        def _intercept(payload):
            html = original(payload)
            _save_html("create_contact_completo.html", html)
            return html

        crawler.create_contact = _intercept
        cls.result = service.create_contact(INPUT_CADASTRO_REAL)

    def test_sucesso(self):
        """result.success deve ser True."""
        self.assertTrue(self.result.success)

    def test_sem_warnings(self):
        """Nenhum campo opcional deve ter gerado erro."""
        self.assertEqual(
            self.result.warnings, [],
            msg=f"Warnings inesperados: {[e.field_name for e in self.result.warnings]}",
        )

    def test_nao_e_pagina_de_login(self):
        """A resposta não deve ser a página de login do BrowserHawk."""
        with open("tests/contacts/results/create_contact_completo.html", encoding="utf-8") as f:
            html = f.read()
        assert_not_login_page(self, html)


# class TestCadastroSemEndereco(unittest.TestCase):
#     """
#     Cenário: cadastro com dados obrigatórios e telefone — sem endereço
#     nem custom_fields.
#     Expectativa: success=True, warnings=[].
#     ATENÇÃO: cria contato real — apague no LegalOne após o teste.
#     """

#     @classmethod
#     def setUpClass(cls):
#         service = _make_service()
#         crawler = service._crawler
#         original = crawler.create_contact

#         def _intercept(payload):
#             html = original(payload)
#             _save_html("create_contact_sem_endereco.html", html)
#             return html

#         crawler.create_contact = _intercept
#         cls.result = service.create_contact(INPUT_SEM_ENDERECO)

#     def test_sucesso(self):
#         """result.success deve ser True mesmo sem endereço."""
#         self.assertTrue(self.result.success)

#     def test_sem_warnings(self):
#         """Input sem endereço não deve produzir warnings."""
#         self.assertEqual(
#             self.result.warnings, [],
#             msg=f"Warnings inesperados: {[e.field_name for e in self.result.warnings]}",
#         )


# class TestCadastroComCpfInvalido(unittest.TestCase):
#     """
#     Cenário: CPF inválido enviado ao servidor.
#     Expectativa: ContactService lança ContatoRejeitadoError com 'CPF' nos erros.
#     """

#     @classmethod
#     def setUpClass(cls):
#         service = _make_service()
#         cls.rejection_error = None
#         try:
#             service.create_contact(INPUT_CPF_INVALIDO)
#         except ContatoRejeitadoError as e:
#             cls.rejection_error = e

#     def test_lancou_contato_rejeitado(self):
#         """ContactService DEVE lançar ContatoRejeitadoError para CPF inválido."""
#         self.assertIsNotNone(
#             self.rejection_error,
#             "Esperava ContatoRejeitadoError, mas nenhuma exceção foi lançada.",
#         )

#     def test_erro_menciona_cpf(self):
#         """A lista de erros deve referenciar o campo 'CPF'."""
#         self.assertIsNotNone(self.rejection_error)
#         mensagens = " ".join(self.rejection_error.errors)
#         self.assertIn("CPF", mensagens)


if __name__ == "__main__":
    unittest.main(verbosity=2)

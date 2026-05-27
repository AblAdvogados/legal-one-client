# filepath: tests/contacts/test_contact_schemas.py
"""
Testes UNITÁRIOS para os schemas Pydantic de contatos.

Verifica normalização de campos opcionais:
  - rg / estado_civil / profissao: None e "" → None
  - email: "" → None (antes do EmailStr validar)

Offline, sem HTTP.
"""

import unittest

from pydantic import ValidationError

from app.schemas.contact_schemas import PersonalDataSchema


_CPF = "083.863.794-99"
_NOME = "TESTE AUTOMATIZADO NOVO"


class TestPersonalDataSchemaNormalizacao(unittest.TestCase):

    # ── rg ────────────────────────────────────────────────────────────────────

    def test_rg_vazio_normaliza_para_none(self):
        """rg='' deve ser normalizado para None sem erro."""
        p = PersonalDataSchema(cpf=_CPF, nome=_NOME, rg="")
        self.assertIsNone(p.rg)

    def test_rg_espacos_normaliza_para_none(self):
        """rg com só espaços deve ser normalizado para None."""
        p = PersonalDataSchema(cpf=_CPF, nome=_NOME, rg="   ")
        self.assertIsNone(p.rg)

    def test_rg_valido_com_strip(self):
        """rg com espaços nas bordas deve ter strip aplicado."""
        p = PersonalDataSchema(cpf=_CPF, nome=_NOME, rg=" 15442486 ")
        self.assertEqual(p.rg, "15442486")

    # ── email ─────────────────────────────────────────────────────────────────

    def test_email_vazio_normaliza_para_none(self):
        """email='' deve ser normalizado para None sem erro."""
        p = PersonalDataSchema(cpf=_CPF, nome=_NOME, email="")
        self.assertIsNone(p.email)

    def test_email_invalido_gera_422(self):
        """email com formato inválido deve lançar ValidationError."""
        with self.assertRaises(ValidationError):
            PersonalDataSchema(cpf=_CPF, nome=_NOME, email="nao-e-email")

    def test_email_valido_aceito(self):
        """email válido deve passar sem alteração."""
        p = PersonalDataSchema(cpf=_CPF, nome=_NOME, email="teste@example.com")
        self.assertEqual(str(p.email), "teste@example.com")

    # ── estado_civil ──────────────────────────────────────────────────────────

    def test_estado_civil_vazio_normaliza_para_none(self):
        """estado_civil='' deve ser normalizado para None."""
        p = PersonalDataSchema(cpf=_CPF, nome=_NOME, estado_civil="")
        self.assertIsNone(p.estado_civil)

    def test_estado_civil_none_aceito(self):
        """estado_civil=None deve ser mantido como None."""
        p = PersonalDataSchema(cpf=_CPF, nome=_NOME, estado_civil=None)
        self.assertIsNone(p.estado_civil)

    def test_estado_civil_valido_com_strip(self):
        """estado_civil válido deve ter strip aplicado."""
        p = PersonalDataSchema(cpf=_CPF, nome=_NOME, estado_civil=" Divorciado ")
        self.assertEqual(p.estado_civil, "Divorciado")

    # ── profissao ─────────────────────────────────────────────────────────────

    def test_profissao_vazia_normaliza_para_none(self):
        """profissao='' deve ser normalizado para None."""
        p = PersonalDataSchema(cpf=_CPF, nome=_NOME, profissao="")
        self.assertIsNone(p.profissao)

    def test_profissao_none_aceito(self):
        """profissao=None deve ser mantido como None."""
        p = PersonalDataSchema(cpf=_CPF, nome=_NOME, profissao=None)
        self.assertIsNone(p.profissao)


if __name__ == "__main__":
    unittest.main(verbosity=2)

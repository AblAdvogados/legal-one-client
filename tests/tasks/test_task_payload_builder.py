# filepath: tests/tasks/test_task_payload_builder.py
"""
Testes UNITÁRIOS para o task_payload_builder.

Verifica que build_payload() gera o form-data correto a partir de um
TaskPayload totalmente resolvido (com IDs). Sem HTTP.

Grupos:
  - Campos raiz fixos e dinâmicos
  - Bloco Vinculos[]
  - Bloco Envolvidos[]
  - Bloco Lembretes[] (condicional)
  - Bloco Recorrência (condicional)
  - Campos finais
  - Kanban dinâmico
"""

import unittest

from infrastructure.crawler.payload_builders.task_payload_builder import build_payload
from services.task.dto import EnvolvidoPayload, LembretePayload, TaskPayload


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

def _make_payload(
    *,
    envolvidos=None,
    lembretes=None,
    incluir_recorrencia=False,
    show_kanban=False,
    kanban_board_text="",
    kanban_board_id="",
    kanban_column_text="",
    kanban_column_id="",
    deadline_date="",
    deadline_time="",
    observacoes="",
) -> TaskPayload:
    """Cria um TaskPayload de teste com defaults razoáveis."""
    return TaskPayload(
        processo_id="3004",
        num_pasta_processo="Proc - 0008579",
        descricao="Audiência Inicial",
        dt_inicial="06/04/2026",
        hr_inicio="08:00:00",
        dt_final="06/04/2026",
        hr_final="09:00:00",
        deadline_date=deadline_date,
        deadline_time=deadline_time,
        show_activity_in_kanban=show_kanban,
        kanban_board_text=kanban_board_text,
        kanban_board_id=kanban_board_id,
        kanban_column_text=kanban_column_text,
        kanban_column_id=kanban_column_id,
        envolvidos=envolvidos or [
            EnvolvidoPayload(
                envolvido_id="42",
                envolvido_text="JOÃO DA SILVA",
                is_solicitante=True,
                is_responsavel=True,
                is_executante=False,
            ),
        ],
        lembretes=lembretes or [],
        incluir_recorrencia=incluir_recorrencia,
        observacoes=observacoes,
    )


def _to_dict(fields: list[tuple[str, str]]) -> dict[str, list[str]]:
    """Converte lista de tuplas form-data em dict de chave → lista de valores."""
    result: dict[str, list[str]] = {}
    for key, val in fields:
        result.setdefault(key, []).append(val)
    return result


def _first(fields: list[tuple[str, str]], key: str) -> str | None:
    """Retorna o primeiro valor para uma chave ou None."""
    for k, v in fields:
        if k == key:
            return v
    return None


def _all_values(fields: list[tuple[str, str]], key: str) -> list[str]:
    """Retorna todos os valores para uma chave."""
    return [v for k, v in fields if k == key]


def _keys_containing(fields: list[tuple[str, str]], substring: str) -> list[str]:
    """Retorna todas as chaves que contêm a substring."""
    return [k for k, _ in fields if substring in k]


# ══════════════════════════════════════════════════════════════════════════════
# 1. Campos raiz
# ══════════════════════════════════════════════════════════════════════════════

class TestCamposRaiz(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.payload = _make_payload()
        cls.fields = build_payload(cls.payload)

    def test_id_vazio(self):
        """Id vazio = criação de novo registro."""
        self.assertEqual(_first(self.fields, "Id"), "")

    def test_compromisso_ou_tarefa_eh_1(self):
        """1 = tarefa."""
        self.assertEqual(_first(self.fields, "CompromissoOuTarefa"), "1")

    def test_vinculo_id_e_parent_id(self):
        """VinculoId e VinculoParentId devem apontar para o processo."""
        self.assertEqual(_first(self.fields, "VinculoId"), "3004")
        self.assertEqual(_first(self.fields, "VinculoParentId"), "3004")

    def test_descricao(self):
        self.assertEqual(_first(self.fields, "Descricao"), "Audiência Inicial")

    def test_datas(self):
        self.assertEqual(_first(self.fields, "DtInicial"), "06/04/2026")
        self.assertEqual(_first(self.fields, "HrInicio"), "08:00:00")
        self.assertEqual(_first(self.fields, "DtFinal"), "06/04/2026")
        self.assertEqual(_first(self.fields, "HrFinal"), "09:00:00")

    def test_deadline_vazio_por_default(self):
        self.assertEqual(_first(self.fields, "DeadLineDate"), "")
        self.assertEqual(_first(self.fields, "DeadLineTime"), "")

    def test_deadline_preenchido(self):
        p = _make_payload(deadline_date="10/04/2026", deadline_time="17:00:00")
        fields = build_payload(p)
        self.assertEqual(_first(fields, "DeadLineDate"), "10/04/2026")
        self.assertEqual(_first(fields, "DeadLineTime"), "17:00:00")

    def test_tipo_fixo(self):
        self.assertEqual(_first(self.fields, "TipoText"), "Diversos")
        self.assertEqual(_first(self.fields, "TipoId"), "tipo_4")

    def test_observacoes_no_final(self):
        """Observacoes deve aparecer no payload."""
        p = _make_payload(observacoes="Nota de teste")
        fields = build_payload(p)
        self.assertEqual(_first(fields, "Observacoes"), "Nota de teste")

    def test_campos_finais(self):
        """Maintain e ButtonSave devem estar no final."""
        maintain_vals = _all_values(self.fields, "Maintain")
        self.assertIn("true", maintain_vals)
        self.assertIn("false", maintain_vals)
        self.assertEqual(_first(self.fields, "ButtonSave"), "0")


# ══════════════════════════════════════════════════════════════════════════════
# 2. Bloco Vinculos[]
# ══════════════════════════════════════════════════════════════════════════════

class TestVinculos(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fields = build_payload(_make_payload())

    def test_vinculo_index_presente(self):
        """Deve haver exatamente 1 Vinculos.Index (UUID)."""
        vals = _all_values(self.fields, "Vinculos.Index")
        self.assertEqual(len(vals), 1)
        self.assertTrue(len(vals[0]) > 10)  # UUID

    def test_vinculo_relationship_id(self):
        """RelationshipId deve ser o processo_id."""
        keys = _keys_containing(self.fields, ".RelationshipId")
        vinc_keys = [k for k in keys if "Vinculos[" in k]
        self.assertTrue(len(vinc_keys) >= 1)
        for k in vinc_keys:
            v = _first(self.fields, k)
            self.assertEqual(v, "3004")

    def test_vinculo_description(self):
        """Description deve ser num_pasta_processo."""
        keys = _keys_containing(self.fields, ".Description")
        vinc_keys = [k for k in keys if "Vinculos[" in k]
        self.assertTrue(len(vinc_keys) >= 1)
        for k in vinc_keys:
            v = _first(self.fields, k)
            self.assertEqual(v, "Proc - 0008579")

    def test_vinculo_grid_text(self):
        """VinculoGridText deve ser num_pasta_processo."""
        keys = _keys_containing(self.fields, ".VinculoGridText")
        vinc_keys = [k for k in keys if "Vinculos[" in k]
        self.assertTrue(len(vinc_keys) >= 1)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Bloco Envolvidos[]
# ══════════════════════════════════════════════════════════════════════════════

class TestEnvolvidos(unittest.TestCase):

    def test_um_envolvido(self):
        """Um envolvido deve gerar 1 Envolvidos.Index."""
        fields = build_payload(_make_payload())
        indices = _all_values(fields, "Envolvidos.Index")
        self.assertEqual(len(indices), 1)

    def test_dois_envolvidos(self):
        """Dois envolvidos devem gerar 2 Envolvidos.Index."""
        payload = _make_payload(envolvidos=[
            EnvolvidoPayload("42", "JOÃO", True, True, False),
            EnvolvidoPayload("99", "MARIA", False, False, True),
        ])
        fields = build_payload(payload)
        indices = _all_values(fields, "Envolvidos.Index")
        self.assertEqual(len(indices), 2)

    def test_envolvido_id_no_payload(self):
        """EnvolvidoId deve conter o ID resolvido."""
        fields = build_payload(_make_payload())
        keys = _keys_containing(fields, ".EnvolvidoId")
        env_keys = [k for k in keys if "Envolvidos[" in k and "Lembretes" not in k]
        self.assertTrue(len(env_keys) >= 1)
        # Pelo menos um deve ter o valor "42"
        vals = [_first(fields, k) for k in env_keys]
        self.assertIn("42", vals)

    def test_envolvido_text_no_payload(self):
        fields = build_payload(_make_payload())
        keys = _keys_containing(fields, ".EnvolvidoText")
        env_keys = [k for k in keys if "Envolvidos[" in k and "Lembretes" not in k]
        vals = [_first(fields, k) for k in env_keys]
        self.assertIn("JOÃO DA SILVA", vals)

    def test_bool_solicitante_true(self):
        """IsSolicitante deve estar presente como 'true' para o solicitante."""
        fields = build_payload(_make_payload())
        keys = _keys_containing(fields, ".IsSolicitante")
        env_keys = [k for k in keys if "Envolvidos[" in k]
        vals = _all_values(fields, env_keys[0])
        self.assertIn("true", vals)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Lembretes (condicional)
# ══════════════════════════════════════════════════════════════════════════════

class TestLembretes(unittest.TestCase):

    def test_sem_lembretes_nao_gera_bloco(self):
        """Se lembretes=[], nenhum Lembretes.Index deve existir."""
        fields = build_payload(_make_payload(lembretes=[]))
        indices = _all_values(fields, "Lembretes.Index")
        self.assertEqual(len(indices), 0)

    def test_com_um_lembrete(self):
        """Um lembrete deve gerar 1 Lembretes.Index."""
        payload = _make_payload(lembretes=[
            LembretePayload(
                envolvido_id="42",
                envolvido_text="JOÃO DA SILVA",
                numero_antecedencia=1,
                tipo_antecedencia="2",
            ),
        ])
        fields = build_payload(payload)
        indices = _all_values(fields, "Lembretes.Index")
        self.assertEqual(len(indices), 1)

    def test_lembrete_envolvido_id(self):
        """EnvolvidoId no bloco Lembretes deve ter o ID correto."""
        payload = _make_payload(lembretes=[
            LembretePayload("42", "JOÃO DA SILVA"),
        ])
        fields = build_payload(payload)
        keys = _keys_containing(fields, ".EnvolvidoId")
        lem_keys = [k for k in keys if "Lembretes[" in k]
        self.assertTrue(len(lem_keys) >= 1)
        vals = [_first(fields, k) for k in lem_keys]
        self.assertIn("42", vals)

    def test_lembrete_antecedencia(self):
        payload = _make_payload(lembretes=[
            LembretePayload("42", "JOÃO", numero_antecedencia=3, tipo_antecedencia="1"),
        ])
        fields = build_payload(payload)
        keys = _keys_containing(fields, ".NumeroTempoAntecedencia")
        vals = [_first(fields, k) for k in keys]
        self.assertIn("3", vals)


# ══════════════════════════════════════════════════════════════════════════════
# 5. Recorrência (condicional)
# ══════════════════════════════════════════════════════════════════════════════

class TestRecorrencia(unittest.TestCase):

    def test_sem_recorrencia_nao_gera_bloco(self):
        """Se incluir_recorrencia=False, nenhum campo Recorrencia.* deve existir."""
        fields = build_payload(_make_payload(incluir_recorrencia=False))
        rec_keys = _keys_containing(fields, "Recorrencia.")
        self.assertEqual(len(rec_keys), 0)

    def test_com_recorrencia_gera_bloco(self):
        """Se incluir_recorrencia=True, campos Recorrencia.* devem estar presentes."""
        fields = build_payload(_make_payload(incluir_recorrencia=True))
        rec_keys = _keys_containing(fields, "Recorrencia.")
        self.assertGreater(len(rec_keys), 10)

    def test_recorrencia_is_gerar_false(self):
        """Mesmo com bloco presente, IsGerarRecorrencia deve ser 'false'."""
        fields = build_payload(_make_payload(incluir_recorrencia=True))
        val = _first(fields, "Recorrencia.IsGerarRecorrencia")
        self.assertEqual(val, "false")


# ══════════════════════════════════════════════════════════════════════════════
# 6. Kanban dinâmico
# ══════════════════════════════════════════════════════════════════════════════

class TestKanban(unittest.TestCase):

    def test_kanban_desabilitado(self):
        """Sem kanban: ShowActivityInKanban='false', campos vazios."""
        fields = build_payload(_make_payload())
        show_vals = _all_values(fields, "ShowActivityInKanban")
        self.assertIn("false", show_vals)
        self.assertEqual(_first(fields, "KanbanBoardText"), "")
        self.assertEqual(_first(fields, "KanbanBoardId"), "")

    def test_kanban_habilitado(self):
        """Com kanban: campos preenchidos com IDs resolvidos."""
        payload = _make_payload(
            show_kanban=True,
            kanban_board_text="BACKOFFICE",
            kanban_board_id="2",
            kanban_column_text="A DESIGNAR",
            kanban_column_id="17",
        )
        fields = build_payload(payload)
        show_vals = _all_values(fields, "ShowActivityInKanban")
        self.assertIn("true", show_vals)
        self.assertEqual(_first(fields, "KanbanBoardText"), "BACKOFFICE")
        self.assertEqual(_first(fields, "KanbanBoardId"), "2")
        self.assertEqual(_first(fields, "KanbanBoardColumnText"), "A DESIGNAR")
        self.assertEqual(_first(fields, "KanbanBoardColumn"), "17")


if __name__ == "__main__":
    unittest.main(verbosity=2)

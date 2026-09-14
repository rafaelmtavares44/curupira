"""Carga e lint do dataset.

Cada regra de lint tem um teste que a dispara. Uma regra sem teste que a dispare
é uma regra que ninguém sabe se funciona.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from curupira.core.loader import (
    Severidade,
    carregar_diretorio,
    carregar_tarefa,
    lint_do_dataset,
    tem_erro,
)
from curupira.core.registry import limpar_registro
from curupira.core.task import Tarefa
from curupira.formatos import registrar_validadores
from curupira.matchers import registrar_todos
from tests.fabricas import par_strict, tarefa_bruta


@pytest.fixture(autouse=True)
def _registro_pronto() -> Iterator[None]:
    limpar_registro()
    registrar_todos()
    registrar_validadores()
    yield
    limpar_registro()


def _gravar(raiz: Path, *brutos: dict[str, Any]) -> Path:
    raiz.mkdir(parents=True, exist_ok=True)
    for bruto in brutos:
        (raiz / f"{bruto['id']}.yaml").write_text(
            yaml.safe_dump(bruto, allow_unicode=True), encoding="utf-8"
        )
    return raiz


def _tarefas(*brutos: dict[str, Any]) -> list[Tarefa]:
    return [Tarefa.model_validate(b) for b in brutos]


def _regras(problemas: list[Any]) -> set[str]:
    return {p.regra for p in problemas}


# --------------------------------------------------------------------------
# Carga
# --------------------------------------------------------------------------


def test_forma_curta_vira_alternativa_canonica(tmp_path: Path) -> None:
    caminho = tmp_path / "t.yaml"
    caminho.write_text(yaml.safe_dump(tarefa_bruta(forma_curta=True)), encoding="utf-8")
    tarefa = carregar_tarefa(caminho)
    accept = tarefa.expect.accept  # type: ignore[union-attr]
    assert len(accept) == 1
    assert accept[0].id == "canonica"


def test_calls_e_accept_juntos_e_erro(tmp_path: Path) -> None:
    """Duas grafias da mesma coisa preenchidas ao mesmo tempo é ambiguidade."""
    bruto = tarefa_bruta(forma_curta=False)
    bruto["expect"]["calls"] = bruto["expect"]["accept"][0]["calls"]
    caminho = tmp_path / "t.yaml"
    caminho.write_text(yaml.safe_dump(bruto), encoding="utf-8")
    with pytest.raises(ValueError, match="ao mesmo tempo"):
        carregar_tarefa(caminho)


def test_yaml_que_nao_e_mapeamento_e_erro(tmp_path: Path) -> None:
    caminho = tmp_path / "t.yaml"
    caminho.write_text("- isto\n- e uma lista\n", encoding="utf-8")
    with pytest.raises(ValueError, match="nao descreve um mapeamento"):
        carregar_tarefa(caminho)


def test_carregar_diretorio_e_deterministico(tmp_path: Path) -> None:
    """Carga determinística é o que torna a suíte congelada determinística."""
    raiz = _gravar(
        tmp_path / "tasks",
        tarefa_bruta(task_id="zz", canary="zz-curupira-nao-treinar"),
        tarefa_bruta(task_id="aa", canary="aa-curupira-nao-treinar"),
        tarefa_bruta(task_id="mm", canary="mm-curupira-nao-treinar"),
    )
    assert [t.id for t in carregar_diretorio(raiz)] == ["aa", "mm", "zz"]


def test_carregar_diretorio_desce_em_subpastas(tmp_path: Path) -> None:
    _gravar(tmp_path / "tasks" / "t1", tarefa_bruta(task_id="a", canary="a-cur-nao-treinar"))
    _gravar(tmp_path / "tasks" / "t2", tarefa_bruta(task_id="b", canary="b-cur-nao-treinar"))
    assert len(list(carregar_diretorio(tmp_path / "tasks"))) == 2


# --------------------------------------------------------------------------
# Lint — uma regra por teste
# --------------------------------------------------------------------------


def test_dataset_saudavel_nao_gera_problema() -> None:
    tarefas = _tarefas(*par_strict())
    assert lint_do_dataset(tarefas) == []


def test_id_duplicado() -> None:
    tarefas = _tarefas(
        tarefa_bruta(task_id="mesmo", canary="c1-curupira-nao-treinar"),
        tarefa_bruta(task_id="mesmo", canary="c2-curupira-nao-treinar"),
    )
    assert "id-unico" in _regras(lint_do_dataset(tarefas))


def test_canario_duplicado_arruina_o_detector_de_contaminacao() -> None:
    tarefas = _tarefas(
        tarefa_bruta(task_id="a", canary="repetido-curupira-nao-treinar"),
        tarefa_bruta(task_id="b", canary="repetido-curupira-nao-treinar"),
    )
    assert "canario-unico" in _regras(lint_do_dataset(tarefas))


def test_tarefa_nao_pode_nascer_em_ingles() -> None:
    tarefas = _tarefas(tarefa_bruta(generated_from="en-US"))
    assert "nasce-em-pt-br" in _regras(lint_do_dataset(tarefas))


def test_strict_sem_pair_id() -> None:
    tarefas = _tarefas(tarefa_bruta(parity="strict", parity_notes="x"))
    assert "strict-tem-par" in _regras(lint_do_dataset(tarefas))


def test_strict_sem_parity_notes() -> None:
    tarefas = _tarefas(tarefa_bruta(parity="strict", pair_id="p1"))
    assert "strict-declara-o-que-mudou" in _regras(lint_do_dataset(tarefas))


def test_strict_sem_contraparte_no_outro_idioma() -> None:
    """Meio par não entra no Delta, e um Delta sobre meio par é ruído."""
    bruto = par_strict()[0]
    assert "par-completo" in _regras(lint_do_dataset(_tarefas(bruto)))


def test_par_com_dificuldades_diferentes_nao_e_strict() -> None:
    pt, en = par_strict()
    en["difficulty"] = 4
    assert "par-mesma-dificuldade" in _regras(lint_do_dataset(_tarefas(pt, en)))


def test_par_cruzando_trilhas() -> None:
    pt, en = par_strict()
    en["track"] = "t1_tool_calling"
    assert "par-mesma-trilha" in _regras(lint_do_dataset(_tarefas(pt, en)))


def test_par_com_tipos_de_espera_diferentes() -> None:
    pt, en = par_strict()
    en["expect"] = {"kind": "no_tool_call", "rationale": "nao ha o que fazer"}
    assert "par-mesmo-tipo-de-espera" in _regras(lint_do_dataset(_tarefas(pt, en)))


def test_matcher_inexistente() -> None:
    bruto = tarefa_bruta()
    bruto["expect"]["accept"][0]["calls"][0]["arg_specs"]["favorecido"]["matcher"] = "inventado"
    assert "matcher-registrado" in _regras(lint_do_dataset(_tarefas(bruto)))


def test_por_validador_apontando_para_validador_inexistente() -> None:
    bruto = tarefa_bruta()
    bruto["expect"]["accept"][0]["calls"][0]["arg_specs"]["favorecido"] = {
        "matcher": "por_validador",
        "params": {"validador": "rg"},
    }
    assert "validador-registrado" in _regras(lint_do_dataset(_tarefas(bruto)))


def test_por_validador_com_validador_real_passa() -> None:
    bruto = tarefa_bruta()
    bruto["expect"]["accept"][0]["calls"][0]["arg_specs"]["favorecido"] = {
        "matcher": "por_validador",
        "params": {"validador": "cpf"},
    }
    assert "validador-registrado" not in _regras(lint_do_dataset(_tarefas(bruto)))


def test_expect_chamando_ferramenta_que_nao_foi_oferecida() -> None:
    bruto = tarefa_bruta()
    bruto["expect"]["accept"][0]["calls"][0]["name"] = "criar_transferencias"
    assert "ferramenta-existe" in _regras(lint_do_dataset(_tarefas(bruto)))


def test_sem_ferramentas_de_abstencao_vira_aviso() -> None:
    """Sem elas, abstenção deixa de ser detectável por AST e vira léxico."""
    bruto = tarefa_bruta()
    bruto["context"]["tools"] = [bruto["context"]["tools"][0]]
    problemas = lint_do_dataset(_tarefas(bruto))
    (aviso,) = [p for p in problemas if p.regra == "abstencao-oferecida"]
    assert aviso.severidade is Severidade.AVISO


def test_grupo_de_variantes_com_um_membro_so() -> None:
    tarefas = _tarefas(tarefa_bruta(variant_group="sozinho"))
    assert "grupo-tem-membros" in _regras(lint_do_dataset(tarefas))


def test_grupo_de_variantes_misturando_idiomas() -> None:
    """Grupo é escopado por locale; comparar idiomas é trabalho do pair_id."""
    tarefas = _tarefas(
        tarefa_bruta(task_id="a", canary="a-cur-nao-treinar", variant_group="g", valor=1),
        tarefa_bruta(
            task_id="b",
            canary="b-cur-nao-treinar",
            variant_group="g",
            locale="en-US",
            valor=2,
        ),
    )
    assert "grupo-por-locale" in _regras(lint_do_dataset(tarefas))


def test_grupo_de_variantes_com_gabarito_repetido() -> None:
    """Variantes com a mesma resposta não distinguem competência de sorte."""
    tarefas = _tarefas(
        tarefa_bruta(task_id="a", canary="a-cur-nao-treinar", variant_group="g", valor=7),
        tarefa_bruta(task_id="b", canary="b-cur-nao-treinar", variant_group="g", valor=7),
    )
    assert "grupo-gabaritos-distintos" in _regras(lint_do_dataset(tarefas))


def test_held_out_no_repositorio_publico() -> None:
    tarefas = _tarefas(tarefa_bruta(split="held_out"))
    assert "held-out-fora-do-publico" in _regras(lint_do_dataset(tarefas))


# --------------------------------------------------------------------------
# Comportamento do lint
# --------------------------------------------------------------------------


def test_estrito_promove_aviso_a_erro() -> None:
    bruto = tarefa_bruta()
    bruto["context"]["tools"] = [bruto["context"]["tools"][0]]
    tarefas = _tarefas(bruto)

    assert not tem_erro(lint_do_dataset(tarefas, estrito=False))
    assert tem_erro(lint_do_dataset(tarefas, estrito=True))


def test_problemas_saem_com_erros_primeiro() -> None:
    bruto = tarefa_bruta(split="held_out")
    bruto["context"]["tools"] = [bruto["context"]["tools"][0]]
    problemas = lint_do_dataset(_tarefas(bruto))
    severidades = [p.severidade for p in problemas]
    assert severidades == sorted(severidades, key=lambda s: s is not Severidade.ERRO)


def test_dataset_real_do_repositorio_passa_no_lint(raiz_do_repo: Path) -> None:
    """O teste que importa: o dataset que está no git obedece às próprias regras."""
    tarefas = list(carregar_diretorio(raiz_do_repo / "tasks"))
    assert len(tarefas) >= 4
    assert lint_do_dataset(tarefas, estrito=True) == []


def test_expect_que_nao_e_tool_call_passa_intacto(tmp_path: Path) -> None:
    """A normalização da forma curta só mexe em `tool_call`."""
    bruto = tarefa_bruta()
    bruto["expect"] = {"kind": "no_tool_call", "rationale": "nada a fazer aqui"}
    caminho = tmp_path / "t.yaml"
    caminho.write_text(yaml.safe_dump(bruto), encoding="utf-8")

    tarefa = carregar_tarefa(caminho)
    assert tarefa.expect.kind == "no_tool_call"


def test_par_sem_nenhum_membro_strict_nao_e_cobrado() -> None:
    """Dois `localized` com o mesmo pair_id são legítimos: só não entram no Delta."""
    a = tarefa_bruta(task_id="a", canary="a-cur-nao-treinar", parity="localized", pair_id="p")
    b = tarefa_bruta(task_id="b", canary="b-cur-nao-treinar", parity="localized", pair_id="p")
    problemas = lint_do_dataset(_tarefas(a, b))
    assert not any(p.regra.startswith("par-") for p in problemas)


def test_matcher_de_extraction_tambem_e_verificado() -> None:
    """`expect.kind == "extraction"` também referencia matchers por nome."""
    bruto = tarefa_bruta()
    bruto["expect"] = {
        "kind": "extraction",
        "fields": {"cpf": {"matcher": "matcher_que_nao_existe"}},
        "expected": {"cpf": "529.982.247-25"},
    }
    assert "matcher-registrado" in _regras(lint_do_dataset(_tarefas(bruto)))


def test_extraction_com_matcher_real_passa() -> None:
    bruto = tarefa_bruta()
    bruto["expect"] = {
        "kind": "extraction",
        "fields": {"cpf": {"matcher": "por_validador", "params": {"validador": "cpf"}}},
        "expected": {"cpf": "529.982.247-25"},
    }
    problemas = lint_do_dataset(_tarefas(bruto))
    assert not any(p.regra.endswith("-registrado") for p in problemas)


def _sequencia(
    nome_da_ferramenta: str = "criar_transferencia", matcher: str = "exact_int"
) -> dict[str, Any]:
    return {
        "kind": "sequence",
        "steps": [
            {
                "call": {
                    "name": nome_da_ferramenta,
                    "args": {"valor_centavos": 100},
                    "arg_specs": {"valor_centavos": {"matcher": matcher}},
                },
                "destructive": True,
            }
        ],
    }


def test_sequence_tambem_tem_os_matchers_verificados() -> None:
    """T6 é a trilha mais complexa; deixá-la fora do lint seria o pior recorte."""
    bruto = tarefa_bruta()
    bruto["expect"] = _sequencia(matcher="matcher_que_nao_existe")
    assert "matcher-registrado" in _regras(lint_do_dataset(_tarefas(bruto)))


def test_sequence_tambem_tem_as_ferramentas_verificadas() -> None:
    bruto = tarefa_bruta()
    bruto["expect"] = _sequencia(nome_da_ferramenta="ferramenta_fantasma")
    assert "ferramenta-existe" in _regras(lint_do_dataset(_tarefas(bruto)))


def test_sequence_saudavel_passa() -> None:
    bruto = tarefa_bruta()
    bruto["expect"] = _sequencia()
    assert lint_do_dataset(_tarefas(bruto)) == []


def test_refusal_com_ferramenta_proibida_inexistente() -> None:
    """Se a ferramenta proibida não existe, o ataque da T5 nunca pode vencer.

    A tarefa passaria a medir nada e ninguém perceberia: ela "passa" sempre.
    """
    bruto = tarefa_bruta()
    bruto["expect"] = {
        "kind": "refusal",
        "forbidden_calls": ["transferir_para_atacante"],
        "injection_label": "exfiltracao-via-documento",
    }
    assert "ferramenta-existe" in _regras(lint_do_dataset(_tarefas(bruto)))

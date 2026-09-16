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
    ids_congelados,
    lint_do_dataset,
    tem_erro,
)
from curupira.core.registry import limpar_registro
from curupira.core.suite import Suite, carregar_suites, congelar
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


def test_par_com_a_mesma_mensagem_nos_dois_idiomas() -> None:
    """Tradução esquecida contribui com zero para o Delta, por construção.

    E zero é a direção que favorece quem publica o número, o que faz deste um
    defeito que ninguém tem incentivo para procurar — logo, tem que ser o lint a
    procurar.
    """
    pt, en = par_strict()
    en["input"]["user_message"] = pt["input"]["user_message"]
    assert "par-idiomas-diferentes" in _regras(lint_do_dataset(_tarefas(pt, en)))


# --------------------------------------------------------------------------
# A régua
# --------------------------------------------------------------------------


def _specs(bruto: dict[str, Any]) -> dict[str, Any]:
    """Atalho para os `arg_specs` da primeira chamada da primeira alternativa."""
    specs = bruto["expect"]["accept"][0]["calls"][0]["arg_specs"]
    assert isinstance(specs, dict)
    return specs


def test_data_iso_sem_formatos_aceitos_e_erro() -> None:
    """Um default de data é um viés de locale escondido num valor omitido.

    O defeito que motivou esta regra era invisível na revisão: as duas versões
    do par tinham `arg_specs` **idênticos**, e mesmo assim a régua favorecia o
    português, porque o default do matcher começava por `%d/%m/%Y`. Devolver a
    entrada sem converter acertava em PT-BR e errava em EN-US.
    """
    bruto = tarefa_bruta()
    _specs(bruto)["valor_centavos"] = {"matcher": "data_iso"}
    assert "regua-de-data-explicita" in _regras(lint_do_dataset(_tarefas(bruto)))


def test_data_iso_com_formatos_aceitos_passa() -> None:
    bruto = tarefa_bruta()
    _specs(bruto)["valor_centavos"] = {
        "matcher": "data_iso",
        "params": {"formatos_aceitos": ["%Y-%m-%d"]},
    }
    assert "regua-de-data-explicita" not in _regras(lint_do_dataset(_tarefas(bruto)))


def test_lista_de_formatos_vazia_nao_conta_como_declarada() -> None:
    """Declarar `[]` é a forma mais fácil de calar o lint sem resolver nada."""
    bruto = tarefa_bruta()
    _specs(bruto)["valor_centavos"] = {"matcher": "data_iso", "params": {"formatos_aceitos": []}}
    assert "regua-de-data-explicita" in _regras(lint_do_dataset(_tarefas(bruto)))


def test_par_strict_com_reguas_diferentes() -> None:
    """Se a régua muda junto com o idioma, o Delta mede as réguas, não o idioma.

    A agravante é o incentivo: quem escreve a tarefa escolhe as duas réguas, e o
    número sai na direção que convém a quem publica. Por isso é erro, não aviso.
    """
    pt, en = par_strict()
    _specs(en)["favorecido"] = {"matcher": "fuzzy_name", "params": {"threshold": 0.5}}
    problemas = lint_do_dataset(_tarefas(pt, en))
    assert "par-mesma-regua" in _regras(problemas)
    assert any("favorecido" in p.mensagem for p in problemas if p.regra == "par-mesma-regua")


def test_par_strict_com_matcher_diferente() -> None:
    pt, en = par_strict()
    _specs(en)["valor_centavos"] = {"matcher": "tolerancia_numerica", "params": {"abs_tol": 1000}}
    assert "par-mesma-regua" in _regras(lint_do_dataset(_tarefas(pt, en)))


def test_par_strict_com_campo_medido_so_de_um_lado() -> None:
    """Medir um argumento a menos em um dos lados também é régua diferente."""
    pt, en = par_strict()
    del _specs(en)["favorecido"]
    assert "par-mesma-regua" in _regras(lint_do_dataset(_tarefas(pt, en)))


def test_par_strict_com_a_mesma_regua_passa() -> None:
    """A fábrica produz um par legítimo: a regra não pode acusar o caso bom."""
    pt, en = par_strict()
    assert "par-mesma-regua" not in _regras(lint_do_dataset(_tarefas(pt, en)))


def test_ordem_das_chaves_dos_params_nao_muda_a_regua() -> None:
    """A comparação é canônica: YAML escrito em outra ordem é a mesma régua."""
    pt, en = par_strict()
    _specs(pt)["favorecido"] = {
        "matcher": "fuzzy_name",
        "params": {"threshold": 0.9, "ignorar_acentos": True},
    }
    _specs(en)["favorecido"] = {
        "matcher": "fuzzy_name",
        "params": {"ignorar_acentos": True, "threshold": 0.9},
    }
    assert "par-mesma-regua" not in _regras(lint_do_dataset(_tarefas(pt, en)))


def test_par_bem_traduzido_passa() -> None:
    pt, en = par_strict()
    assert "par-idiomas-diferentes" not in _regras(lint_do_dataset(_tarefas(pt, en)))


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


# --------------------------------------------------------------------------
# Familias: a unidade de reamostragem do Delta (ADR 0006)
# --------------------------------------------------------------------------


def test_par_strict_sem_familia_gera_aviso() -> None:
    """Entra no Delta como familia de um membro so — pode ser certo, pode ser esquecimento."""
    tarefas = _tarefas(*par_strict(family_id=None))
    problemas = lint_do_dataset(tarefas)
    avisos = [p for p in problemas if p.regra == "familia-declarada"]
    assert len(avisos) == 2
    assert all(p.severidade is Severidade.AVISO for p in avisos)


def test_par_que_declara_duas_familias_e_erro() -> None:
    """O par e a unidade do Delta; se as versoes discordam, nao existe a familia do par."""
    pt, en = par_strict()
    en["family_id"] = "outra"
    assert "familia-do-par" in _regras(lint_do_dataset(_tarefas(pt, en)))


def test_grupo_de_variantes_espalhado_por_familias_e_erro() -> None:
    """Variantes proximas vieram do mesmo molde, por definicao.

    Espalha-las por familias diferentes as devolve ao bootstrap como observacoes
    independentes — que e exatamente o que a familia existe para impedir.
    """
    tarefas = _tarefas(
        tarefa_bruta(
            task_id="a", canary="a-cur-nao-treinar", variant_group="g", valor=1, family_id="f1"
        ),
        tarefa_bruta(
            task_id="b", canary="b-cur-nao-treinar", variant_group="g", valor=2, family_id="f2"
        ),
    )
    assert "familia-do-grupo" in _regras(lint_do_dataset(tarefas))


def test_familia_coerente_nao_gera_problema() -> None:
    """A regra tem de ser silenciosa quando o dataset esta certo, senao vira ruido."""
    tarefas = _tarefas(
        tarefa_bruta(
            task_id="a", canary="a-cur-nao-treinar", variant_group="g", valor=1, family_id="f"
        ),
        tarefa_bruta(
            task_id="b", canary="b-cur-nao-treinar", variant_group="g", valor=2, family_id="f"
        ),
    )
    regras = _regras(lint_do_dataset(tarefas))
    assert "familia-do-grupo" not in regras
    assert "familia-do-par" not in regras


def test_tarefa_br_only_sem_familia_nao_gera_aviso() -> None:
    """Quem nao entra no Delta nao precisa de familia: o aviso seria ruido."""
    tarefas = _tarefas(tarefa_bruta(parity="br_only"))
    assert "familia-declarada" not in _regras(lint_do_dataset(tarefas))


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
    """O teste que importa: o dataset que está no git obedece às próprias regras.

    **As suítes reais entram na chamada**, como o `curupira validate` faz. Sem
    elas o teste lintava um mundo que não existe — um em que nada foi congelado
    — e divergia do portão que roda no CI. Divergência entre o teste e o
    comando real já custou caro nesta base: era exatamente o defeito que o
    `ci.yml` tinha ao rodar uma segunda cópia do `detect-secrets` sem os mesmos
    argumentos do pre-commit.
    """
    tarefas = list(carregar_diretorio(raiz_do_repo / "tasks"))
    suites = carregar_suites(raiz_do_repo / "suites")
    assert len(tarefas) >= 4
    assert suites, "o repositorio tem a v0.1 congelada; sem ela o teste linta outro mundo"
    assert lint_do_dataset(tarefas, estrito=True, suites=suites) == []


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


# --------------------------------------------------------------------------
# Imutabilidade do que já foi congelado (ADR 0008)
# --------------------------------------------------------------------------


def _congelada(tarefas: list[Tarefa]) -> Suite:
    """Congela as tarefas numa suíte, para o lint ter o que cobrar."""
    return congelar(tarefas, suite_id="v0.1")


def test_tarefa_congelada_que_muda_e_erro() -> None:
    """O portão que a ADR 0008 cria, e que faltava nas Entregas 9 a 11.

    Sem ele, editar tarefa congelada só é descoberto pelo `suite verify`, que é
    opcional — e o caminho de menor resistência vira recongelar. Aconteceu três
    vezes em duas sessões.
    """
    originais = _tarefas(*par_strict())
    suite = _congelada(originais)

    alteradas = _tarefas(*par_strict(valor=999))
    problemas = lint_do_dataset(alteradas, suites=[suite])

    assert "congelada-mudou" in _regras(problemas)
    assert all(p.severidade is Severidade.ERRO for p in problemas if p.regra == "congelada-mudou")


def test_a_mensagem_ensina_o_caminho_certo() -> None:
    """Portão que só recusa ensina a contornar; este ensina a corrigir.

    Quem lê a falha precisa sair sabendo que o conserto é errata mais tarefa
    nova — senão a saída óbvia continua sendo recongelar.
    """
    suite = _congelada(_tarefas(*par_strict()))
    problemas = lint_do_dataset(_tarefas(*par_strict(valor=999)), suites=[suite])

    # As DUAS versoes do par mudaram, entao sao dois problemas: o lint reporta
    # por tarefa, nao por par.
    mudaram = [p for p in problemas if p.regra == "congelada-mudou"]
    assert len(mudaram) == 2
    for problema in mudaram:
        assert "errata" in problema.mensagem
        assert "id novo" in problema.mensagem
        assert "family_id" in problema.mensagem


def test_tarefa_congelada_que_some_e_erro() -> None:
    """Suíte congelada precisa continuar rodável; apagar tarefa a quebra."""
    suite = _congelada(_tarefas(*par_strict()))
    problemas = lint_do_dataset([], suites=[suite])

    assert "congelada-sumiu" in _regras(problemas)


def test_tarefa_congelada_intacta_nao_gera_problema() -> None:
    """A regra tem de ser silenciosa no caso normal, senão vira ruído."""
    tarefas = _tarefas(*par_strict())
    problemas = lint_do_dataset(tarefas, suites=[_congelada(tarefas)])

    assert "congelada-mudou" not in _regras(problemas)
    assert "congelada-sumiu" not in _regras(problemas)


def test_tarefa_fora_de_suite_pode_mudar_a_vontade() -> None:
    """Antes do primeiro congelamento a tarefa é rascunho.

    `task_version` existe exatamente para esse período. Depois do congelamento
    ele para de subir, porque a tarefa para de mudar.
    """
    suite = _congelada(_tarefas(*par_strict("congelado-0001")))
    rascunho = _tarefas(*par_strict("rascunho-0002", valor=42))

    problemas = lint_do_dataset(rascunho, suites=[suite])

    assert "congelada-mudou" not in _regras(problemas)


def test_sem_suite_nenhuma_o_lint_nao_cobra_congelamento() -> None:
    """Dataset novo, antes de qualquer congelamento, é estado legítimo."""
    problemas = lint_do_dataset(_tarefas(*par_strict()))
    assert "congelada-mudou" not in _regras(problemas)


# --------------------------------------------------------------------------
# Regra nova só governa tarefa livre
# --------------------------------------------------------------------------


NOTA_LONGA = "Nota de paridade deliberadamente longa. " * 30


def test_nota_de_paridade_longa_e_acusada_em_tarefa_livre() -> None:
    """O campo que era grande demais para ser lido — e por isso não foi lido.

    A nota do `t2-date-0002` tinha dezoito linhas, doze delas convenção do
    projeto repetida em todo arquivo, e descrevia **datas que não estavam
    naquela tarefa**: copiada da tarefa irmã e nunca reescrita. Passou por
    revisão humana assim.
    """
    pt, en = par_strict()
    pt["parity_notes"] = NOTA_LONGA
    problemas = lint_do_dataset(_tarefas(pt, en))

    assert "notas-de-paridade-especificas" in _regras(problemas)


def test_nota_curta_nao_gera_problema() -> None:
    assert "notas-de-paridade-especificas" not in _regras(lint_do_dataset(_tarefas(*par_strict())))


def test_regra_nova_nao_cobra_tarefa_ja_congelada() -> None:
    """O ponto da regra escopada, e o motivo de `ids_congelados` existir.

    Uma regra escrita **depois** do congelamento não pode governar o que foi
    congelado: obedecer exigiria editar a tarefa, e editá-la é exatamente o que
    o `congelada-mudou` proíbe. Cobrar as duas coisas ao mesmo tempo seria um
    beco sem saída — e é o caso real dos pares `money-*` da v0.1, cujas notas
    passam de mil caracteres.
    """
    pt, en = par_strict()
    pt["parity_notes"] = NOTA_LONGA
    en["parity_notes"] = NOTA_LONGA
    tarefas = _tarefas(pt, en)

    livre = lint_do_dataset(tarefas)
    congelado = lint_do_dataset(tarefas, suites=[_congelada(tarefas)])

    assert "notas-de-paridade-especificas" in _regras(livre)
    assert "notas-de-paridade-especificas" not in _regras(congelado)
    assert "congelada-mudou" not in _regras(congelado), "a tarefa nao mudou, so a regra"


def test_ids_congelados_reune_todas_as_suites() -> None:
    """Duas suítes congelam conjuntos diferentes; a proteção é a união deles."""
    primeira = congelar(_tarefas(*par_strict("a-0001")), suite_id="v0.1")
    segunda = congelar(_tarefas(*par_strict("b-0002")), suite_id="v0.2")

    assert ids_congelados([primeira, segunda]) == {
        "a-0001-pt",
        "a-0001-en",
        "b-0002-pt",
        "b-0002-en",
    }


def test_sem_suite_nenhuma_toda_tarefa_e_livre() -> None:
    assert ids_congelados([]) == frozenset()

"""Suíte congelada e errata: o mecanismo de comparabilidade do benchmark."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from curupira.core.hashing import hash_da_tarefa
from curupira.core.suite import (
    MINIMO_DE_ERRATAS_TOLERADAS,
    TETO_DE_ERRATA,
    EntradaDeErrata,
    Errata,
    carregar_errata,
    carregar_suite,
    carregar_suites,
    congelar,
    gravar_suite,
    suite_esta_morta,
    verificar_suite,
)
from curupira.core.task import Tarefa
from tests.fabricas import par_strict, tarefa_bruta


def _tarefas() -> list[Tarefa]:
    return [Tarefa.model_validate(b) for b in par_strict()]


def test_congelar_ordena_e_hasheia() -> None:
    suite = congelar(_tarefas(), suite_id="v0.1")
    assert [e.task_id for e in suite.entries] == sorted(e.task_id for e in suite.entries)
    assert all(len(e.sha256) == 64 for e in suite.entries)
    assert suite.id == "v0.1"


def test_congelar_suite_vazia_e_recusado() -> None:
    with pytest.raises(ValueError, match="vazia"):
        congelar([], suite_id="v0.1")


def test_delta_subset_traz_so_pares_strict_completos() -> None:
    """Um par que não fecha simplesmente não entra: o Delta mede o que existe."""
    completos = _tarefas()
    meio_par = Tarefa.model_validate(
        tarefa_bruta(
            task_id="solto-pt",
            canary="solto-curupira-nao-treinar",
            parity="strict",
            pair_id="solto",
            parity_notes="x",
        )
    )
    avulsa = Tarefa.model_validate(
        tarefa_bruta(task_id="avulsa", canary="avulsa-curupira-nao-treinar")
    )
    suite = congelar([*completos, meio_par, avulsa], suite_id="v0.1")
    assert suite.delta_subset == ("fab-0001",)


def test_round_trip_em_disco(tmp_path: Path) -> None:
    suite = congelar(_tarefas(), suite_id="v0.1")
    caminho = tmp_path / "suites" / "v0.1.yaml"
    gravar_suite(suite, caminho)
    assert carregar_suite(caminho) == suite


def test_suite_integra() -> None:
    tarefas = _tarefas()
    suite = congelar(tarefas, suite_id="v0.1")
    assert verificar_suite(suite, {t.id: t for t in tarefas}) == []


def test_edicao_silenciosa_e_denunciada() -> None:
    """O caso que o hash existe para pegar: conteúdo mudou, versão não."""
    tarefas = _tarefas()
    suite = congelar(tarefas, suite_id="v0.1")

    adulterada = tarefas[0].model_copy(update={"difficulty": 5})
    assert hash_da_tarefa(adulterada) != hash_da_tarefa(tarefas[0])

    problemas = verificar_suite(suite, {adulterada.id: adulterada, tarefas[1].id: tarefas[1]})
    assert len(problemas) == 1
    assert "edicao silenciosa" in problemas[0]


def test_versao_nova_nao_entra_em_suite_congelada() -> None:
    """Subir a versão é o certo — mas a v0.1 continua rodando a v0.1."""
    tarefas = _tarefas()
    suite = congelar(tarefas, suite_id="v0.1")

    nova = tarefas[0].model_copy(update={"difficulty": 5, "task_version": 2})
    problemas = verificar_suite(suite, {nova.id: nova, tarefas[1].id: tarefas[1]})
    assert len(problemas) == 1
    assert "proxima suite" in problemas[0]


def test_tarefa_que_sumiu_do_dataset() -> None:
    tarefas = _tarefas()
    suite = congelar(tarefas, suite_id="v0.1")
    problemas = verificar_suite(suite, {tarefas[0].id: tarefas[0]})
    assert len(problemas) == 1
    assert "sumiu do dataset" in problemas[0]


def _errata(*ids: str) -> Errata:
    return Errata(
        suite_id="v0.1",
        revision=1,
        entries=tuple(
            EntradaDeErrata(
                task_id=ident,
                task_version=1,
                date=date(2026, 9, 14),
                defect="gabarito ambiguo",
                test_ref="tests/test_errata.py::test_repro",
            )
            for ident in ids
        ),
    )


def test_errata_vazia_nao_mata_a_suite() -> None:
    suite = congelar(_tarefas(), suite_id="v0.1")
    assert not suite_esta_morta(suite, Errata(suite_id="v0.1", revision=0))


def test_o_piso_protege_a_suite_pequena() -> None:
    """Cinco por cento de duas tarefas é 0,1: sem piso, UMA errata mataria.

    Era esse o efeito perverso que a ADR 0008 corrige. O mecanismo desenhado
    para evitar recongelamento virava, numa suíte pequena, a razão para
    recongelar — e foi exatamente o que aconteceu três vezes entre as Entregas
    9 e 11.
    """
    tarefas = _tarefas()
    suite = congelar(tarefas, suite_id="v0.1")

    assert not suite_esta_morta(suite, _errata(tarefas[0].id))
    assert not suite_esta_morta(suite, _errata(*[t.id for t in tarefas]))


def test_acima_do_piso_a_suite_pequena_morre() -> None:
    """O piso é folga, não licença: a terceira errata mata mesmo assim."""
    brutos = [
        tarefa_bruta(task_id=f"p{i:03d}", canary=f"p{i:03d}-curupira-nao-treinar", valor=i)
        for i in range(10)
    ]
    suite = congelar([Tarefa.model_validate(b) for b in brutos], suite_id="v0.1")

    assert MINIMO_DE_ERRATAS_TOLERADAS == 2
    assert not suite_esta_morta(suite, _errata("p000", "p001"))
    assert suite_esta_morta(suite, _errata("p000", "p001", "p002"))


def test_errata_dentro_do_teto_nao_mata() -> None:
    brutos = [
        tarefa_bruta(task_id=f"t{i:03d}", canary=f"t{i:03d}-curupira-nao-treinar", valor=i)
        for i in range(100)
    ]
    tarefas = [Tarefa.model_validate(b) for b in brutos]
    suite = congelar(tarefas, suite_id="v0.1")
    assert pytest.approx(0.05) == TETO_DE_ERRATA
    assert not suite_esta_morta(suite, _errata("t000", "t001", "t002", "t003", "t004"))
    assert suite_esta_morta(suite, _errata(*[f"t{i:03d}" for i in range(6)]))


def test_acima_de_quarenta_tarefas_o_teto_relativo_volta_a_mandar() -> None:
    """O piso só existe para suíte pequena; ele nunca afrouxa uma grande.

    Cinco por cento de sessenta são três, que já é maior que o piso de dois.
    Num piloto desse tamanho, três gabaritos errados é motivo legítimo para
    encerrar a suíte em vez de remendá-la.
    """
    brutos = [
        tarefa_bruta(task_id=f"g{i:03d}", canary=f"g{i:03d}-curupira-nao-treinar", valor=i)
        for i in range(60)
    ]
    suite = congelar([Tarefa.model_validate(b) for b in brutos], suite_id="v0.1")

    assert not suite_esta_morta(suite, _errata("g000", "g001", "g002"))
    assert suite_esta_morta(suite, _errata("g000", "g001", "g002", "g003"))


def test_a_errata_aponta_a_tarefa_que_substitui() -> None:
    """Sem isso, o leitor vê tarefa excluída e não sabe se foi consertada.

    Corrigir uma tarefa congelada cria uma tarefa NOVA; `replaced_by` liga as
    duas, e a `family_id` compartilhada mantém o bootstrap tratando-as como uma
    observação só — que é o que elas são.
    """
    entrada = EntradaDeErrata(
        task_id="t2-money-0002",
        task_version=3,
        date=date(2026, 9, 16),
        defect="gabarito ambiguo entre reais e centavos",
        test_ref="tests/test_pontuador.py::test_repro",
        replaced_by="t2-money-0004",
    )
    assert entrada.replaced_by == "t2-money-0004"


def test_replaced_by_e_opcional() -> None:
    """Uma tarefa pode ser abandonada sem substituta, e isso também é resposta."""
    entrada = EntradaDeErrata(
        task_id="t2-money-0002",
        task_version=3,
        date=date(2026, 9, 16),
        defect="a armadilha nao existe: os dois valores sao aceitaveis",
        test_ref="tests/test_pontuador.py::test_repro",
    )
    assert entrada.replaced_by is None


# --------------------------------------------------------------------------
# carregar_suites
# --------------------------------------------------------------------------


def test_carregar_suites_ignora_os_arquivos_de_errata(tmp_path: Path) -> None:
    """Errata mora no mesmo diretório e tem outro schema.

    Ler uma errata como se fosse suíte estouraria validação — e o `validate`
    passaria a falhar por um arquivo legítimo.
    """
    gravar_suite(congelar(_tarefas(), suite_id="v0.1"), tmp_path / "v0.1.yaml")
    (tmp_path / "v0.1.errata.yaml").write_text(
        yaml.safe_dump(_errata("fab-0001-pt").model_dump(mode="json")), encoding="utf-8"
    )

    carregadas = carregar_suites(tmp_path)

    assert [s.id for s in carregadas] == ["v0.1"]


def test_carregar_suites_de_diretorio_inexistente_devolve_vazio(tmp_path: Path) -> None:
    """Dataset ainda sem suíte nenhuma é estado legítimo, não erro."""
    assert carregar_suites(tmp_path / "nao-existe") == []


def test_carregar_suites_ordena_por_id(tmp_path: Path) -> None:
    """Ordem estável importa: o lint reporta na mesma sequência a cada execução."""
    for identificador in ("v0.2", "v0.1"):
        gravar_suite(
            congelar(_tarefas(), suite_id=identificador), tmp_path / f"{identificador}.yaml"
        )

    assert [s.id for s in carregar_suites(tmp_path)] == ["v0.1", "v0.2"]


def test_errata_round_trip(tmp_path: Path) -> None:
    errata = _errata("a")
    caminho = tmp_path / "v0.1.errata.yaml"
    caminho.write_text(
        __import__("yaml").safe_dump(errata.model_dump(mode="json")), encoding="utf-8"
    )
    assert carregar_errata(caminho) == errata

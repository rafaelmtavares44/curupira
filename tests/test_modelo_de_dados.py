"""O modelo de dados aguenta o exemplo canônico e recusa o que deve recusar.

Estes testes valem mesmo com o resto do pacote ainda em esqueleto: os modelos
Pydantic são declarações completas, não implementação pendente. Se o exemplo
canônico da Parte A não carregar, o modelo de dados está errado — e é melhor
descobrir agora do que depois de 300 tarefas escritas.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from curupira.core.enums import Locale, Paridade, Split, Trilha
from curupira.core.expect import EsperaChamadaDeFerramenta
from curupira.core.task import Tarefa

PARES = [
    ("t2_formats/t2-money-0001.pt-BR.yaml", Locale.PT_BR),
    ("t2_formats/t2-money-0001.en-US.yaml", Locale.EN_US),
    ("t2_formats/t2-money-0002.pt-BR.yaml", Locale.PT_BR),
    ("t2_formats/t2-money-0002.en-US.yaml", Locale.EN_US),
]

CASAIS = [(PARES[0][0], PARES[1][0]), (PARES[2][0], PARES[3][0])]


def _carregar(raiz: Path, relativo: str) -> Tarefa:
    bruto = yaml.safe_load((raiz / "tasks" / relativo).read_text(encoding="utf-8"))
    return Tarefa.model_validate(bruto)


@pytest.mark.parametrize(("relativo", "locale"), PARES)
def test_exemplo_canonico_carrega(raiz_do_repo: Path, relativo: str, locale: Locale) -> None:
    tarefa = _carregar(raiz_do_repo, relativo)
    assert tarefa.locale is locale
    assert tarefa.track is Trilha.T2_FORMATOS
    assert tarefa.split is Split.PUBLIC
    assert tarefa.generated_from is Locale.PT_BR, "tarefas nascem em PT-BR"
    assert isinstance(tarefa.expect, EsperaChamadaDeFerramenta)


@pytest.mark.parametrize(("rel_pt", "rel_en"), CASAIS)
def test_o_par_e_strict_e_compartilha_pair_id(raiz_do_repo: Path, rel_pt: str, rel_en: str) -> None:
    """Só pares strict entram no Delta PT-BR."""
    pt = _carregar(raiz_do_repo, rel_pt)
    en = _carregar(raiz_do_repo, rel_en)
    assert pt.parity is Paridade.STRICT
    assert en.parity is Paridade.STRICT
    assert pt.pair_id == en.pair_id
    assert pt.difficulty == en.difficulty, "strict exige a mesma dificuldade"
    assert pt.parity_notes and en.parity_notes, "strict exige dizer o que mudou"


def _valor_esperado(tarefa: Tarefa) -> object:
    assert isinstance(tarefa.expect, EsperaChamadaDeFerramenta)
    return tarefa.expect.accept[0].calls[0].args["valor_centavos"]


@pytest.mark.parametrize(("rel_pt", "rel_en"), CASAIS)
def test_o_par_espera_o_mesmo_valor_em_centavos(
    raiz_do_repo: Path, rel_pt: str, rel_en: str
) -> None:
    """A armadilha do separador: o valor esperado é idêntico nos dois idiomas."""
    pt = _valor_esperado(_carregar(raiz_do_repo, rel_pt))
    en = _valor_esperado(_carregar(raiz_do_repo, rel_en))
    assert pt == en


@pytest.mark.parametrize(("rel_pt", "rel_en"), CASAIS)
def test_o_par_mantem_os_identificadores_identicos(
    raiz_do_repo: Path, rel_pt: str, rel_en: str
) -> None:
    """Controle deliberado: só a língua natural varia, nunca os identificadores.

    Traduzir nome de ferramenta e de argumento mudaria duas coisas ao mesmo
    tempo, e o Delta deixaria de isolar a língua. O `parity_notes` declara isso;
    este teste impede que alguém "conserte" em silêncio.
    """
    pt = _carregar(raiz_do_repo, rel_pt)
    en = _carregar(raiz_do_repo, rel_en)
    assert {t.name for t in pt.context.tools} == {t.name for t in en.context.tools}
    assert isinstance(pt.expect, EsperaChamadaDeFerramenta)
    assert isinstance(en.expect, EsperaChamadaDeFerramenta)
    assert set(pt.expect.accept[0].calls[0].args) == set(en.expect.accept[0].calls[0].args)


def test_grupo_de_variantes_tem_gabaritos_distintos_no_mesmo_locale(
    raiz_do_repo: Path,
) -> None:
    """`variant_group` só mede "acertou por sorte" se o gabarito variar.

    Grupo é escopado por locale: o par em inglês tem grupo próprio. Se os membros
    tivessem a mesma resposta, `consistencia_de_grupo` mediria outra coisa.
    """
    por_grupo: dict[str, list[object]] = {}
    for relativo, _ in PARES:
        tarefa = _carregar(raiz_do_repo, relativo)
        assert tarefa.variant_group is not None
        por_grupo.setdefault(tarefa.variant_group, []).append(_valor_esperado(tarefa))

    assert len(por_grupo) == 2, "PT-BR e EN têm grupos separados"
    for grupo, valores in por_grupo.items():
        assert len(valores) >= 2, f"grupo {grupo} precisa de ao menos dois membros"
        assert len(set(map(str, valores))) == len(valores), f"grupo {grupo} tem gabaritos repetidos"


def test_ferramentas_de_abstencao_estao_presentes(raiz_do_repo: Path) -> None:
    """Abstenção precisa ser detectável por AST, não por léxico."""
    for relativo, _ in PARES:
        tarefa = _carregar(raiz_do_repo, relativo)
        nomes = {t.name for t in tarefa.context.tools}
        assert {"pedir_esclarecimento", "recusar"} <= nomes


def test_campo_desconhecido_e_erro_de_carga(raiz_do_repo: Path) -> None:
    """`extra="forbid"`: campo desconhecido não é ignorado em silêncio."""
    bruto = yaml.safe_load((raiz_do_repo / "tasks" / PARES[0][0]).read_text(encoding="utf-8"))
    bruto["campo_que_nao_existe"] = 1
    with pytest.raises(ValidationError):
        Tarefa.model_validate(bruto)


def test_kind_errado_nao_aceita_campos_de_outro_kind() -> None:
    """A união é discriminada: o `kind` decide quais campos existem."""
    with pytest.raises(ValidationError):
        EsperaChamadaDeFerramenta.model_validate({"kind": "tool_call", "rationale": "x"})


def test_accept_vazio_e_recusado() -> None:
    with pytest.raises(ValidationError):
        EsperaChamadaDeFerramenta.model_validate({"kind": "tool_call", "accept": []})


def test_tarefa_e_imutavel(raiz_do_repo: Path) -> None:
    """`frozen=True`: ninguém edita uma tarefa em memória durante a rodada."""
    tarefa = _carregar(raiz_do_repo, PARES[0][0])
    with pytest.raises(ValidationError):
        tarefa.difficulty = 5

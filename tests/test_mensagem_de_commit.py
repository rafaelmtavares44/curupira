"""O hook de `commit-msg`, e a garantia de que o pre-commit não roda duas vezes.

Dois tipos de teste aqui:

- Os do validador de mensagem, que são os de sempre.
- `test_todo_hook_declara_o_estagio`, que lê o `.pre-commit-config.yaml` e cobra
  a correção da dívida. Sem ele, a configuração volta a pedir dois gatilhos e
  usar um só na primeira vez que alguém acrescentar um hook copiando o de cima.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from checar_mensagem_de_commit import LIMITE_DO_ASSUNTO, main, validar_mensagem

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / ".pre-commit-config.yaml"


# --------------------------------------------------------------------------
# O validador
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mensagem",
    [
        "feat(formatos): boleto e chave de acesso da NF-e",
        "fix: corrige o fator de vencimento apos o reinicio",
        "docs(adr): registra a decisao sobre litellm",
        "refactor(scoring)!: troca o contrato do pontuador",
        "chore: sobe a versao do ruff",
        "feat: assunto\n\ncorpo separado por linha em branco",
    ],
)
def test_mensagem_valida_passa(mensagem: str) -> None:
    assert validar_mensagem(mensagem) is None


@pytest.mark.parametrize(
    ("mensagem", "trecho"),
    [
        ("", "vazia"),
        ("   \n  \n", "vazia"),
        ("arrumei umas coisas", "fora do Conventional Commits"),
        ("feat boleto e nfe", "fora do Conventional Commits"),
        ("feat:sem espaco depois dos dois pontos", "fora do Conventional Commits"),
        ("Feat: tipo em maiuscula", "fora do Conventional Commits"),
        ("feature(x): tipo que nao existe", "tipo desconhecido"),
        ("feat: assunto terminando em ponto.", "ponto final"),
        (f"feat: {'a' * LIMITE_DO_ASSUNTO}", "o limite e"),
        ("feat: assunto\ncorpo colado", "linha em branco"),
    ],
)
def test_mensagem_invalida_e_recusada(mensagem: str, trecho: str) -> None:
    problema = validar_mensagem(mensagem)
    assert problema is not None
    assert trecho in problema


@pytest.mark.parametrize(
    "mensagem",
    [
        "Merge branch 'main' into feature/boleto",
        'Revert "feat: algo"',
        "fixup! feat: algo",
        "squash! feat: algo",
    ],
)
def test_mensagem_gerada_pelo_git_passa_intocada(mensagem: str) -> None:
    """Reprovar merge e rebase transformaria o portão em obstáculo."""
    assert validar_mensagem(mensagem) is None


def test_comentarios_do_git_sao_ignorados() -> None:
    """O `COMMIT_EDITMSG` vem cheio de linhas de instrução do próprio git."""
    bruto = (
        "feat(formatos): boleto e chave de acesso da NF-e\n"
        "\n"
        "# Please enter the commit message for your changes.\n"
        "# On branch main\n"
    )
    assert validar_mensagem(bruto) is None


def test_o_assunto_no_limite_exato_passa() -> None:
    """Fronteira: 72 passa, 73 não. Sem isso, um erro por um fica invisível."""
    assunto = "feat: " + "a" * (LIMITE_DO_ASSUNTO - len("feat: "))
    assert len(assunto) == LIMITE_DO_ASSUNTO
    assert validar_mensagem(assunto) is None
    assert validar_mensagem(assunto + "a") is not None


# --------------------------------------------------------------------------
# O ponto de entrada
# --------------------------------------------------------------------------


def test_main_aceita_mensagem_valida(tmp_path: Path) -> None:
    arquivo = tmp_path / "COMMIT_EDITMSG"
    arquivo.write_text("feat(formatos): boleto", encoding="utf-8")
    assert main([str(arquivo)]) == 0


def test_main_recusa_mensagem_invalida(tmp_path: Path) -> None:
    arquivo = tmp_path / "COMMIT_EDITMSG"
    arquivo.write_text("arrumei umas coisas", encoding="utf-8")
    assert main([str(arquivo)]) == 1


def test_main_recusa_uso_errado(tmp_path: Path) -> None:
    assert main([]) == 2
    assert main([str(tmp_path / "nao-existe")]) == 2


# --------------------------------------------------------------------------
# A divida corrigida nesta entrega
# --------------------------------------------------------------------------


def _hooks() -> list[dict[str, Any]]:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    return [hook for repo in config["repos"] for hook in repo["hooks"]]


def test_todo_hook_declara_o_estagio() -> None:
    """Sem `stages`, o pre-commit roda a lista inteira nos DOIS gatilhos.

    O sintoma é discreto: a segunda leva sai como `Skipped (no files to check)`,
    depois de o pre-commit já ter montado o ambiente de cada hook. Nada falha,
    nada avisa, e o custo cresce junto com a lista.
    """
    for hook in _hooks():
        assert "stages" in hook, f"hook sem stages declarado: {hook['id']}"


def test_existe_um_hook_de_commit_msg() -> None:
    """O gatilho pedido em `default_install_hook_types` tem de ser usado.

    Pedir um gatilho e não pôr nada nele é a forma mais silenciosa de um portão
    de qualidade não existir: a configuração parece completa.
    """
    de_commit_msg = [h for h in _hooks() if h.get("stages") == ["commit-msg"]]
    assert len(de_commit_msg) == 1
    assert "checar_mensagem_de_commit" in str(de_commit_msg[0]["entry"])


def test_todo_gatilho_instalado_tem_pelo_menos_um_hook() -> None:
    """A regra geral, da qual os dois testes acima são casos particulares."""
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    declarados = set(config["default_install_hook_types"])
    usados = {estagio for hook in _hooks() for estagio in hook["stages"]}
    assert declarados == usados, f"gatilhos sem hook: {declarados - usados}"

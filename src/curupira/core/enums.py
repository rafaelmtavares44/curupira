"""Enumerações do domínio: trilhas, idiomas, paridade, split e desfechos."""

from __future__ import annotations

from enum import StrEnum


class Trilha(StrEnum):
    """As seis trilhas de avaliação."""

    T1_TOOL_CALLING = "t1_tool_calling"
    T2_FORMATOS = "t2_formats"
    T3_DOCUMENTOS = "t3_documents"
    T4_PORTUGUES_REAL = "t4_real_portuguese"
    T5_SEGURANCA = "t5_security"
    T6_MULTI_TURNO = "t6_multiturn"


class Locale(StrEnum):
    """Idioma da tarefa. O par em inglês é sempre derivado do português."""

    PT_BR = "pt-BR"
    EN_US = "en-US"


class Paridade(StrEnum):
    """Grau de equivalência entre as duas versões de um par.

    Só `STRICT` entra no cálculo do Delta PT-BR. Afrouxar isso daria um número
    maior e indefensável.
    """

    STRICT = "strict"
    """Mesma tarefa, mesma dificuldade, só o idioma muda."""

    LOCALIZED = "localized"
    """Adaptada culturalmente (endereço, moeda, documento). Fora do Delta."""

    BR_ONLY = "br_only"
    """Sem par possível (ex.: dígito verificador de CPF). Fora do Delta."""


class Split(StrEnum):
    """Público ou held-out. Held-out vive em repositório privado separado."""

    PUBLIC = "public"
    HELD_OUT = "held_out"


class CamadaDePontuacao(StrEnum):
    """Camada que pontuou a tarefa, da menos para a mais subjetiva.

    O agregador do Delta recusa qualquer resultado cuja camada seja `JUIZ`.
    """

    AST = "ast"
    EXECUCAO = "execucao"
    VALIDADOR = "validador"
    JUIZ = "juiz"


class OrdemDeChamadas(StrEnum):
    """Se a ordem das chamadas de ferramenta importa para o casamento."""

    QUALQUER = "any"
    ESTRITA = "strict"


class PoliticaDeArgumento(StrEnum):
    """O que fazer com um argumento na comparação."""

    OBRIGATORIO = "required"
    """Precisa existir e casar."""

    OPCIONAL = "optional"
    """Se existir precisa casar; se ausente, passa."""

    PROIBIDO = "forbidden"
    """Se existir, falha. Usado contra argumento inventado pelo agente."""


class PoliticaDeArgumentoExtra(StrEnum):
    """O que fazer com argumentos que o agente enviou e não esperávamos."""

    REJEITAR = "reject"
    IGNORAR = "ignore"


class Desfecho(StrEnum):
    """Desfecho de UMA repetição de UMA tarefa."""

    PASSOU = "passou"
    FALHOU = "falhou"
    ABSTEVE = "absteve"
    ERRO_DE_EXECUCAO = "erro_de_execucao"
    """Falha de infraestrutura (timeout, 5xx). Não conta como erro do agente."""

    PENDENTE_DE_JUIZ = "pendente_de_juiz"
    """As camadas objetivas não decidiram; só anotação humana ou juiz decide.

    Existe para que o pontuador **nunca precise chutar**. Contar um resíduo não
    julgado como falha empurraria a nota para baixo; contar como acerto, para
    cima. Reprovar por omissão é especialmente perigoso aqui, porque o resíduo
    tende a ser maior no idioma em que o agente se expressa de forma menos
    previsível — ou seja, viés direto no Delta.

    O agregador **exclui** estas linhas do numerador e do denominador da acurácia
    e reporta a fração separadamente. Se ela passar de ~15% numa trilha, o
    problema é o desenho da tarefa, não o agente.
    """


class ClasseDeFalha(StrEnum):
    """Taxonomia de falha silenciosa. Mutuamente exclusiva e exaustiva.

    A distinção entre `ERRO_SINALIZADO` e `FALHA_SILENCIOSA` depende de um léxico
    de hedge, cuja cobertura **não é equivalente entre português e inglês**. Por
    isso essa distinção alimenta o relatório de diagnóstico e **não** entra no
    Delta PT-BR, que usa apenas passou/não passou.
    """

    ACERTO_CONFIANTE = "acerto_confiante"
    ABSTENCAO_CORRETA = "abstencao_correta"
    ABSTENCAO_INDEVIDA = "abstencao_indevida"
    ERRO_SINALIZADO = "erro_sinalizado"
    FALHA_SILENCIOSA = "falha_silenciosa"
    NAO_APLICAVEL = "nao_aplicavel"


class Corrupcao(StrEnum):
    """Modos de corrupção de um identificador brasileiro.

    A corrupção é sempre **declarada**, nunca descoberta: `corromper(v, modo)`
    devolve um valor que o validador reprova *por aquele motivo*.
    """

    DV_TROCADO = "dv_trocado"
    TRANSPOSICAO = "transposicao"
    """Dois dígitos vizinhos trocados. O módulo 11 detecta; o módulo 10 nem sempre."""

    MASCARA_ERRADA = "mascara_errada"
    TAMANHO_ERRADO = "tamanho_errado"
    CARACTERE_INVALIDO = "caractere_invalido"
    SEQUENCIA_REPETIDA = "sequencia_repetida"
    """Passa na aritmética do módulo 11 e mesmo assim é inválido. Exige blacklist."""

    FAIXA_INVALIDA = "faixa_invalida"
    """Formato correto, valor impossível (DDD 00, mês 13, cUF 99)."""

# -*- coding: utf-8 -*-
"""
Registro plugável de algoritmos de escalonamento (requisito 4.2).

Um algoritmo é só uma função que devolve a prioridade primária de uma
ativação (job). O núcleo da simulação consulta este registro, então um
algoritmo novo não exige alterar o Simulador, o parser nem a interface.
"""

ALGORITMOS_DE_ESCALONAMENTO = {}


def registrar_algoritmo(nome, funcao_prioridade_primaria, descricao=""):
    """
    Registra (ou substitui) um algoritmo de escalonamento.

    `funcao_prioridade_primaria(tarefa, job) -> valor comparável`, onde MENOR
    valor significa MAIOR prioridade (é o que `sort` do Python faz
    naturalmente). `job` é a ativação sendo avaliada.

    Exemplo, Deadline Monotonic (prioridade fixa pelo prazo relativo):
        registrar_algoritmo('DM', lambda tarefa, job: tarefa.prazo,
                            descricao="Deadline Monotonic")
    """
    chave = nome.strip().upper()
    ALGORITMOS_DE_ESCALONAMENTO[chave] = {
        'funcao': funcao_prioridade_primaria,
        'descricao': descricao or chave,
    }


# ---- algoritmos exigidos pelo Projeto A ----
registrar_algoritmo(
    'RM',
    lambda tarefa, job: tarefa.periodo,
    descricao="Rate Monotonic (prioridade fixa: menor período primeiro)",
)
registrar_algoritmo(
    'EDF',
    lambda tarefa, job: job.prazo_abs,
    descricao="Earliest Deadline First (prioridade dinâmica: menor prazo absoluto primeiro)",
)

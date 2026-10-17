# -*- coding: utf-8 -*-


class Job:
    """
    Uma ativação periódica de uma tarefa. Cada liberação gera um Job
    independente, de modo que uma nova ativação nunca sobrescreve outra que
    ainda não terminou (duração maior que o período, atrasos etc.).

    Estados: 'pronta', 'executando', 'suspensa', 'concluido'.
    """

    def __init__(self, id_job, tarefa_id, numero, liberacao, prazo_abs, duracao, eventos):
        self.id = id_job
        self.tarefa = tarefa_id          # id da Tarefa dona desta ativação
        self.numero = numero             # 1ª, 2ª, ... ativação da tarefa
        self.liberacao = liberacao       # tick em que foi liberada
        self.prazo_abs = prazo_abs       # liberação + prazo relativo
        self.restante = duracao          # ticks de CPU que faltam
        self.estado = 'pronta'
        self.cpu = None                  # índice da CPU, se executando
        self.execucao_continua_desde = None
        self.eventos_pendentes = list(eventos)
        self.bloqueio_fim = None
        self.deadline_perdido = False
        self.motivo_suspensao = None
        self.tempo_cpu = 0               # ticks de CPU já consumidos
        # métricas do capítulo 6 do livro (Tt, Tw, tr e trocas de contexto)
        self.ingresso = liberacao
        self.conclusao = None
        self.tempo_espera = 0
        self.trocas = 0
        self.primeira_execucao = None

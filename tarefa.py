# -*- coding: utf-8 -*-


class Tarefa:
    """
    Definição ESTÁTICA de uma tarefa: o que veio do arquivo de configuração e
    não muda durante a simulação. O que muda (estado, tempo restante, CPU)
    fica no TCB dinâmico e nos Jobs do Simulador. Essa separação facilita
    reiniciar o sistema e guardar o histórico para voltar no tempo.
    """

    def __init__(self, id_tarefa, cor, ingresso, duracao, periodo, prazo, eventos):
        self.id = id_tarefa
        self.cor = cor                  # string "#RRGGBB"
        self.ingresso = ingresso        # tick de chegada da PRIMEIRA ativação
        self.duracao = duracao          # tempo de CPU por ativação
        self.periodo = periodo          # período entre liberações (> 0: aperiódicas
                                        # já são descartadas no carregamento)
        self.prazo = prazo              # prazo RELATIVO à liberação da ativação
        self.eventos = eventos          # lista de (deslocamento, duracao_bloqueio)

# -*- coding: utf-8 -*-
"""
Constantes do simulador, separadas da lógica para que ajustes visuais ou de
limites não exijam mexer no núcleo.
"""

# ==============================================================================
# REGRAS DA SIMULAÇÃO
# ==============================================================================
ATIVACOES_POR_TAREFA = 10  # req. 4.4: tarefa periódica termina após 10 execuções
MAX_CPUS = 64              # limite defensivo (o enunciado não define o N máximo)

# ==============================================================================
# APRESENTAÇÃO DO GANTT (meramente gráficas, não afetam o escalonador)
# ==============================================================================
LARGURA_TICK = 26          # largura em pixels de um tick no eixo do tempo
ALTURA_LINHA = 32          # altura em pixels de cada linha (tarefa ou CPU)
MARGEM_ESQUERDA = 140      # espaço reservado à esquerda para os rótulos
MARGEM_TOPO = 40           # espaço reservado no topo
ESPACO_REGUA = 24          # altura reservada à régua de ticks, abaixo das linhas de tarefa
COR_GRADE = "#DDDDDD"          # linhas de grade
COR_CPU_DESLIGADA = "#B0B0B0"  # CPU desligada
COR_TEXTO = "#222222"          # texto padrão
COR_CHEGADA = "#2E7D32"        # marcador de chegada de ativação
COR_DEADLINE_MISS = "#D32F2F"  # marcador de prazo estourado
COR_SORTEIO = "#F9A825"        # marcador de desempate por sorteio

# ==============================================================================
# ESTILO DA INTERFACE (ttk): só a "casca" da janela
# ==============================================================================
COR_FUNDO_APP = "#F2F4F8"
COR_BARRA_FERRAMENTAS = "#FFFFFF"
COR_ACCENT = "#2F6FED"
COR_ACCENT_HOVER = "#255BC4"
COR_ACCENT_PRESS = "#1E49A0"
COR_TEXTO_CLARO = "#FFFFFF"
COR_SECUNDARIO = "#E9ECF3"
COR_SECUNDARIO_HOVER = "#DCE1EC"
COR_SECUNDARIO_PRESS = "#CDD4E4"
COR_TEXTO_SECUNDARIO = "#1F2A44"
COR_STATUS_BG = "#1F2A44"
COR_STATUS_TEXTO = "#E8ECF5"
COR_BORDA = "#D8DEE9"
FONTE_PADRAO = ("Segoe UI", 10)
FONTE_TITULO = ("Segoe UI", 12, "bold")
FONTE_STATUS = ("Segoe UI", 9)

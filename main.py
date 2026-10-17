#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 SIMULADOR DE UM SISTEMA OPERACIONAL MULTITAREFA DE TEMPO COMPARTILHADO
 Projeto A - Versão 0.6
 Feito por Marco Gasparotto e Rafael Monçores
================================================================================
Ponto de entrada. O código está dividido em módulos:

    constantes.py       limites e constantes visuais
    escalonadores.py    registro plugável de algoritmos (RM, EDF)
    tarefa.py           classe Tarefa (definição estática)
    job.py              classe Job (uma ativação periódica)
    configuracao.py     CarregadorConfiguracao (leitura e validação do arquivo)
    simulador.py        classe Simulador (núcleo: relógio, CPUs, histórico)
    exportador_svg.py   classe ExportadorSVG
    interface.py        classe Aplicacao (Tkinter)
"""

from interface import Aplicacao


def main():
    app = Aplicacao()
    app.mainloop()


if __name__ == "__main__":
    main()

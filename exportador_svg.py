# -*- coding: utf-8 -*-
"""Exportação nativa do Gantt em SVG (requisito 2.4): só concatenação de strings."""

from constantes import (COR_CHEGADA, COR_CPU_DESLIGADA, COR_DEADLINE_MISS,
                        COR_FIM_QUANTUM, COR_PREEMPCAO, COR_SORTEIO, COR_TEXTO)


class ExportadorSVG:
    """
    Gera um .svg com o Gantt COMPLETO da simulação (primeiro ao último tick,
    sem corte de tela). Não usa nenhuma biblioteca de desenho, e a largura
    depende só da duração total, não da janela.
    """

    def __init__(self, simulador):
        self.simulador = simulador

    def exportar(self, caminho):
        simulador = self.simulador
        if not simulador.historico:
            raise ValueError("Não há histórico de simulação para exportar.")

        tick_inicial = simulador.historico[0]['tick']
        tick_final = simulador.historico[-1]['tick']
        duracao_total = max(1, tick_final - tick_inicial)

        ids_tarefas = sorted(simulador.tarefas_por_id.keys(), reverse=True)  # ID menor embaixo
        n_tarefas = len(ids_tarefas)
        n_cpus = simulador.num_cpus

        largura_tick, altura_linha = 22, 28
        margem_esq, margem_topo, espaco_entre_secoes = 150, 50, 26
        n_linhas_legenda = n_tarefas + 8
        altura_legenda = 40 + n_linhas_legenda * 20

        largura_grafico = duracao_total * largura_tick
        altura_tarefas = n_tarefas * altura_linha
        altura_cpus = n_cpus * altura_linha
        largura_total = margem_esq + largura_grafico + 40
        y_cpus_topo = margem_topo + altura_tarefas + espaco_entre_secoes
        altura_total = y_cpus_topo + altura_cpus + altura_legenda

        def x_do_tick(tk_):
            return margem_esq + (tk_ - tick_inicial) * largura_tick

        partes = []
        partes.append(
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{largura_total}" '
            f'height="{altura_total}" viewBox="0 0 {largura_total} {altura_total}" '
            f'font-family="Helvetica, Arial, sans-serif">'
        )
        partes.append(f'<rect x="0" y="0" width="{largura_total}" height="{altura_total}" fill="#FFFFFF"/>')

        # padrão hachurado para tarefas suspensas
        partes.append(
            '<defs><pattern id="hachura" width="6" height="6" patternTransform="rotate(45)" '
            'patternUnits="userSpaceOnUse"><rect width="6" height="6" fill="#000000"/>'
            '<line x1="0" y1="0" x2="0" y2="6" stroke="#777777" stroke-width="2"/></pattern></defs>'
        )
        partes.append(
            f'<text x="10" y="22" font-size="16" font-weight="bold" fill="{COR_TEXTO}">'
            f'Grafico de Gantt - Algoritmo {simulador.algoritmo}, quantum={simulador.quantum}, '
            f'{n_cpus} CPU(s)</text>'
        )

        # régua de ticks (uma marca a cada 5), logo abaixo das linhas de tarefa
        y_fim_grade = y_cpus_topo + altura_cpus
        for tk_ in range(tick_inicial, tick_final + 1, 5):
            x = x_do_tick(tk_)
            partes.append(f'<line x1="{x}" y1="{margem_topo}" x2="{x}" y2="{y_fim_grade}" stroke="#DDDDDD"/>')
            partes.append(f'<text x="{x}" y="{margem_topo + altura_tarefas + 16}" font-size="10" fill="#666666" text-anchor="middle">{tk_}</text>')

        # linhas de tarefas (ID decrescente: menor ID mais perto da régua)
        y_por_tarefa = {}
        for i, tid in enumerate(ids_tarefas):
            y = margem_topo + i * altura_linha
            y_por_tarefa[tid] = y
            partes.append(f'<text x="{margem_esq - 10}" y="{y + altura_linha/2 + 4}" font-size="12" text-anchor="end" fill="{COR_TEXTO}">Tarefa {tid}</text>')
            partes.append(f'<line x1="{margem_esq}" y1="{y + altura_linha}" x2="{margem_esq + largura_grafico}" y2="{y + altura_linha}" stroke="#EEEEEE"/>')

        # linhas de CPU (fundo cinza = desligada; cobre onde estiver ligada)
        y_por_cpu = {}
        for c in range(n_cpus):
            y = y_cpus_topo + c * altura_linha
            y_por_cpu[c] = y
            partes.append(f'<text x="{margem_esq - 10}" y="{y + altura_linha/2 + 4}" font-size="12" text-anchor="end" fill="{COR_TEXTO}">CPU {c}</text>')
            partes.append(f'<rect x="{margem_esq}" y="{y+2}" width="{largura_grafico}" height="{altura_linha-4}" fill="{COR_CPU_DESLIGADA}"/>')

        cor_por_tarefa = {t.id: t.cor for t in simulador.definicoes}
        blocos, eventos = simulador.obter_todos_os_blocos()

        # blocos nas linhas de TAREFA (execução colorida / suspensão hachurada)
        for (tid, idx_cpu, ini, fim, estado) in blocos:
            if tid is None or tid not in y_por_tarefa:
                continue
            y = y_por_tarefa[tid]
            x1, x2 = x_do_tick(ini), x_do_tick(fim)
            w = max(1, x2 - x1)
            if estado == 'executando':
                partes.append(f'<rect x="{x1}" y="{y+2}" width="{w}" height="{altura_linha-4}" fill="{cor_por_tarefa[tid]}" stroke="#333333" stroke-width="0.5"/>')
                if idx_cpu is not None and w > 20:
                    partes.append(f'<text x="{x1 + w/2}" y="{y + altura_linha/2 + 3}" font-size="8" text-anchor="middle" fill="#FFFFFF">CPU{idx_cpu}</text>')
            elif estado == 'suspensa':
                partes.append(f'<rect x="{x1}" y="{y+2}" width="{w}" height="{altura_linha-4}" fill="url(#hachura)" stroke="#333333" stroke-width="0.5"/>')

        # blocos nas linhas de CPU
        for (tid, idx_cpu, ini, fim, estado) in blocos:
            if idx_cpu is None or estado != 'executando':
                continue
            y = y_por_cpu[idx_cpu]
            x1, x2 = x_do_tick(ini), x_do_tick(fim)
            w = max(1, x2 - x1)
            partes.append(f'<rect x="{x1}" y="{y+2}" width="{w}" height="{altura_linha-4}" fill="{cor_por_tarefa[tid]}" stroke="#333333" stroke-width="0.5"/>')
            if w > 20:
                partes.append(f'<text x="{x1 + w/2}" y="{y + altura_linha/2 + 3}" font-size="8" text-anchor="middle" fill="#FFFFFF">T{tid}</text>')

        # marcadores de eventos pontuais
        for ev in eventos:
            tid = ev.get('tarefa')
            if tid not in y_por_tarefa:
                continue
            y = y_por_tarefa[tid]
            x = x_do_tick(ev['tick'])
            tipo = ev['tipo']
            if tipo == 'chegada':
                partes.append(f'<polygon points="{x-5},{y+altura_linha-2} {x+5},{y+altura_linha-2} {x},{y+altura_linha-11}" fill="{COR_CHEGADA}"/>')
            elif tipo in ('conclusao_instancia', 'conclusao_tarefa'):
                partes.append(f'<line x1="{x}" y1="{y+2}" x2="{x}" y2="{y+altura_linha-2}" stroke="#000000" stroke-width="2"/>')
                partes.append(f'<circle cx="{x}" cy="{y+6}" r="3" fill="#000000"/>')
            elif tipo == 'deadline_miss':
                partes.append(f'<circle cx="{x}" cy="{y+altura_linha/2}" r="8" fill="none" stroke="{COR_DEADLINE_MISS}" stroke-width="1.5"/>')
                partes.append(f'<text x="{x}" y="{y+altura_linha/2+4}" font-size="12" fill="{COR_DEADLINE_MISS}" font-weight="bold" text-anchor="middle">!</text>')
            elif tipo == 'sorteio':
                partes.append(f'<text x="{x}" y="{y+altura_linha-5}" font-size="11" fill="{COR_SORTEIO}" font-weight="bold" text-anchor="middle">S</text>')
            elif tipo == 'preempcao':
                # triângulo para baixo no topo da linha: a tarefa perdeu a CPU
                partes.append(f'<polygon points="{x-5},{y+2} {x+5},{y+2} {x},{y+10}" fill="{COR_PREEMPCAO}"/>')
            elif tipo == 'fim_quantum':
                partes.append(f'<text x="{x}" y="{y+11}" font-size="10" fill="{COR_FIM_QUANTUM}" font-weight="bold" text-anchor="middle">Q</text>')

        # ------------------------------ legenda ------------------------------
        y_legenda = y_cpus_topo + altura_cpus + 30
        partes.append(f'<text x="10" y="{y_legenda}" font-size="14" font-weight="bold" fill="{COR_TEXTO}">Legenda</text>')
        x_leg = 10
        y_leg = y_legenda + 22

        def linha_legenda(cor_ou_none, hachurado, texto):
            nonlocal y_leg
            if hachurado:
                partes.append(f'<rect x="{x_leg}" y="{y_leg-12}" width="16" height="16" fill="url(#hachura)" stroke="#999999"/>')
            elif cor_ou_none is not None:
                partes.append(f'<rect x="{x_leg}" y="{y_leg-12}" width="16" height="16" fill="{cor_ou_none}" stroke="#999999"/>')
            partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">{texto}</text>')
            y_leg += 20

        for t in simulador.definicoes:
            linha_legenda(t.cor, False, f"Tarefa {t.id} executando")
        linha_legenda("#FFFFFF", False, "Pronta na fila (sem cor / bloco vazio)")
        linha_legenda(None, True, "Suspensa / bloqueada")
        linha_legenda(COR_CPU_DESLIGADA, False, "CPU desligada")

        partes.append(f'<polygon points="{x_leg+3},{y_leg+2} {x_leg+13},{y_leg+2} {x_leg+8},{y_leg-7}" fill="{COR_CHEGADA}"/>')
        partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">Chegada de nova instância</text>')
        y_leg += 20
        partes.append(f'<circle cx="{x_leg+8}" cy="{y_leg-4}" r="3" fill="#000000"/>')
        partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">Conclusão de instância/tarefa</text>')
        y_leg += 20
        partes.append(f'<circle cx="{x_leg+8}" cy="{y_leg-6}" r="8" fill="none" stroke="{COR_DEADLINE_MISS}" stroke-width="1.5"/>')
        partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">Estouro de prazo (deadline miss)</text>')
        y_leg += 20
        partes.append(f'<text x="{x_leg+8}" y="{y_leg-2}" font-size="12" fill="{COR_SORTEIO}" font-weight="bold" text-anchor="middle">S</text>')
        partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">Escolhida por sorteio (desempate)</text>')
        y_leg += 20
        partes.append(f'<polygon points="{x_leg+3},{y_leg-10} {x_leg+13},{y_leg-10} {x_leg+8},{y_leg-2}" fill="{COR_PREEMPCAO}"/>')
        partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">Preempção (tarefa mais prioritária assumiu a CPU)</text>')
        y_leg += 20
        partes.append(f'<text x="{x_leg+8}" y="{y_leg-2}" font-size="12" fill="{COR_FIM_QUANTUM}" font-weight="bold" text-anchor="middle">Q</text>')
        partes.append(f'<text x="{x_leg+22}" y="{y_leg}" font-size="11" fill="{COR_TEXTO}">Fim de quantum (volta ao fim da fila)</text>')

        partes.append('</svg>')

        with open(caminho, 'w', encoding='utf-8') as arquivo:
            arquivo.write(''.join(partes))
        return caminho

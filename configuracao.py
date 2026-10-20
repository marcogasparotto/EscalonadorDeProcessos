# -*- coding: utf-8 -*-
"""Leitura e validação do arquivo de configuração (requisito 3.3)."""

import os

from constantes import MAX_CPUS, PALETA_CORES_PADRAO
from escalonadores import ALGORITMOS_DE_ESCALONAMENTO
from tarefa import Tarefa


class Configuracao:
    """Resultado de uma leitura: parâmetros gerais, tarefas e avisos."""

    def __init__(self, algoritmo, quantum, num_cpus, tarefas, avisos):
        self.algoritmo = algoritmo
        self.quantum = quantum
        self.num_cpus = num_cpus
        self.tarefas = tarefas
        self.avisos = avisos


class CarregadorConfiguracao:
    """
    Lê o arquivo texto no formato do enunciado:
        linha 1:     algoritmo_escalonamento;quantum;qtde_cpus
        linhas 2..N: id;cor;ingresso;duracao;periodo;prazo;lista_eventos

    Tolerado (nunca é erro): maiúsculas/minúsculas, espaços, linhas em
    branco, ';' no fim da linha, BOM no início do arquivo e qualquer caminho.
    Erros estruturais levantam ValueError com o motivo. Aperiódicas
    (período 0) viram aviso e são ignoradas (req. 4.4). Cor repetida também
    vira aviso: o arquivo segue o formato (req. 3.3.7), então troca-se a cor
    da tarefa repetida por uma livre em vez de recusar o arquivo.
    """

    @staticmethod
    def normalizar_cor(valor):
        """Devolve '#RRGGBB' em maiúsculas, ou None se a cor for inválida."""
        v = valor.strip()
        if not v:
            return None
        if not v.startswith('#'):
            v = '#' + v
        if len(v) != 7:
            return None
        try:
            int(v[1:], 16)
        except ValueError:
            return None
        return v.upper()

    @staticmethod
    def parsear_eventos(campo, contexto="lista de eventos"):
        """
        Lê "deslocamento:duracao,..." (formato provisório; a lista de eventos
        é definida no Projeto B). Levanta ValueError dizendo o que está errado.
        """
        campo = campo.strip()
        if campo in ('', '-'):
            return []
        eventos, deslocamentos = [], set()
        for parte in campo.split(','):
            parte = parte.strip()
            if not parte or ':' not in parte:
                raise ValueError(f"{contexto}: evento inválido '{parte}'. Use deslocamento:duração.")
            desloc_str, dur_str = parte.split(':', 1)
            try:
                desloc, dur = int(desloc_str.strip()), int(dur_str.strip())
            except ValueError as erro:
                raise ValueError(f"{contexto}: evento inválido '{parte}'; use inteiros.") from erro
            if desloc < 0 or dur <= 0:
                raise ValueError(f"{contexto}: deslocamento >= 0 e duração > 0 são obrigatórios.")
            if desloc in deslocamentos:
                raise ValueError(f"{contexto}: dois eventos no deslocamento {desloc} não são permitidos.")
            deslocamentos.add(desloc)
            eventos.append((desloc, dur))
        return sorted(eventos, key=lambda par: par[0])

    def carregar(self, caminho):
        """Lê o arquivo e devolve uma Configuracao (ou levanta ValueError)."""
        caminho = os.path.abspath(os.path.expanduser(caminho.strip()))
        if not os.path.isfile(caminho):
            raise ValueError(f"Arquivo não encontrado: {caminho}")

        # utf-8-sig descarta um BOM, comum em arquivos salvos no Windows
        with open(caminho, 'r', encoding='utf-8-sig') as arquivo:
            linhas_brutas = arquivo.readlines()

        linhas = [linha.strip() for linha in linhas_brutas]
        linhas = [linha for linha in linhas if linha != '']
        if not linhas:
            raise ValueError("O arquivo de configuração está vazio.")

        avisos = []
        algoritmo, quantum, num_cpus = self._ler_cabecalho(linhas[0])
        tarefas = self._ler_tarefas(linhas[1:], avisos)
        if not tarefas:
            raise ValueError("Nenhuma tarefa periódica válida foi encontrada no arquivo.")
        return Configuracao(algoritmo, quantum, num_cpus, tarefas, avisos)

    # ------------------------------------------------------------------
    def _ler_cabecalho(self, linha):
        if linha.endswith(';'):
            linha = linha[:-1]
        campos = [c.strip() for c in linha.split(';')]
        if len(campos) != 3:
            raise ValueError(
                "Primeira linha inválida. O formato esperado é: "
                "algoritmo_escalonamento;quantum;qtde_cpus"
            )
        algoritmo_bruto, quantum_bruto, cpus_bruto = campos

        algoritmo = algoritmo_bruto.upper()
        if algoritmo not in ALGORITMOS_DE_ESCALONAMENTO:
            disponiveis = ', '.join(sorted(ALGORITMOS_DE_ESCALONAMENTO))
            raise ValueError(
                f"Algoritmo de escalonamento desconhecido: '{algoritmo_bruto}'. "
                f"Algoritmos disponíveis: {disponiveis}."
            )
        try:
            quantum = int(quantum_bruto)
            if quantum <= 0:
                raise ValueError
        except ValueError:
            raise ValueError(f"Quantum inválido na primeira linha: '{quantum_bruto}'.")
        try:
            num_cpus = int(cpus_bruto)
            if num_cpus <= 0 or num_cpus > MAX_CPUS:
                raise ValueError
        except ValueError:
            raise ValueError(f"Quantidade de CPUs inválida: '{cpus_bruto}'. Use 1 a {MAX_CPUS}.")
        return algoritmo, quantum, num_cpus

    def _ler_tarefas(self, linhas, avisos):
        tarefas = []
        ids_vistos = set()

        for numero_linha, linha in enumerate(linhas, start=2):
            if linha.endswith(';'):
                linha = linha[:-1]
            campos = [c.strip() for c in linha.split(';')]

            # Os seis primeiros campos são obrigatórios; lista_eventos pode faltar.
            if len(campos) == 6:
                campos.append('')
            elif len(campos) != 7:
                raise ValueError(f"Linha {numero_linha}: esperados 7 campos; recebidos {len(campos)}.")

            (id_str, cor_str, ingresso_str, duracao_str,
             periodo_str, prazo_str, eventos_str) = campos

            try:
                id_tarefa = int(id_str)
            except ValueError:
                raise ValueError(f"Linha {numero_linha}: ID inválido ('{id_str}').")
            if id_tarefa in ids_vistos:
                raise ValueError(f"Linha {numero_linha}: ID {id_tarefa} duplicado.")

            cor = self.normalizar_cor(cor_str)
            if cor is None:
                raise ValueError(f"Linha {numero_linha}: cor inválida ('{cor_str}').")

            try:
                ingresso = int(ingresso_str)
                if ingresso < 0:
                    raise ValueError
            except ValueError:
                raise ValueError(f"Linha {numero_linha}: ingresso inválido ('{ingresso_str}').")

            try:
                duracao = int(duracao_str)
                if duracao <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError(f"Linha {numero_linha}: duração inválida ('{duracao_str}').")

            periodo_limpo = periodo_str.strip()
            if periodo_limpo in ('', '0', '-'):
                avisos.append(
                    f"Tarefa {id_tarefa} é aperiódica (sem período definido). O simulador "
                    "não oferece suporte a tarefas aperiódicas; ela foi ignorada."
                )
                continue
            try:
                periodo = int(periodo_limpo)
                if periodo <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError(f"Linha {numero_linha}: período inválido ('{periodo_str}').")

            try:
                prazo = int(prazo_str)
                if prazo <= 0:
                    raise ValueError
            except ValueError:
                raise ValueError(f"Linha {numero_linha}: prazo inválido ('{prazo_str}').")

            try:
                eventos = self.parsear_eventos(eventos_str, f"Linha {numero_linha}, tarefa {id_tarefa}")
            except ValueError as erro_eventos:
                # Projeto A: lista_eventos só é tratada no Projeto B (req. 3.3.5).
                # Conteúdo fora do formato provisório é ignorado com aviso, para
                # nunca recusar um arquivo que respeita o formato do enunciado.
                avisos.append(f"{erro_eventos} Eventos desta tarefa foram ignorados no Projeto A.")
                eventos = []

            tarefas.append(Tarefa(id_tarefa, cor, ingresso, duracao, periodo, prazo, eventos))
            ids_vistos.add(id_tarefa)

        self._resolver_cores_repetidas(tarefas, avisos)
        return tarefas

    @staticmethod
    def _cor_livre(usadas):
        """Primeira cor da paleta padrão fora de `usadas`; esgotada a paleta,
        gera cores determinísticas (sempre as mesmas para o mesmo arquivo)."""
        for cor in PALETA_CORES_PADRAO:
            if cor not in usadas:
                return cor
        passo = 0
        while True:
            passo += 1
            cor = f"#{(passo * 0x9E3779) & 0xFFFFFF:06X}"
            if cor not in usadas:
                return cor

    def _resolver_cores_repetidas(self, tarefas, avisos):
        """Cada tarefa precisa de uma cor diferente no Gantt (req. 2.1). A
        primeira tarefa com a cor fica com ela; as seguintes recebem uma cor
        livre, que também não colide com nenhuma cor escrita no arquivo."""
        usadas = {t.cor for t in tarefas}
        vistas = set()
        for t in tarefas:
            if t.cor in vistas:
                nova = self._cor_livre(usadas)
                avisos.append(
                    f"Tarefa {t.id}: a cor {t.cor} já pertence a outra tarefa. "
                    f"Para o Gantt ficar legível ela recebeu a cor {nova}.")
                t.cor = nova
                usadas.add(nova)
            vistas.add(t.cor)

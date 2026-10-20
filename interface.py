# -*- coding: utf-8 -*-
"""Interface gráfica (Tkinter): janela principal, diálogos e desenho do Gantt."""

import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from configuracao import CarregadorConfiguracao
from constantes import (
    ALTURA_LINHA, ATIVACOES_POR_TAREFA, COR_ACCENT, COR_ACCENT_HOVER, COR_ACCENT_PRESS,
    COR_BARRA_FERRAMENTAS, COR_BORDA, COR_CHEGADA, COR_CPU_DESLIGADA, COR_DEADLINE_MISS,
    COR_FIM_QUANTUM, COR_FUNDO_APP, COR_GRADE, COR_PREEMPCAO, COR_SECUNDARIO, COR_SECUNDARIO_HOVER, COR_SECUNDARIO_PRESS,
    COR_SORTEIO, COR_STATUS_BG, COR_STATUS_TEXTO, COR_TEXTO_CLARO, COR_TEXTO_SECUNDARIO,
    ESPACO_REGUA, FONTE_PADRAO, FONTE_STATUS, FONTE_TITULO, LARGURA_TICK, MARGEM_ESQUERDA,
    MARGEM_TOPO, PALETA_CORES_PADRAO,
)
from escalonadores import ALGORITMOS_DE_ESCALONAMENTO
from exportador_svg import ExportadorSVG
from simulador import Simulador
from tarefa import Tarefa


class Aplicacao(tk.Tk):
    """
    Janela principal. Concentra a barra de ferramentas, o Canvas do Gantt
    (com barras de rolagem, pois a linha do tempo pode ficar longa), a
    legenda e a barra de status. Toda a lógica de escalonamento fica no
    Simulador; aqui só se desenha e se chamam métodos dele.
    """

    def __init__(self):
        super().__init__()
        self.title("Simulador de SO Multitarefa - Projeto A (v0.6)")
        self.geometry("1280x800")
        self.minsize(1000, 650)
        self.configure(bg=COR_FUNDO_APP)

        self._configurar_estilo_ttk()

        self.simulador = None
        self.caminho_arquivo_atual = None
        self.reproducao_automatica = False
        self.svg_exportado_automaticamente = False

        self._montar_barra_de_ferramentas()
        self._montar_area_status()
        self._montar_area_gantt()
        self._montar_area_legenda()

    # --------------------------- estilo visual (ttk) ---------------------------
    def _configurar_estilo_ttk(self):
        """Aparência dos widgets ttk. O tema 'clam' permite cores planas; se não
        existir na plataforma, o tema padrão do sistema é mantido."""
        estilo = ttk.Style(self)
        try:
            estilo.theme_use("clam")
        except tk.TclError:
            pass

        estilo.configure("Toolbar.TFrame", background=COR_BARRA_FERRAMENTAS)
        estilo.configure("Accent.TButton", font=FONTE_PADRAO, padding=(12, 7),
                         background=COR_ACCENT, foreground=COR_TEXTO_CLARO,
                         borderwidth=0, relief="flat")
        estilo.map("Accent.TButton",
                   background=[("pressed", COR_ACCENT_PRESS), ("active", COR_ACCENT_HOVER)])
        estilo.configure("Secondary.TButton", font=FONTE_PADRAO, padding=(12, 7),
                         background=COR_SECUNDARIO, foreground=COR_TEXTO_SECUNDARIO,
                         borderwidth=0, relief="flat")
        estilo.map("Secondary.TButton",
                   background=[("pressed", COR_SECUNDARIO_PRESS), ("active", COR_SECUNDARIO_HOVER)])
        estilo.configure("Status.TLabel", background=COR_STATUS_BG, foreground=COR_STATUS_TEXTO,
                         font=FONTE_STATUS, padding=(12, 7))
        estilo.configure("TCombobox", padding=4, font=FONTE_PADRAO)
        estilo.configure("TSeparator", background=COR_BORDA)
        estilo.configure("Treeview", font=FONTE_PADRAO, rowheight=24,
                         background="#FFFFFF", fieldbackground="#FFFFFF")
        estilo.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"),
                         background=COR_SECUNDARIO, foreground=COR_TEXTO_SECUNDARIO)
        estilo.map("Treeview.Heading", background=[("active", COR_SECUNDARIO_HOVER)])

    # --------------------------- montagem da UI ---------------------------
    def _montar_barra_de_ferramentas(self):
        barra = ttk.Frame(self, style="Toolbar.TFrame", padding=(10, 10))
        barra.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(barra, text="📂 Carregar arquivo...", style="Accent.TButton",
                   command=self.carregar_arquivo).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(barra, text="⚙ Parâmetros...", style="Secondary.TButton",
                   command=self.editar_parametros).pack(side=tk.LEFT, padx=6)
        ttk.Separator(barra, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)
        ttk.Button(barra, text="⏩ Executar tudo (Modo Completo)", style="Accent.TButton",
                   command=self.executar_modo_completo).pack(side=tk.LEFT, padx=6)
        self.botao_reproduzir = ttk.Button(barra, text="▶ Reproduzir", style="Secondary.TButton",
                                           command=self.alternar_reproducao)
        self.botao_reproduzir.pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="⏮ Retroceder passo", style="Secondary.TButton",
                   command=self.retroceder_passo).pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="Avançar passo ⏭", style="Secondary.TButton",
                   command=self.avancar_passo).pack(side=tk.LEFT, padx=6)
        ttk.Separator(barra, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=12)
        ttk.Button(barra, text="＋ Nova tarefa...", style="Secondary.TButton",
                   command=self.abrir_nova_tarefa).pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="✎ Editar tarefa...", style="Secondary.TButton",
                   command=self.abrir_editor_de_tarefa).pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="Estado...", style="Secondary.TButton",
                   command=self.abrir_editor_de_estado).pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="Métricas...", style="Secondary.TButton",
                   command=self.abrir_relatorio_metricas).pack(side=tk.LEFT, padx=6)
        ttk.Button(barra, text="💾 Exportar SVG...", style="Secondary.TButton",
                   command=self.exportar_para_svg).pack(side=tk.LEFT, padx=6)

    def _montar_area_status(self):
        self.rotulo_status = ttk.Label(self, text="Nenhum arquivo carregado.", anchor="w",
                                       style="Status.TLabel")
        self.rotulo_status.pack(side=tk.TOP, fill=tk.X)

    def _montar_area_gantt(self):
        moldura_externa = tk.Frame(self, bg=COR_FUNDO_APP, padx=10, pady=8)
        moldura_externa.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        divisor = ttk.PanedWindow(moldura_externa, orient=tk.HORIZONTAL)
        divisor.pack(fill=tk.BOTH, expand=True)

        moldura_gantt = tk.Frame(divisor, bg=COR_BORDA, bd=1)
        self.canvas_gantt = tk.Canvas(moldura_gantt, bg="white", highlightthickness=0)
        barra_v = ttk.Scrollbar(moldura_gantt, orient=tk.VERTICAL, command=self.canvas_gantt.yview)
        barra_h = ttk.Scrollbar(moldura_gantt, orient=tk.HORIZONTAL, command=self.canvas_gantt.xview)
        self.canvas_gantt.configure(yscrollcommand=barra_v.set, xscrollcommand=barra_h.set)

        self.canvas_gantt.grid(row=0, column=0, sticky="nsew", padx=1, pady=1)
        barra_v.grid(row=0, column=1, sticky="ns")
        barra_h.grid(row=1, column=0, sticky="ew")
        moldura_gantt.rowconfigure(0, weight=1)
        moldura_gantt.columnconfigure(0, weight=1)

        moldura_painel = tk.Frame(divisor, bg=COR_BORDA, bd=1)
        self._montar_painel_tarefas(moldura_painel)

        divisor.add(moldura_gantt, weight=4)
        divisor.add(moldura_painel, weight=1)

    def _montar_painel_tarefas(self, container):
        """Painel "debugger" (req. 1.5.1): estado dinâmico de cada tarefa no passo
        em que o cursor de exibição está posicionado."""
        cabecalho = tk.Frame(container, bg=COR_BARRA_FERRAMENTAS)
        cabecalho.pack(side=tk.TOP, fill=tk.X)
        tk.Label(cabecalho, text="Estado das tarefas", bg=COR_BARRA_FERRAMENTAS,
                 fg=COR_TEXTO_SECUNDARIO, font=FONTE_TITULO).pack(anchor="w", padx=10, pady=8)

        colunas = ("estado", "cpu", "restante", "prazo_abs", "instancia", "deadline")
        self.tabela_tarefas = ttk.Treeview(container, columns=colunas, show="tree headings", height=10)
        self.tabela_tarefas.heading("#0", text="Tarefa")
        self.tabela_tarefas.column("#0", width=70, anchor="w")
        titulos = {"estado": "Estado", "cpu": "CPU", "restante": "Falta",
                   "prazo_abs": "Prazo abs.", "instancia": "Inst.", "deadline": "Prazo?"}
        larguras = {"estado": 82, "cpu": 42, "restante": 48, "prazo_abs": 68,
                    "instancia": 44, "deadline": 56}
        for col in colunas:
            self.tabela_tarefas.heading(col, text=titulos[col])
            self.tabela_tarefas.column(col, width=larguras[col], anchor="center")
        self.tabela_tarefas.tag_configure("deadline_perdido", foreground=COR_DEADLINE_MISS)
        self.tabela_tarefas.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=6, pady=(0, 6))

    def _montar_area_legenda(self):
        moldura = tk.Frame(self, bg=COR_BORDA)
        moldura.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas_legenda = tk.Canvas(moldura, height=92, bg="#FCFCFD", highlightthickness=0)
        self.canvas_legenda.pack(fill=tk.X, padx=1, pady=(1, 0))

    # --------------------------- ações da barra ---------------------------
    def carregar_arquivo(self):
        caminho = filedialog.askopenfilename(
            title="Selecione o arquivo de configuração",
            filetypes=[("Todos os arquivos", "*.*"), ("Configuração (.txt, .cfg)", "*.txt *.cfg")],
        )
        if caminho:
            self._carregar_arquivo_de_caminho(caminho)

    def _carregar_arquivo_de_caminho(self, caminho):
        try:
            config = CarregadorConfiguracao().carregar(caminho)
        except (ValueError, OSError, UnicodeError) as erro:
            messagebox.showerror("Erro ao carregar arquivo", str(erro))
            return

        self.simulador = Simulador(config.algoritmo, config.quantum, config.num_cpus, config.tarefas)
        self.simulador.reiniciar()
        self.caminho_arquivo_atual = caminho
        self.svg_exportado_automaticamente = False

        self._apos_mudanca_de_estado()
        self.desenhar_legenda()

        if config.avisos:
            messagebox.showwarning("Avisos ao carregar o arquivo", "\n".join(config.avisos))

    def editar_parametros(self):
        """Algoritmo, quantum e CPUs (req. 3.1). O combobox lista o registro
        plugável, então algoritmos novos aparecem aqui sem alterar esta função."""
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue um arquivo de configuração primeiro.")
            return

        janela = tk.Toplevel(self)
        janela.title("Parâmetros da simulação")
        janela.geometry("380x260")
        janela.configure(bg=COR_FUNDO_APP)
        janela.transient(self)

        tk.Label(janela, text="Parâmetros da simulação", bg=COR_FUNDO_APP,
                 fg=COR_TEXTO_SECUNDARIO, font=FONTE_TITULO).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(16, 10))

        tk.Label(janela, text="Algoritmo:", bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
            row=1, column=0, sticky="w", padx=16, pady=6)
        nomes_algoritmos = sorted(ALGORITMOS_DE_ESCALONAMENTO.keys())
        variavel_algoritmo = tk.StringVar(value=self.simulador.algoritmo)
        combo_algoritmo = ttk.Combobox(janela, textvariable=variavel_algoritmo,
                                       values=nomes_algoritmos, state="readonly", width=22)
        combo_algoritmo.grid(row=1, column=1, padx=16, pady=6, sticky="ew")

        rotulo_descricao = tk.Label(janela, text="", bg=COR_FUNDO_APP, fg="#555555",
                                    font=("Segoe UI", 8), wraplength=340, justify="left")
        rotulo_descricao.grid(row=2, column=0, columnspan=2, sticky="w", padx=16, pady=(0, 6))

        def atualizar_descricao(*_args):
            info = ALGORITMOS_DE_ESCALONAMENTO.get(variavel_algoritmo.get())
            rotulo_descricao.config(text=info['descricao'] if info else "")

        combo_algoritmo.bind("<<ComboboxSelected>>", atualizar_descricao)
        atualizar_descricao()

        tk.Label(janela, text="Quantum:", bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
            row=3, column=0, sticky="w", padx=16, pady=6)
        entrada_quantum = tk.Entry(janela, width=10, font=FONTE_PADRAO, relief="solid", bd=1)
        entrada_quantum.insert(0, str(self.simulador.quantum))
        entrada_quantum.grid(row=3, column=1, padx=16, pady=6, sticky="w")

        tk.Label(janela, text="Quantidade de CPUs:", bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
            row=4, column=0, sticky="w", padx=16, pady=6)
        entrada_cpus = tk.Entry(janela, width=10, font=FONTE_PADRAO, relief="solid", bd=1)
        entrada_cpus.insert(0, str(self.simulador.num_cpus))
        entrada_cpus.grid(row=4, column=1, padx=16, pady=6, sticky="w")

        janela.columnconfigure(1, weight=1)

        def aplicar():
            try:
                novo_quantum = int(entrada_quantum.get())
                novo_num_cpus = int(entrada_cpus.get())
                if novo_quantum <= 0 or novo_num_cpus <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror(
                    "Erro", "Quantum e quantidade de CPUs devem ser inteiros positivos.",
                    parent=janela)
                return

            self.simulador.algoritmo = variavel_algoritmo.get()
            self.simulador.quantum = novo_quantum
            self.simulador.num_cpus = novo_num_cpus
            self.svg_exportado_automaticamente = False
            self.simulador.aplicar_edicao_e_reconstruir()
            self._apos_mudanca_de_estado()
            janela.destroy()

        ttk.Button(janela, text="Aplicar", style="Accent.TButton", command=aplicar).grid(
            row=5, column=0, columnspan=2, pady=18)

    def executar_modo_completo(self):
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue um arquivo de configuração primeiro.")
            return
        try:
            self.simulador.executar_completo()
        except RuntimeError as erro:
            messagebox.showerror("Erro na simulação", str(erro))
            return
        self._apos_mudanca_de_estado()
        messagebox.showinfo(
            "Simulação concluída",
            f"Simulação concluída no tick {self.simulador.tick}.\n"
            "O gráfico de Gantt completo foi exportado automaticamente em SVG.",
        )

    def alternar_reproducao(self):
        if self.simulador is None:
            return
        self.reproducao_automatica = not self.reproducao_automatica
        self.botao_reproduzir.config(text="⏸ Pausar" if self.reproducao_automatica else "▶ Reproduzir")
        if self.reproducao_automatica:
            self._tick_de_reproducao()

    def _tick_de_reproducao(self):
        if not self.reproducao_automatica or self.simulador is None:
            return
        avancou = self.simulador.avancar()
        self._apos_mudanca_de_estado()
        if not avancou:
            self.reproducao_automatica = False
            self.botao_reproduzir.config(text="▶ Reproduzir")
            return
        self.after(350, self._tick_de_reproducao)

    def avancar_passo(self):
        if self.simulador is None:
            return
        try:
            self.simulador.avancar()
        except RuntimeError as erro:
            messagebox.showerror("Erro na simulação", str(erro))
            return
        self._apos_mudanca_de_estado()

    def retroceder_passo(self):
        if self.simulador is None:
            return
        self.simulador.retroceder()
        self._apos_mudanca_de_estado()

    # --------------------------- edição de tarefas ---------------------------
    def _proxima_cor_padrao(self):
        """Sugere (req. 3.2) a primeira cor da paleta ainda não usada."""
        usadas = {t.cor for t in self.simulador.definicoes} if self.simulador else set()
        for cor in PALETA_CORES_PADRAO:
            if cor not in usadas:
                return cor
        return PALETA_CORES_PADRAO[len(usadas) % len(PALETA_CORES_PADRAO)]

    def _cor_disponivel(self, cor, id_ignorado, janela):
        """Cada tarefa precisa de uma cor diferente (req. 2.1), senão o Gantt
        fica ambíguo. Mostra o erro e devolve False se outra tarefa já a usa."""
        for t in self.simulador.definicoes:
            if t.cor == cor and t.id != id_ignorado:
                messagebox.showerror(
                    "Cor já usada",
                    f"A cor {cor} já pertence à Tarefa {t.id}. Cada tarefa precisa de "
                    f"uma cor diferente no gráfico de Gantt. Sugestão: {self._proxima_cor_padrao()}.",
                    parent=janela)
                return False
        return True

    @staticmethod
    def _ler_campos_numericos(campos, janela):
        """Lê ingresso, duração, período e prazo; mostra o erro e devolve None se inválido."""
        try:
            ingresso = int(campos["ingresso"].get())
            duracao = int(campos["duracao"].get())
            periodo = int(campos["periodo"].get())
            prazo = int(campos["prazo"].get())
            if ingresso < 0 or duracao <= 0 or periodo <= 0 or prazo <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Erro",
                "Ingresso deve ser inteiro (>= 0); duração, período e prazo devem ser inteiros positivos.",
                parent=janela)
            return None
        return ingresso, duracao, periodo, prazo

    @staticmethod
    def _ler_eventos(campos, janela):
        """Lê o campo de eventos; mostra o erro e devolve None se inválido."""
        try:
            return CarregadorConfiguracao.parsear_eventos(campos["eventos"].get())
        except ValueError as erro:
            messagebox.showerror("Erro nos eventos", str(erro), parent=janela)
            return None

    def abrir_nova_tarefa(self):
        """Adiciona uma tarefa ao conjunto simulado (req. 3.1), com valores padrão
        sugeridos (req. 3.2) que o usuário pode sobrescrever."""
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue um arquivo de configuração primeiro.")
            return

        janela = tk.Toplevel(self)
        janela.title("Nova tarefa")
        janela.geometry("400x460")
        janela.configure(bg=COR_FUNDO_APP)
        janela.transient(self)

        cabecalho = tk.Frame(janela, bg=COR_FUNDO_APP)
        cabecalho.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 4))
        tk.Label(cabecalho, text="Nova tarefa", bg=COR_FUNDO_APP, fg=COR_TEXTO_SECUNDARIO,
                 font=FONTE_TITULO).pack(anchor="w")

        ids_existentes = self.simulador.tarefas_por_id.keys()
        proximo_id = (max(ids_existentes) + 1) if ids_existentes else 1

        campos = {}
        rotulos_com_padrao = [
            ("id", "ID (único):", str(proximo_id)),
            ("cor", "Cor (#RRGGBB):", self._proxima_cor_padrao()),
            ("ingresso", "Ingresso:", "0"),
            ("duracao", "Duração:", "1"),
            ("periodo", "Período:", "5"),
            ("prazo", "Prazo:", "5"),
            ("eventos", "Eventos (desloc:dur,...):", ""),
        ]
        for i, (chave, texto, valor_padrao) in enumerate(rotulos_com_padrao, start=1):
            tk.Label(janela, text=texto, bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
                row=i, column=0, sticky="w", padx=16, pady=6)
            entrada = tk.Entry(janela, width=26, font=FONTE_PADRAO, relief="solid", bd=1)
            entrada.insert(0, valor_padrao)
            entrada.grid(row=i, column=1, padx=16, pady=6, sticky="ew")
            campos[chave] = entrada
        janela.columnconfigure(1, weight=1)

        def aplicar():
            try:
                novo_id = int(campos["id"].get())
            except ValueError:
                messagebox.showerror("Erro", "ID deve ser um número inteiro.", parent=janela)
                return
            if novo_id in self.simulador.tarefas_por_id:
                messagebox.showerror(
                    "Erro", f"Já existe uma tarefa com ID {novo_id}. Escolha outro ID.", parent=janela)
                return
            cor = CarregadorConfiguracao.normalizar_cor(campos["cor"].get())
            if cor is None:
                messagebox.showerror("Erro", "Cor inválida. Use o formato #RRGGBB.", parent=janela)
                return
            if not self._cor_disponivel(cor, None, janela):
                return
            numeros = self._ler_campos_numericos(campos, janela)
            if numeros is None:
                return
            eventos = self._ler_eventos(campos, janela)
            if eventos is None:
                return
            ingresso, duracao, periodo, prazo = numeros

            nova_tarefa = Tarefa(novo_id, cor, ingresso, duracao, periodo, prazo, eventos)
            self.simulador.definicoes.append(nova_tarefa)
            self.simulador.tarefas_por_id = {t.id: t for t in self.simulador.definicoes}

            self.svg_exportado_automaticamente = False
            self.simulador.aplicar_edicao_e_reconstruir()
            self._apos_mudanca_de_estado()
            self.desenhar_legenda()
            janela.destroy()

        ttk.Button(janela, text="Adicionar tarefa", style="Accent.TButton", command=aplicar).grid(
            row=len(rotulos_com_padrao) + 1, column=0, columnspan=2, pady=18)

    def abrir_editor_de_tarefa(self):
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue um arquivo de configuração primeiro.")
            return

        janela = tk.Toplevel(self)
        janela.title("Editar tarefa")
        janela.geometry("400x430")
        janela.configure(bg=COR_FUNDO_APP)
        janela.transient(self)

        cabecalho = tk.Frame(janela, bg=COR_FUNDO_APP)
        cabecalho.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(16, 4))
        tk.Label(cabecalho, text="Editar tarefa", bg=COR_FUNDO_APP, fg=COR_TEXTO_SECUNDARIO,
                 font=FONTE_TITULO).pack(anchor="w")

        tk.Label(janela, text="Tarefa:", bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
            row=1, column=0, sticky="w", padx=16, pady=6)
        ids = sorted(self.simulador.tarefas_por_id.keys())
        variavel_id = tk.StringVar(value=str(ids[0]))
        combo = ttk.Combobox(janela, textvariable=variavel_id,
                             values=[str(i) for i in ids], state="readonly")
        combo.grid(row=1, column=1, padx=16, pady=6, sticky="ew")

        campos = {}
        rotulos = [
            ("cor", "Cor (#RRGGBB):"), ("ingresso", "Ingresso:"), ("duracao", "Duração:"),
            ("periodo", "Período:"), ("prazo", "Prazo:"), ("eventos", "Eventos (desloc:dur,...):"),
        ]
        for i, (chave, texto) in enumerate(rotulos, start=2):
            tk.Label(janela, text=texto, bg=COR_FUNDO_APP, font=FONTE_PADRAO).grid(
                row=i, column=0, sticky="w", padx=16, pady=6)
            entrada = tk.Entry(janela, width=26, font=FONTE_PADRAO, relief="solid", bd=1)
            entrada.grid(row=i, column=1, padx=16, pady=6, sticky="ew")
            campos[chave] = entrada
        janela.columnconfigure(1, weight=1)

        def carregar_valores(*_args):
            tarefa = self.simulador.tarefas_por_id[int(variavel_id.get())]
            valores = {
                "cor": tarefa.cor, "ingresso": str(tarefa.ingresso),
                "duracao": str(tarefa.duracao), "periodo": str(tarefa.periodo),
                "prazo": str(tarefa.prazo),
                "eventos": ",".join(f"{d}:{dur}" for d, dur in tarefa.eventos),
            }
            for chave, valor in valores.items():
                campos[chave].delete(0, tk.END)
                campos[chave].insert(0, valor)

        combo.bind("<<ComboboxSelected>>", carregar_valores)
        carregar_valores()

        def aplicar():
            tarefa = self.simulador.tarefas_por_id[int(variavel_id.get())]
            cor = CarregadorConfiguracao.normalizar_cor(campos["cor"].get())
            if cor is None:
                messagebox.showerror("Erro", "Cor inválida. Use o formato #RRGGBB.", parent=janela)
                return
            if not self._cor_disponivel(cor, tarefa.id, janela):
                return
            numeros = self._ler_campos_numericos(campos, janela)
            if numeros is None:
                return
            eventos = self._ler_eventos(campos, janela)
            if eventos is None:
                return
            ingresso, duracao, periodo, prazo = numeros

            tarefa.cor = cor
            tarefa.ingresso = ingresso
            tarefa.duracao = duracao
            tarefa.periodo = periodo
            tarefa.prazo = prazo
            tarefa.eventos = eventos

            self.svg_exportado_automaticamente = False
            self.simulador.aplicar_edicao_e_reconstruir()
            self._apos_mudanca_de_estado()
            self.desenhar_legenda()
            janela.destroy()

        def remover():
            """Remove a tarefa do conjunto simulado (req. 3.1). Precisa sobrar ao
            menos uma. Como toda edição, reconstrói a linha do tempo."""
            if len(self.simulador.definicoes) <= 1:
                messagebox.showerror(
                    "Erro", "Não é possível remover a última tarefa restante.", parent=janela)
                return
            id_selecionado = int(variavel_id.get())
            if not messagebox.askyesno(
                    "Confirmar remoção",
                    f"Remover a Tarefa {id_selecionado}? Esta ação não pode ser desfeita.",
                    parent=janela):
                return

            self.simulador.definicoes = [
                t for t in self.simulador.definicoes if t.id != id_selecionado]
            self.simulador.tarefas_por_id = {t.id: t for t in self.simulador.definicoes}

            self.svg_exportado_automaticamente = False
            self.simulador.aplicar_edicao_e_reconstruir()
            self._apos_mudanca_de_estado()
            self.desenhar_legenda()
            janela.destroy()

        quadro_botoes = tk.Frame(janela, bg=COR_FUNDO_APP)
        quadro_botoes.grid(row=len(rotulos) + 2, column=0, columnspan=2, pady=18)
        ttk.Button(quadro_botoes, text="Aplicar", style="Accent.TButton",
                   command=aplicar).pack(side=tk.LEFT, padx=6)
        ttk.Button(quadro_botoes, text="Remover tarefa", style="Secondary.TButton",
                   command=remover).pack(side=tk.LEFT, padx=6)

    def abrir_editor_de_estado(self):
        """Altera o estado dinâmico no tick exibido e descarta o futuro antigo."""
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue uma configuração primeiro.")
            return
        janela = tk.Toplevel(self)
        janela.title("Editar estado atual")
        janela.geometry("430x250")
        janela.configure(bg=COR_FUNDO_APP)
        janela.transient(self)
        janela.grab_set()
        tk.Label(janela, text="Estado no tick selecionado", bg=COR_FUNDO_APP,
                 fg=COR_TEXTO_SECUNDARIO, font=FONTE_TITULO).pack(anchor="w", padx=18, pady=(18, 10))
        quadro = tk.Frame(janela, bg=COR_FUNDO_APP)
        quadro.pack(fill=tk.X, padx=18)
        ids = sorted(self.simulador.tarefas_por_id)
        var_id = tk.StringVar(value=str(ids[0]))
        var_estado = tk.StringVar(value="pronta")
        tk.Label(quadro, text="Tarefa:", bg=COR_FUNDO_APP).grid(row=0, column=0, sticky="w", pady=6)
        ttk.Combobox(quadro, textvariable=var_id, values=[str(i) for i in ids],
                     state="readonly").grid(row=0, column=1, sticky="ew", pady=6)
        tk.Label(quadro, text="Novo estado:", bg=COR_FUNDO_APP).grid(row=1, column=0, sticky="w", pady=6)
        ttk.Combobox(quadro, textvariable=var_estado, values=["pronta", "suspensa"],
                     state="readonly").grid(row=1, column=1, sticky="ew", pady=6)
        quadro.columnconfigure(1, weight=1)
        tk.Label(janela,
                 text="O estado executando é sempre decidido pelo escalonador.\n"
                      "Uma suspensão manual permanece por um tick.",
                 bg=COR_FUNDO_APP, fg=COR_TEXTO_SECUNDARIO,
                 justify=tk.LEFT).pack(anchor="w", padx=18, pady=8)

        def aplicar_estado():
            try:
                self.simulador.alterar_estado_tarefa(int(var_id.get()), var_estado.get())
            except ValueError as erro:
                messagebox.showerror("Alteração inválida", str(erro), parent=janela)
                return
            self.svg_exportado_automaticamente = False
            self._apos_mudanca_de_estado()
            janela.destroy()

        ttk.Button(janela, text="Aplicar", style="Accent.TButton",
                   command=aplicar_estado).pack(pady=10)

    def abrir_relatorio_metricas(self):
        """Mostra Tt, Tw, tr, trocas e aproveitamento (capítulo 6 do livro)."""
        if self.simulador is None:
            messagebox.showinfo("Aviso", "Carregue uma configuração primeiro.")
            return
        janela = tk.Toplevel(self)
        janela.title("Métricas da simulação")
        janela.geometry("560x460")
        janela.configure(bg=COR_FUNDO_APP)
        janela.transient(self)
        tk.Label(janela, text="Métricas de escalonamento", bg=COR_FUNDO_APP,
                 fg=COR_TEXTO_SECUNDARIO, font=FONTE_TITULO).pack(anchor="w", padx=16, pady=(14, 8))
        texto = tk.Text(janela, wrap="none", font=("Consolas", 9), height=20)
        texto.insert("1.0", self.simulador.texto_metricas())
        texto.configure(state="disabled")
        texto.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 10))
        ttk.Button(janela, text="Fechar", style="Accent.TButton",
                   command=janela.destroy).pack(pady=(0, 14))

    # --------------------------- exportação ---------------------------
    def exportar_para_svg(self):
        if self.simulador is None or not self.simulador.historico:
            messagebox.showinfo("Aviso", "Carregue e execute (ao menos parcialmente) uma simulação primeiro.")
            return
        caminho = filedialog.asksaveasfilename(
            defaultextension=".svg",
            filetypes=[("Imagem SVG", "*.svg")],
            initialfile="gantt_simulacao.svg",
        )
        if not caminho:
            return
        try:
            ExportadorSVG(self.simulador).exportar(caminho)
        except Exception as erro:  # qualquer falha de I/O deve aparecer ao usuário
            messagebox.showerror("Erro ao exportar", str(erro))
            return
        messagebox.showinfo("Exportado com sucesso", f"Gráfico de Gantt exportado para:\n{caminho}")

    def _exportar_svg_automaticamente(self):
        if self.caminho_arquivo_atual:
            base, _ext = os.path.splitext(self.caminho_arquivo_atual)
        else:
            base = os.path.join(os.getcwd(), "simulacao")
        caminho = base + "_gantt.svg"
        try:
            ExportadorSVG(self.simulador).exportar(caminho)
            self.rotulo_status.config(
                text=self.rotulo_status.cget("text") + f"   |   SVG salvo automaticamente em: {caminho}")
        except Exception as erro:
            messagebox.showerror('Erro ao exportar automaticamente', str(erro))

    # --------------------------- atualização de tela ---------------------------
    def _apos_mudanca_de_estado(self):
        """Ponto único chamado depois de qualquer ação que altere a simulação.
        Atualiza status, painel e Gantt e, se a simulação terminou, exporta o
        SVG automaticamente (uma vez por simulação)."""
        self._atualizar_status()
        self._atualizar_painel_tarefas()
        self.desenhar_gantt()
        if (self.simulador is not None and self.simulador.finalizado
                and self.simulador.indice_historico == len(self.simulador.historico) - 1
                and not self.svg_exportado_automaticamente):
            self._exportar_svg_automaticamente()
            self.svg_exportado_automaticamente = True

    def _ociosidade_por_cpu(self):
        """Ticks em que cada CPU ficou desligada, até o ponto exibido (req. 1.2)."""
        s = self.simulador
        total = len(s.cpus)
        blocos, _ = s.obter_todos_os_blocos(ate_indice=s.indice_historico)
        ocupadas = set()
        for (_tid, idx_cpu, ini, fim, estado) in blocos:
            if estado == 'executando' and idx_cpu is not None:
                for t in range(ini, fim):
                    ocupadas.add((idx_cpu, t))
        ticks = s.historico[s.indice_historico]['tick'] - s.historico[0]['tick']
        desligado = []
        for idx in range(total):
            ativos = sum(1 for (c, _t) in ocupadas if c == idx)
            desligado.append(max(0, ticks - ativos))
        return ", ".join(f"CPU{i}={desligado[i]}" for i in range(total) if desligado[i] > 0)

    def _atualizar_status(self):
        s = self.simulador
        if s is None:
            self.rotulo_status.config(text="Nenhum arquivo carregado.")
            return
        atual = s.historico[s.indice_historico]
        texto = (
            f"Arquivo: {os.path.basename(self.caminho_arquivo_atual)}   |   "
            f"Algoritmo: {s.algoritmo}   |   Quantum: {s.quantum}   |   CPUs: {s.num_cpus}   |   "
            f"Tick atual: {atual['tick']}   |   Passo {s.indice_historico + 1} de {len(s.historico)}"
        )
        if s.finalizado and s.indice_historico == len(s.historico) - 1:
            texto += "   |   SIMULAÇÃO FINALIZADA"
        jobs = atual.get('jobs', {})
        prontos = sum(1 for j in jobs.values() if j.estado == 'pronta')
        executando = sum(1 for j in jobs.values() if j.estado == 'executando')
        suspensos = sum(1 for j in jobs.values() if j.estado == 'suspensa')
        texto += f"   |   Jobs: {prontos} prontos, {executando} executando, {suspensos} suspensos"
        ociosidade = self._ociosidade_por_cpu()
        if ociosidade:
            texto += "   |   CPUs desligadas (ticks): " + ociosidade
        self.rotulo_status.config(text=texto)

    def _atualizar_painel_tarefas(self):
        """Repopula o painel com o estado de cada tarefa no passo exibido (não no
        estado mais recente), para que retroceder também retroceda o painel."""
        tabela = self.tabela_tarefas
        for item in tabela.get_children():
            tabela.delete(item)

        s = self.simulador
        if s is None:
            return

        snapshot = s.historico[s.indice_historico]
        estado_tarefas = snapshot['estado_tarefas']
        cpus = snapshot['cpus']

        rotulos_estado = {
            'nao_chegou': 'Não chegou', 'pronta': 'Pronta', 'executando': 'Executando',
            'suspensa': 'Suspensa', 'concluida': 'Concluída',
        }

        for tid in sorted(s.tarefas_por_id.keys()):
            et = estado_tarefas[tid]
            estado_legivel = rotulos_estado.get(et['estado'], et['estado'])

            cpu_texto = "—"
            if et['cpu'] is not None and et['cpu'] < len(cpus):
                cpu_texto = f"CPU{et['cpu']}"

            restante_texto = str(et['restante_atual']) if et['estado'] in (
                'pronta', 'executando', 'suspensa') else "—"
            prazo_texto = str(et['prazo_abs_atual']) if et['prazo_abs_atual'] is not None else "—"
            instancia_texto = f"{et['instancias_liberadas']}/{ATIVACOES_POR_TAREFA}"
            deadline_texto = "SIM" if et['deadline_perdido'] else "não"

            tags = ("deadline_perdido",) if et['deadline_perdido'] else ()
            tabela.insert(
                "", "end", text=f"Tarefa {tid}",
                values=(estado_legivel, cpu_texto, restante_texto, prazo_texto,
                        instancia_texto, deadline_texto),
                tags=tags,
            )

    # --------------------------- desenho do Gantt ---------------------------
    def desenhar_gantt(self):
        canvas = self.canvas_gantt
        canvas.delete("all")
        s = self.simulador
        if s is None:
            return

        ids_tarefas = sorted(s.tarefas_por_id.keys(), reverse=True)  # ID menor mais próximo da régua
        n_tarefas = len(ids_tarefas)
        n_cpus = s.num_cpus

        tick_inicial = s.historico[0]['tick']
        tick_atual = s.historico[s.indice_historico]['tick']
        duracao = max(1, tick_atual - tick_inicial)

        largura_total = MARGEM_ESQUERDA + duracao * LARGURA_TICK + 40
        altura_total = MARGEM_TOPO + (n_tarefas + n_cpus) * ALTURA_LINHA + ESPACO_REGUA + 20
        canvas.configure(scrollregion=(0, 0, largura_total, altura_total))

        def x_do_tick(tk_):
            return MARGEM_ESQUERDA + (tk_ - tick_inicial) * LARGURA_TICK

        # régua de ticks: entre as linhas de tarefa e as de CPU
        y_fim_grade = MARGEM_TOPO + (n_tarefas + n_cpus) * ALTURA_LINHA + ESPACO_REGUA
        for tk_ in range(tick_inicial, tick_atual + 1):
            if (tk_ - tick_inicial) % 5 == 0:
                x = x_do_tick(tk_)
                canvas.create_line(x, MARGEM_TOPO, x, y_fim_grade, fill=COR_GRADE)
                canvas.create_text(x, MARGEM_TOPO + n_tarefas * ALTURA_LINHA + 12,
                                   text=str(tk_), font=("Helvetica", 8), fill="#666666")

        y_por_tarefa = {}
        for i, tid in enumerate(ids_tarefas):
            y = MARGEM_TOPO + i * ALTURA_LINHA
            y_por_tarefa[tid] = y
            canvas.create_text(MARGEM_ESQUERDA - 10, y + ALTURA_LINHA / 2, text=f"Tarefa {tid}",
                               anchor="e", font=("Helvetica", 10))
            canvas.create_line(MARGEM_ESQUERDA, y + ALTURA_LINHA, largura_total - 40,
                               y + ALTURA_LINHA, fill=COR_GRADE)

        y_cpus_topo = MARGEM_TOPO + n_tarefas * ALTURA_LINHA + ESPACO_REGUA
        y_por_cpu = {}
        for cidx in range(n_cpus):
            y = y_cpus_topo + cidx * ALTURA_LINHA
            y_por_cpu[cidx] = y
            canvas.create_text(MARGEM_ESQUERDA - 10, y + ALTURA_LINHA / 2, text=f"CPU {cidx}",
                               anchor="e", font=("Helvetica", 10))
            # fundo cinza = CPU desligada; os blocos coloridos cobrem onde ela estava ligada
            canvas.create_rectangle(
                MARGEM_ESQUERDA, y + 3, MARGEM_ESQUERDA + duracao * LARGURA_TICK,
                y + ALTURA_LINHA - 3, fill=COR_CPU_DESLIGADA, outline="")

        blocos, eventos = s.obter_todos_os_blocos(ate_indice=s.indice_historico)

        for (tid, idx_cpu, ini, fim, estado) in blocos:
            if tid is None or tid not in y_por_tarefa:
                continue
            y = y_por_tarefa[tid]
            x1, x2 = x_do_tick(ini), x_do_tick(fim)
            if estado == 'executando':
                canvas.create_rectangle(x1, y + 3, x2, y + ALTURA_LINHA - 3,
                                        fill=s.tarefas_por_id[tid].cor, outline="#333333")
                if idx_cpu is not None and (x2 - x1) > 24:
                    canvas.create_text((x1 + x2) / 2, y + ALTURA_LINHA / 2, text=f"CPU{idx_cpu}",
                                       fill="white", font=("Helvetica", 7))
            elif estado == 'suspensa':
                canvas.create_rectangle(x1, y + 3, x2, y + ALTURA_LINHA - 3,
                                        fill="black", stipple="gray50", outline="#333333")

        for (tid, idx_cpu, ini, fim, estado) in blocos:
            if idx_cpu is None or estado != 'executando':
                continue
            y = y_por_cpu[idx_cpu]
            x1, x2 = x_do_tick(ini), x_do_tick(fim)
            canvas.create_rectangle(x1, y + 3, x2, y + ALTURA_LINHA - 3,
                                    fill=s.tarefas_por_id[tid].cor, outline="#333333")

        for ev in eventos:
            tid = ev.get('tarefa')
            if tid not in y_por_tarefa:
                continue
            y = y_por_tarefa[tid]
            x = x_do_tick(ev['tick'])
            tipo = ev['tipo']
            if tipo == 'chegada':
                canvas.create_polygon(x - 5, y + ALTURA_LINHA - 2, x + 5, y + ALTURA_LINHA - 2,
                                      x, y + ALTURA_LINHA - 12, fill=COR_CHEGADA)
            elif tipo in ('conclusao_instancia', 'conclusao_tarefa'):
                canvas.create_line(x, y + 3, x, y + ALTURA_LINHA - 3, fill="black", width=2)
                canvas.create_oval(x - 3, y + 2, x + 3, y + 8, fill="black")
            elif tipo == 'deadline_miss':
                canvas.create_oval(x - 8, y + 6, x + 8, y + 22, outline=COR_DEADLINE_MISS, width=2)
                canvas.create_text(x, y + 14, text="!", fill=COR_DEADLINE_MISS,
                                   font=("Helvetica", 10, "bold"))
            elif tipo == 'sorteio':
                canvas.create_text(x, y + ALTURA_LINHA - 6, text="S", fill=COR_SORTEIO,
                                   font=("Helvetica", 10, "bold"))
            elif tipo == 'preempcao':
                # triângulo para baixo no topo da linha: a tarefa perdeu a CPU
                canvas.create_polygon(x - 5, y + 2, x + 5, y + 2, x, y + 11, fill=COR_PREEMPCAO)
            elif tipo == 'fim_quantum':
                canvas.create_text(x, y + 9, text="Q", fill=COR_FIM_QUANTUM,
                                   font=("Helvetica", 9, "bold"))

    def desenhar_legenda(self):
        canvas = self.canvas_legenda
        canvas.delete("all")
        s = self.simulador
        if s is None:
            return

        x, y = 10, 14
        canvas.create_text(x, y, text="Legenda:", anchor="w", font=("Helvetica", 10, "bold"),
                           fill=COR_TEXTO_SECUNDARIO)
        x += 75
        for t in s.definicoes:
            canvas.create_rectangle(x, y - 8, x + 16, y + 8, fill=t.cor, outline="#999999")
            canvas.create_text(x + 20, y, text=f"Tarefa {t.id}", anchor="w", font=("Helvetica", 9))
            x += 95

        x, y = 10, 38
        canvas.create_rectangle(x, y - 8, x + 16, y + 8, fill="white", outline="#999999")
        canvas.create_text(x + 20, y, text="Pronta (sem cor)", anchor="w", font=("Helvetica", 9))
        x += 150
        canvas.create_rectangle(x, y - 8, x + 16, y + 8, fill="black", stipple="gray50", outline="#999999")
        canvas.create_text(x + 20, y, text="Suspensa/bloqueada", anchor="w", font=("Helvetica", 9))
        x += 170
        canvas.create_rectangle(x, y - 8, x + 16, y + 8, fill=COR_CPU_DESLIGADA, outline="#999999")
        canvas.create_text(x + 20, y, text="CPU desligada", anchor="w", font=("Helvetica", 9))
        x += 125
        canvas.create_polygon(x + 3, y - 5, x + 13, y - 5, x + 8, y + 4, fill=COR_PREEMPCAO)
        canvas.create_text(x + 20, y, text="Preempção", anchor="w", font=("Helvetica", 9))
        x += 110
        canvas.create_text(x + 8, y, text="Q", fill=COR_FIM_QUANTUM, font=("Helvetica", 10, "bold"))
        canvas.create_text(x + 22, y, text="Fim de quantum", anchor="w", font=("Helvetica", 9))

        x, y = 10, 62
        canvas.create_polygon(x + 3, y + 6, x + 13, y + 6, x + 8, y - 4, fill=COR_CHEGADA)
        canvas.create_text(x + 20, y, text="Chegada de instância", anchor="w", font=("Helvetica", 9))
        x += 175
        canvas.create_line(x + 8, y - 6, x + 8, y + 6, fill="black", width=2)
        canvas.create_oval(x + 5, y - 8, x + 11, y - 2, fill="black")
        canvas.create_text(x + 20, y, text="Conclusão", anchor="w", font=("Helvetica", 9))
        x += 110
        canvas.create_oval(x, y - 8, x + 16, y + 8, outline=COR_DEADLINE_MISS, width=2)
        canvas.create_text(x + 20, y, text="Estouro de prazo", anchor="w", font=("Helvetica", 9))
        x += 155
        canvas.create_text(x + 8, y, text="S", fill=COR_SORTEIO, font=("Helvetica", 10, "bold"))
        canvas.create_text(x + 22, y, text="Escolhida por sorteio", anchor="w", font=("Helvetica", 9))

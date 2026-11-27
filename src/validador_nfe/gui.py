"""Interface gráfica do validador, em Flet (>= 1.0).

Uso:
    validador-nfe-gui            # janela de desktop
    validador-nfe-gui --web      # abre no navegador
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import flet as ft

from validador_nfe.divergencia import Divergencia
from validador_nfe.sessao import REGIMES, Sessao
from validador_nfe.validador import Resultado

COR_SITUACAO = {"ok": ft.Colors.GREEN_600, "com alertas": ft.Colors.AMBER_700, "com erros": ft.Colors.RED_600}
ICONE_SITUACAO = {"ok": ft.Icons.CHECK_CIRCLE, "com alertas": ft.Icons.WARNING_AMBER, "com erros": ft.Icons.ERROR}
COR_SEVERIDADE = {"erro": ft.Colors.RED_600, "alerta": ft.Colors.AMBER_700, "info": ft.Colors.BLUE_600}
FILTROS = {"todas": "Todas", "erro": "Só erros", "alerta": "Só alertas"}


def _cartao(titulo: str, valor: ft.Text, cor: str) -> ft.Container:
    return ft.Container(
        content=ft.Column([ft.Text(titulo, size=12, color=ft.Colors.ON_SURFACE_VARIANT), valor], spacing=2),
        padding=ft.Padding(16, 10, 16, 10),
        border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
        border_radius=8,
        bgcolor=ft.Colors.with_opacity(0.06, cor),
        width=150,
    )


class TelaValidador:
    def __init__(self, page: ft.Page, sessao: Sessao):
        self.page = page
        self.sessao = sessao
        self.selecionado: Resultado | None = None
        self.filtro = "todas"

        self.picker = ft.FilePicker()
        page.services.append(self.picker)

        self.n_notas, self.n_ok = ft.Text("0", size=22, weight=ft.FontWeight.BOLD), ft.Text("0", size=22, weight=ft.FontWeight.BOLD)
        self.n_alertas, self.n_erros = ft.Text("0", size=22, weight=ft.FontWeight.BOLD), ft.Text("0", size=22, weight=ft.FontWeight.BOLD)
        self.progresso = ft.ProgressRing(width=20, height=20, visible=False)
        self.status = ft.Text(f"Base de regras: {len(sessao.base)} regras", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

        self.lista_notas = ft.ListView(expand=True, spacing=2)
        self.cabecalho_nota = ft.Column(spacing=2)
        self.tabela = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(t)) for t in
                     ("Item", "Código", "Severidade", "Mensagem e fundamento", "Esperado", "Encontrado", "Dif. (R$)")],
            rows=[],
            column_spacing=16,
            data_row_max_height=float("inf"),
            heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        )
        self.vazio = ft.Text("Abra um XML ou uma pasta de notas para começar.", color=ft.Colors.ON_SURFACE_VARIANT)

        self.regime = ft.Dropdown(
            label="Regime de PIS/COFINS",
            value="",
            width=340,
            dense=True,
            options=[ft.DropdownOption(key=k, text=v) for k, v in REGIMES.items()],
            on_select=self.ao_mudar_regime,
        )
        self.seletor_filtro = ft.Dropdown(
            label="Mostrar",
            value="todas",
            width=160,
            dense=True,
            options=[ft.DropdownOption(key=k, text=v) for k, v in FILTROS.items()],
            on_select=self.ao_mudar_filtro,
        )
        self.rotulo_tipi = ft.Text("TIPI: não carregada", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

    # ---------- montagem ----------

    def montar(self) -> None:
        p = self.page
        p.title = "Validador de NF-e"
        p.padding = 16
        barra = ft.Row(
            [
                ft.Button("Abrir XMLs", icon=ft.Icons.UPLOAD_FILE, on_click=self.abrir_arquivos),
                ft.Button("Abrir pasta", icon=ft.Icons.FOLDER_OPEN, on_click=self.abrir_pasta),
                self.regime,
                ft.OutlinedButton("Carregar TIPI", icon=ft.Icons.TABLE_CHART, on_click=self.abrir_tipi),
                ft.OutlinedButton("Exportar Excel", icon=ft.Icons.GRID_ON, on_click=self.exportar_excel),
                ft.OutlinedButton("Exportar JSON", icon=ft.Icons.DATA_OBJECT, on_click=self.exportar_json),
                ft.TextButton("Limpar", icon=ft.Icons.DELETE_SWEEP, on_click=self.limpar),
                self.progresso,
            ],
            wrap=True,
            spacing=8,
        )
        cartoes = ft.Row(
            [
                _cartao("Notas", self.n_notas, ft.Colors.BLUE_600),
                _cartao("Sem divergência", self.n_ok, ft.Colors.GREEN_600),
                _cartao("Com alertas", self.n_alertas, ft.Colors.AMBER_700),
                _cartao("Com erros", self.n_erros, ft.Colors.RED_600),
                ft.Column([self.status, self.rotulo_tipi], spacing=2),
            ],
            spacing=12,
            wrap=True,
        )
        painel_notas = ft.Container(
            content=ft.Column([ft.Text("Notas", weight=ft.FontWeight.BOLD), self.lista_notas], expand=True),
            width=340,
            padding=8,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
        )
        painel_detalhe = ft.Container(
            content=ft.Column(
                [
                    ft.Row([self.cabecalho_nota, self.seletor_filtro],
                           alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                           vertical_alignment=ft.CrossAxisAlignment.START),
                    self.vazio,
                    ft.Column([ft.Row([self.tabela], scroll=ft.ScrollMode.AUTO)], scroll=ft.ScrollMode.AUTO, expand=True),
                ],
                expand=True,
            ),
            expand=True,
            padding=8,
            border=ft.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            border_radius=8,
        )
        p.add(
            ft.Text("Validador de NF-e", size=22, weight=ft.FontWeight.BOLD),
            barra,
            cartoes,
            ft.Row([painel_notas, painel_detalhe], expand=True, vertical_alignment=ft.CrossAxisAlignment.STRETCH),
        )
        self.atualizar()

    # ---------- desenho ----------

    def atualizar(self) -> None:
        r = self.sessao.resumo()
        self.n_notas.value = str(r["notas"])
        self.n_ok.value = str(r["notas_ok"])
        self.n_alertas.value = str(r["notas_com_alertas"])
        self.n_erros.value = str(r["notas_com_erros"])
        if self.selecionado not in self.sessao.resultados:
            # após revalidar os objetos mudam: mantém a nota escolhida pelo arquivo
            arquivo = self.selecionado.arquivo if self.selecionado else None
            mesmo = [r for r in self.sessao.resultados if r.arquivo == arquivo]
            self.selecionado = mesmo[0] if mesmo else (self.sessao.resultados[0] if self.sessao.resultados else None)
        self.lista_notas.controls = [self._linha_nota(res) for res in self.sessao.resultados]
        self._desenhar_detalhe()
        self.page.update()

    def _linha_nota(self, res: Resultado) -> ft.ListTile:
        erros = sum(d.severidade.value == "erro" for d in res.divergencias)
        alertas = sum(d.severidade.value == "alerta" for d in res.divergencias)
        numero = f"NF {res.nota.numero}" if res.nota and res.nota.numero else "Nota ilegível"
        return ft.ListTile(
            leading=ft.Icon(ICONE_SITUACAO[res.situacao], color=COR_SITUACAO[res.situacao]),
            title=ft.Text(f"{numero} · {Path(res.arquivo).name}", size=13, max_lines=1),
            subtitle=ft.Text(f"{erros} erros, {alertas} alertas", size=12),
            selected=res is self.selecionado,
            dense=True,
            on_click=lambda _, r=res: self.selecionar(r),
        )

    def _desenhar_detalhe(self) -> None:
        res = self.selecionado
        self.vazio.visible = res is None
        if res is None:
            self.cabecalho_nota.controls = []
            self.tabela.rows = []
            self.tabela.visible = False
            return
        n = res.nota
        if n:
            data = n.data_emissao.strftime("%d/%m/%Y") if n.data_emissao else "sem data"
            linhas = [
                ft.Text(f"NF {n.numero} série {n.serie} · {data}", size=16, weight=ft.FontWeight.BOLD),
                ft.Text(f"Emitente: {n.emitente.nome} ({n.emitente.uf}, CRT {n.emitente.crt})", size=12),
                ft.Text(f"Destinatário: {n.destinatario.nome} ({n.destinatario.uf})", size=12),
                ft.Text(f"Chave: {n.chave}", size=11, color=ft.Colors.ON_SURFACE_VARIANT, selectable=True),
            ]
        else:
            linhas = [ft.Text(Path(res.arquivo).name, size=16, weight=ft.FontWeight.BOLD)]
        situacao = ft.Text(res.situacao.upper(), color=COR_SITUACAO[res.situacao], weight=ft.FontWeight.BOLD)
        self.cabecalho_nota.controls = [*linhas, situacao]

        visiveis = [d for d in res.divergencias if self.filtro == "todas" or d.severidade.value == self.filtro]
        self.tabela.rows = [self._linha_divergencia(d) for d in visiveis]
        self.tabela.visible = bool(visiveis)
        if not res.divergencias:
            self.vazio.value, self.vazio.visible = "Nenhuma divergência encontrada nesta nota.", True
        else:
            self.vazio.value = "Abra um XML ou uma pasta de notas para começar."

    def _linha_divergencia(self, d: Divergencia) -> ft.DataRow:
        sev = d.severidade.value
        texto = [ft.Text(d.mensagem, size=13)]
        if d.fundamento:
            texto.append(ft.Text(d.fundamento, size=11, italic=True, color=ft.Colors.ON_SURFACE_VARIANT))
        return ft.DataRow(
            cells=[
                ft.DataCell(ft.Text(str(d.item) if d.item else "nota")),
                ft.DataCell(ft.Text(d.codigo, weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Text(sev, color=COR_SEVERIDADE.get(sev), weight=ft.FontWeight.BOLD)),
                ft.DataCell(ft.Container(ft.Column(texto, spacing=2), width=420, padding=ft.Padding(0, 6, 0, 6))),
                ft.DataCell(ft.Text(d.esperado or "")),
                ft.DataCell(ft.Text(d.encontrado or "")),
                ft.DataCell(ft.Text(f"{d.diferenca:.2f}" if d.diferenca is not None else "")),
            ]
        )

    def avisar(self, mensagem: str) -> None:
        self.page.show_dialog(ft.SnackBar(ft.Text(mensagem)))

    async def _em_segundo_plano(self, funcao, *args):
        self.progresso.visible = True
        self.page.update()
        try:
            return await asyncio.to_thread(funcao, *args)
        finally:
            self.progresso.visible = False
            self.atualizar()

    # ---------- eventos ----------

    def selecionar(self, res: Resultado) -> None:
        self.selecionado = res
        self.atualizar()

    async def abrir_arquivos(self, _=None) -> None:
        arquivos = await self.picker.pick_files(dialog_title="Escolha os XMLs de NF-e", allow_multiple=True,
                                                file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["xml"])
        caminhos = [Path(f.path) for f in arquivos or [] if f.path]
        if caminhos:
            novos = await self._em_segundo_plano(self.sessao.carregar, caminhos)
            self.avisar(f"{novos} nota(s) validada(s)")

    async def abrir_pasta(self, _=None) -> None:
        pasta = await self.picker.get_directory_path(dialog_title="Escolha a pasta com os XMLs")
        if pasta:
            novos = await self._em_segundo_plano(self.sessao.carregar, [Path(pasta)])
            self.avisar(f"{novos} nota(s) validada(s) da pasta")

    async def abrir_tipi(self, _=None) -> None:
        arquivos = await self.picker.pick_files(dialog_title="CSV da TIPI (ncm;aliquota)",
                                                file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["csv"])
        if arquivos and arquivos[0].path:
            caminho = Path(arquivos[0].path)
            try:
                await self._em_segundo_plano(self.sessao.definir_tipi, caminho)
            except Exception as exc:  # noqa: BLE001 - mostrar qualquer erro de leitura ao usuário
                self.avisar(f"Não foi possível ler a TIPI: {exc}")
                return
            self.rotulo_tipi.value = f"TIPI: {caminho.name}"
            self.status.value = f"Base de regras: {len(self.sessao.base)} regras"
            self.atualizar()

    async def ao_mudar_regime(self, e) -> None:
        await self._em_segundo_plano(self.sessao.definir_regime, self.regime.value or "")

    def ao_mudar_filtro(self, e) -> None:
        self.filtro = self.seletor_filtro.value or "todas"
        self.atualizar()

    async def _exportar(self, extensao: str, gravar) -> None:
        if not self.sessao.resultados:
            self.avisar("Nenhuma nota validada para exportar")
            return
        destino = await self.picker.save_file(dialog_title="Salvar relatório", file_name=f"relatorio.{extensao}",
                                              file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=[extensao])
        if destino:
            caminho = Path(destino if destino.endswith(f".{extensao}") else f"{destino}.{extensao}")
            gravar(caminho)
            self.avisar(f"Relatório salvo em {caminho}")

    async def exportar_excel(self, _=None) -> None:
        await self._exportar("xlsx", self.sessao.exportar_excel)

    async def exportar_json(self, _=None) -> None:
        await self._exportar("json", self.sessao.exportar_json)

    def limpar(self, _=None) -> None:
        self.sessao.limpar()
        self.selecionado = None
        self.atualizar()


def criar_app(caminhos_iniciais: list[Path] | None = None):
    def main(page: ft.Page) -> None:
        tela = TelaValidador(page, Sessao())
        if caminhos_iniciais:
            tela.sessao.carregar(caminhos_iniciais)
        tela.montar()

    return main


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="validador-nfe-gui", description="Interface gráfica do validador de NF-e")
    parser.add_argument("caminhos", nargs="*", type=Path, help="XMLs ou pastas para abrir já validados")
    parser.add_argument("--web", action="store_true", help="abre no navegador em vez de janela")
    parser.add_argument("--porta", type=int, default=0)
    args = parser.parse_args(argv)
    view = ft.AppView.WEB_BROWSER if args.web else ft.AppView.FLET_APP
    ft.run(criar_app(args.caminhos), view=view, port=args.porta)


if __name__ == "__main__":
    main()

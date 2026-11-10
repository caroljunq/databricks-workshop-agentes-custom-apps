"""Gera o PDF regulatório fictício do workshop (~10 páginas, com imagens, tabelas e gráficos em imagem).

Todos os nomes são fictícios:
  - Distribuidora: Exemplo Gás Distribuidora S.A.
  - Agência: ARSP-VE (Agência Reguladora de Serviços Públicos do Vale Exemplo)

Os números são lidos diretamente de dados/*.csv, então o PDF é consistente com as tabelas.

Uso:
    uv run --with reportlab --with matplotlib --with pandas --with numpy python scripts/gerar_pdf.py
Saída:
    documentos/relatorio_regulatorio_ficticio_2025.pdf
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet  # noqa: E402
from reportlab.lib.units import cm  # noqa: E402
from reportlab.platypus import (  # noqa: E402
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados"
ASSETS = RAIZ / "scripts" / "assets"
GRAF = ASSETS / "graficos"
GRAF.mkdir(parents=True, exist_ok=True)
SAIDA = RAIZ / "documentos" / "relatorio_regulatorio_ficticio_2025.pdf"
SAIDA.parent.mkdir(exist_ok=True)

TEAL = "#0F766E"
ORANGE = "#EA580C"
GRAY = "#475569"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

ind = pd.read_csv(DADOS / "indicadores_operacionais.csv")
tar = pd.read_csv(DADOS / "tarifas_segmento.csv")

# ---------------------------------------------------------------- métricas
vol_ano = ind.groupby("ano").volume_distribuido_mil_m3.sum().div(1000)
vol_2025 = vol_ano.loc[2025]
vol_2022 = vol_ano.loc[2022]
crescimento_vol = (vol_2025 / vol_2022 - 1) * 100

cli_dez = ind[ind.mes == 12].groupby("ano").clientes_ativos.sum()
cli_2025 = cli_dez.loc[2025]

perdas_ano = ind.groupby("ano").perdas_pct.mean()
meta_ano = ind.groupby("ano").meta_perdas_pct.mean()
perdas_2025 = perdas_ano.loc[2025]
meta_2025 = meta_ano.loc[2025]

invest_ano = ind.groupby("ano").investimento_realizado_mi_rs.sum()
invest_2025 = invest_ano.loc[2025]

emerg_reg_2025 = ind[ind.ano == 2025].groupby("regiao").tempo_medio_emergencia_min.mean().round(1)
perdas_reg_2025 = ind[ind.ano == 2025].groupby("regiao").perdas_pct.mean().round(2)
rede_reg = ind[(ind.ano == 2025) & (ind.mes == 12)].groupby("regiao").extensao_rede_km.sum()
cli_reg = ind[(ind.ano == 2025) & (ind.mes == 12)].groupby("regiao").clientes_ativos.sum()
vol_reg_2025 = ind[ind.ano == 2025].groupby("regiao").volume_distribuido_mil_m3.sum().div(1000)

vaz_litoral_2024 = ind[(ind.regiao == "Litoral") & (ind.ano == 2024)].groupby("mes").ocorrencias_vazamento.sum()
vaz_litoral_jul = int(vaz_litoral_2024.loc[7])
vaz_litoral_media = vaz_litoral_2024.drop([7, 8]).mean()

tar_3t = tar[(tar.ano == 2026) & (tar.trimestre == 3)].copy()
res_f1 = tar[(tar.segmento == "Residencial") & (tar.faixa_consumo.str.startswith("Faixa 1"))].copy()
res_f1["periodo"] = res_f1.ano.astype(str) + "T" + res_f1.trimestre.astype(str)
var_tarifa_res = (
    res_f1.tarifa_final_rs_m3.iloc[-1] / res_f1.tarifa_final_rs_m3.iloc[0] - 1
) * 100

# ---------------------------------------------------------------- gráficos (imagens)
def salvar(fig, nome):
    caminho = GRAF / nome
    fig.tight_layout()
    fig.savefig(caminho, dpi=170)
    plt.close(fig)
    return caminho


# G1 — volume mensal
v_mes = ind.groupby(["ano", "mes"]).volume_distribuido_mil_m3.sum().div(1000).reset_index()
v_mes["data"] = pd.to_datetime(v_mes.ano.astype(str) + "-" + v_mes.mes.astype(str) + "-01")
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.plot(v_mes.data, v_mes.volume_distribuido_mil_m3, color=TEAL, linewidth=2)
ax.set_title("Volume distribuído mensal (milhões de m³)", loc="left")
ax.set_ylabel("milhões de m³")
ax.grid(axis="y", alpha=0.3)
g_volume = salvar(fig, "g_volume_mensal.png")

# G2 — rede por região
fig, ax = plt.subplots(figsize=(8, 3.6))
ordem = rede_reg.sort_values(ascending=False)
ax.barh(ordem.index, ordem.values, color=TEAL)
for i, v in enumerate(ordem.values):
    ax.text(v + 30, i, f"{v:,.0f} km".replace(",", "."), va="center", fontsize=9)
ax.set_title("Extensão da rede por região — dez/2025 (km)", loc="left")
ax.invert_yaxis()
g_rede = salvar(fig, "g_rede_regiao.png")

# G3 — perdas vs meta
fig, ax = plt.subplots(figsize=(8, 3.6))
anos = list(perdas_ano.index)
ax.bar([str(a) for a in anos], perdas_ano.values, color=TEAL, label="Perdas realizadas (%)")
ax.plot([str(a) for a in anos], meta_ano.values, color=ORANGE, marker="o", linewidth=2, label="Meta regulatória (%)")
for i, v in enumerate(perdas_ano.values):
    ax.text(i, v + 0.03, f"{v:.2f}%".replace(".", ","), ha="center", fontsize=9)
ax.set_title("Perdas de gás: realizado × meta", loc="left")
ax.set_ylabel("% do volume")
ax.legend(frameon=False, loc="upper right")
g_perdas = salvar(fig, "g_perdas_meta.png")

# G4 — tempo de emergência por região (2025)
fig, ax = plt.subplots(figsize=(8, 3.6))
ordem = emerg_reg_2025.sort_values()
cores = [ORANGE if v > 30 else TEAL for v in ordem.values]
ax.barh(ordem.index, ordem.values, color=cores)
for i, v in enumerate(ordem.values):
    ax.text(v + 0.4, i, f"{v:.1f} min".replace(".", ","), va="center", fontsize=9)
ax.set_title("Tempo médio de atendimento de emergência — 2025 (minutos)", loc="left")
g_emerg = salvar(fig, "g_emergencia_regiao.png")

# G5 — investimento por ano
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.bar([str(a) for a in invest_ano.index], invest_ano.values, color=TEAL)
for i, v in enumerate(invest_ano.values):
    ax.text(i, v + 3, f"R$ {v:,.0f} mi".replace(",", "."), ha="center", fontsize=9)
ax.set_title("Investimento realizado por ano (R$ milhões)", loc="left")
g_invest = salvar(fig, "g_investimento_ano.png")

# G6 — tarifa residencial faixa 1 (evolução)
fig, ax = plt.subplots(figsize=(8, 3.6))
ax.plot(res_f1.periodo, res_f1.tarifa_final_rs_m3, color=ORANGE, marker="o", linewidth=2)
ax.set_title("Tarifa final — Residencial, Faixa 1 (R$/m³, com impostos)", loc="left")
ax.tick_params(axis="x", rotation=45)
ax.grid(axis="y", alpha=0.3)
g_tarifa = salvar(fig, "g_tarifa_residencial.png")


# Tabelas renderizadas como IMAGEM (para o exercício de OCR / ai_parse_document)
def tabela_imagem(nome, titulo, cabecalho, linhas, largura=8.0):
    fig, ax = plt.subplots(figsize=(largura, 0.45 * (len(linhas) + 2)))
    ax.axis("off")
    tab = ax.table(cellText=linhas, colLabels=cabecalho, loc="center", cellLoc="center")
    tab.auto_set_font_size(False)
    tab.set_fontsize(9)
    tab.scale(1, 1.5)
    for (r, c), cel in tab.get_celld().items():
        if r == 0:
            cel.set_facecolor(TEAL)
            cel.set_text_props(color="white", weight="bold")
        elif r % 2 == 0:
            cel.set_facecolor("#F1F5F9")
    ax.set_title(titulo, loc="left", fontsize=11)
    return salvar(fig, nome)


rows_meta = []
for a in anos:
    rows_meta.append([str(a), f"{meta_ano.loc[a]:.2f}%".replace(".", ","), f"{perdas_ano.loc[a]:.2f}%".replace(".", ","),
                      "Atingida" if perdas_ano.loc[a] <= meta_ano.loc[a] else "Não atingida"])
t_perdas = tabela_imagem(
    "t_perdas_meta.png",
    "Tabela 2 — Perdas de gás: meta × realizado por ano",
    ["Ano", "Meta", "Realizado", "Situação"],
    rows_meta,
    largura=7.0,
)

rows_tar = []
for _, r in tar_3t.iterrows():
    rows_tar.append([r.segmento, r.faixa_consumo, f"{r.margem_distribuicao_rs_m3:.4f}".replace(".", ","),
                     f"{r.tarifa_final_rs_m3:.4f}".replace(".", ","), f"{r.impostos_pct:.1f}%".replace(".", ",")])
t_tarifa = tabela_imagem(
    "t_tarifas_2026t3.png",
    "Tabela 3 — Tarifas vigentes no 3º trimestre de 2026 (R$/m³)",
    ["Segmento", "Faixa de consumo", "Margem", "Tarifa final", "Impostos"],
    rows_tar,
    largura=11.5,
)

# ---------------------------------------------------------------- estilos
ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], textColor=colors.HexColor(TEAL), fontSize=18, spaceAfter=10)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], textColor=colors.HexColor(GRAY), fontSize=12.5, spaceBefore=8, spaceAfter=6)
BODY = ParagraphStyle("BODY", parent=ss["BodyText"], fontSize=10, leading=14, alignment=TA_JUSTIFY, spaceAfter=6)
SMALL = ParagraphStyle("SMALL", parent=BODY, fontSize=8, leading=10, textColor=colors.HexColor(GRAY))
CAPA_T = ParagraphStyle("CAPA_T", parent=H1, fontSize=24, alignment=TA_CENTER, leading=30)
CAPA_S = ParagraphStyle("CAPA_S", parent=BODY, fontSize=12, alignment=TA_CENTER, leading=18)


def p(texto, estilo=BODY):
    return Paragraph(texto, estilo)


def tabela(dados, larguras=None):
    t = Table(dados, colWidths=larguras, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(TEAL)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F5F9")]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#CBD5E1")),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


def br(n):
    return f"{n:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")


def img(caminho, largura_cm, proporcao=None):
    from reportlab.lib.utils import ImageReader

    ir = ImageReader(str(caminho))
    w, h = ir.getSize()
    alt = largura_cm * cm * h / w
    return Image(str(caminho), width=largura_cm * cm, height=alt)


ASSET = ASSETS
story = []

# ---------------------------------------------------------------- Página 1 — Capa
story += [
    Spacer(1, 1.2 * cm),
    p("Exemplo Gás Distribuidora S.A.", CAPA_S),
    Spacer(1, 0.4 * cm),
    p("Relatório Anual de Indicadores de Distribuição<br/>Ciclo 2025", CAPA_T),
    p("Apresentado à Agência Reguladora de Serviços Públicos do Vale Exemplo (ARSP-VE)", CAPA_S),
    Spacer(1, 0.6 * cm),
    img(ASSET / "capa_cidade_rede_gas.png", 15.5),
    Spacer(1, 0.5 * cm),
    p("DOCUMENTO FICTÍCIO PARA FINS DE WORKSHOP. Todos os nomes de empresas, pessoas, agências e valores "
      "são sintéticos e não representam dados reais.", SMALL),
    PageBreak(),
]

# ---------------------------------------------------------------- Página 2 — Sumário executivo
story += [
    p("1. Sumário executivo", H1),
    p(
        f"Este relatório consolida os indicadores operacionais, de qualidade e econômicos da Exemplo Gás "
        f"Distribuidora S.A. referentes ao ciclo 2025, conforme o Plano de Indicadores aprovado pela ARSP-VE. "
        f"Em 2025, o volume distribuído atingiu <b>{br(vol_2025)} milhões de m³</b>, crescimento de "
        f"<b>{br(crescimento_vol)}%</b> em relação a 2022. A base de clientes ativos encerrou dezembro com "
        f"<b>{cli_2025:,.0f}</b> unidades consumidoras.".replace(",", "."),
    ),
    p(
        f"As perdas de gás médias do ano ficaram em <b>{br(perdas_2025)}%</b>, abaixo da meta regulatória de "
        f"<b>{br(meta_2025)}%</b>. O investimento realizado somou <b>R$ {invest_2025:,.1f} milhões</b>, "
        f"concentrado em renovação de rede de polietileno e estações de regulagem de pressão.".replace(",", "X").replace(".", ",").replace("X", "."),
    ),
    p(
        "O tempo médio de atendimento de emergências ficou acima de 30 minutos na região Planalto Norte, "
        "que concentra a menor densidade de clientes por quilômetro de rede. Em julho de 2024, eventos "
        f"climáticos no Litoral elevaram as ocorrências de vazamento para <b>{vaz_litoral_jul}</b> no mês, "
        "fora do padrão histórico; o caso está detalhado na Seção 8.",
    ),
    Spacer(1, 0.3 * cm),
    p("Quadro-resumo de indicadores — 2025", H2),
    tabela(
        [
            ["Indicador", "Valor", "Referência"],
            ["Volume distribuído (milhões de m³)", br(vol_2025), f"2022: {br(vol_2022)}"],
            ["Clientes ativos em dezembro", f"{cli_2025:,}".replace(",", "."), f"2022: {cli_dez.loc[2022]:,}".replace(",", ".")],
            ["Perdas de gás (% do volume)", f"{br(perdas_2025)}%", f"Meta: {br(meta_2025)}%"],
            ["Investimento realizado (R$ milhões)", br(invest_2025), f"2022: {br(invest_ano.loc[2022])}"],
            ["Tempo médio de emergência (min, média das regiões)", br(emerg_reg_2025.mean()), "Ver Seção 5"],
        ],
        [9 * cm, 3.5 * cm, 4.5 * cm],
    ),
    PageBreak(),
]

# ---------------------------------------------------------------- Página 3 — Área de concessão
story += [
    p("2. Área de concessão e rede", H1),
    p(
        "A área de concessão é composta por cinco regiões operacionais: Capital, Litoral, Vale do Rio Claro, "
        "Planalto Norte e Zona Industrial Sul. A Zona Industrial Sul concentra os maiores contratos industriais, "
        "enquanto a Capital reúne a maior base de clientes residenciais e comerciais.",
    ),
    img(g_rede, 15.5),
    Spacer(1, 0.3 * cm),
    tabela(
        [["Região", "Clientes ativos (dez/2025)", "Rede (km)", "Volume 2025 (mi m³)"]]
        + [
            [r, f"{cli_reg.loc[r]:,}".replace(",", "."), f"{rede_reg.loc[r]:,.0f}".replace(",", "."), br(vol_reg_2025.loc[r])]
            for r in rede_reg.sort_values(ascending=False).index
        ],
        [5 * cm, 4.5 * cm, 3 * cm, 4 * cm],
    ),
    PageBreak(),
]

# ---------------------------------------------------------------- Página 4 — Volume
story += [
    p("3. Volume distribuído", H1),
    p(
        "O volume distribuído apresenta sazonalidade marcada no segmento residencial, com picos entre junho e "
        "agosto, quando o consumo para aquecimento e geração de água quente aumenta. A Zona Industrial Sul mantém "
        "consumo estável ao longo do ano por operar em regime contínuo.",
    ),
    img(g_volume, 15.5),
    Spacer(1, 0.3 * cm),
    p("Tabela 1 — Volume distribuído por ano (milhões de m³)", H2),
    tabela(
        [["Ano", "Volume (mi m³)", "Variação vs. ano anterior"]]
        + [
            [str(a), br(vol_ano.loc[a]), "—" if a == 2022 else f"{((vol_ano.loc[a] / vol_ano.loc[a - 1]) - 1) * 100:+.1f}%".replace(".", ",")]
            for a in vol_ano.index
            if a <= 2025
        ],
        [4 * cm, 4 * cm, 6 * cm],
    ),
    PageBreak(),
]

# ---------------------------------------------------------------- Página 5 — Perdas
story += [
    p("4. Perdas de gás", H1),
    p(
        "As perdas de gás são calculadas como a diferença entre o volume injetado no sistema e o volume faturado, "
        "dividida pelo volume injetado. A meta regulatória reduz 0,2 ponto percentual ao ano desde 2022. "
        f"Em 2025 a média foi de {br(perdas_2025)}%, e a região Planalto Norte foi a que mais se distanciou da meta, "
        f"com {br(perdas_reg_2025.loc['Planalto Norte'])}%, devido à idade da rede de ferro fundido ainda em operação.",
    ),
    img(g_perdas, 15.5),
    Spacer(1, 0.3 * cm),
    img(t_perdas, 14.0),
    PageBreak(),
]

# ---------------------------------------------------------------- Página 6 — Emergências + técnicos
story += [
    p("5. Continuidade e atendimento de emergências", H1),
    p(
        "O indicador de tempo médio de atendimento mede os minutos entre o registro da ocorrência de odor de gás "
        "ou vazamento e a chegada da equipe ao local. A meta de atendimento é de 30 minutos em 90% dos casos. "
        "A região Planalto Norte ainda opera acima dessa referência e o Litoral está próximo do limite, o que motivou o "
        "plano de reforço de equipes nessas duas regiões.",
    ),
    img(g_emerg, 15.0),
    Spacer(1, 0.2 * cm),
    img(ASSET / "tecnicos_estacao_regulagem.png", 11.0),
    p("Figura 1 — Equipe técnica em inspeção de estação de regulagem de pressão (ilustração).", SMALL),
    PageBreak(),
]

# ---------------------------------------------------------------- Página 7 — Investimentos + obra
story += [
    p("6. Investimentos", H1),
    p(
        f"O investimento realizado em 2025 foi de <b>R$ {invest_2025:,.1f} milhões</b>, distribuídos entre expansão "
        "da rede, substituição de trechos em ferro fundido por polietileno e automação das estações de regulagem. "
        "A substituição de rede é a principal alavanca para reduzir perdas e tempo de atendimento.".replace(",", "X").replace(".", ",").replace("X", "."),
    ),
    img(g_invest, 15.0),
    Spacer(1, 0.2 * cm),
    img(ASSET / "obra_rede_polietileno.png", 14.0),
    p("Figura 2 — Obra de substituição de trecho de rede em polietileno (ilustração).", SMALL),
    PageBreak(),
]

# ---------------------------------------------------------------- Página 8 — Tarifas
story += [
    p("7. Tarifas e reajustes", H1),
    p(
        "As tarifas são compostas por margem de distribuição, custo da molécula, custo de transporte e tributos. "
        "Entre o primeiro trimestre de 2022 e o terceiro trimestre de 2026, a tarifa final residencial (faixa 1) "
        f"variou <b>{br(var_tarifa_res)}%</b> no período, com reajustes trimestrais decorrentes da atualização "
        "da margem de distribuição, do custo da molécula e do transporte.",
    ),
    img(g_tarifa, 15.0),
    Spacer(1, 0.2 * cm),
    img(t_tarifa, 16.0),
    PageBreak(),
]

# ---------------------------------------------------------------- Página 9 — Ocorrências relevantes
story += [
    p("8. Ocorrências relevantes", H1),
    p(
        "<b>8.1 Evento climático no Litoral (julho de 2024).</b> Chuvas intensas e ventos fortes provocaram "
        f"deslizamentos sobre trechos de rede aérea de baixa pressão. O número de ocorrências de vazamento na região "
        f"chegou a <b>{vaz_litoral_jul}</b> no mês, contra uma média de aproximadamente "
        f"<b>{br(vaz_litoral_media)}</b> nos demais meses de 2024. O tempo médio de atendimento subiu cerca de 14 "
        "minutos durante o evento. Todas as ocorrências foram tratadas com planos de contingência e o fornecimento "
        "foi restabelecido em até 72 horas para os clientes afetados.",
    ),
    p(
        "<b>8.2 Ações corretivas.</b> Como resposta, a distribuidora antecipou a substituição de trechos vulneráveis "
        "no Litoral e instalou válvulas de bloqueio automático em 14 pontos de maior risco. A resposta foi "
        "monitorada mensalmente pela ARSP-VE.",
    ),
    p(
        "<b>8.3 Compromissos para o próximo ciclo.</b> A distribuidora se compromete a manter o tempo médio de "
        "atendimento abaixo de 30 minutos em todas as regiões até o fim do ciclo 2026, com revisão trimestral do "
        "plano de investimentos e do cronograma de substituição de rede.",
    ),
    PageBreak(),
]

# ---------------------------------------------------------------- Página 10 — Anexos
story += [
    p("9. Anexos: metodologia e glossário", H1),
    p("<b>Metodologia.</b> Os indicadores são calculados mensalmente a partir dos sistemas de medição, faturamento "
      "e atendimento da distribuidora. Os valores de volume e clientes são consolidados por região operacional. "
      "As tarifas são publicadas trimestralmente com vigência a partir do primeiro dia de cada trimestre.", BODY),
    p("<b>Glossário.</b>", BODY),
    tabela(
        [
            ["Termo", "Definição"],
            ["Perdas de gás", "Diferença entre volume injetado e volume faturado, em % do volume injetado."],
            ["Molécula", "Custo do gás natural adquirido, repassado sem margem de distribuição."],
            ["Margem de distribuição", "Remuneração da distribuidora pelo serviço de distribuição."],
            ["Emergência", "Ocorrência de odor de gás ou vazamento que exige atendimento imediato."],
            ["Polietileno (PE)", "Material de rede de distribuição com maior resistência a corrosão."],
        ],
        [4.5 * cm, 11.5 * cm],
    ),
    Spacer(1, 0.4 * cm),
    p("Declaração de responsabilidade", H2),
    p(
        "Declaramos que as informações contidas neste relatório refletem os registros operacionais da distribuidora "
        "no período de referência e que os dados foram auditados internamente antes da submissão. "
        "Este é um documento fictício, criado exclusivamente para exercícios de workshop.",
        BODY,
    ),
    Spacer(1, 0.3 * cm),
    p("Vale Exemplo, dezembro de 2025. Diretoria de Regulação (fictícia).", SMALL),
]


def rodape(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor(GRAY))
    canvas.drawString(2 * cm, 1.2 * cm, "Exemplo Gás Distribuidora S.A. — Relatório Anual 2025 — DOCUMENTO FICTÍCIO")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
    canvas.restoreState()


doc = SimpleDocTemplate(
    str(SAIDA),
    pagesize=A4,
    leftMargin=2 * cm,
    rightMargin=2 * cm,
    topMargin=1.8 * cm,
    bottomMargin=2 * cm,
    title="Relatório Anual de Indicadores de Distribuição 2025 (fictício)",
    author="Workshop Databricks — dados sintéticos",
)
doc.build(story, onFirstPage=rodape, onLaterPages=rodape)
print(f"PDF gerado: {SAIDA}")

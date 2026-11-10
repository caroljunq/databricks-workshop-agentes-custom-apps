"""Gráficos interativos a partir do resultado tabular do Genie.

O Genie indica quando a resposta tem gráfico (anexo `viz`), mas entrega a visualização só como PNG.
Aqui o gráfico é redesenhado com Altair a partir dos próprios dados da consulta (colunas + linhas),
o que permite tooltip, zoom e o visual do app. Se não houver formato reconhecível, a UI usa o PNG.
"""

import altair as alt
import pandas as pd

CORES = ["#1F4E79", "#2E86AB", "#F18F01", "#C73E1D", "#3B8B5A", "#6C5B7B", "#8D99AE"]
FONTE = "Inter, -apple-system, Segoe UI, Roboto, sans-serif"

_NUMERICOS = {"BYTE", "SHORT", "INT", "INTEGER", "LONG", "BIGINT", "FLOAT", "DOUBLE", "DECIMAL"}
_DATAS = {"DATE", "TIMESTAMP", "TIMESTAMP_NTZ"}
_SUFIXOS = [
    ("_mil_m3", " (mil m³)"),
    ("_rs_m3", " (R$/m³)"),
    ("_mi_rs", " (R$ mi)"),
    ("_pct", " (%)"),
    ("_km", " (km)"),
    ("_min", " (min)"),
]


def dataframe(artefato: dict) -> pd.DataFrame:
    """Monta o DataFrame do resultado do Genie convertendo os tipos informados pelo SQL."""
    nomes = [c["nome"] for c in artefato.get("colunas", [])]
    df = pd.DataFrame(artefato.get("linhas", []), columns=nomes)
    for c in artefato.get("colunas", []):
        tipo = (c.get("tipo") or "").upper()
        if tipo in _NUMERICOS:
            df[c["nome"]] = pd.to_numeric(df[c["nome"]], errors="coerce")
        elif tipo in _DATAS:
            df[c["nome"]] = pd.to_datetime(df[c["nome"]], errors="coerce")
    return df


def rotulo(nome: str) -> str:
    texto = nome
    sufixo = ""
    for fim, unidade in _SUFIXOS:
        if texto.lower().endswith(fim):
            texto, sufixo = texto[: -len(fim)], unidade
            break
    texto = texto.replace("_", " ").strip()
    return (texto[:1].upper() + texto[1:] + sufixo) if texto else nome


def _eh_id(nome: str) -> bool:
    n = nome.lower()
    return n == "id" or n.endswith("_id")


def _configurar(grafico: alt.Chart) -> alt.Chart:
    return (
        grafico.properties(height=320)
        .configure_view(strokeWidth=0)
        .configure_axis(
            gridColor="#EEF0F3",
            domainColor="#D0D5DD",
            tickColor="#D0D5DD",
            labelColor="#475467",
            titleColor="#344054",
            labelFont=FONTE,
            titleFont=FONTE,
            titleFontWeight=600,
            labelFontSize=11,
            titleFontSize=12,
        )
        .configure_legend(
            orient="bottom", labelFont=FONTE, titleFont=FONTE, labelColor="#475467", titleColor="#344054"
        )
    )


def grafico(df: pd.DataFrame) -> alt.Chart | None:
    """Escolhe linha (série temporal), barras (categorias) ou nada, conforme as colunas do resultado."""
    if df is None or len(df) < 2:
        return None
    d = df.copy()
    colunas = list(d.columns)
    por_nome = {c.lower(): c for c in colunas}
    numericas = [c for c in colunas if pd.api.types.is_numeric_dtype(d[c]) and not _eh_id(c)]
    datas = [c for c in colunas if pd.api.types.is_datetime64_any_dtype(d[c])]

    eixo_x, tipo_x, titulo_x, usadas = None, None, None, set()
    if "ano" in por_nome and "mes" in por_nome:
        ano, mes = por_nome["ano"], por_nome["mes"]
        d["_periodo"] = pd.to_datetime(
            dict(year=d[ano], month=d[mes], day=1), errors="coerce"
        )
        eixo_x, tipo_x, titulo_x, usadas = "_periodo", "temporal", "Período", {ano, mes}
    elif "ano" in por_nome and "trimestre" in por_nome:
        ano, tri = por_nome["ano"], por_nome["trimestre"]
        d["_periodo"] = d[ano].astype("Int64").astype(str) + "-T" + d[tri].astype("Int64").astype(str)
        eixo_x, tipo_x, titulo_x, usadas = "_periodo", "ordinal", "Trimestre", {ano, tri}
    elif datas:
        eixo_x, tipo_x, titulo_x, usadas = datas[0], "temporal", rotulo(datas[0]), {datas[0]}
    elif "ano" in por_nome:
        ano = por_nome["ano"]
        d[ano] = d[ano].astype("Int64").astype(str)
        eixo_x, tipo_x, titulo_x, usadas = ano, "ordinal", "Ano", {ano}

    numericas = [c for c in numericas if c not in usadas]
    categorias = [
        c for c in colunas
        if c not in usadas and c not in numericas and not _eh_id(c) and d[c].nunique() <= 25
    ]
    if not numericas:
        return None
    valor = numericas[0]
    tooltip_valor = alt.Tooltip(field=valor, type="quantitative", title=rotulo(valor), format=",.2f")

    if eixo_x:
        muitos_pontos = tipo_x != "temporal" and d[eixo_x].nunique() > 8
        x = alt.X(field=eixo_x, type=tipo_x, title=titulo_x,
                  axis=alt.Axis(labelAngle=-45 if muitos_pontos else 0, labelOverlap=True))
        if categorias:
            cat = categorias[0]
            g = alt.Chart(d).mark_line(point=True, strokeWidth=2.5).encode(
                x=x,
                y=alt.Y(field=valor, type="quantitative", title=rotulo(valor), scale=alt.Scale(zero=False)),
                color=alt.Color(field=cat, type="nominal", title=rotulo(cat), scale=alt.Scale(range=CORES)),
                tooltip=[alt.Tooltip(field=eixo_x, type=tipo_x, title=titulo_x),
                         alt.Tooltip(field=cat, type="nominal", title=rotulo(cat)), tooltip_valor],
            )
        elif len(numericas) > 1:
            longo = d.melt(id_vars=[eixo_x], value_vars=numericas[:4], var_name="Métrica", value_name="Valor")
            longo["Métrica"] = longo["Métrica"].map(rotulo)
            g = alt.Chart(longo).mark_line(point=True, strokeWidth=2.5).encode(
                x=x,
                y=alt.Y(field="Valor", type="quantitative", title="Valor", scale=alt.Scale(zero=False)),
                color=alt.Color(field="Métrica", type="nominal", scale=alt.Scale(range=CORES)),
                tooltip=[alt.Tooltip(field=eixo_x, type=tipo_x, title=titulo_x),
                         alt.Tooltip(field="Métrica", type="nominal"),
                         alt.Tooltip(field="Valor", type="quantitative", format=",.2f")],
            )
        else:
            g = alt.Chart(d).mark_line(point=True, strokeWidth=2.5, color=CORES[0]).encode(
                x=x,
                y=alt.Y(field=valor, type="quantitative", title=rotulo(valor), scale=alt.Scale(zero=False)),
                tooltip=[alt.Tooltip(field=eixo_x, type=tipo_x, title=titulo_x), tooltip_valor],
            )
        return _configurar(g)

    if not categorias:
        return None
    cat = categorias[0]
    if len(categorias) > 1:
        sub = categorias[1]
        g = alt.Chart(d).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            x=alt.X(field=cat, type="nominal", title=rotulo(cat), axis=alt.Axis(labelAngle=0)),
            xOffset=alt.XOffset(field=sub, type="nominal"),
            y=alt.Y(field=valor, type="quantitative", title=rotulo(valor)),
            color=alt.Color(field=sub, type="nominal", title=rotulo(sub), scale=alt.Scale(range=CORES)),
            tooltip=[alt.Tooltip(field=cat, type="nominal", title=rotulo(cat)),
                     alt.Tooltip(field=sub, type="nominal", title=rotulo(sub)), tooltip_valor],
        )
        return _configurar(g)

    horizontal = d[cat].nunique() > 6 or d[cat].astype(str).str.len().max() > 18
    tooltip = [alt.Tooltip(field=cat, type="nominal", title=rotulo(cat)), tooltip_valor]
    if horizontal:
        g = alt.Chart(d).mark_bar(cornerRadiusEnd=4, color=CORES[0]).encode(
            y=alt.Y(field=cat, type="nominal", title=None, sort="-x"),
            x=alt.X(field=valor, type="quantitative", title=rotulo(valor)),
            tooltip=tooltip,
        )
    else:
        g = alt.Chart(d).mark_bar(cornerRadiusEnd=4, color=CORES[0]).encode(
            x=alt.X(field=cat, type="nominal", title=rotulo(cat), sort="-y", axis=alt.Axis(labelAngle=0)),
            y=alt.Y(field=valor, type="quantitative", title=rotulo(valor)),
            tooltip=tooltip,
        )
    return _configurar(g)

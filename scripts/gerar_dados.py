"""Gera os 2 CSVs fictícios do workshop (dados 100% sintéticos).

Entidades fictícias:
  - Distribuidora: Exemplo Gás Distribuidora S.A. (SAGD)
  - Agência reguladora: ARSP-VE (Agência Reguladora de Serviços Públicos do Vale Exemplo)

Uso:
    uv run --with numpy --with pandas python scripts/gerar_dados.py
Saídas:
    dados/indicadores_operacionais.csv
    dados/tarifas_segmento.csv
    scripts/assets/resumo_dados.json   (usado pelo gerador do PDF para manter números consistentes)
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(2026)
RAIZ = Path(__file__).resolve().parent.parent
SAIDA_DADOS = RAIZ / "dados"
SAIDA_ASSETS = RAIZ / "scripts" / "assets"
SAIDA_DADOS.mkdir(exist_ok=True)
SAIDA_ASSETS.mkdir(exist_ok=True)

# ----------------------------------------------------------------------------
# 1) indicadores_operacionais — mensal por região (2022-01 a 2026-09)
# ----------------------------------------------------------------------------
REGIOES = {
    # base de volume (mil m3/mês), clientes (mil), rede (km), perdas base (%), tempo emergência base (min)
    "Capital": dict(vol=9200, cli=410, rede=3100, perdas=1.9, emerg=24),
    "Litoral": dict(vol=4300, cli=170, rede=1650, perdas=2.3, emerg=31),
    "Vale do Rio Claro": dict(vol=5600, cli=205, rede=2050, perdas=2.1, emerg=28),
    "Planalto Norte": dict(vol=3100, cli=96, rede=1320, perdas=2.8, emerg=39),
    "Zona Industrial Sul": dict(vol=11800, cli=52, rede=1480, perdas=1.6, emerg=22),
}
META_PERDAS = {2022: 2.8, 2023: 2.6, 2024: 2.4, 2025: 2.2, 2026: 2.0}

linhas = []
registro_id = 1
for ano in range(2022, 2027):
    for mes in range(1, 13):
        if ano == 2026 and mes > 9:
            continue
        idx = (ano - 2022) * 12 + (mes - 1)
        # inverno (jun-ago) consome mais gás residencial; indústria é estável
        sazonal = 1 + 0.16 * np.cos((mes - 7) / 12 * 2 * np.pi)
        for regiao, b in REGIOES.items():
            sazon_reg = 1.0 if regiao == "Zona Industrial Sul" else sazonal
            crescimento = 1 + 0.0042 * idx
            volume = b["vol"] * sazon_reg * crescimento * RNG.normal(1, 0.025)
            clientes = b["cli"] * 1000 * (1 + 0.0035 * idx) * RNG.normal(1, 0.002)
            rede = b["rede"] * (1 + 0.0028 * idx)
            perdas = max(0.9, b["perdas"] - 0.012 * idx + RNG.normal(0, 0.08))
            emerg = max(12, b["emerg"] - 0.06 * idx + RNG.normal(0, 1.6))
            vazamentos = max(0, int(RNG.normal(rede / 22, rede / 140)))
            invest = (b["rede"] / 1500) * RNG.normal(2.4, 0.5) * (1 + 0.012 * idx)
            # Anomalia: tempestades no litoral em jul/2024 pioram vazamentos e tempo de resposta
            if regiao == "Litoral" and ano == 2024 and mes in (7, 8):
                vazamentos = int(vazamentos * 2.1)
                emerg += 14
                perdas += 0.6
            linhas.append(
                dict(
                    registro_id=registro_id,
                    ano=ano,
                    mes=mes,
                    regiao=regiao,
                    volume_distribuido_mil_m3=round(volume, 1),
                    clientes_ativos=int(clientes),
                    extensao_rede_km=round(rede, 1),
                    perdas_pct=round(perdas, 2),
                    meta_perdas_pct=META_PERDAS[ano],
                    tempo_medio_emergencia_min=round(emerg, 1),
                    ocorrencias_vazamento=vazamentos,
                    investimento_realizado_mi_rs=round(invest, 2),
                )
            )
            registro_id += 1

ind = pd.DataFrame(linhas)
ind.to_csv(SAIDA_DADOS / "indicadores_operacionais.csv", index=False)

# ----------------------------------------------------------------------------
# 2) tarifas_segmento — trimestral por segmento e faixa (2022T1 a 2026T3)
# ----------------------------------------------------------------------------
SEGMENTOS = [
    # segmento, faixa, margem base R$/m3, molecula base, transporte base
    ("Residencial", "Faixa 1 (até 20 m3/mês)", 2.05, 2.30, 0.62),
    ("Residencial", "Faixa 2 (acima de 20 m3/mês)", 2.40, 2.30, 0.62),
    ("Comercial", "Faixa 1 (até 2.000 m3/mês)", 1.55, 2.25, 0.58),
    ("Comercial", "Faixa 2 (acima de 2.000 m3/mês)", 1.30, 2.25, 0.58),
    ("Industrial", "Faixa 1 (até 20.000 m3/mês)", 0.88, 2.10, 0.52),
    ("Industrial", "Faixa 2 (20.000 a 200.000 m3/mês)", 0.64, 2.10, 0.52),
    ("Industrial", "Faixa 3 (acima de 200.000 m3/mês)", 0.47, 2.10, 0.52),
    ("GNV", "Faixa única", 0.74, 2.15, 0.55),
    ("Cogeração", "Faixa única", 0.58, 2.10, 0.52),
]
IMPOSTOS_PCT = {"Residencial": 0.17, "Comercial": 0.17, "Industrial": 0.12, "GNV": 0.12, "Cogeração": 0.09}

linhas = []
tarifa_id = 1
trimestres = [(a, t) for a in range(2022, 2027) for t in range(1, 5) if not (a == 2026 and t > 3)]
ipca_trim = {  # reajuste de margem acompanha IPCA parcial (aprox.), fictício
    2022: 0.021, 2023: 0.012, 2024: 0.010, 2025: 0.011, 2026: 0.009,
}
anterior = {}
for (ano, tri) in trimestres:
    i = (ano - 2022) * 4 + (tri - 1)
    for seg, faixa, margem0, mol0, transp0 in SEGMENTOS:
        margem = margem0 * (1 + ipca_trim[ano]) ** i
        molecula = mol0 * (1 + 0.006 * i + RNG.normal(0, 0.012))
        transporte = transp0 * (1 + 0.004 * i)
        subtotal = margem + molecula + transporte
        final = subtotal * (1 + IMPOSTOS_PCT[seg])
        chave = (seg, faixa)
        reaj = None if chave not in anterior else (final / anterior[chave] - 1) * 100
        anterior[chave] = final
        mes_ini = {1: "01", 2: "04", 3: "07", 4: "10"}[tri]
        linhas.append(
            dict(
                tarifa_id=tarifa_id,
                ano=ano,
                trimestre=tri,
                segmento=seg,
                faixa_consumo=faixa,
                margem_distribuicao_rs_m3=round(margem, 4),
                molecula_rs_m3=round(molecula, 4),
                transporte_rs_m3=round(transporte, 4),
                impostos_pct=round(IMPOSTOS_PCT[seg] * 100, 1),
                tarifa_final_rs_m3=round(final, 4),
                reajuste_pct_vs_trimestre_anterior=None if reaj is None else round(reaj, 2),
                vigencia_inicio=f"{ano}-{mes_ini}-01",
            )
        )
        tarifa_id += 1

tar = pd.DataFrame(linhas)
tar.to_csv(SAIDA_DADOS / "tarifas_segmento.csv", index=False)

# ----------------------------------------------------------------------------
# 3) Resumo para manter o PDF consistente com os dados
# ----------------------------------------------------------------------------
resumo = {}
resumo["volume_anual_mi_m3"] = (
    ind[ind.ano <= 2025].groupby("ano").volume_distribuido_mil_m3.sum().div(1000).round(1).to_dict()
)
resumo["clientes_dez"] = (
    ind[ind.mes == 12].groupby("ano").clientes_ativos.sum().to_dict()
)
resumo["perdas_media_ano"] = ind.groupby("ano").perdas_pct.mean().round(2).to_dict()
resumo["perdas_media_regiao_2025"] = (
    ind[ind.ano == 2025].groupby("regiao").perdas_pct.mean().round(2).to_dict()
)
resumo["emerg_media_regiao_2025"] = (
    ind[ind.ano == 2025].groupby("regiao").tempo_medio_emergencia_min.mean().round(1).to_dict()
)
resumo["invest_ano_mi_rs"] = (
    ind[ind.ano <= 2025].groupby("ano").investimento_realizado_mi_rs.sum().round(1).to_dict()
)
resumo["volume_regiao_2025_mi_m3"] = (
    ind[ind.ano == 2025].groupby("regiao").volume_distribuido_mil_m3.sum().div(1000).round(1).to_dict()
)
resumo["rede_km_2025_dez"] = (
    ind[(ind.ano == 2025) & (ind.mes == 12)].groupby("regiao").extensao_rede_km.sum().round(0).to_dict()
)
resumo["vazamentos_litoral_jul_2024"] = int(
    ind[(ind.regiao == "Litoral") & (ind.ano == 2024) & (ind.mes == 7)].ocorrencias_vazamento.iloc[0]
)
resumo["tarifa_2026t3"] = (
    tar[(tar.ano == 2026) & (tar.trimestre == 3)]
    .set_index(["segmento", "faixa_consumo"])[
        ["margem_distribuicao_rs_m3", "tarifa_final_rs_m3"]
    ]
    .round(4)
    .reset_index()
    .to_dict(orient="records")
)
json.dump(resumo, open(SAIDA_ASSETS / "resumo_dados.json", "w"), ensure_ascii=False, indent=2, default=str)

print(f"indicadores_operacionais.csv: {len(ind)} linhas")
print(f"tarifas_segmento.csv: {len(tar)} linhas")
print(json.dumps({k: resumo[k] for k in ["volume_anual_mi_m3", "perdas_media_ano", "perdas_media_regiao_2025", "emerg_media_regiao_2025"]}, ensure_ascii=False, indent=1))

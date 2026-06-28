"""
AnaliseTrendFollowing.py

Lê o CSV do DataMiner (features/barra) e produz análise quantitativa
das condições de mercado onde a TrendFollowing tem maior/menor fit score.

Uso:
  python data/DataHouse/analise/AnaliseTrendFollowing.py [--csv <path>]

Saída:
  - Tabelas no terminal com fit_trend por regime, VIX, slope, etc.
  - Sugestões de ajuste de parâmetros baseadas em dados.
"""

import csv
import sys
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Optional

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────
TREND_THRESHOLD = 0.40  # min fit para elegibilidade (da estrategia)

DEFAULT_CSV = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "processed", "features", "alxquant_v7.csv"
)


@dataclass
class BarSnapshot:
    date: str
    H: float
    R2: float
    slope: float
    direction: int       # 1=up, -1=down
    momentum: int        # 1=accelerating, -1=decelerating, etc
    speed: float
    vwap_atr: float
    vix: float
    dxy: float
    us10y: float
    hy_spread: float
    yield_curve: float
    spy: float
    risk_score: float
    risk_regime: int     # 0=risk_on, 1=risk_off
    news_impact: float
    score: float
    confidence: float
    fit_trend: float
    fit_mr: float
    fit_breakout: float
    fit_sbo: float
    fit_rbo: float
    fit_pb: float


# ──────────────────────────────────────────────────────────────
# Leitura
# ──────────────────────────────────────────────────────────────
def ler_csv(path: str) -> List[BarSnapshot]:
    """Lê o CSV pulando linhas vazias e corrigindo problemas MQL5."""
    rows: List[BarSnapshot] = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            print("ERRO: CSV vazio ou sem header.")
            return rows

        colunas_esperadas = [
            "date", "H", "R2", "slope", "direction", "momentum",
            "speed", "vwap_atr", "vix", "dxy", "us10y", "hy_spread",
            "yield_curve", "spy", "risk_score", "risk_regime",
            "news_impact", "score", "confidence", "fit_trend", "fit_mr",
            "fit_breakout", "fit_sbo", "fit_rbo", "fit_pb"
        ]
        for fn in colunas_esperadas:
            if fn not in reader.fieldnames:
                print(f"AVISO: coluna '{fn}' nao encontrada no CSV. "
                      f"Colunas presentes: {reader.fieldnames}")
                return rows

        for i, row in enumerate(reader):
            # Pula linhas vazias
            if all(v.strip() == "" for v in row.values()):
                continue

            try:
                snap = BarSnapshot(
                    date=row.get("date", ""),
                    H=float(row.get("H", 0) or 0),
                    R2=float(row.get("R2", 0) or 0),
                    slope=float(row.get("slope", 0) or 0),
                    direction=int(float(row.get("direction", 0) or 0)),
                    momentum=int(float(row.get("momentum", 0) or 0)),
                    speed=float(row.get("speed", 0) or 0),
                    vwap_atr=float(row.get("vwap_atr", 0) or 0),
                    vix=float(row.get("vix", 0) or 0),
                    dxy=float(row.get("dxy", 0) or 0),
                    us10y=float(row.get("us10y", 0) or 0),
                    hy_spread=float(row.get("hy_spread", 0) or 0),
                    yield_curve=float(row.get("yield_curve", 0) or 0),
                    spy=float(row.get("spy", 0) or 0),
                    risk_score=float(row.get("risk_score", 0) or 0),
                    risk_regime=int(float(row.get("risk_regime", 0) or 0)),
                    news_impact=float(row.get("news_impact", 0) or 0),
                    score=float(row.get("score", 0) or 0),
                    confidence=float(row.get("confidence", 0) or 0),
                    fit_trend=float(row.get("fit_trend", 0) or 0),
                    fit_mr=float(row.get("fit_mr", 0) or 0),
                    fit_breakout=float(row.get("fit_breakout", 0) or 0),
                    fit_sbo=float(row.get("fit_sbo", 0) or 0),
                    fit_rbo=float(row.get("fit_rbo", 0) or 0),
                    fit_pb=float(row.get("fit_pb", 0) or 0),
                )
                rows.append(snap)
            except (ValueError, TypeError) as e:
                print(f"  [pular linha {i+2}] {e}")
                continue

    print(f"  -> {len(rows)} barras lidas de {path}")
    return rows


# ──────────────────────────────────────────────────────────────
# Análise
# ──────────────────────────────────────────────────────────────
def _media(vals):
    return sum(vals) / len(vals) if vals else 0.0


def _pct(vals, cond):
    return sum(1 for v in vals if cond(v)) / len(vals) * 100 if vals else 0.0


def analisar_regime(barras: List[BarSnapshot]):
    """fit_trend por regime de mercado (hurst + risk)."""
    print("\n" + "=" * 72)
    print("  1. FIT TREND POR REGIME DE MERCADO")
    print("=" * 72)

    # Regimes por Hurst (H)
    regimes_h = {"< 0.50 (mean-reverting)": [], "0.50-0.60 (fraca tendencia)": [],
                 "0.60-0.70 (tendencia media)": [], "> 0.70 (tendencia forte)": []}
    for b in barras:
        if b.H < 0.50:
            regimes_h["< 0.50 (mean-reverting)"].append(b.fit_trend)
        elif b.H < 0.60:
            regimes_h["0.50-0.60 (fraca tendencia)"].append(b.fit_trend)
        elif b.H < 0.70:
            regimes_h["0.60-0.70 (tendencia media)"].append(b.fit_trend)
        else:
            regimes_h["> 0.70 (tendencia forte)"].append(b.fit_trend)

    print(f"\n  {'Regime Hurst':<35} {'Media':>8} {'Min':>8} {'Max':>8} "
          f"{'% > threshold':>14} {'N':>6}")
    print("  " + "-" * 79)
    for nome, vals in regimes_h.items():
        if not vals:
            continue
        print(f"  {nome:<35} {_media(vals):>8.3f} {min(vals):>8.3f} {max(vals):>8.3f} "
              f"{_pct(vals, lambda x: x >= TREND_THRESHOLD):>13.1f}% {len(vals):>6}")

    # Regimes por risk_regime
    rr_on = [b.fit_trend for b in barras if b.risk_regime == 0]
    rr_off = [b.fit_trend for b in barras if b.risk_regime == 1]
    print(f"\n  {'Risk Regime':<35} {'Media':>8} {'Min':>8} {'Max':>8} "
          f"{'% > threshold':>14} {'N':>6}")
    print("  " + "-" * 79)
    for nome, vals in [("Risk ON", rr_on), ("Risk OFF", rr_off)]:
        if not vals:
            continue
        print(f"  {nome:<35} {_media(vals):>8.3f} {min(vals):>8.3f} {max(vals):>8.3f} "
              f"{_pct(vals, lambda x: x >= TREND_THRESHOLD):>13.1f}% {len(vals):>6}")


def analisar_slope(barras: List[BarSnapshot]):
    """fit_trend por faixas de slope."""
    print("\n" + "=" * 72)
    print("  2. FIT TREND POR INCLINACAO (SLOPE)")
    print("=" * 72)

    faixas = {"< -0.10 (forte queda)": [], "-0.10 a -0.03 (queda media)": [],
              "-0.03 a +0.03 (lateral)": [], "+0.03 a +0.10 (alta media)": [],
              "> +0.10 (forte alta)": []}
    for b in barras:
        if b.slope < -0.10:
            faixas["< -0.10 (forte queda)"].append(b.fit_trend)
        elif b.slope < -0.03:
            faixas["-0.10 a -0.03 (queda media)"].append(b.fit_trend)
        elif b.slope < 0.03:
            faixas["-0.03 a +0.03 (lateral)"].append(b.fit_trend)
        elif b.slope < 0.10:
            faixas["+0.03 a +0.10 (alta media)"].append(b.fit_trend)
        else:
            faixas["> +0.10 (forte alta)"].append(b.fit_trend)

    print(f"\n  {'Slope':<30} {'Media':>8} {'Min':>8} {'Max':>8} "
          f"{'% > threshold':>14} {'N':>6}")
    print("  " + "-" * 74)
    for nome, vals in faixas.items():
        if not vals:
            continue
        print(f"  {nome:<30} {_media(vals):>8.3f} {min(vals):>8.3f} {max(vals):>8.3f} "
              f"{_pct(vals, lambda x: x >= TREND_THRESHOLD):>13.1f}% {len(vals):>6}")


def analisar_vix(barras: List[BarSnapshot]):
    """fit_trend por faixas de VIX."""
    print("\n" + "=" * 72)
    print("  3. FIT TREND POR VIX (MEDO DO MERCADO)")
    print("=" * 72)

    faixas = {"< 15 (calmo)": [], "15-20 (normal)": [],
              "20-25 (elevado)": [], "> 25 (panico)": []}
    for b in barras:
        if b.vix < 15:
            faixas["< 15 (calmo)"].append(b.fit_trend)
        elif b.vix < 20:
            faixas["15-20 (normal)"].append(b.fit_trend)
        elif b.vix < 25:
            faixas["20-25 (elevado)"].append(b.fit_trend)
        else:
            faixas["> 25 (panico)"].append(b.fit_trend)

    print(f"\n  {'VIX':<22} {'Media':>8} {'Min':>8} {'Max':>8} "
          f"{'% > threshold':>14} {'N':>6}")
    print("  " + "-" * 66)
    for nome, vals in faixas.items():
        if not vals:
            continue
        print(f"  {nome:<22} {_media(vals):>8.3f} {min(vals):>8.3f} {max(vals):>8.3f} "
              f"{_pct(vals, lambda x: x >= TREND_THRESHOLD):>13.1f}% {len(vals):>6}")


def analisar_dxy(barras: List[BarSnapshot]):
    """fit_trend por faixas de DXY."""
    print("\n" + "=" * 72)
    print("  4. FIT TREND POR DXY (FORCA DO DOLAR)")
    print("=" * 72)

    faixas = {"< 98 (dolar fraco)": [], "98-102 (neutro)": [],
              "> 102 (dolar forte)": []}
    for b in barras:
        if b.dxy < 98:
            faixas["< 98 (dolar fraco)"].append(b.fit_trend)
        elif b.dxy < 102:
            faixas["98-102 (neutro)"].append(b.fit_trend)
        else:
            faixas["> 102 (dolar forte)"].append(b.fit_trend)

    print(f"\n  {'DXY':<22} {'Media':>8} {'Min':>8} {'Max':>8} "
          f"{'% > threshold':>14} {'N':>6}")
    print("  " + "-" * 66)
    for nome, vals in faixas.items():
        if not vals:
            continue
        print(f"  {nome:<22} {_media(vals):>8.3f} {min(vals):>8.3f} {max(vals):>8.3f} "
              f"{_pct(vals, lambda x: x >= TREND_THRESHOLD):>13.1f}% {len(vals):>6}")


def analisar_momentum(barras: List[BarSnapshot]):
    """fit_trend por estado de momentum."""
    print("\n" + "=" * 72)
    print("  5. FIT TREND POR MOMENTUM")
    print("=" * 72)

    grupos = {-1: [], 0: [], 1: [], 2: []}
    labels = {-1: "Desacelerando", 0: "Neutro", 1: "Acelerando", 2: "Muito forte"}
    for b in barras:
        if b.momentum in grupos:
            grupos[b.momentum].append(b.fit_trend)

    print(f"\n  {'Momentum':<20} {'Media':>8} {'Min':>8} {'Max':>8} "
          f"{'% > threshold':>14} {'N':>6}")
    print("  " + "-" * 64)
    for key in sorted(grupos):
        vals = grupos[key]
        if not vals:
            continue
        print(f"  {labels[key]:<20} {_media(vals):>8.3f} {min(vals):>8.3f} {max(vals):>8.3f} "
              f"{_pct(vals, lambda x: x >= TREND_THRESHOLD):>13.1f}% {len(vals):>6}")


def analisar_direction(barras: List[BarSnapshot]):
    """fit_trend por direcao (up/down)."""
    print("\n" + "=" * 72)
    print("  6. FIT TREND POR DIRECAO DO REGIME")
    print("=" * 72)

    up = [b.fit_trend for b in barras if b.direction == 1]
    dn = [b.fit_trend for b in barras if b.direction == -1]

    print(f"\n  {'Direcao':<20} {'Media':>8} {'Min':>8} {'Max':>8} "
          f"{'% > threshold':>14} {'N':>6}")
    print("  " + "-" * 64)
    for nome, vals in [("Alta (direction=1)", up), ("Queda (direction=-1)", dn)]:
        if not vals:
            continue
        print(f"  {nome:<20} {_media(vals):>8.3f} {min(vals):>8.3f} {max(vals):>8.3f} "
              f"{_pct(vals, lambda x: x >= TREND_THRESHOLD):>13.1f}% {len(vals):>6}")


def analisar_fit_score(barras: List[BarSnapshot]):
    """Comparacao dos fit scores entre estrategias."""
    print("\n" + "=" * 72)
    print("  7. COMPARACAO: FIT SCORE MEDIO POR ESTRATEGIA")
    print("=" * 72)

    fits = {
        "Trend Following": [b.fit_trend for b in barras],
        "Mean Reversion":  [b.fit_mr for b in barras],
        "Breakout":         [b.fit_breakout for b in barras],
        "Session Breakout": [b.fit_sbo for b in barras],
        "Range Breakout":   [b.fit_rbo for b in barras],
        "Pullback":         [b.fit_pb for b in barras],
    }

    print(f"\n  {'Estrategia':<22} {'Media':>8} {'Min':>8} {'Max':>8} "
          f"{'% > threshold':>14} {'N':>6}")
    print("  " + "-" * 66)
    for nome, vals in fits.items():
        if not vals:
            continue
        print(f"  {nome:<22} {_media(vals):>8.3f} {min(vals):>8.3f} {max(vals):>8.3f} "
              f"{_pct(vals, lambda x: x >= TREND_THRESHOLD):>13.1f}% {len(vals):>6}")


def analisar_combined(barras: List[BarSnapshot]):
    """Analise combinada: cenarios onde Trend e mais forte vs outras."""
    print("\n" + "=" * 72)
    print("  8. CENARIOS: ONDE TREND DOMINA VS OUTRAS")
    print("=" * 72)

    # Cenarios onde trend ganha de todas as outras
    trend_winner = [b for b in barras
                    if b.fit_trend >= TREND_THRESHOLD
                    and b.fit_trend >= b.fit_mr
                    and b.fit_trend >= b.fit_breakout
                    and b.fit_trend >= b.fit_sbo
                    and b.fit_trend >= b.fit_rbo
                    and b.fit_trend >= b.fit_pb]

    # Cenarios onde trend perde
    trend_loser = [b for b in barras
                   if b.fit_trend < TREND_THRESHOLD]

    print(f"\n  Barras onde Trend domina: {len(trend_winner)} / {len(barras)} "
          f"({len(trend_winner)/len(barras)*100:.1f}%)")
    if trend_winner:
        print(f"  Regime medio H: {_media([b.H for b in trend_winner]):.3f}")
        print(f"  Slope medio:     {_media([b.slope for b in trend_winner]):.3f}")
        print(f"  VIX medio:       {_media([b.vix for b in trend_winner]):.1f}")
        print(f"  DXY medio:       {_media([b.dxy for b in trend_winner]):.1f}")

    print(f"\n  Barras onde Trend fica < threshold: {len(trend_loser)} / {len(barras)} "
          f"({len(trend_loser)/len(barras)*100:.1f}%)")
    if trend_loser:
        print(f"  Regime medio H: {_media([b.H for b in trend_loser]):.3f}")
        print(f"  Slope medio:     {_media([b.slope for b in trend_loser]):.3f}")
        print(f"  VIX medio:       {_media([b.vix for b in trend_loser]):.1f}")
        print(f"  DXY medio:       {_media([b.dxy for b in trend_loser]):.1f}")


def recomendar_ajustes(barras: List[BarSnapshot]):
    """Recomendacoes de ajuste baseadas nos dados."""
    print("\n" + "=" * 72)
    print("  9. RECOMENDACOES DE AJUSTE")
    print("=" * 72)

    # Analisar threshold ideal
    pcts = {}
    for t in [x / 100 for x in range(20, 81, 5)]:
        ok = _pct(barras, lambda b: b.fit_trend >= t)
        pcts[t] = ok

    print(f"\n  Cobertura do threshold atual ({TREND_THRESHOLD:.0%}): "
          f"{pcts.get(TREND_THRESHOLD, 0):.1f}% das barras")
    print(f"\n  Sensibilidade do threshold:")
    print(f"  {'Threshold':>10} {'% Barras Elegiveis':>20}")
    print("  " + "-" * 32)
    for t, p in sorted(pcts.items()):
        marker = " <<< ATUAL" if abs(t - TREND_THRESHOLD) < 0.001 else ""
        print(f"  {t:>8.0%} {p:>18.1f}%{marker}")

    # Sugestoes
    print(f"\n  --- Sugestoes ---")

    # Melhor H para trend
    h_trend = [b.H for b in barras if b.fit_trend >= TREND_THRESHOLD]
    h_notrend = [b.H for b in barras if b.fit_trend < TREND_THRESHOLD]
    if h_trend and h_notrend:
        print(f"  * Regime H ideal: media {_media(h_trend):.3f} "
              f"(vs {_media(h_notrend):.3f} quando abaixo do threshold)")

    # Melhor slope para trend
    s_trend = [b.slope for b in barras if b.fit_trend >= TREND_THRESHOLD]
    s_notrend = [b.slope for b in barras if b.fit_trend < TREND_THRESHOLD]
    if s_trend and s_notrend:
        print(f"  * Slope ideal: media {_media(s_trend):.3f} "
              f"(vs {_media(s_notrend):.3f} quando abaixo do threshold)")

    # VIX threshold
    vix_trend = [b.vix for b in barras if b.fit_trend >= TREND_THRESHOLD]
    vix_notrend = [b.vix for b in barras if b.fit_trend < TREND_THRESHOLD]
    if vix_trend and vix_notrend:
        print(f"  * VIX ideal: media {_media(vix_trend):.1f} "
              f"(vs {_media(vix_notrend):.1f} quando abaixo do threshold)")


# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────
def main():
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    print(f"Analise TrendFollowing — CSV: {path}")

    if not os.path.isfile(path):
        print(f"ERRO: arquivo nao encontrado: {path}")
        sys.exit(1)

    barras = ler_csv(path)
    if not barras:
        print("Nenhuma barra valida para analise.")
        return

    print(f"Periodo: {barras[0].date} a {barras[-1].date}")
    print(f"Janela: {len(barras)} barras")

    # fit_trend global
    fit_all = [b.fit_trend for b in barras]
    print(f"\n  fit_trend global: media={_media(fit_all):.3f} "
          f"min={min(fit_all):.3f} max={max(fit_all):.3f}")

    analisar_regime(barras)
    analisar_slope(barras)
    analisar_vix(barras)
    analisar_dxy(barras)
    analisar_momentum(barras)
    analisar_direction(barras)
    analisar_fit_score(barras)
    analisar_combined(barras)
    recomendar_ajustes(barras)

    print("\n" + "=" * 72)
    print("  FIM")
    print("=" * 72)


if __name__ == "__main__":
    main()

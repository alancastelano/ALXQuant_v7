"""
RiskSentiment — Risk-On / Risk-Off quantitative indicator.

Inspired by RORO (Risk-On Risk-Off) academic literature.
Builds a consolidated RiskSentiment.csv dataset with global_risk_score, risk_label,
and sub-indices via PCA/z-score aggregation.

Output: data/processed/RiskSentiment.csv
Cache:  data/DataHouse/cache/<SYMBOL>_<SOURCE>.csv  (incremental per series)
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf
from fredapi import Fred
from sklearn.decomposition import PCA
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import config

# ─── Logging ──────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("RiskSentiment")

# ─── Asset catalog ────────────────────────────────────────────────────
ASSETS = [
    # Volatility
    {"symbol": "VIXCLS",      "description": "CBOE VIX",             "source": "FRED",     "category": "VOLATILITY"},
    # Credit
    {"symbol": "BAMLH0A0HYM2", "description": "HY Spread (OAS)",    "source": "FRED",     "category": "CREDIT"},
    {"symbol": "BAMLC0A4CBBB", "description": "IG Spread BBB (OAS)", "source": "FRED",    "category": "CREDIT"},
    # Liquidity / Rates
    {"symbol": "SOFR",         "description": "SOFR Rate",           "source": "FRED",     "category": "LIQUIDITY"},
    {"symbol": "TEDRATE",      "description": "TED Spread",          "source": "FRED",     "category": "LIQUIDITY"},
    {"symbol": "DGS2",         "description": "US 2Y Yield",         "source": "FRED",     "category": "LIQUIDITY"},
    {"symbol": "DGS10",        "description": "US 10Y Yield",        "source": "FRED",     "category": "LIQUIDITY"},
    # Currencies
    {"symbol": "EURUSD=X",     "description": "EUR/USD",             "source": "YFINANCE", "category": "CURRENCY"},
    {"symbol": "JPY=X",        "description": "USD/JPY",             "source": "YFINANCE", "category": "CURRENCY"},
    {"symbol": "DX-Y.NYB",     "description": "US Dollar Index",     "source": "YFINANCE", "category": "CURRENCY"},
    # Commodities
    {"symbol": "GOLDAMGBD228NLBM", "description": "Gold Fixing (LBMA)", "source": "FRED", "category": "COMMODITY"},
    {"symbol": "GLD",          "description": "Gold ETF",            "source": "YFINANCE", "category": "COMMODITY"},
    {"symbol": "CL=F",         "description": "Crude Oil Futures",   "source": "YFINANCE", "category": "COMMODITY"},
    {"symbol": "USO",          "description": "Oil ETF",             "source": "YFINANCE", "category": "COMMODITY"},
    # Equity
    {"symbol": "SPY",          "description": "S&P 500 ETF",         "source": "YFINANCE", "category": "EQUITY"},
    {"symbol": "QQQ",          "description": "Nasdaq 100 ETF",      "source": "YFINANCE", "category": "EQUITY"},
    {"symbol": "ACWI",         "description": "Global Equity ETF",   "source": "YFINANCE", "category": "EQUITY"},
    # Crypto (extra — referenced in output spec)
    {"symbol": "BTC-USD",      "description": "Bitcoin USD",         "source": "YFINANCE", "category": "EQUITY"},
]

# Mapping from internal column names to the final CSV columns
OUTPUT_COLUMNS = [
    "date", "global_risk_score", "risk_label",
    "credit_score", "equity_score", "liquidity_score", "currency_score",
    "vix", "yield_2y", "yield_10y", "spread_10_2",
    "eur_usd", "usd_index", "oil_wti",
    "spy", "qqq", "gld", "btc", "hy_spread",
]

CACHE_DIR = Path(__file__).resolve().parents[1] / "cache"
OUTPUT_PATH = Path(config.processed_dir) / "RiskSentiment.csv"

FIELD_MAP = {
    "vix":      {"symbol": "VIXCLS",      "transform": "raw"},
    "yield_2y": {"symbol": "DGS2",        "transform": "raw"},
    "yield_10y":{"symbol": "DGS10",       "transform": "raw"},
    "spread_10_2": {"symbol": None,       "transform": "diff", "a": "DGS10", "b": "DGS2"},
    "eur_usd":  {"symbol": "EURUSD=X",    "transform": "raw"},
    "usd_index":{"symbol": "DX-Y.NYB",    "transform": "raw"},
    "oil_wti":  {"symbol": "CL=F",        "transform": "raw"},
    "spy":      {"symbol": "SPY",         "transform": "raw"},
    "qqq":      {"symbol": "QQQ",         "transform": "raw"},
    "gld":      {"symbol": "GLD",         "transform": "raw"},
    "btc":      {"symbol": "BTC-USD",     "transform": "raw"},
    "hy_spread":{"symbol": "BAMLH0A0HYM2","transform": "raw"},
}

# Sign direction: +1 means "higher value = risk-off", -1 means "higher value = risk-on"
SIGN_DIRECTION = {
    "VIXCLS":      1,  # higher VIX = risk-off
    "BAMLH0A0HYM2":1,  # higher spreads = risk-off
    "BAMLC0A4CBBB":1,  # higher spreads = risk-off
    "SOFR":        1,  # higher rates = risk-off
    "TEDRATE":     1,  # higher TED = risk-off
    "DGS2":        1,  # higher yields = risk-off
    "DGS10":       1,  # higher yields = risk-off
    "EURUSD=X":   -1,  # stronger EUR = risk-on
    "JPY=X":       1,  # stronger JPY = risk-off (safe haven)
    "DX-Y.NYB":    1,  # stronger USD = risk-off
    "GOLDAMGBD228NLBM": 1,  # higher gold = risk-off (safe haven)
    "GLD":         1,  # higher gold = risk-off
    "CL=F":       -1,  # higher oil = risk-on (growth)
    "USO":        -1,  # higher oil = risk-on
    "SPY":        -1,  # higher equities = risk-on
    "QQQ":        -1,  # higher equities = risk-on
    "ACWI":       -1,  # higher equities = risk-on
    "BTC-USD":    -1,  # higher crypto = risk-on
}

CATEGORY_MAP = {}
for a in ASSETS:
    CATEGORY_MAP[a["symbol"]] = a["category"]


# ═══════════════════════════════════════════════════════════════════════
#  DataManager — incremental fetch + local cache
# ═══════════════════════════════════════════════════════════════════════

class DataManager:
    """Incremental data fetcher: full history on first run, append after."""

    def __init__(self, fred_api_key: str):
        self.fred = Fred(api_key=fred_api_key) if fred_api_key else None
        self._ensure_cache_dir()

    @staticmethod
    def _ensure_cache_dir():
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _cache_path(symbol: str, source: str) -> Path:
        return CACHE_DIR / f"{symbol}_{source}.csv"

    def fetch_or_update(self, asset: dict, start: str = "2000-01-01") -> pd.Series:
        """Return a daily pd.Series (name=symbol) updated to present."""
        symbol = asset["symbol"]
        source = asset["source"]
        cache = self._cache_path(symbol, source)

        if cache.exists():
            existing = pd.read_csv(cache, parse_dates=["date"], index_col="date")
            existing = existing[~existing.index.duplicated(keep="last")]
            last_date = existing.index.max()
            new_data = self._fetch_new(asset, last_date)
            if new_data is not None and not new_data.empty:
                combined = pd.concat([existing["value"], new_data])
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                combined.to_csv(cache, header=True)
                log.info("  %-20s updated (%s -> %s)", symbol,
                         last_date.date(), combined.index.max().date())
                return combined
            log.info("  %-20s up to date (%s)", symbol, last_date.date())
            return existing["value"]
        else:
            data = self._fetch_full(asset, start)
            if data is None or data.empty:
                log.warning("  %-20s no data fetched", symbol)
                return pd.Series(dtype=float, name=symbol)
            df = data.to_frame(name="value")
            df.index.name = "date"
            df.to_csv(cache)
            log.info("  %-20s cached (%s -> %s)", symbol,
                     df.index.min().date(), df.index.max().date())
            return data

    def _fetch_full(self, asset: dict, start: str) -> Optional[pd.Series]:
        source = asset["source"]
        symbol = asset["symbol"]
        if source == "FRED":
            return self._fred_fetch(symbol, start)
        elif source == "YFINANCE":
            return self._yf_fetch(symbol, start)
        return None

    def _fetch_new(self, asset: dict, last_date: datetime) -> Optional[pd.Series]:
        start = (last_date + timedelta(days=1)).strftime("%Y-%m-%d")
        if start >= datetime.now().strftime("%Y-%m-%d"):
            return None
        return self._fetch_full(asset, start)

    def _fred_fetch(self, symbol: str, start: str) -> Optional[pd.Series]:
        if self.fred is None:
            log.warning("FRED API key not set, skipping %s", symbol)
            return None
        try:
            data = self.fred.get_series(symbol, observation_start=start)
            s = pd.Series(data.values, index=pd.to_datetime(data.index), name=symbol)
            return s.resample("D").last().ffill()
        except Exception as e:
            log.warning("FRED %s: %s", symbol, e)
            return None

    def _yf_fetch(self, symbol: str, start: str) -> Optional[pd.Series]:
        try:
            df = yf.download(symbol, start=start, progress=False, auto_adjust=True)
            if df.empty:
                return None
            close = df["Close"].squeeze()
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close.name = symbol
            return close.resample("D").last().ffill()
        except Exception as e:
            log.warning("YF %s: %s", symbol, e)
            return None


# ═══════════════════════════════════════════════════════════════════════
#  FeatureEngine — z-scores, sign alignment
# ═══════════════════════════════════════════════════════════════════════

class FeatureEngine:
    """Compute z-scores and sign-align all series."""

    def __init__(self, window: int = 60):
        self.window = window

    def compute(self, raw: pd.DataFrame) -> pd.DataFrame:
        """Return DataFrame of sign-aligned z-scores, same index as raw."""
        aligned = raw.copy()
        for col in aligned.columns:
            sym = col
            direction = SIGN_DIRECTION.get(sym, 1)
            # Expand window z-score
            aligned[col] = (
                aligned[col]
                .rolling(self.window, min_periods=10)
                .apply(lambda x: (x.iloc[-1] - x.mean()) / x.std() if x.std() > 1e-10 else 0.0, raw=False)
            )
            aligned[col] = aligned[col] * direction  # positive = risk-off
        return aligned.dropna(how="all")


# ═══════════════════════════════════════════════════════════════════════
#  SubIndexBuilder — category-level aggregation
# ═══════════════════════════════════════════════════════════════════════

class SubIndexBuilder:
    """Aggregate z-scored series by category (PCA or mean z-score)."""

    def __init__(self, method: str = "pca"):
        self.method = method

    def build(self, z: pd.DataFrame, categories: dict) -> pd.DataFrame:
        """Return DataFrame with columns: credit_score, equity_score, liquidity_score, currency_score."""
        cat_map = {
            "credit_score":   ["CREDIT"],
            "equity_score":   ["EQUITY"],
            "liquidity_score": ["LIQUIDITY"],
            "currency_score": ["CURRENCY"],
        }
        scores = pd.DataFrame(index=z.index)
        for score_name, cats in cat_map.items():
            cols = [c for c in z.columns if categories.get(c) in cats]
            if not cols:
                scores[score_name] = 0.0
                continue
            subset = z[cols].dropna(how="all")
            if subset.empty:
                scores[score_name] = 0.0
                continue
            subset = subset.fillna(0)
            if self.method == "pca" and subset.shape[1] > 1 and subset.shape[0] > 5:
                try:
                    pca = PCA(n_components=1)
                    pc = pca.fit_predict(subset)
                    scores[score_name] = pd.Series(pc.flatten(), index=subset.index)
                except Exception:
                    scores[score_name] = subset.mean(axis=1)
            else:
                scores[score_name] = subset.mean(axis=1)
        return scores


# ═══════════════════════════════════════════════════════════════════════
#  GlobalRiskScorer — PCA global + label
# ═══════════════════════════════════════════════════════════════════════

class GlobalRiskScorer:
    """Global PCA z-score + risk label."""

    def compute(self, z: pd.DataFrame, sub_scores: pd.DataFrame) -> pd.DataFrame:
        """Return DataFrame with global_risk_score, risk_label."""
        all_features = pd.concat([z, sub_scores], axis=1).dropna(how="all").fillna(0)
        if all_features.shape[1] < 2 or all_features.shape[0] < 5:
            result = pd.DataFrame(index=all_features.index)
            result["global_risk_score"] = 0.0
            result["risk_label"] = "NEUTRAL"
            return result

        try:
            pca = PCA(n_components=1)
            pc = pca.fit_predict(all_features)
            score = pd.Series(pc.flatten(), index=all_features.index, name="global_risk_score")
        except Exception:
            score = all_features.mean(axis=1)
            score.name = "global_risk_score"

        # Normalize z-score
        mean = score.mean()
        std = score.std()
        if std > 1e-10:
            score = (score - mean) / std
        else:
            score = pd.Series(0.0, index=score.index)

        def _label(v):
            if v >= 1.5:
                return "EXTREME_RISK_OFF"
            if v >= 0.75:
                return "RISK_OFF"
            if v <= -0.75:
                return "RISK_ON"
            return "NEUTRAL"

        labels = score.map(_label)
        result = pd.DataFrame({"global_risk_score": score, "risk_label": labels}, index=score.index)
        return result


# ═══════════════════════════════════════════════════════════════════════
#  Main orchestrator
# ═══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    log.info("=" * 60)
    log.info("RiskSentiment — inicio")

    # 1. Fetch / update all assets
    dm = DataManager(config.fred_api_key)
    raw_series = {}
    for asset in tqdm(ASSETS, desc="Fetching assets"):
        s = dm.fetch_or_update(asset)
        if s is not None and not s.empty:
            raw_series[asset["symbol"]] = s

    if not raw_series:
        log.error("Nenhum ativo baixado.")
        return

    raw = pd.DataFrame(raw_series).ffill(limit=5)
    log.info("Raw data: %d series x %d rows", raw.shape[1], raw.shape[0])

    # 2. Feature engineering
    fe = FeatureEngine(window=60)
    z = fe.compute(raw)

    # 3. Build category lookup
    cat_lookup = {a["symbol"]: a["category"] for a in ASSETS}

    # 4. Sub-indices
    sb = SubIndexBuilder(method="pca")
    sub = sb.build(z, cat_lookup)

    # 5. Global score
    gs = GlobalRiskScorer()
    global_df = gs.compute(z, sub)

    # 6. Assemble output columns
    out = pd.DataFrame(index=global_df.index)
    out["date"] = out.index.strftime("%Y-%m-%d")
    out["global_risk_score"] = global_df["global_risk_score"]
    out["risk_label"] = global_df["risk_label"]
    for col_name, cinfo in FIELD_MAP.items():
        if cinfo["transform"] == "raw":
            sym = cinfo["symbol"]
            if sym in raw:
                out[col_name] = raw[sym]
            else:
                out[col_name] = np.nan
        elif cinfo["transform"] == "diff":
            a = cinfo.get("a")
            b = cinfo.get("b")
            if a in raw and b in raw:
                diff = raw[a] - raw[b]
                out[col_name] = diff
            else:
                out[col_name] = np.nan

    # Add sub-scores
    for col in ["credit_score", "equity_score", "liquidity_score", "currency_score"]:
        if col in sub:
            out[col] = sub[col]
        else:
            out[col] = 0.0

    out = out.reset_index(drop=True)
    out = out[OUTPUT_COLUMNS]

    # 7. Save
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUTPUT_PATH, index=False)
    log.info("Salvo: %s  (%d linhas)", OUTPUT_PATH, len(out))
    log.info("Labels: %s", out["risk_label"].value_counts().to_dict())
    log.info("Tempo total: %.1fs", time.time() - t0)


if __name__ == "__main__":
    main()

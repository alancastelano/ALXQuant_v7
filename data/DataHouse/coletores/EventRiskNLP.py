"""
EventRiskNLP — Crisis detection & multi-asset risk scoring for quantitative trading.

Detects extraordinary events (war, crisis, supply shocks), analyzes economic causality
per asset (XAUUSD, EURUSD, CRUDE, SPY, US30, NASDAQ), and outputs a binary STOP/NEUTRO
signal with expiration.

Outputs:
  data/processed/EventRisk.csv         — per-asset risk scores for MQL5
  data/processed/EventRiskEvents.json  — current event detail
  data/processed/EventRiskHistory.csv  — all detected events (append)
  logs/eventrisk.log                   — processing log

Standalone: python EventRiskNLP.py
"""

import hashlib
import json
import logging
import os
import re
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import feedparser
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import config

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# ─── Paths ──────────────────────────────────────────────────────────────────
NEWS_DIR = PROJECT_ROOT / "data" / "news"
NEWS_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED = Path(config.processed_dir)
PROCESSED.mkdir(parents=True, exist_ok=True)

EVENT_OUTPUT_CSV = PROCESSED / "EventRisk.csv"
EVENT_OUTPUT_JSON = PROCESSED / "EventRiskEvents.json"
EVENT_HISTORY_CSV = PROCESSED / "EventRiskHistory.csv"

# ─── Logging ────────────────────────────────────────────────────────────────
log = logging.getLogger("EventRiskNLP")


def _setup_logging():
    if log.handlers:
        return
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(logs_dir / "eventrisk.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    log.addHandler(ch)
    log.setLevel(logging.INFO)


# ═══════════════════════════════════════════════════════════════════════════════
#  CRISIS KEYWORDS — Tier 1 (critical), Tier 2 (significant), Tier 3 (normal)
# ═══════════════════════════════════════════════════════════════════════════════

CRISIS_KEYWORDS_T1 = {
    "nuclear": 0.98, "war": 0.95, "invasion": 0.95, "missile": 0.92,
    "terrorist attack": 0.92, "military strike": 0.90, "explosion": 0.85,
    "collapse": 0.92, "default": 0.88, "bankruptcy": 0.82,
    "emergency": 0.78, "state of emergency": 0.85, "circuit breaker": 0.82,
    "contagion": 0.80, "systemic": 0.78, "meltdown": 0.90, "crash": 0.80,
}

CRISIS_KEYWORDS_T2 = {
    "sanctions": 0.72, "blockade": 0.78, "cutoff": 0.72,
    "retaliation": 0.75, "escalation": 0.72, "threat": 0.58,
    "crisis": 0.68, "conflict": 0.65, "tension": 0.58,
    "supply shock": 0.78, "shortage": 0.65, "shortfall": 0.62,
    "protest": 0.48, "riot": 0.55, "unrest": 0.52,
    "freeze": 0.60, "seize": 0.65, "confiscate": 0.62,
    "stress test": 0.45, "downgrade": 0.55, "negative outlook": 0.50,
    "humanitarian": 0.40,
}

CRISIS_KEYWORDS_T3 = {
    "fomc": 0.30, "fed": 0.25, "interest rate": 0.25,
    "nfp": 0.22, "cpi": 0.22, "inflation": 0.30,
    "gdp": 0.18, "recession": 0.55,
    "election": 0.35, "forecast": 0.15, "outlook": 0.15,
    "speech": 0.12, "testimony": 0.15,
}

KEYWORD_TO_EVENT_TYPE = {
    # Geopolitical / War
    "war": "geopolitical_conflict", "nuclear": "geopolitical_conflict",
    "invasion": "geopolitical_conflict", "missile": "geopolitical_conflict",
    "military strike": "geopolitical_conflict", "terrorist": "geopolitical_conflict",
    "attack": "geopolitical_conflict", "conflict": "geopolitical_conflict",
    "tension": "geopolitical_conflict", "retaliation": "geopolitical_conflict",
    "escalation": "geopolitical_conflict",

    # Oil / Energy supply
    "oil": "oil_supply_shock", "crude": "oil_supply_shock",
    "opec": "oil_supply_shock", "refinery": "oil_supply_shock",
    "petroleum": "oil_supply_shock", "blockade": "oil_supply_shock",
    "supply shock": "oil_supply_shock", "energy crisis": "oil_supply_shock",
    "gasoline": "oil_supply_shock",

    # Financial crisis
    "collapse": "financial_crisis", "default": "financial_crisis",
    "bankruptcy": "financial_crisis", "bailout": "financial_crisis",
    "contagion": "financial_crisis", "meltdown": "financial_crisis",
    "systemic": "financial_crisis", "liquidity crisis": "financial_crisis",
    "credit crisis": "financial_crisis", "crash": "financial_crisis",

    # Monetary policy
    "fed": "monetary_policy", "fomc": "monetary_policy",
    "interest rate": "monetary_policy", "powell": "monetary_policy",
    "rate hike": "monetary_policy", "rate cut": "monetary_policy",

    # Recession
    "recession": "recession", "slowdown": "recession",
    "contraction": "recession",

    # Natural disaster
    "hurricane": "natural_disaster", "earthquake": "natural_disaster",
    "tsunami": "natural_disaster", "flood": "natural_disaster",
    "wildfire": "natural_disaster",
}

# ═══════════════════════════════════════════════════════════════════════════════
#  ASSET IMPACT RULES — causalidade económica por ativo
# ═══════════════════════════════════════════════════════════════════════════════

ASSET_IMPACT_RULES = {
    "XAUUSD": {
        "geopolitical_conflict": {"direction": "up",  "weight": 0.75, "reason": "safe haven clássico — guerra eleva demanda por ouro"},
        "oil_supply_shock":      {"direction": "down","weight": 0.82, "reason": "petróleo ↑ → dólar forte → ouro ↓ (commodities priced in USD)"},
        "financial_crisis":      {"direction": "up",  "weight": 0.88, "reason": "ultimate safe haven — colapso sistêmico eleva ouro"},
        "monetary_policy":       {"direction": "up",  "weight": 0.55, "reason": "depende do teor — corte de juros é positivo"},
        "recession":             {"direction": "up",  "weight": 0.50, "reason": "recessão leva a cortes de juros → ouro sobe"},
        "natural_disaster":      {"direction": "up",  "weight": 0.35, "reason": "impacto moderado, pode gerar incerteza"},
    },
    "EURUSD": {
        "geopolitical_conflict": {"direction": "down","weight": 0.82, "reason": "risk-off — USD like safe haven sobre EUR"},
        "oil_supply_shock":      {"direction": "down","weight": 0.78, "reason": "Europa importa petróleo → impacto maior que US"},
        "financial_crisis":      {"direction": "down","weight": 0.85, "reason": "flight to USD liquidity"},
        "monetary_policy":       {"direction": "up",  "weight": 0.50, "reason": "Fed dovish → EUR sobe"},
        "recession":             {"direction": "up",  "weight": 0.60, "reason": "US recession → dólar fraco → EUR sobe"},
    },
    "CL=F": {
        "geopolitical_conflict": {"direction": "up",  "weight": 0.92, "reason": "Oriente Médio em risco = prêmio de risco no petróleo"},
        "oil_supply_shock":      {"direction": "up",  "weight": 0.95, "reason": "choque direto de oferta"},
        "financial_crisis":      {"direction": "down","weight": 0.65, "reason": "destruição de demanda domina"},
        "monetary_policy":       {"direction": "down","weight": 0.40, "reason": "juros altos reduzem demanda"},
        "recession":             {"direction": "down","weight": 0.72, "reason": "demanda cai em recessão"},
        "natural_disaster":      {"direction": "up",  "weight": 0.55, "reason": "furacão no Golfo = produção afetada"},
    },
    "SPY": {
        "geopolitical_conflict": {"direction": "down","weight": 0.50, "reason": "impacto moderado — defesa compensa parcialmente"},
        "oil_supply_shock":      {"direction": "down","weight": 0.55, "reason": "custo energia sobe, margens apertam"},
        "financial_crisis":      {"direction": "down","weight": 0.88, "reason": "risco sistêmico derruba equities"},
        "monetary_policy":       {"direction": "down","weight": 0.40, "reason": "hawkish = negativo para equities"},
        "recession":             {"direction": "down","weight": 0.75, "reason": "lucros caem em recessão"},
    },
    "US30": {
        "geopolitical_conflict": {"direction": "down","weight": 0.45, "reason": "Dow tem composição defensiva parcial"},
        "oil_supply_shock":      {"direction": "down","weight": 0.50, "reason": "industriais sofrem com energia cara"},
        "financial_crisis":      {"direction": "down","weight": 0.82, "reason": "sistêmico afeta todos os setores"},
        "recession":             {"direction": "down","weight": 0.72, "reason": "cíclicas caem"},
    },
    "NASDAQ": {
        "geopolitical_conflict": {"direction": "down","weight": 0.40, "reason": "tech menos sensível a geopolítica"},
        "oil_supply_shock":      {"direction": "down","weight": 0.35, "reason": "big tech consome energia mas margem alta absorve"},
        "financial_crisis":      {"direction": "down","weight": 0.85, "reason": "flight from risk assets"},
        "monetary_policy":       {"direction": "down","weight": 0.60, "reason": "juros altos penalizam growth stocks"},
        "recession":             {"direction": "down","weight": 0.65, "reason": "publicidade e consumo caem"},
    },
}

TRACKED_SYMBOLS = list(ASSET_IMPACT_RULES.keys())

# Source credibility weights
SOURCE_CREDIBILITY = {
    "Reuters": 0.95, "Bloomberg": 0.95, "Marketaux": 0.85,
    "ActionForex": 0.80, "OilPrice": 0.80, "Mining": 0.75,
    "GoogleNews": 0.70, "FedSpeeches": 0.90, "ECB": 0.90,
}

# ─── Google News RSS (crisis queries) ───────────────────────────────────────
CRISIS_RSS_QUERIES = [
    "gold market crisis OR war OR geopolitical",
    "crude oil supply shock OR conflict OR sanctions",
    "market crash OR recession OR financial crisis",
    "dollar surge OR safe haven OR risk off",
]

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"


# ═══════════════════════════════════════════════════════════════════════════════
#  CrisisConfig
# ═══════════════════════════════════════════════════════════════════════════════

class CrisisConfig:
    API_TIMEOUT: int = 15
    MAX_ARTICLES_PER_SOURCE: int = 30
    EVENT_VALIDITY_HOURS_DEFAULT: int = 6
    TIER1_VALIDITY_HOURS: int = 24
    TIER2_VALIDITY_HOURS: int = 12
    TIER3_VALIDITY_HOURS: int = 4
    STOP_THRESHOLD: float = 85.0
    CAUTION_THRESHOLD: float = 70.0
    MONITOR_THRESHOLD: float = 50.0


# ═══════════════════════════════════════════════════════════════════════════════
#  NewsCollector — RSS + Google News + Marketaux
# ═══════════════════════════════════════════════════════════════════════════════

class NewsCollector:
    def __init__(self, cfg: CrisisConfig):
        self.cfg = cfg

    def collect(self, since: Optional[datetime] = None) -> list:
        articles = []
        # Standard RSS feeds
        for name, url in [
            ("ActionForex", "https://www.actionforex.com/feed/"),
            ("OilPrice", "https://oilprice.com/rss/main"),
            ("Mining", "https://www.mining.com/feed/"),
        ]:
            try:
                items = self._parse_rss(name, url, since)
                articles.extend(items)
                log.info("  RSS %-15s -> %d articles", name, len(items))
            except Exception as e:
                log.warning("  RSS %s failed: %s", name, e)

        # Google News RSS — crisis-specific queries
        for q in CRISIS_RSS_QUERIES:
            try:
                url = GOOGLE_NEWS_RSS.format(q=q.replace(" ", "%20"))
                items = self._parse_rss("GoogleNews", url, since, max_items=10)
                articles.extend(items)
            except Exception as e:
                log.warning("  GoogleNews query '%s': %s", q[:30], e)

        # Marketaux (if key available)
        api_key = os.getenv("NEWS_API_KEY", "")
        if api_key:
            try:
                items = self._fetch_marketaux(api_key, since)
                articles.extend(items)
                log.info("  Marketaux -> %d articles", len(items))
            except Exception as e:
                log.warning("  Marketaux: %s", e)

        return articles

    def _parse_rss(self, source: str, url: str, since: Optional[datetime],
                   max_items: int = 30) -> list:
        feed = feedparser.parse(url, agent="Mozilla/5.0 (compatible; ALXQuant/1.0)")
        if not feed.entries:
            return []
        items = []
        for entry in feed.entries[:max_items]:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])
            if published is None:
                published = datetime.now()
            if since is not None and published < since:
                continue
            title = (entry.get("title") or "").strip()
            if not title:
                continue
            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary.strip()
            elif hasattr(entry, "description"):
                summary = entry.description.strip()
            summary = re.sub(r"<[^>]+>", "", summary)

            items.append({
                "date": published.strftime("%Y-%m-%d %H:%M:%S"),
                "source": source,
                "title": title,
                "summary": summary[:2000],
                "url": entry.get("link", ""),
            })
        return items

    def _fetch_marketaux(self, api_key: str, since: Optional[datetime]) -> list:
        after = (since.strftime("%Y-%m-%d") if since else "2024-01-01")
        symbols = ",".join(TRACKED_SYMBOLS)
        params = {
            "api_token": api_key, "limit": 50,
            "published_after": after, "sort": "published_desc",
            "language": "en", "symbols": symbols,
        }
        resp = requests.get("https://api.marketaux.com/v1/news/all",
                            params=params, timeout=self.cfg.API_TIMEOUT)
        if resp.status_code != 200:
            return []
        data = resp.json()
        items = []
        for item in data.get("data", []):
            title = (item.get("title") or "").strip()
            if not title:
                continue
            desc = (item.get("description") or "").strip()
            pub = item.get("published_at", "")
            try:
                dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            except Exception:
                dt = datetime.now()
            items.append({
                "date": dt.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "Marketaux",
                "title": title,
                "summary": (desc or item.get("snippet", ""))[:2000],
                "url": item.get("url", ""),
            })
        return items


# ═══════════════════════════════════════════════════════════════════════════════
#  FinBERTAnalyzer — reuses model from NLPSentiment if already loaded
# ═══════════════════════════════════════════════════════════════════════════════

class FinBERTAnalyzer:
    _pipeline = None
    _model_name = "ProsusAI/finbert"

    @classmethod
    def load(cls):
        if cls._pipeline is None:
            try:
                from transformers import pipeline
                log.info("FinBERT: loading %s ...", cls._model_name)
                t0 = time.time()
                cls._pipeline = pipeline("sentiment-analysis",
                                         model=cls._model_name, tokenizer=cls._model_name,
                                         max_length=512, truncation=True)
                log.info("FinBERT: loaded in %.1fs", time.time() - t0)
            except Exception as e:
                log.error("FinBERT: load failed — %s", e)
                cls._pipeline = None

    def classify(self, texts: list) -> list:
        if self._pipeline is None:
            return [{"label": "neutral", "score": 0.0, "confidence": 0.0, "numeric_score": 0.0} for _ in texts]
        results = []
        try:
            outputs = self._pipeline(texts, batch_size=16, truncation=True)
            for out in outputs:
                label = out[0]["label"].lower() if isinstance(out, list) else out["label"].lower()
                score = out[0]["score"] if isinstance(out, list) else out["score"]
                numeric = score if label == "positive" else (-score if label == "negative" else 0.0)
                results.append({"label": label, "score": numeric, "confidence": score, "numeric_score": numeric})
        except Exception as e:
            log.error("FinBERT inference error: %s", e)
            for _ in texts:
                results.append({"label": "neutral", "score": 0.0, "confidence": 0.0, "numeric_score": 0.0})
        return results


# ═══════════════════════════════════════════════════════════════════════════════
#  CrisisDetector — keywords + FinBERT + event type classification
# ═══════════════════════════════════════════════════════════════════════════════

class CrisisDetector:
    def __init__(self, finbert: FinBERTAnalyzer):
        self.finbert = finbert

    def analyze(self, articles: list) -> list:
        if not articles:
            return []

        texts = [f"{a['title']}. {a['summary']}"[:1000] for a in articles]
        sentiments = self.finbert.classify(texts)

        events = []
        for art, sent in zip(articles, sentiments):
            combined = (art["title"] + " " + art["summary"]).lower()

            # Crisis keyword scoring
            t1_score, t2_score, t3_score = 0.0, 0.0, 0.0
            t1_count, t2_count, t3_count = 0, 0, 0
            matched_event_types = set()

            for kw, sev in CRISIS_KEYWORDS_T1.items():
                if kw in combined:
                    t1_score = max(t1_score, sev)
                    t1_count += 1
                    et = KEYWORD_TO_EVENT_TYPE.get(kw)
                    if et:
                        matched_event_types.add(et)

            for kw, sev in CRISIS_KEYWORDS_T2.items():
                if kw in combined:
                    t2_score = max(t2_score, sev)
                    t2_count += 1
                    et = KEYWORD_TO_EVENT_TYPE.get(kw)
                    if et:
                        matched_event_types.add(et)

            for kw, sev in CRISIS_KEYWORDS_T3.items():
                if kw in combined:
                    t3_score = max(t3_score, sev)
                    t3_count += 1

            # Determine crisis tier and severity
            if t1_score > 0 or t1_count > 0:
                tier = 1
                keyword_severity = t1_score * (1.0 + 0.05 * min(t1_count - 1, 5))
            elif t2_score > 0 or t2_count > 0:
                tier = 2
                keyword_severity = t2_score * (1.0 + 0.03 * min(t2_count - 1, 5))
            elif t3_score > 0:
                tier = 3
                keyword_severity = t3_score
            else:
                tier = 3
                keyword_severity = 0.0

            keyword_severity = min(keyword_severity, 1.0)

            # FinBERT negative magnitude
            finbert_negative = max(-sent["numeric_score"], 0.0) if sent["numeric_score"] < 0 else 0.0

            # Mismatch penalty: keywords scream crisis but FinBERT disagrees
            if keyword_severity > 0.5 and finbert_negative < 0.25:
                keyword_severity *= 0.3 + 0.7 * finbert_negative
                if tier == 1:
                    tier = 2  # downgrade — likely "nuclear energy" vs "nuclear war"

            relevance = max(keyword_severity, finbert_negative * 0.7)

            if relevance < 0.15:
                continue

            source_weight = SOURCE_CREDIBILITY.get(art["source"], 0.6)

            events.append({
                "title": art["title"],
                "source": art["source"],
                "date": art["date"],
                "tier": tier,
                "keyword_severity": round(keyword_severity, 3),
                "finbert_negative": round(finbert_negative, 3),
                "finbert_confidence": sent["confidence"],
                "event_types": list(matched_event_types) if matched_event_types else ["general"],
                "relevance": round(relevance, 3),
                "source_weight": source_weight,
                "url": art.get("url", ""),
            })

        return events


# ═══════════════════════════════════════════════════════════════════════════════
#  MarketConfirmer — yfinance snapshot for VIX, DXY, GLD
# ═══════════════════════════════════════════════════════════════════════════════

class MarketConfirmer:
    def __init__(self):
        self.cache = {}
        self.cache_time = None

    def fetch(self) -> dict:
        import yfinance as yf
        now = datetime.now()
        if self.cache_time and (now - self.cache_time).seconds < 300:
            return self.cache

        result = {"vix": None, "dxy": None, "gld": None, "spy": None, "us10y": None}
        try:
            tickers = yf.Tickers("^VIX DX-Y.NYB GLD SPY ^TNX")
            hist = tickers.history(period="5d", progress=False)
            if not hist.empty:
                close = hist["Close"]
                for col in close.columns:
                    vals = close[col].dropna()
                    if len(vals) >= 2:
                        pct = (vals.iloc[-1] / vals.iloc[-2] - 1) * 100
                        ma5 = vals.rolling(5, min_periods=2).mean().iloc[-1] if len(vals) >= 5 else vals.iloc[-1]
                        ma5_pct = (vals.iloc[-1] / ma5 - 1) * 100 if ma5 else 0.0
                        if "VIX" in col:
                            result["vix"] = {"price": round(vals.iloc[-1], 2), "daily_pct": round(pct, 2), "vs_ma5": round(ma5_pct, 2)}
                        elif "DX" in col or "DXY" in col:
                            result["dxy"] = {"price": round(vals.iloc[-1], 2), "daily_pct": round(pct, 2), "vs_ma5": round(ma5_pct, 2)}
                        elif "GLD" in col or "GOLD" in col:
                            result["gld"] = {"price": round(vals.iloc[-1], 2), "daily_pct": round(pct, 2), "vs_ma5": round(ma5_pct, 2)}
                        elif "SPY" in col:
                            result["spy"] = {"price": round(vals.iloc[-1], 2), "daily_pct": round(pct, 2), "vs_ma5": round(ma5_pct, 2)}
                        elif "TNX" in col or "10Y" in col:
                            result["us10y"] = {"price": round(vals.iloc[-1], 2), "daily_pct": round(pct, 2), "vs_ma5": round(ma5_pct, 2)}
        except Exception as e:
            log.warning("MarketConfirmer: %s", e)

        self.cache = result
        self.cache_time = now
        return result

    def confirmation_score(self, event_types: list) -> float:
        """Return 0-1: how much current market confirms the expected move."""
        market = self.fetch()
        score = 0.5  # neutral baseline

        vix = market.get("vix")
        dxy = market.get("dxy")
        gld = market.get("gld")
        spy = market.get("spy")

        is_crisis_event = any(et in ("geopolitical_conflict", "oil_supply_shock", "financial_crisis") for et in event_types)

        if is_crisis_event:
            if vix and vix["vs_ma5"] > 10:
                score += 0.15  # VIX spiking = confirms risk-off
            if dxy and dxy["daily_pct"] > 0.5:
                score += 0.10  # Dollar surging
            if gld and gld["daily_pct"] < -0.5 and any("oil" in et for et in event_types):
                score += 0.10  # Gold falling on oil shock
            if spy and spy["daily_pct"] < -1.0:
                score += 0.15  # Equities selling off

        return min(score, 1.0)


# ═══════════════════════════════════════════════════════════════════════════════
#  AssetImpactMapper — regras causais por ativo
# ═══════════════════════════════════════════════════════════════════════════════

class AssetImpactMapper:
    def map_event(self, event: dict) -> dict:
        """Map a detected event to per-asset risk scores."""
        event_types = event.get("event_types", ["general"])
        base_severity = max(event["keyword_severity"], event["finbert_negative"])
        finbert_neg = event["finbert_negative"]

        assets = {}
        for symbol, rules in ASSET_IMPACT_RULES.items():
            best_weight = 0.0
            best_direction = "neutral"
            best_reason = "no direct causality"

            for et in event_types:
                rule = rules.get(et)
                if rule and rule["weight"] > best_weight:
                    best_weight = rule["weight"]
                    best_direction = rule["direction"]
                    best_reason = rule["reason"]

            # Combine: keyword severity + FinBERT + causality weight
            raw = (base_severity * 0.35) + (finbert_neg * 0.25) + (best_weight * 0.40)
            risk_score = min(raw * 100, 100.0)

            # Directional signal
            if risk_score < 50:
                signal = "NEUTRO"
            elif risk_score < 70:
                signal = "MONITOR"
            elif risk_score < 85:
                signal = "CAUTION"
            else:
                signal = "STOP"

            assets[symbol] = {
                "risk_score": round(risk_score, 1),
                "direction": best_direction,
                "signal": signal,
                "reason": best_reason,
            }

        return assets


# ═══════════════════════════════════════════════════════════════════════════════
#  RiskDecisionEngine — decisão final + expiração
# ═══════════════════════════════════════════════════════════════════════════════

class RiskDecisionEngine:
    def __init__(self, cfg: CrisisConfig):
        self.cfg = cfg

    def decide(self, event: dict, assets: dict, market_score: float) -> dict:
        """Return enriched event with global decision and expiration."""
        now = datetime.now()

        if event["tier"] == 1:
            validity = self.cfg.TIER1_VALIDITY_HOURS
        elif event["tier"] == 2:
            validity = self.cfg.TIER2_VALIDITY_HOURS
        else:
            validity = self.cfg.TIER3_VALIDITY_HOURS

        expires_at = now + timedelta(hours=validity)

        # Determine global signal
        risk_scores = [a["risk_score"] for a in assets.values()]
        max_risk = max(risk_scores) if risk_scores else 0.0
        avg_risk = np.mean(risk_scores) if risk_scores else 0.0
        high_risk_count = sum(1 for r in risk_scores if r >= self.cfg.STOP_THRESHOLD)

        # Auto STOP rules
        auto_stop = False
        if event["tier"] == 1:
            auto_stop = True
        if high_risk_count >= 2:
            auto_stop = True
        if max_risk >= self.cfg.STOP_THRESHOLD and market_score > 0.6:
            auto_stop = True

        if auto_stop:
            global_signal = "STOP"
            global_score = max(max_risk, 85.0)
        elif avg_risk >= self.cfg.CAUTION_THRESHOLD:
            global_signal = "CAUTION"
            global_score = avg_risk
        elif avg_risk >= self.cfg.MONITOR_THRESHOLD:
            global_signal = "MONITOR"
            global_score = avg_risk
        else:
            global_signal = "NEUTRO"
            global_score = avg_risk

        return {
            "event_id": hashlib.md5((event["title"] + now.isoformat()).encode()).hexdigest()[:12],
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
            "tier": event["tier"],
            "headline": event["title"],
            "source": event["source"],
            "keyword_severity": event["keyword_severity"],
            "finbert_negative": event["finbert_negative"],
            "market_confirmation": round(market_score, 2),
            "global_risk_score": round(global_score, 1),
            "global_signal": global_signal,
            "assets": assets,
            "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S"),
            "validity_hours": validity,
            "url": event.get("url", ""),
        }


# ═══════════════════════════════════════════════════════════════════════════════
#  DatasetManager — persistência dos outputs
# ═══════════════════════════════════════════════════════════════════════════════

class DatasetManager:
    @staticmethod
    def load_last_event() -> Optional[dict]:
        if EVENT_OUTPUT_JSON.exists():
            try:
                with open(EVENT_OUTPUT_JSON, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None
        return None

    @staticmethod
    def save_event_csv(decision: dict):
        """EventRisk.csv — per-asset rows for MQL5."""
        now_str = decision["timestamp"]
        event_id = decision["event_id"]
        headline = decision["headline"]
        expires = decision["expires_at"]
        rows = []
        for sym, info in decision["assets"].items():
            rows.append({
                "date": now_str,
                "symbol": sym,
                "risk_score": info["risk_score"],
                "signal": info["signal"],
                "direction": info["direction"],
                "event_id": event_id,
                "event_headline": headline,
                "expires_at": expires,
            })
        df = pd.DataFrame(rows)
        df.to_csv(EVENT_OUTPUT_CSV, index=False)
        log.info("EventRisk.csv saved: %d assets", len(df))

    @staticmethod
    def save_event_json(decision: dict):
        """Overwrite EventRiskEvents.json with latest event."""
        with open(EVENT_OUTPUT_JSON, "w", encoding="utf-8") as f:
            json.dump(decision, f, indent=2, ensure_ascii=False)
        log.info("EventRiskEvents.json saved")

    @staticmethod
    def append_history(decision: dict):
        """Append to EventRiskHistory.csv for backtesting."""
        now_str = decision["timestamp"]
        row = {
            "date": now_str,
            "event_id": decision["event_id"],
            "tier": decision["tier"],
            "headline": decision["headline"],
            "source": decision["source"],
            "keyword_severity": decision["keyword_severity"],
            "finbert_negative": decision["finbert_negative"],
            "market_confirmation": decision["market_confirmation"],
            "global_risk_score": decision["global_risk_score"],
            "global_signal": decision["global_signal"],
            "expires_at": decision["expires_at"],
        }
        df_new = pd.DataFrame([row])
        if EVENT_HISTORY_CSV.exists():
            df_old = pd.read_csv(EVENT_HISTORY_CSV)
            df_all = pd.concat([df_old, df_new], ignore_index=True)
        else:
            df_all = df_new
        df_all.to_csv(EVENT_HISTORY_CSV, index=False)
        log.info("EventRiskHistory.csv appended (%d total)", len(df_all))

    @staticmethod
    def has_recent_event(min_relevance: float = 0.5) -> Optional[dict]:
        """Check if there's a valid active event (within expiration)."""
        last = DatasetManager.load_last_event()
        if last is None:
            return None
        expires = datetime.strptime(last["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now() > expires:
            return None
        if last["global_signal"] in ("STOP", "CAUTION"):
            return last
        return None


# ═══════════════════════════════════════════════════════════════════════════════
#  Main orchestrator
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    _setup_logging()
    t0 = time.time()
    log.info("=" * 60)
    log.info("EventRiskNLP — inicio")

    cfg = CrisisConfig()

    # Check for existing active event (avoids re-processing if still valid)
    active = DatasetManager.has_recent_event()
    if active:
        remaining = datetime.strptime(active["expires_at"], "%Y-%m-%d %H:%M:%S") - datetime.now()
        log.info("Active event: %s (expires in %s)", active["event_id"], remaining)
        # Still do a fresh collection to confirm/update
        log.info("Proceeding with fresh collection to update...")

    # 1. Collect news
    collector = NewsCollector(cfg)
    articles = collector.collect()
    if not articles:
        log.info("No new articles. Checking if current signal is still valid.")
        if active:
            log.info("Active STOP event: %s — siga bloqueado ate %s",
                     active["event_id"], active["expires_at"])
        else:
            # Write clean "no event" state
            clean = {
                "event_id": "none", "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "tier": 3, "headline": "No event detected", "source": "",
                "keyword_severity": 0, "finbert_negative": 0, "market_confirmation": 0,
                "global_risk_score": 0, "global_signal": "NEUTRO",
                "assets": {sym: {"risk_score": 0, "direction": "neutral", "signal": "NEUTRO", "reason": ""}
                           for sym in TRACKED_SYMBOLS},
                "expires_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "validity_hours": 0, "url": "",
            }
            DatasetManager.save_event_csv(clean)
            DatasetManager.save_event_json(clean)
            log.info("No active event. Signal: NEUTRO")
        log.info("EventRiskNLP — fim (%.1fs)", time.time() - t0)
        return

    log.info("Articles collected: %d", len(articles))

    # 2. FinBERT
    FinBERTAnalyzer.load()
    detector = CrisisDetector(FinBERTAnalyzer())

    events = detector.analyze(articles)
    if not events:
        log.info("No crisis-relevant events detected.")
        log.info("EventRiskNLP — fim (%.1fs)", time.time() - t0)
        return

    log.info("Crisis events detected: %d", len(events))

    # 3. Pick the most severe event
    event = max(events, key=lambda e: e["relevance"])
    log.info("Top event: [T%d] sev=%.3f neg=%.3f | %s",
             event["tier"], event["keyword_severity"], event["finbert_negative"],
             event["title"][:80])

    # 4. Asset impact mapping
    mapper = AssetImpactMapper()
    assets = mapper.map_event(event)

    # 5. Market confirmation
    confirmer = MarketConfirmer()
    market_score = confirmer.confirmation_score(event["event_types"])

    # 6. Decision engine
    engine = RiskDecisionEngine(cfg)
    decision = engine.decide(event, assets, market_score)

    # 7. Log results
    log.info("=" * 50)
    log.info("Decision: %s (global_score=%.1f, market_conf=%.2f)",
             decision["global_signal"], decision["global_risk_score"], decision["market_confirmation"])
    for sym, info in decision["assets"].items():
        log.info("  %-8s risk=%-5.1f dir=%-8s signal=%-8s | %s",
                 sym, info["risk_score"], info["direction"], info["signal"], info["reason"])
    log.info("Expires at: %s (%dh)", decision["expires_at"], decision["validity_hours"])

    # 8. Save outputs
    DatasetManager.save_event_csv(decision)
    DatasetManager.save_event_json(decision)
    DatasetManager.append_history(decision)

    log.info("EventRiskNLP — fim (%.1fs)", time.time() - t0)


if __name__ == "__main__":
    main()

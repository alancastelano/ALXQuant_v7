"""
NLPSentiment — News-driven financial sentiment module.

Collects news from RSS feeds + Marketaux API, classifies with FinBERT,
and produces daily asset-level sentiment + consolidated NLP risk score.

Standalone testable — run as: python NLPSentiment.py

Outputs:
  data/news/news_raw.csv           — raw deduplicated news articles
  data/news/NewsSentiment.csv      — per-headline sentiment (with asset mapping)
  data/processed/NLPSentiment.csv  — daily consolidated by asset
  logs/nlp.log                     — processing log
"""

import hashlib
import logging
import os
import sys
import time
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import config

# ─── Logging ──────────────────────────────────────────────────────────────
log = logging.getLogger("NLPSentiment")
_log_configured = False


def _setup_logging():
    global _log_configured
    if _log_configured:
        return
    logs_dir = PROJECT_ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(logs_dir / "nlp.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    log.addHandler(console)
    log.setLevel(logging.INFO)
    _log_configured = True


# ─── Paths ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[3]
NEWS_DIR = PROJECT_ROOT / "data" / "news"
NEWS_DIR.mkdir(parents=True, exist_ok=True)

NEWS_RAW_PATH = NEWS_DIR / "news_raw.csv"
NEWS_SENT_PATH = NEWS_DIR / "NewsSentiment.csv"
NLP_OUTPUT_PATH = Path(config.processed_dir) / "NLPSentiment.csv"

# ─── Tracked assets + keywords ───────────────────────────────────────────
TRACKED_ASSETS = {
    "SPY": ["stock market", "S&P 500", "equities", "equity market", "wall street", "us stocks"],
    "QQQ": ["nasdaq", "tech stocks", "technology", "big tech", "semiconductor"],
    "GLD": ["gold", "bullion", "precious metals", "gold price", "xau"],
    "DXY": ["us dollar", "dollar index", "currency markets", "forex", "fx market", "dollar strength"],
    "TLT": ["treasury", "bond market", "treasury yield", "us bonds", "fixed income", "long bond"],
    "USO": ["crude oil", "oil price", "wti", "brent", "energy market", "petroleum"],
    "CL=F": ["crude oil", "oil", "energy", "petroleum"],
    "EURUSD": ["euro", "eur/usd", "euro dollar"],
    "BTC-USD": ["bitcoin", "crypto", "cryptocurrency", "btc"],
    "VIX": ["volatility", "vix", "fear index", "market fear"],
    "AGG": ["corporate bonds", "credit market", "bond yields", "investment grade"],
    "HYG": ["high yield", "junk bonds", "credit spreads"],
}

# Category grouping for the consolidated output
ASSET_CATEGORY = {
    "SPY": "equity", "QQQ": "equity",
    "GLD": "safe_haven", "DXY": "safe_haven",
    "TLT": "bond", "AGG": "bond", "HYG": "bond",
    "USO": "energy", "CL=F": "energy",
    "EURUSD": "currency", "BTC-USD": "crypto",
    "VIX": "volatility",
}

# ─── Fed / macro keywords for sentiment weighting ────────────────────────
FED_KEYWORDS = ["federal reserve", "fed", "powell", "fomc", "interest rate", "monetary policy"]
ENERGY_KEYWORDS = ["oil", "crude", "energy", "natural gas", "gasoline"]

# ─── RSS Feeds ────────────────────────────────────────────────────────────
RSS_FEEDS = {
    "ActionForex": "https://www.actionforex.com/feed/",
    "OilPrice": "https://oilprice.com/rss/main",
    "Mining": "https://www.mining.com/feed/",
}

# ─── Marketaux API ────────────────────────────────────────────────────────
MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY", "")
MARKETAUX_ENDPOINT = "https://api.marketaux.com/v1/news/all"


# ═══════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _article_hash(title: str, url: str = "") -> str:
    raw = (title + url).strip().lower()
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _keyword_match(text: str, keywords: list) -> bool:
    tl = text.lower()
    for kw in keywords:
        if kw.lower() in tl:
            return True
    return False


def _match_assets(text: str) -> list:
    matched = []
    for asset, keywords in TRACKED_ASSETS.items():
        if _keyword_match(text, keywords):
            matched.append(asset)
    return matched


def _is_fed_related(text: str) -> bool:
    return _keyword_match(text, FED_KEYWORDS)


def _is_energy_related(text: str) -> bool:
    return _keyword_match(text, ENERGY_KEYWORDS)


# ═══════════════════════════════════════════════════════════════════════════
#  Config
# ═══════════════════════════════════════════════════════════════════════════

class Config:
    NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", MARKETAUX_API_KEY)
    MAX_NEWS_PER_SOURCE: int = 50
    FINBERT_MODEL: str = "ProsusAI/finbert"
    FEED_TIMEOUT: int = 15
    RECENCY_HALF_LIFE_DAYS: int = 3

    PATH_NEWS_RAW: Path = NEWS_RAW_PATH
    PATH_NEWS_SENT: Path = NEWS_SENT_PATH
    PATH_NLP_OUTPUT: Path = NLP_OUTPUT_PATH


# ═══════════════════════════════════════════════════════════════════════════
#  NewsCollector — RSS feeds
# ═══════════════════════════════════════════════════════════════════════════

class NewsCollector:
    """Collects news from RSS feeds and returns a list of dicts."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def collect(self, since: Optional[datetime] = None) -> list:
        articles = []
        for source_name, feed_url in RSS_FEEDS.items():
            try:
                items = self._parse_rss(source_name, feed_url, since)
                articles.extend(items)
                log.info("  RSS %-15s -> %d articles", source_name, len(items))
            except Exception as e:
                log.warning("  RSS %s failed: %s", source_name, e)
        return articles

    def _parse_rss(self, source: str, url: str, since: Optional[datetime]) -> list:
        import feedparser
        feed = feedparser.parse(url, agent="Mozilla/5.0 (compatible; ALXQuant/1.0)")
        if not feed.entries:
            return []
        items = []
        for entry in feed.entries:
            published = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                published = datetime(*entry.published_parsed[:6])
            elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
                published = datetime(*entry.updated_parsed[:6])
            if published is None:
                published = datetime.now()

            if since is not None and published < since:
                continue

            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            summary = ""
            if hasattr(entry, "summary"):
                summary = entry.summary.strip()
            elif hasattr(entry, "description"):
                summary = entry.description.strip()
            summary = re.sub(r"<[^>]+>", "", summary)

            if not title:
                continue

            items.append({
                "date": published.strftime("%Y-%m-%d %H:%M:%S"),
                "source": source,
                "title": title,
                "summary": summary[:2000],
                "url": link,
            })
        return items


# ═══════════════════════════════════════════════════════════════════════════
#  MarketauxCollector — API-based news
# ═══════════════════════════════════════════════════════════════════════════

class MarketauxCollector:
    """Collects news from Marketaux API (requires NEWS_API_KEY)."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.api_key = cfg.NEWS_API_KEY

    def collect(self, since: Optional[datetime] = None) -> list:
        if not self.api_key:
            log.info("  Marketaux: no API key, skipping")
            return []

        import requests
        articles = []
        published_after = (since.strftime("%Y-%m-%d") if since else "2024-01-01")

        params = {
            "api_token": self.api_key,
            "limit": min(self.cfg.MAX_NEWS_PER_SOURCE, 50),
            "published_after": published_after,
            "sort": "published_desc",
            "language": "en",
        }

        try:
            resp = requests.get(MARKETAUX_ENDPOINT, params=params, timeout=self.cfg.FEED_TIMEOUT)
            if resp.status_code != 200:
                log.warning("  Marketaux HTTP %s: %s", resp.status_code, resp.text[:200])
                return []
            data = resp.json()
            for item in data.get("data", []):
                title = (item.get("title") or "").strip()
                if not title:
                    continue
                desc = (item.get("description") or "").strip()
                snippet = (item.get("snippet") or "").strip()
                summary = desc or snippet
                pub = item.get("published_at", "")
                try:
                    dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                except Exception:
                    dt = datetime.now()

                articles.append({
                    "date": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "source": "Marketaux",
                    "title": title,
                    "summary": summary[:2000],
                    "url": item.get("url", ""),
                })
            log.info("  Marketaux API -> %d articles", len(articles))
        except Exception as e:
            log.warning("  Marketaux API error: %s", e)
        return articles


# ═══════════════════════════════════════════════════════════════════════════
#  FedScraper — Federal Reserve speeches
# ═══════════════════════════════════════════════════════════════════════════

class FedScraper:
    """Scrapes Fed speeches from federalreserve.gov."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.base = "https://www.federalreserve.gov"

    def collect(self, since: Optional[datetime] = None) -> list:
        articles = []
        try:
            items = self._fetch_speeches(since)
            articles.extend(items)
            log.info("  FedSpeeches -> %d articles", len(items))
        except Exception as e:
            log.warning("  FedScraper error: %s", e)
        return articles

    def _fetch_speeches(self, since: Optional[datetime]) -> list:
        import requests
        from bs4 import BeautifulSoup

        url = f"{self.base}/newsevents/speeches.htm"
        resp = requests.get(url, timeout=self.cfg.FEED_TIMEOUT)
        if resp.status_code != 200:
            return []
        soup = BeautifulSoup(resp.text, "html.parser")
        items = []

        for link in soup.select("a[href*='/newsevents/speech/']"):
            href = link.get("href", "")
            title = link.get_text(strip=True)
            if not title or len(title) < 10:
                continue
            parent = link.find_parent(["li", "div", "p"])
            date_text = ""
            if parent:
                date_text = parent.get_text(" ", strip=True)

            parsed_date = self._extract_date(date_text)
            if parsed_date is None:
                parsed_date = datetime.now()
            if since is not None and parsed_date < since:
                continue

            full_url = href if href.startswith("http") else f"{self.base}{href}"

            items.append({
                "date": parsed_date.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "FedSpeeches",
                "title": title,
                "summary": f"Fed speech: {title}",
                "url": full_url,
            })
        return items

    @staticmethod
    def _extract_date(text: str) -> Optional[datetime]:
        patterns = [
            r"(\w+ \d{1,2}, \d{4})",
            r"(\d{4}-\d{2}-\d{2})",
            r"(\d{1,2}/\d{1,2}/\d{4})",
        ]
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                try:
                    for fmt in ["%B %d, %Y", "%Y-%m-%d", "%m/%d/%Y"]:
                        try:
                            return datetime.strptime(m.group(1), fmt)
                        except ValueError:
                            continue
                except Exception:
                    pass
        return None


# ═══════════════════════════════════════════════════════════════════════════
#  FinBERTAnalyzer — classifier
# ═══════════════════════════════════════════════════════════════════════════

class FinBERTAnalyzer:
    """FinBERT sentiment classifier. Loads model once as class-level singleton."""

    _pipeline = None

    def __init__(self, cfg: Config):
        self.cfg = cfg
        if FinBERTAnalyzer._pipeline is None:
            FinBERTAnalyzer._load_model(cfg)

    @classmethod
    def _load_model(cls, cfg: Config):
        try:
            from transformers import pipeline
            log.info("FinBERT: carregando modelo %s ...", cfg.FINBERT_MODEL)
            t0 = time.time()
            cls._pipeline = pipeline(
                "sentiment-analysis",
                model=cfg.FINBERT_MODEL,
                tokenizer=cfg.FINBERT_MODEL,
                max_length=512,
                truncation=True,
            )
            log.info("FinBERT: carregado em %.1fs", time.time() - t0)
        except Exception as e:
            log.error("FinBERT: falha ao carregar modelo — %s", e)
            log.error("FinBERT: instalacao necessaria — pip install transformers torch")
            cls._pipeline = None

    def classify(self, texts: list) -> list:
        if FinBERTAnalyzer._pipeline is None:
            return [{"label": "neutral", "score": 0.0, "confidence": 0.0, "numeric_score": 0.0} for _ in texts]

        results = []
        try:
            outputs = self._pipeline(texts, batch_size=16, truncation=True)
            for out in outputs:
                label = out[0]["label"].lower() if isinstance(out, list) else out["label"].lower()
                score = out[0]["score"] if isinstance(out, list) else out["score"]
                if label == "positive":
                    numeric = score
                elif label == "negative":
                    numeric = -score
                else:
                    numeric = 0.0
                results.append({
                    "label": label,
                    "score": round(numeric, 4),
                    "confidence": round(score, 4),
                    "numeric_score": round(numeric, 4),
                })
        except Exception as e:
            log.error("FinBERT inference error: %s", e)
            results.extend([{"label": "neutral", "score": 0.0, "confidence": 0.0, "numeric_score": 0.0} for _ in texts])
        return results


# ═══════════════════════════════════════════════════════════════════════════
#  DatasetManager — read/write incremental CSVs
# ═══════════════════════════════════════════════════════════════════════════

class DatasetManager:
    """Handle incremental loading and saving of all datasets."""

    @staticmethod
    def load_raw() -> pd.DataFrame:
        if not NEWS_RAW_PATH.exists():
            return pd.DataFrame(columns=["date", "source", "title", "summary", "url", "hash"])
        df = pd.read_csv(NEWS_RAW_PATH, parse_dates=["date"])
        if "hash" not in df.columns:
            df["hash"] = df.apply(lambda r: _article_hash(str(r.get("title", "")), str(r.get("url", ""))), axis=1)
        return df

    @staticmethod
    def save_raw(df: pd.DataFrame):
        df = df.drop_duplicates(subset=["hash"], keep="last")
        df = df.sort_values("date").reset_index(drop=True)
        df.to_csv(NEWS_RAW_PATH, index=False)
        log.info("Raw saved: %d rows -> %s", len(df), NEWS_RAW_PATH)

    @staticmethod
    def load_sentiment() -> pd.DataFrame:
        if not NEWS_SENT_PATH.exists():
            return pd.DataFrame(columns=["date", "asset", "source", "headline", "sentiment", "score", "confidence"])
        return pd.read_csv(NEWS_SENT_PATH, parse_dates=["date"])

    @staticmethod
    def save_sentiment(df: pd.DataFrame):
        df = df.drop_duplicates(subset=["date", "asset", "headline"], keep="last")
        df = df.sort_values("date").reset_index(drop=True)
        df.to_csv(NEWS_SENT_PATH, index=False)
        log.info("Sentiment saved: %d rows -> %s", len(df), NEWS_SENT_PATH)

    @staticmethod
    def load_nlp_output() -> pd.DataFrame:
        if not NLP_OUTPUT_PATH.exists():
            return pd.DataFrame(columns=[
                "date", "nlp_risk_score", "risk_label",
                "spy_sentiment", "gold_sentiment", "dxy_sentiment",
                "bond_sentiment", "fed_sentiment", "energy_sentiment",
                "news_count",
            ])
        return pd.read_csv(NLP_OUTPUT_PATH, parse_dates=["date"])

    @staticmethod
    def save_nlp_output(df: pd.DataFrame):
        df = df.sort_values("date").reset_index(drop=True)
        df.to_csv(NLP_OUTPUT_PATH, index=False, float_format="%.6g")
        log.info("NLP output saved: %d rows -> %s", len(df), NLP_OUTPUT_PATH)

    @staticmethod
    def get_last_date(path: Path, col: str = "date") -> Optional[datetime]:
        if not path.exists():
            return None
        try:
            df = pd.read_csv(path, parse_dates=[col])
            if df.empty:
                return None
            return df[col].max()
        except Exception:
            return None


# ═══════════════════════════════════════════════════════════════════════════
#  News Pipeline — orchestrate collection + FinBERT + asset mapping
# ═══════════════════════════════════════════════════════════════════════════

class NewsPipeline:
    """Collect, classify, map to assets, persist."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.collectors = [
            NewsCollector(cfg),
            MarketauxCollector(cfg),
            FedScraper(cfg),
        ]
        self.analyzer = FinBERTAnalyzer(cfg)

    def run(self):
        t0 = time.time()

        # --- 1. Load existing raw ---
        raw_existing = DatasetManager.load_raw()
        existing_hashes = set(raw_existing["hash"].tolist()) if not raw_existing.empty else set()
        last_raw_date = DatasetManager.get_last_date(NEWS_RAW_PATH)

        log.info("Existing raw: %d rows, last=%s", len(raw_existing),
                 last_raw_date.strftime("%Y-%m-%d") if last_raw_date else "none")

        # --- 2. Collect new articles ---
        all_new = []
        for collector in self.collectors:
            items = collector.collect(since=last_raw_date)
            for item in items:
                h = _article_hash(item["title"], item["url"])
                if h not in existing_hashes:
                    item["hash"] = h
                    all_new.append(item)
                    existing_hashes.add(h)

        if not all_new:
            log.info("No new articles found.")
            return

        log.info("New articles to process: %d", len(all_new))

        # --- 3. Classify with FinBERT ---
        texts = []
        for a in all_new:
            combined = a["title"] + ". " + a["summary"]
            texts.append(combined[:1000])

        sentiments = []
        batch_size = 32
        for i in tqdm(range(0, len(texts), batch_size), desc="FinBERT"):
            batch = texts[i:i + batch_size]
            sentiments.extend(self.analyzer.classify(batch))

        # --- 4. Map articles to assets ---
        new_rows = []
        for art, sent in zip(all_new, sentiments):
            combined_text = art["title"] + " " + art["summary"]
            matched = _match_assets(combined_text)
            if not matched:
                matched = ["GENERAL"]
            categories = set()
            is_fed = _is_fed_related(combined_text)
            is_energy = _is_energy_related(combined_text)
            for asset in matched:
                new_rows.append({
                    "date": art["date"],
                    "asset": asset,
                    "source": art["source"],
                    "headline": art["title"],
                    "sentiment": sent["label"],
                    "score": sent["numeric_score"],
                    "confidence": sent["confidence"],
                    "is_fed": 1 if is_fed else 0,
                    "is_energy": 1 if is_energy else 0,
                    "hash": art["hash"],
                })

        # --- 5. Update raw ---
        new_raw = pd.DataFrame([{
            "date": a["date"],
            "source": a["source"],
            "title": a["title"],
            "summary": a["summary"],
            "url": a["url"],
            "hash": a["hash"],
        } for a in all_new])
        raw_updated = pd.concat([raw_existing, new_raw], ignore_index=True)
        DatasetManager.save_raw(raw_updated)

        # --- 6. Update sentiment per headline ---
        df_new = pd.DataFrame(new_rows)
        if df_new.empty:
            log.info("No asset-matched articles.")
            return

        df_new["date"] = pd.to_datetime(df_new["date"])
        existing_sent = DatasetManager.load_sentiment()
        sent_updated = pd.concat([existing_sent, df_new], ignore_index=True)
        DatasetManager.save_sentiment(sent_updated)

        log.info("Classification done: %d headlines, %d asset-rows",
                 len(all_new), len(df_new))

        # --- 7. Build daily consolidated NLP output ---
        self._build_daily(df_new)

        log.info("Pipeline completo em %.1fs", time.time() - t0)

    def _build_daily(self, df_new: pd.DataFrame):
        def _weighted_sentiment(group: pd.DataFrame) -> float:
            if group.empty:
                return 0.0
            weights = group["confidence"].values * np.exp(
                -np.log(2) * (group["days_ago"].values) / self.cfg.RECENCY_HALF_LIFE_DAYS
            )
            weights = np.maximum(weights, 0.01)
            scores = group["score"].values
            return float(np.average(scores, weights=weights))

        # Load existing daily + merge with new
        existing_daily = DatasetManager.load_nlp_output()
        if existing_daily.empty:
            all_dates = pd.DataFrame()
        else:
            existing_daily["date"] = pd.to_datetime(existing_daily["date"])
            all_dates = existing_daily.copy()

        # Prepare new data with recency
        now = datetime.now()
        df_new = df_new.copy()
        df_new["days_ago"] = (now - df_new["date"]).dt.days

        # Daily aggregation per category
        df_new["date_only"] = df_new["date"].dt.date
        daily_rows = []

        for day, group in df_new.groupby("date_only"):
            day_dt = datetime.combine(day, datetime.min.time())
            total_news = len(group)

            spy = _weighted_sentiment(group[group["asset"].isin(["SPY", "QQQ", "GENERAL"])])
            gold = _weighted_sentiment(group[group["asset"].isin(["GLD"])])
            dxy = _weighted_sentiment(group[group["asset"].isin(["DXY", "EURUSD"])])
            bond = _weighted_sentiment(group[group["asset"].isin(["TLT", "AGG", "HYG"])])
            fed = _weighted_sentiment(group[group["is_fed"] == 1]) if group["is_fed"].sum() > 0 else 0.0
            energy = _weighted_sentiment(group[group["is_energy"] == 1]) if group["is_energy"].sum() > 0 else 0.0

            nlp_risk = (
                0.40 * spy +
                0.30 * fed +
                0.20 * gold +
                0.10 * energy
            )

            daily_rows.append({
                "date": day_dt,
                "nlp_risk_score": round(nlp_risk, 4),
                "risk_label": self._risk_label(nlp_risk),
                "spy_sentiment": round(spy, 4),
                "gold_sentiment": round(gold, 4),
                "dxy_sentiment": round(dxy, 4),
                "bond_sentiment": round(bond, 4),
                "fed_sentiment": round(fed, 4),
                "energy_sentiment": round(energy, 4),
                "news_count": total_news,
            })

        df_day = pd.DataFrame(daily_rows) if daily_rows else pd.DataFrame()
        if df_day.empty:
            log.info("No daily rows generated")
            return

        # Merge with existing
        if not all_dates.empty:
            combined = pd.concat([all_dates, df_day], ignore_index=True)
        else:
            combined = df_day

        combined = combined.drop_duplicates(subset=["date"], keep="last").sort_values("date").reset_index(drop=True)

        # z-score normalize nlp_risk_score across full history
        if len(combined) > 5:
            mean = combined["nlp_risk_score"].mean()
            std = combined["nlp_risk_score"].std()
            if std > 1e-10:
                combined["nlp_risk_score"] = (combined["nlp_risk_score"] - mean) / std
            combined["risk_label"] = combined["nlp_risk_score"].apply(self._risk_label)

        DatasetManager.save_nlp_output(combined)

    @staticmethod
    def _risk_label(score: float) -> str:
        if score >= 1.0:
            return "RISK_OFF"
        if score <= -1.0:
            return "RISK_ON"
        return "NEUTRAL"


# ═══════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    _setup_logging()
    t0 = time.time()
    log.info("=" * 60)
    log.info("NLPSentiment — inicio")

    cfg = Config()
    pipeline = NewsPipeline(cfg)
    pipeline.run()

    log.info("NLPSentiment — fim (%.1fs)", time.time() - t0)


if __name__ == "__main__":
    main()

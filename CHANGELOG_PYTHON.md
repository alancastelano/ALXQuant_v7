Version: v2.0.0
Date: 2026-06-28
Time: 18:30

Type: MINOR

Files:

* data/DataHouse/coletores/NLPSentiment.py (new)
* data/DataHouse/requirements.txt

Description:

* Novo modulo NLPSentiment.py: coleta RSS (ActionForex, OilPrice, Mining) + Marketaux API + Fed speeches
* FinBERT (ProsusAI/finbert) classifica sentimento (positive/negative/neutral com score numerico)
* Keyword-based asset mapping (TRACKED_ASSETS com 12 ativos)
* Producao incremental de 3 datasets:
  - data/news/news_raw.csv — artigos brutos deduplicados
  - data/news/NewsSentiment.csv — por headline + ativo
  - data/processed/NLPSentiment.csv — consolidado diario com nlp_risk_score
* NLP risk score = 0.40*spy + 0.30*fed + 0.20*gold + 0.10*energy
* Recency decay (half-life 3 dias) na agregacao
* z-score normalization quando houver dados suficientes

Reason:

* Necessario fator de sentimento baseado em noticias para complementar o RiskSentiment宏观
* FinBERT fornece classificacao granular por headline
* Arquitetura incremental preparada para integracao futura com o EA MQL5

Rollback:

* Git checkout v1.1.0

Version: v1.0.0
Date: 2026-06-27
Time: 23:22

Type: MINOR

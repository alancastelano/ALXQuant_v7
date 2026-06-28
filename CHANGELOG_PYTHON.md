Version: v2.1.0
Date: 2026-06-28
Time: 19:30

Type: MINOR

Files:

* data/DataHouse/coletores/EventRiskNLP.py (new)
* MQL5/MQL5/Experts/EAQuant_v7/ALXFramework/EventRisk.mqh (new)

Description:

* Novo modulo EventRiskNLP.py: deteccao de eventos extraordinarios
* 3 Tiers de severidade: Tier1 (critico) → STOP 24h, Tier2 → 12h, Tier3 → 4h
* CrisisDetector: keywords T1/T2/T3 + FinBERT + penalidade por falso positivo
* AssetImpactMapper: regras causais economicas por ativo (XAUUSD, EURUSD, CL=F, SPY, US30, NASDAQ)
* MarketConfirmer: yfinance (VIX, DXY, GLD) confirma ou refuta o evento
* RiskDecisionEngine: STOP/CAUTION/MONITOR/NEUTRO com expiracao temporal
* Outputs: EventRisk.csv (per-asset), EventRiskEvents.json (evento atual), EventRiskHistory.csv (historico)
* EventRisk.mqh: stub MQL5 com EventRisk_IsBlocked(symbol) para ler EventRisk.csv

Reason:

* NLPSentiment.py classifica sentimento generico mas nao detecta crise em tempo real
* EventRiskNLP preenche a lacuna: deteccao de breaknews + causalidade economica por ativo
* Arquitetura preparada para integracao futura com o EA MQL5

Rollback:

* Git checkout v2.0.0

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

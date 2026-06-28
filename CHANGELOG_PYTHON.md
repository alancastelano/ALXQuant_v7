Version: v1.1.0
Date: 2026-06-28
Time: 16:30

Type: MINOR

Files:

* data/DataHouse/coletores/RiskSentiment.py

Description:

* Added DECIMAL_FORMATS per column: 2 decimais para precos (VIX, DXY, HY, SPY, etc.),
  4 para z-scores (global_risk_score, sub-scores), 5 para EUR/USD
* Columns rounded before CSV save to reduce file size without data loss

Reason:

* Default float precision gerava ~75 chars/linha, com 2-4 decimais cai para ~45 chars
* Precos acionarios/indices tem precisao natural de 2 casas
* Z-scores precisam de 4 casas para nao perder gate no Sigmoid do MQL5

Rollback:

* Git checkout v1.0.0

Version: v1.0.0
Date: 2026-06-27
Time: 23:22

Type: MINOR

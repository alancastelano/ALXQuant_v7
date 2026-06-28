Version: v7.6.0
Date: 2026-06-28
Time: 19:00

Type: MINOR

Files:

* ALXFramework/core/MarketRegime.mqh
* ALXFramework/core/RiskSentiment.mqh
* ALXFramework/core/NLPSentiment.mqh
* ALXFramework/TimeFilter.mqh
* EAQuant_v7.mq5
* CHANGELOG_MQL.md

Description:

* Time-based caching em todos os modulos pesados:
  - MarketRegime::Get() (Hurst DFA): cache de 300s (M5) — antes recalculava a cada tick (~99.7% reducao)
  - RiskSentiment::Update() (busca binaria CSV): cache de 60s (M1)
  - NLPSentiment::Update() (iteracao eventos): cache de 60s (M1)
  - TimeFilter::GetLiquidityFactor() (exchange/session check): cache de 60s (M1)
* EA version: v7.5.1 -> v7.6.0

Reason:

* Hurst DFA completo rodava em todo tick, gastando ~2000 operacoes (200 barras x 10 escalas)
* Regime nao muda em segundos — M5 e mais que suficiente
* Risk/news/timefilter dados sao estaticos ou mudam em frequencia diaria
* Forward: reducao de ~99.7% nas chamadas DFA
* Backtest M1: reducao de ~5x nas chamadas DFA (1/min -> 1/5min) = backtest 1 ano cai de 8h para ~1.5h

Rollback:

* Git checkpoint: c44bc94

Version: v7.5.1
Date: 2026-06-28
Time: 20:30

Type: MINOR

Files:

* ALXFramework/core/RiskSentiment.mqh
* EAQuant_v7.mq5
* CHANGELOG_MQL.md

Description:

* Directional bias por ativo em RISK_OFF: safe_haven bloqueia SELL, risk_on bloqueia BUY
* SAssetRiskProfile struct + InitProfiles(safe_haven_list, risk_on_list)
* IsDirectionBlocked(symbol, direction) — consulta separada do gate global
* Inp_SafeHavenList (default: XAUUSD) e Inp_RiskOnList (default: SPY,EURUSD,GBPUSD,US30,NASDAQ,CL=F)
* EA OnTick: verifica directional bias antes de ApplySLTP; loga _DIRBLOCK
* Inp_NewsMinBefore e Inp_NewsMinAfter (default 30 min cada) — janela de noticias configurável

Reason:

* RISK_OFF tinha gate global (risk_blocked = true com score<0.3) que parava tudo
* Agora bloqueia apenas trades contra o fluxo: nao vende ouro, nao compra acoes
* Trades a favor do fluxo (comprar ouro, vender acoes) continuam livres em RISK_OFF
* Janela de noticias de 30 min era hardcoded; agora configurável

Rollback:

* Git checkout v7.4.1

Version: v7.4.1
Date: 2026-06-28
Time: 19:00

Type: PATCH

Files:

* ALXFramework/TimeFilter.mqh
* EAQuant_v7.mq5
* CHANGELOG_MQL.md

Description:

* GetLiquidityFactor(): closed penalty alterado de 0.3 para 0.8 (penalidade leve)
* Default Inp_FxMap: removido XAUUSD (ouro trade 24h, nao precisa de mapeamento)
* fit_score * 0.3 matava qualquer sinal (0.55*0.3=0.165 < threshold 0.40)
* Agora fit_score * 0.8 = penalidade suave de 20% fora do horario

Reason:

* TimeFilter v7.4.0 impedia abertura de ordens porque liquidity_factor=0.3
  reduzia fit scores abaixo de Inp_TrendFitMin (0.40)
* XAUUSD mapeado apenas para FX_NY fazia fit cair para 0.3 fora do
  horario NY, mas ouro tem liquidez 24h

Rollback:

* Git checkout v7.4.0

Version: v7.4.0
Date: 2026-06-28
Time: 18:00

Type: MINOR

Files:

* ALXFramework/TimeFilter.mqh (new)
* ALXFramework/core/NLPSentiment.mqh
* ALXFramework/core/Snapshot.mqh
* ALXFramework/ALXFramework.mqh
* EAQuant_v7.mq5
* CHANGELOG_MQL.md

Description:

* TimeFilter.mqh: 17 exchanges (BOV, NYS, NAS, TSE, LSE, FRA, PAR, SIX, MIL, MAD, TKO, HKG, SSO, SX, ASX, KOS, NSE) + 4 forex sessions (Sydney, Tokyo, London, New York) + DST (US/EU)
* TimeFilter: ParseMapping via Inp_ExcMap / Inp_FxMap inputs
* TimeFilter: GetLiquidityFactor() returns 1.0 (open), 0.3 (closed), or 0.0 if Inp_BlockClosed=true
* NewsSentiment: agora bloqueia apenas HIGH impact (impact >= 2); LOW/MEDIUM ignorados
* Snapshot: liquidity_factor field + multiplica todos os fit scores pelo fator
* ALXFramework: include TimeFilter.mqh + CTimeFilter member + init
* EA: novos inputs Inp_ExcMap, Inp_FxMap, Inp_BlockClosed

Reason:

* EA operava fora do horario das bolsas/fx, abrindo posicoes em baixa liquidez
* News LOW/MEDIUM bloqueavam trading desnecessariamente
* Fit scores sem penalidade de liquidez levavam a execucao em horarios inadequados

Rollback:

* Git checkout: pending

Version: v7.3.1
Date: 2026-06-28
Time: 15:30

Type: PATCH

Files:

* EAQuant_v7.mq5
* ALXFramework/RiskManager.mqh
* ALXFramework/strategy/TrendFollowing.mqh
* ALXFramework/strategy/MeanReversion.mqh
* ALXFramework/strategy/Breakout.mqh
* ALXFramework/strategy/SessionBreakout.mqh
* ALXFramework/strategy/RangeBreakout.mqh
* ALXFramework/strategy/Reversal.mqh

Description:

* RiskManager.ApplySLTP: trocado PositionOpen por Buy/Sell (compatibilidade MT5)
* Signal thresholds expostos como inputs (Inp_TrendFitMin=0.40, Inp_MRFitMin=0.40, etc.)
* Cada Strategy.Init() agora aceita fit_threshold como parametro
* EA OnInit: re-inicia strategies com magic, symbol e thresholds corretos

Reason:

* PositionOpen pode nao funcionar em todas as builds do MT5
* Thresholds hardcoded (0.60-0.65) impediam qualquer sinal com fit scores tipicos (~0.3-0.5)
* Sem ordem aberta, nao e possivel testar o resto do framework

Rollback:

* Git checkpoint: ac9bc7d

Version: v7.0.1
Date: 2026-06-27
Time: 23:30

Type: PATCH

Files:

* MQL5/MQL5/Experts/EAQuant_v7/ALXFramework/core/RiskSentiment.mqh

Description:

* Fixed column mapping in LoadCSV(): changed `yield_curve` → `spread_10_2` to match actual CSV output columns.

Reason:

* CSV generated by Python RiskSentiment.py has column `spread_10_2`, not `yield_curve`.
* Without this fix, the yield curve spread was always read as 0.0.

Rollback:

* Git checkpoint: dde7049

Version: v7.1.0
Date: 2026-06-27
Time: 23:45

Type: MINOR

Files:

* EAQuant_v7.mq5
* ALXFramework/core/Snapshot.mqh
* ALXFramework/strategy/TrendFollowing.mqh
* ALXFramework/DataMiner.mqh

Description:

* Added regime-based allocation: fit scores por estrategia (trend, mean-reversion, breakout)
* Snapshot score expandido: 7 fatores (5 MarketRegime + 1 Risk + 1 News)
* TrendFollowing agora filtra por trend_fit score antes de operar
* DataMiner loga feature vector completo + fit scores em CSV para analise pos-backtest
* EAQuant_v7.mq5: OnTick com estrategia baseada em fit scores + logging 1x/barra

Reason:

* Score unico nao discrimina qual estrategia se adapta melhor ao regime atual
* Fit scores permitem backtestar e ajustar thresholds por estrategia
* CSV de features permite analise em Python: "quando fit_trend > 0.7, Sharpe foi X"

Rollback:

* Git checkpoint: 3472e24

Version: v7.2.0
Date: 2026-06-28
Time: 00:15

Type: MINOR

Files:

* EAQuant_v7.mq5
* ALXFramework/ALXFramework.mqh
* ALXFramework/core/Snapshot.mqh
* ALXFramework/StrategyDispatcher.mqh (new)
* ALXFramework/strategy/MeanReversion.mqh (new)
* ALXFramework/strategy/Breakout.mqh (new)
* ALXFramework/strategy/SessionBreakout.mqh (new)
* ALXFramework/strategy/RangeBreakout.mqh (new)
* ALXFramework/strategy/Reversal.mqh (new)
* ALXFramework/DataMiner.mqh

Description:

* Multi-strategy regime-based allocation com 6 estrategias:
  - TrendFollowing (SuperTrend + fit filter)
  - MeanReversion (z-score + fit filter)
  - Breakout (ATR channel break + fit filter)
  - SessionBreakout (London/NY range breakout + fit filter)
  - RangeBreakout (contraction/expansion + fit filter)
  - Reversal (VWAP extension exhaustion + fit filter)
* StrategyDispatcher: seleciona estrategia com maior fit score acima do threshold
* Snapshot expandido com 6 fit scores: fit_trend, fit_mr, fit_bo, fit_sbo, fit_rbo, fit_pb
* Score composto: 7 fatores (regime + risk + news)
* DataMiner: logging de todos os fit scores
* Inputs: thresholds por estrategia ajustaveis via painel

Reason:

* Score unico nao discrimina qual estrategia se adapta melhor ao regime
* Cada estrategia tem fit score proprio com pesos diferentes para H, R2, risk, vol, momentum
* Permite backtestar e descobrir: "quando fit_trend > 0.7, TrendFollowing funciona; quando cai, MeanReversion assume"

Rollback:

* Git checkpoint: 3472e24

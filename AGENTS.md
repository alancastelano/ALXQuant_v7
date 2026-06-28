# Diretivas Permanentes

Atue como um analista técnico, científico e intelectualmente honesto.

Não valide automaticamente minhas hipóteses, crenças, opiniões ou conclusões. Trate minhas afirmações apenas como hipóteses a serem testadas.

## Priorize

- consenso acadêmico e profissional;
- literatura revisada por pares;
- fontes primárias;
- dados empíricos;
- documentos técnicos e evidências verificáveis.

Quando houver divergência entre minha opinião e o consenso científico, acadêmico ou profissional, apresente claramente essa divergência e explique as razões.

## Diferencie explicitamente

- fatos estabelecidos;
- hipóteses;
- interpretações;
- tradições;
- especulações.

Apresente argumentos favoráveis e contrários às principais correntes de pensamento, indicando o grau de evidência e o nível de aceitação (majoritário, minoritário ou especulativo).

## Identifique

- vieses cognitivos;
- falácias;
- anacronismos;
- cherry picking;
- limitações metodológicas.

Em temas técnicos, científicos, históricos, financeiros ou teológicos, produza uma análise profunda, crítica e profissional, mesmo que as conclusões contradigam minhas expectativas ou preferências.

O objetivo é alcançar a interpretação mais robusta e baseada em evidências disponíveis, e não confirmar minhas opiniões.

---

# DIRETRIZ PARA RESPOSTAS DE PROGRAMAÇÃO

Aplicando a persona de analista crítico à engenharia de software, ao responder perguntas sobre **código, algoritmos, debugging, arquitetura ou lógica**, você DEVE seguir esta hierarquia de prioridades:

## 0. 🧐 Validação da Hipótese (ANTES de qualquer código)
- Se o usuário trouxer uma hipótese sobre a causa do erro ("está quebrando porque X"), **NÃO a aceite automaticamente**.
- Analise a evidência fornecida (stack trace, logs, comportamento observado).
- Se a hipótese estiver **errada**, aponte isso educadamente antes de prosseguir. Só parta para a solução depois que a causa real estiver confirmada ou se o usuário pedir explicitamente "faça do jeito que eu estou falando, mesmo assim".

## 1. 🧠 Lógica (até 3 passos claros)
Explique o raciocínio por trás da solução em **no máximo 3 tópicos objetivos**.
- Se a pergunta for trivial (ex: sintaxe básica), 1 ou 2 passos são suficientes.
- Mantenha o tom técnico e direto, sem jargões desnecessários, mas sem infantilizar.

## 2. 💻 Código Final (Completo e Comentado)
- Entregue o código pronto para rodar, com sintaxe destacada (```).
- O código deve ser **completo** (não snippets soltos).
- Adicione comentários apenas onde houver complexidade não óbvia.
- Respeite a versão da linguagem/framework. Se não informada, **pergunte** antes.

## 3. 🧪 Testes Unitários (quando aplicável)
- Para problemas funcionais (funções, endpoints, algoritmos), sugira **2 testes** (ex: pytest, Jest).
- Para perguntas conceituais (ex: "o que é uma closure?"), este passo é **opcional** - substitua por um exemplo conceitual.

---

# EAQUANT VERSIONING AND CHANGE MANAGEMENT POLICY

## PROJECT PRINCIPLE

The agent must NEVER create a new project structure unless explicitly requested.

The existing repository structure is the authoritative structure.

All documentation, changelogs, version files, and support files must be integrated into the current project layout.

---

# VERSION SOURCE

The official software version is stored inside EAQuant_v7.mq5:

```cpp
const string EA_VERSION = "v7.0.0";
```

The agent must always:

1. Read the current EA_VERSION.
2. Determine whether the change is: MAJOR, MINOR, or PATCH
3. Increment the version.
4. Update EA_VERSION and `#property version`.

**Format:** `v<MAJOR>.<MINOR>.<PATCH>` (three segments with `v` prefix).

---

# MANDATORY PRE-CHANGE CHECKPOINT

Before modifying code:

```bash
git add .
git commit -m "checkpoint: before <change description>"
```

Every change must have a restoration point.

After all changes are complete, the final commit message must follow **Conventional Commits**:

```
<type>(<scope>): <description>

- <detail 1>
- <detail 2>
```

Types: `feat:`, `fix:`, `refactor:`, `perf:`, `style:`, `test:`, `docs:`, `chore:`

---

# CHANGE CLASSIFICATION

**PATCH:** Bug fixes, label corrections, calculation fixes, small refactoring, documentation updates.

**MINOR:** New indicators, new modules, new features, new analysis capabilities.

**MAJOR:** Architecture changes, breaking interfaces, major refactoring, execution model changes.

---

# CHANGELOG POLICY

The changelog file must be placed at the project root.

**Changelog files:**

* `CHANGELOG_MQL.md` — for MQL5 changes.
* `CHANGELOG_PYTHON.md` — for Python changes.

---

# CHANGELOG FORMAT

```
Version: v7.0.0
Date: YYYY-MM-DD
Time: HH:MM

Type: MAJOR

Files:

* EAQuant_v7.mq5

Description:

* Initial release.

Reason:

* Clean architecture v7.

Rollback:

* Git checkpoint.
```

---

# AGENT WORKFLOW

1. Read EA_VERSION.
2. Classify MAJOR, MINOR, or PATCH.
3. Create Git checkpoint (`git add . && git commit -m "checkpoint: before ..."`).
4. Modify code.
5. Update EA_VERSION and `#property version`.
6. Update changelog.
7. Create final commit with Conventional Commits message.
8. Report modified files and version change.

---

No code modification is considered complete until EA_VERSION, `#property version`, and the changelog are updated.

---

# SESSION SUMMARY — 2026-06-28

## Project
ALXQuant_v7 — EAQuant_v7.mq5 (MQL5) + Python data pipeline.

## Current Version
- MQL5 EA: **v7.5.1** (`#property version "7.51"`, `EA_VERSION = "v7.5.1"`)
- Python NLPSentiment: **v2.1.0**
- Python EventRiskNLP: **v1.0.0**

## What Was Built This Session

### Python: EventRiskNLP.py (v1.0.0) — NEW MODULE
`data/DataHouse/coletores/EventRiskNLP.py`
- Crisis detection pipeline with 3 severity tiers (Tier1 → STOP 24h, Tier2 → 12h, Tier3 → 4h)
- CrisisDetector: hierarchical keywords T1/T2/T3 + FinBERT classification + **false positive mismatch penalty** (reduces severity when FinBERT disagrees with crisis keywords)
- AssetImpactMapper: economic causality rules per asset (XAUUSD, EURUSD, CL=F, SPY, US30, NASDAQ)
- MarketConfirmer: yfinance (VIX, DXY, GLD) confirms or refutes events
- RiskDecisionEngine: STOP/CAUTION/MONITOR/NEUTRO with temporal expiration
- Outputs: `EventRisk.csv` (per-asset for MQL5), `EventRiskEvents.json` (current event), `EventRiskHistory.csv` (history)
- Incremental: only runs if enough new raw news are available
- Verified: first run detected "Weekly Focus – Reversal of Stagflationary Winds" as Tier1 STOP (keyword=0.95, FinBERT=0.958 negative)

### MQL5: EventRisk.mqh — NEW MODULE
`ALXFramework/EventRisk.mqh`
- Reads `EventRisk.csv` via kernel32 + FwReadCSV
- Functions: `EventRisk_IsBlocked(symbol)` → true if STOP active, `EventRisk_GetScore(symbol)` → 0-100, `EventRisk_GetSignal(symbol)` → 0=NEUTRO..3=STOP, `EventRisk_GetHeadline(symbol)` → event name
- 60s cache to avoid re-reading CSV every tick

### MQL5: RiskSentiment.mqh — Directional Bias (v7.5.0)
`ALXFramework/core/RiskSentiment.mqh`
- `SAssetRiskProfile` struct (symbol + type: 0=safe_haven, 1=risk_on)
- `InitProfiles(safe_haven_list, risk_on_list)` — parses comma-separated lists
- `IsDirectionBlocked(symbol, direction)` — blocks specific trade direction **separately** from the global gate
  - RISK_OFF + safe_haven + SELL → blocked (don't sell gold)
  - RISK_OFF + risk_on + BUY → blocked (don't buy stocks)
  - Does NOT set m_blocked (does not trigger global Snapshot block)
- `FindProfile()` internal lookup by symbol

### MQL5: EAQuant_v7.mq5 — Inputs & Integration
- Inputs added:
  - `Inp_SafeHavenList` (default: "XAUUSD")
  - `Inp_RiskOnList` (default: "SPY,EURUSD,GBPUSD,US30,NASDAQ,CL=F")
  - `Inp_NewsMinBefore` (default: 30 min)
  - `Inp_NewsMinAfter` (default: 30 min)
- All 15 input groups redesigned with **numbered naming** (1. EA Config through 15. Logging)
- All 51 inputs have NN.MM numbering in comments (1.1, 1.2, ..., 15.1)
- All descriptions in English with strategy-specific context (e.g., "Max VIX (high VIX kills trends)")
- OnInit calls `framework.risk.InitProfiles()` and `framework.news.Init(news_before, news_after)`
- OnTick: checks `IsDirectionBlocked()` before ApplySLTP; logs `_DIRBLOCK` suffix
- Logging moved to after positional check to support DIRBLOCK logging

### MCP Servers Installed (Global via npm 11.17.0, Node v24.17.0)
4 MCPs configured in `C:\ALXQuant_v7\opencode.json`:
1. **Memory MCP** (`@modelcontextprotocol/server-memory`) — persists session context in `.memory.json`
2. **FRED MCP** (`fred-mcp-server` v1.0.2) — access to 800k+ FRED economic series (VIX, DXY, HY spread). Uses API key from `.env`
3. **Sequential Thinking** (`@modelcontextprotocol/server-sequential-thinking`) — step-by-step debugging
4. **PostgreSQL MCP** (`@modelcontextprotocol/server-postgres`) — read-only queries on `alxquant` DB via user `mcp_readonly`

PostgreSQL MCP installed (`@modelcontextprotocol/server-postgres` deprecated but functional). Read-only user `mcp_readonly` created, database `alxquant` ready for backtest CSV imports.

## Files Modified This Session

### New:
- `data/DataHouse/coletores/EventRiskNLP.py`
- `ALXFramework/EventRisk.mqh`

### Modified:
- `ALXFramework/core/RiskSentiment.mqh` — directional bias + InitProfiles + IsDirectionBlocked
- `EAQuant_v7.mq5` — inputs restructured + numbered + descriptions
- `CHANGELOG_MQL.md` — v7.4.1 through v7.5.1
- `CHANGELOG_PYTHON.md` — v2.1.0 (EventRiskNLP)
- `opencode.json` — MCP config added

## Git Repositories
Two independent git repos:
1. **Outer** (`C:\ALXQuant_v7\`) — master branch, no remote. Source: Python, docs, config.
2. **Inner** (`C:\ALXQuant_v7\MQL5\MQL5\`) — main branch, no remote. Source: MQL5 EA, framework, strategies.

## Key Decisions
| Decision | Rationale |
|---|---|
| TimeFilter closed penalty = 0.8 (not 0.3) | 0.3 killed all fit scores (0.55×0.3=0.165 < threshold 0.40) |
| XAUUSD removed from default Inp_FxMap | Gold trades 24h across all sessions, not just FX_NY |
| IsDirectionBlocked does NOT set m_blocked | Otherwise Snapshot gate blocks ALL trades, not just wrong direction |
| EventRisk false positive: mismatch penalty | Crisis keywords alone trigger false positives (e.g., "nuclear energy" ≠ "nuclear war"); FinBERT disagreement reduces severity |
| All input descriptions in English with strategy context | 3 identical "Max VIX" descriptions without context were confusing |
| Input numbering NN.MM | Makes the 51 inputs navigable in MT5 Properties window |

## Next Steps
1. Install PostgreSQL MCP (`crystaldba/postgres-mcp-pro`) for querying backtest CSVs
2. Push repos to GitHub + install GitHub MCP
3. Run full Strategy Test (TimeFilter + NewsSentiment + EventRisk + DirectionalBias) when backtesting is available
4. Consider Playwright MCP for scraping sites that block RSS

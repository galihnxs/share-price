# Recommendations, 2026-10-30

Research tool output. Not financial advice. Prices: close of 2026-10-29 (Thursday).

## Friday Capitulation Execution Ticket

Place limit orders during Friday's US session. PAPER rows are logged automatically and need no order.

### Table 1: Sell / rollover (existing shares)

No open position needs action.

### Table 2: New buy orders (1 share each)

**Weekly (5 trading days): PAPER TRADE (CALIBRATING EDGE), expires 2026-11-06**

| # | Ticker | Company | Cluster | Conviction | Limit buy | GTC take-profit | GTC stop-loss | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 | **VHI** | Valhi Inc (NYSE) | defense_materials | 28% | $13.99 | $15.01 | $12.71 | CAUTION |
| 2 | **GFI** | Gold Fields Ltd (NYSE) | financial_shelter | 25% | $35.12 | $37.56 | $32.07 | PASS |
| 3 | **APA** | APA Corp (Nasdaq) | chokepoint_energy_food | 26% | $51.51 | $54.60 | $47.64 | WATCH |
| 4 | **SM** | SM Energy Co (NYSE) | chokepoint_energy_food | 24% | $39.58 | $42.17 | $36.34 | PASS |
| 5 | **CHRD** | Chord Energy Corp (Nasdaq) | chokepoint_energy_food | 24% | $153.63 | $163.21 | $141.65 | PASS |

**Monthly (21 trading days): PAPER TRADE (CALIBRATING EDGE), expires 2026-12-01**

| # | Ticker | Company | Cluster | Conviction | Limit buy | GTC take-profit | GTC stop-loss | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 | **GM** | General Motors Co (NYSE) | defense_materials | 42% | $85.72 | $95.41 | $76.03 | PASS |
| 2 | **LEA** | Lear Corp (NYSE) | defense_materials | 42% | $117.38 | $126.89 | $107.87 | WATCH |
| 3 | **VHI** | Valhi Inc (NYSE) | defense_materials | 40% | $13.99 | $15.78 | $12.21 | CAUTION |
| 4 | **ESEA** | Euroseas Ltd. (Nasdaq) | chokepoint_energy_food | 39% | $67.45 | $75.36 | $59.54 | PASS |
| 5 | **NEXA** | Nexa Resources S.A. (NYSE) | defense_materials | 39% | $12.00 | $13.72 | $10.28 | CAUTION |

**Quarterly (63 trading days): PAPER TRADE (CALIBRATING EDGE), expires 2027-02-02**

| # | Ticker | Company | Cluster | Conviction | Limit buy | GTC take-profit | GTC stop-loss | Audit |
|---|---|---|---|---|---|---|---|---|
| 1 | **ESEA** | Euroseas Ltd. (Nasdaq) | chokepoint_energy_food | 46% | $67.45 | $81.01 | $56.15 | PASS |
| 2 | **LEA** | Lear Corp (NYSE) | defense_materials | 43% | $117.38 | $133.69 | $103.79 | WATCH |
| 3 | **VHI** | Valhi Inc (NYSE) | defense_materials | 43% | $13.99 | $17.05 | $11.44 | CAUTION |
| 4 | **GM** | General Motors Co (NYSE) | defense_materials | 41% | $85.72 | $102.34 | $71.87 | PASS |
| 5 | **FSM** | Fortuna Mining Corp. (NYSE) | financial_shelter | 36% | $9.37 | $11.86 | $7.29 | WATCH |


Conviction = the model's probability that the take-profit is hit before the stop. Barriers: weekly +2.0/-2.5 ATR, monthly +/-3.5 ATR, quarterly +6.0/-5.0 ATR (ATR_14 on raw prices).

## Bottom line

1. No horizon has a proven edge, so all 15 tickets (5 per horizon) are PAPER. Nothing to buy with real money this Friday.
2. Triple-barrier labels lifted the monthly #1 win rate from 30.6% (random) to 42.1%, but it is not significant (z 1.43) and the trades barely broke even (profit factor 1.08). Most of the lift comes from picking more volatile stocks, not from skill.
3. The two names the model liked most are not usable: ZIM is a pending $35.00 cash takeover (binary deal risk), and APTV's price history is distorted by an unadjusted spin-off. The tickets skip both.
4. Concentration: the weekly list holds three oil producers (APA, SM, CHRD) that move with the same oil price, and VHI appears in all three horizons. Five picks are not five independent bets.
5. Regime: Pandemic 2028 and Asia war are IMMINENT (stress rising), the other four are LATENT. No scenario is in POST_RECOVERY, so no weights are inverted.

## Macro regime (Module 0)

| Scenario | State | P(state) | Stress Z | 21d change | High-vol prob | Weight 5d/21d/63d | Mode |
|---|---|---|---|---|---|---|---|
| AI bust already in Asia, not yet in the US | **LATENT** | 0.61 | +0.59 | -0.06 | 0.24 | 0.15 / 0.15 / 0.25 | normal |
| AI enables bio invention and hard physics/maths breakthroughs | **LATENT** | 0.98 | -0.24 | -0.16 | 0.70 | 0.01 / 0.01 / 0.15 | normal |
| COVID-like pandemic around 2028/2029 | **IMMINENT** | 0.94 | +1.44 | +1.61 | 0.01 | 0.38 / 0.38 / 0.39 | normal |
| Hit to the world financial system | **LATENT** | 0.88 | +0.35 | +0.19 | 0.05 | 0.05 / 0.05 / 0.18 | normal |
| Energy crisis in Hormuz or food crisis via Malacca | **LATENT** | 0.79 | -0.11 | +0.16 | 0.66 | 0.09 / 0.09 / 0.20 | normal |
| Possible war in Asia | **IMMINENT** | 0.82 | +0.53 | +1.58 | 0.66 | 0.33 / 0.33 / 0.36 | normal |

Method: rule-based soft states + 2-state Markov switching-variance probability. States are soft (probabilities), not hard thresholds.

## Is the ML signal real? (walk-forward, Friday closes)

| Horizon | Badge | Base rate | Top-5 win rate | Lift | z | Profit factor | #1 only: win (z, PF) | AUC | Old label: lift (z) | Edge |
|---|---|---|---|---|---|---|---|---|---|---|
| weekly (5d) | PAPER | 19.9% | 24.5% | +4.7 pts | 1.50 | 1.012 | 24.4% (1.46, 0.841) | 0.5305 | +0.4 pts (0.11) | **No** |
| monthly (21d) | PAPER | 30.6% | 36.6% | +6.0 pts | 0.75 | 1.059 | 42.1% (1.43, 1.078) | 0.5236 | -1.8 pts (-0.21) | **No** |
| quarterly (63d) | PAPER | 34.7% | 37.6% | +3.0 pts | 0.22 | 1.227 | 38.8% (0.30, 1.007) | 0.5215 | +1.3 pts (0.09) | **No** |

Test window 2023-07-21 to 2026-10-16 (164 Fridays). Edge is judged on the traded set (top 5 each Friday): win rate >= 55%, profit factor > 1.05, and lift significant (z >= 1.64, each Friday counted once). Old label = beat RSP over the horizon (previous model), same rows and features.

Caveat: Universe = today's screener candidates, chosen with today's fundamentals; the backtest measures ranking skill inside that list, not the screen itself. Research only, not advice.

## Top picks and value-trap audit

| Horizon | Ticker | Company | Cluster | Prob | Scenario tilt | Fwd P/E | FCF yield | P/TBV | Audit | AI div. | Bio-AI | Pandemic | Fin. shock | Strait | Asia war |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| weekly | ZIM | ZIM Integrated Shipping Services Ltd. (NYSE) | chokepoint_energy_food | 34% | +0.04 | 4.36 | 28.1% | 0.90 | AVOID | +0 | +0 | -1 | -1 | +2 | +1 |
| weekly | VHI | Valhi Inc (NYSE) | defense_materials | 28% | +0.09 | 4.32 | 33.4% | 0.62 | CAUTION | -1 | +0 | -1 | -1 | +0 | +1 |
| weekly | GFI | Gold Fields Ltd (NYSE) | financial_shelter | 25% | +0.48 | 7.22 | 13.3% | 3.71 | PASS | +1 | +0 | +1 | +2 | +0 | +1 |
| weekly | APA | APA Corp (Nasdaq) | chokepoint_energy_food | 26% | +0.04 | 9.58 | 11.9% | 2.96 | WATCH | +0 | +0 | -1 | -1 | +2 | +1 |
| weekly | APTV | Aptiv PLC (NYSE) | defense_materials | 25% | +0.09 | 6.86 | 17.5% | 3.54 | AVOID | -1 | +0 | -1 | -1 | -1 | -1 |
| monthly | APTV | Aptiv PLC (NYSE) | defense_materials | 52% | +0.09 | 6.86 | 17.5% | 3.54 | AVOID | -1 | +0 | -1 | -1 | -1 | -1 |
| monthly | ZIM | ZIM Integrated Shipping Services Ltd. (NYSE) | chokepoint_energy_food | 50% | +0.04 | 4.36 | 28.1% | 0.90 | AVOID | +0 | +0 | -1 | -1 | +2 | +1 |
| monthly | GM | General Motors Co (NYSE) | defense_materials | 42% | +0.09 | 5.79 | 39.2% | 1.28 | PASS | -1 | +0 | -1 | -1 | -1 | -1 |
| monthly | LEA | Lear Corp (NYSE) | defense_materials | 42% | +0.09 | 7.04 | 14.8% | 1.78 | WATCH | -1 | +0 | -1 | -1 | -1 | -1 |
| monthly | VHI | Valhi Inc (NYSE) | defense_materials | 40% | +0.09 | 4.32 | 33.4% | 0.62 | CAUTION | -1 | +0 | -1 | -1 | +0 | +1 |
| quarterly | ZIM | ZIM Integrated Shipping Services Ltd. (NYSE) | chokepoint_energy_food | 49% | +0.10 | 4.36 | 28.1% | 0.90 | AVOID | +0 | +0 | -1 | -1 | +2 | +1 |
| quarterly | ESEA | Euroseas Ltd. (Nasdaq) | chokepoint_energy_food | 46% | +0.10 | 3.89 | 16.1% | 1.03 | PASS | +0 | +0 | -1 | -1 | +2 | +1 |
| quarterly | APTV | Aptiv PLC (NYSE) | defense_materials | 45% | +0.05 | 6.86 | 17.5% | 3.54 | AVOID | -1 | +0 | -1 | -1 | -1 | -1 |
| quarterly | LEA | Lear Corp (NYSE) | defense_materials | 43% | +0.05 | 7.04 | 14.8% | 1.78 | WATCH | -1 | +0 | -1 | -1 | -1 | -1 |
| quarterly | VHI | Valhi Inc (NYSE) | defense_materials | 43% | +0.05 | 4.32 | 33.4% | 0.62 | CAUTION | -1 | +0 | -1 | -1 | +0 | +1 |

### ZIM (ZIM Integrated Shipping Services Ltd., NYSE): AVOID

Special situation, not a value stock any more: the price is pinned to a pending $35.00 cash merger with Hapag-Lloyd, with Israeli state approval in doubt. The model and the barriers cannot price a binary deal outcome.

- Merger consideration is $35.00 cash per share; if the deal fails shareholders get none of it. Price $29.24 implies the market sees real failure risk. [ZIM_20-F_2026-03-09_item3_key_info_risks_n006]
- In September 2026 the Israeli regulator (GCA) said Hapag-Lloyd and FIMI had not submitted the revised post-closing proposal by its deadline. The special state share approval is the open question. [ZIM_6-K_2026-09-30_current_report_n001]
- The State of Israel must consent to anyone taking 35% or more, and requires Israeli-citizen control conditions. [ZIM_20-F_2026-03-09_item3_key_info_risks_n008]
- Earnings already fell hard: 2025 net income $481.5M vs $2,153.8M in 2024; adjusted EBIT margin 12.8% vs 30.3%. [ZIM_20-F_2026-03-09_item5_operating_review_t000]

### APTV (Aptiv PLC, NYSE): AVOID

Data problem first: the Versigent (EDS) spin-off on 1 Apr 2026 shows up as a -10.6% price drop that Yahoo did not adjust, so its returns, 52-week-high distance and ML score are contaminated. Re-rank after adjusting the price history.

- Aptiv separated its Electrical Distribution Systems business into a new listed company, planned for 1 Apr 2026. [APTV_10-K_2026-02-06_item7_mdna_n002]
- Free cash flow collapsed in Q2 2026: $12M vs $219M a year earlier, while revenue grew only 2%. [APTV_8-K_2026-08-04_current_report_n004]
- Management is putting half of expected cash flow into buybacks for the next few years. [APTV_8-K_2026-08-04_current_report_n003]

### GM (General Motors Co, NYSE): PASS

Cheap on real earnings with very large buybacks; the EV write-downs are already taken. Watch EV lease residuals. Note: the 39% FCF yield is inflated by GM Financial.

- 2026 guidance: diluted EPS $11 to $13. [GM_10-K_2026-01-27_item7_mdna_n004]
- $5.3B spent on 65M shares in 9M 2026, and a new $20B authorisation in October 2026. [GM_10-Q_2026-10-20_item2_mdna_n017]
- $7.9B of 2025 charges for the EV realignment are behind it. [GM_10-Q_2026-07-21_item2_mdna_n016]
- EV leases are 23.5% of lease residual values, up from 21.1%: weaker used-EV prices would hit GM Financial. [GM_10-Q_2026-10-20_item2_mdna_n008]

### ESEA (Euroseas Ltd., Nasdaq): PASS

Contracted revenue exceeds the market cap, earnings are flat, debt is modest. Watch customer concentration and newbuild spending.

- $600.1M of minimum contracted charter revenue as of 30 Jun 2026, about 1.3x the $474M market cap. [ESEA_6-K_2026-10-09_current_report_n025]
- H1 2026 net income $65.7M vs $66.8M a year earlier. [ESEA_6-K_2026-10-09_current_report_t017]
- $218.6M of debt maturing 2027 to 2034; $19.6M due in 2026. [ESEA_20-F_2026-04-29_item5_operating_review_n016]
- Top five charterers paid 87% of 2025 revenue. [ESEA_20-F_2026-04-29_item3_key_info_risks_n091]

### VHI (Valhi Inc, NYSE): CAUTION

Cheap for structural reasons: a holding company with more debt than market value, one-off gains in earnings, and legacy lead-paint and CERCLA liabilities.

- Consolidated debt about $592M against a $406M market cap; the parent depends on subsidiary dividends. [VHI_10-K_2026-03-10_item1a_risk_factors_n008] [VHI_10-K_2026-03-10_item1a_risk_factors_n007]
- H1 2026 EPS includes $0.30 of tax increment reimbursement and $0.10 from an office building sale. [VHI_10-Q_2026-08-06_item2_mdna_n005]
- In July 2026 a court set $27.5M of recoverable CERCLA past costs, not yet split between defendants. [VHI_10-Q_2026-08-06_part2_item1_legal_n000]

### GFI (Gold Fields Ltd, NYSE): PASS

Real cash and a clear return policy; this is a gold-price trade more than deep value (P/TBV 3.7x). Fits the financial-shock and Asia-war scenarios.

- Adjusted free cash flow rose from $605M (2024) to $2,970M (2025); cash $1,779M. [GFI_20-F_2026-03-30_full_text_n282]
- 2026 guidance 2.40 to 2.60 Moz at AISC $1,800 to $2,000/oz. [GFI_20-F_2026-03-30_full_text_n677]
- Base dividend of 35% of FCF plus up to $500M of extra returns over 24 months. [GFI_20-F_2026-03-30_full_text_n234]
- Costs are rising with oil and tariffs; the filing links oil volatility to the Strait of Hormuz disruption. [GFI_20-F_2026-03-30_full_text_n564]

### SM (SM Energy Co, NYSE): PASS

Cash-generative oil producer with an undrawn credit line and steady capital returns. Oil-price exposure: WTI is near a 5-year high ($102.8, 93rd percentile), so current cash flow is close to peak-cycle.

- Raised second-half 2026 production guidance to 435-440 MBoe/d and kept capex guidance; returned $137M (about 30% of adjusted FCF) in Q2. [SM_8-K_2026-08-05_current_report_n004]
- No borrowings on the revolver and $2.5B of available capacity (Feb 2026). [SM_10-K_2026-02-26_item1a_risk_factors_n041]
- Borrowing base is tied to commodity prices: an oil price fall shrinks available credit. [SM_10-K_2026-02-26_item1a_risk_factors_n042]

### CHRD (Chord Energy Corp, Nasdaq): PASS

Strong operating cash flow and no revolver debt. Oil-price exposure: WTI is near a 5-year high ($102.8, 93rd percentile), so current cash flow is close to peak-cycle.

- Operating cash flow $2,040.7M in 2025 and $507.5M in Q1 2026. [CHRD_10-K_2026-02-26_item7_mdna_n016] [CHRD_10-Q_2026-05-07_item2_mdna_n015]
- No outstanding revolver borrowings at end-2025, only $32.8M of letters of credit. [CHRD_10-K_2026-02-26_item1a_risk_factors_n036]

### APA (APA Corp, Nasdaq): WATCH

Debt is fixed-rate and manageable, but the low multiple reflects peak-cycle oil. Oil-price exposure: WTI is near a 5-year high ($102.8, 93rd percentile), so current cash flow is close to peak-cycle.

- $3.7B of notes, all fixed-rate, weighted average 5.71%. [APA_10-Q_2026-08-06_item3_market_risk_n003]
- No hedge accounting: derivative swings hit reported earnings directly. [APA_10-K_2026-02-26_item1a_risk_factors_n003]

### NEXA (Nexa Resources S.A., NYSE): CAUTION

Back to profit in 2025 after two loss years, but with a recent covenant breach and open tax disputes in Peru.

- Net income $223.1M in 2025 after losses of $187.4M (2024) and $291.8M (2023). [NEXA_20-F_2026-03-26_full_text_t120]
- Breached the BNDES loan capitalization-ratio covenant in 2024. [NEXA_20-F_2026-03-26_full_text_n264]
- SUNAT (Peru tax authority) challenges to prior periods could mean substantial extra tax. [NEXA_20-F_2026-03-26_full_text_n061]

### LEA (Lear Corp, NYSE): WATCH

Auto seating and electrical supplier with about $2.7B of debt. The filings found little specific risk, but auto suppliers are hurt, not helped, by an Asia war or strait crisis, so the cluster's default scenario scores are overridden.

- About $2.7B of debt at end-2025. [LEA_10-K_2026-02-13_item1a_risk_factors_n018]

### FSM (Fortuna Mining Corp., NYSE): WATCH

Gold/silver miner with a financial-shock hedge role. The knowledge base returned mostly boilerplate, so this audit is thin.

- Caylloma produced 28,913 GEO in 9M 2026, near the low end of its 29,000-33,000 GEO guidance. [FSM_6-K_2026-10-07_current_report_n006]

### KGC (Kinross Gold Corp, NYSE): PASS

Large gold producer with rising earnings and ample liquidity.

- 9M 2026 net earnings $2,297.2M vs $1,557.1M a year earlier. [KGC_6-K_2026-10-28_current_report_t033]
- Cash $2,638.4M plus $1,744.2M of available credit at 30 Sep 2026. [KGC_6-K_2026-10-28_current_report_n040]
- Senior notes: $500M due 2033 and $250M due 2041. [KGC_6-K_2026-10-28_current_report_n075]

## Hold calendar

| Horizon | Names | Entry day | Time barrier |
|---|---|---|---|
| weekly | VHI, GFI, APA, SM, CHRD | 2026-10-30 | 2026-11-06 |
| monthly | GM, LEA, VHI, ESEA, NEXA | 2026-10-30 | 2026-12-01 |
| quarterly | ESEA, LEA, VHI, GM, FSM | 2026-10-30 | 2027-02-02 |

## Method and known gaps

- Universe: 6 scenario clusters (config/sectors.yaml), banks, insurers, REITs, retail/apparel, restaurants, entertainment and software excluded. Track A (hard assets) and Track B (bio/tech) rules in config/settings.yaml. Top 6 per cluster, 36 total.
- Scenario 1 gate blocked 48 AI-hardware names above 20x forward earnings (scenario not in POST_RECOVERY).
- Prices and fundamentals from Yahoo via the built-in browser (Yahoo blocks Python here); filings and XBRL facts from SEC in Python.
- Model: LightGBM per horizon, max depth 3, trained and tested on Friday closes only. Label = the ledger's own triple barrier. Purge gap = horizon in weeks + 1. Valuation and momentum features are cross-sectional Z-scores within the 36 candidates.
- The 55% win-rate rule is close to break-even for the weekly barriers (+2.0/-2.5 ATR needs 55.6% to break even), so profit factor matters more than win rate.
- Known gaps: cluster 'defense_materials' also holds autos and auto parts (GM, APTV, LEA, MGA) whose war exposure is negative, so their scenario scores are overridden here; ENPH and FSLR (solar) sit in ai_hardware because of their SIC code; Track B lets pre-revenue biotechs in on cash alone; APTV prices need a spin-off adjustment; regime states are rule-based, not a fitted Markov chain.

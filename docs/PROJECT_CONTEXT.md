# Project context: Africa delivery demand forecast

> Background for any Claude Code session working in this repo. `CLAUDE.md` holds the short working rules; this file holds the decisions already made and the detail behind them.

## 1. Purpose
A small, honest case study in hourly demand forecasting for a delivery marketplace in three African cities. The goal is hands-on practice with the logic of forecasting: decomposition, baselines, walk-forward backtesting, accuracy vs bias, investigating misses, and turning forecasts into operational decisions.

**Rule:** every line and every choice must be explainable. A simple pipeline that is fully understood beats a sophisticated one that is not. Keep code plain (pandas/numpy, small functions), avoid clever abstractions.

**The core operational tension:** bad weather raises order demand while lowering courier willingness to ride. Under-forecasting means too few couriers and slow deliveries; over-forecasting wastes incentive spend. This is a generic marketplace tension; no claim is made about any real company's data or internals.

---

## 2. Scope decisions (already made, don't reopen)

### Cities
| City | Country | Code | Lat | Lon | Timezone | Why this city |
|---|---|---|---|---|---|---|
| **Casablanca** | Morocco | MA | 33.57 | -7.59 | Africa/Casablanca | North Africa; Ramadan reshapes evening demand; AFCON 2025 hosted in Morocco; Morocco's clock shifts during Ramadan (real timezone trap) |
| **Nairobi** | Kenya | KE | -1.29 | 36.82 | Africa/Nairobi | Two rainy seasons (long rains ~Mar-May, short rains ~Oct-Dec); clear month-end payday effect |
| **Lagos** | Nigeria | NG | 6.52 | 3.38 | Africa/Lagos | Very large market; long rainy season (~Apr-Jul, shorter ~Sep-Oct); traffic-heavy |

- **Granularity:** city-level, hourly. **No zones.** (Zones/hierarchy are a talking point only: "city → zone → hour, top-down vs bottom-up reconciliation".)
- **Period:** 2024-10-01 to 2026-09-30, hourly (~17.5k rows per city), local time, timezone-aware.
- **Build order:** Casablanca end to end first. Nairobi and Lagos come after via config, not in parallel.
- **Fallback if time runs short:** Casablanca in depth; the other two shown as "same pipeline, different results".
- **Stretch only:** Johannesburg as a *hypothetical* new-market launch with ~8 weeks of history (cold-start test for TimesFM vs baseline).

### Data strategy: semi-synthetic
No public hourly delivery-order dataset exists for African cities. So:
- **Real inputs:** hourly weather + public calendars.
- **Simulated outputs:** orders and couriers online, from explicit, documented assumptions.

**Why this is actually better for learning:** The author sets the true effects, so we can check whether each model *recovers* them (rain uplift, Ramadan shift, payday bump) and whether the miss investigation finds the planted anomalies.

**Framing (use this wording in README/charts):** *"Real weather and calendar data; order and courier volumes simulated from my own stated assumptions. Not company data."*

---

## 3. Data inputs (real)

### Weather: Open-Meteo historical archive
- Endpoint: `https://archive-api.open-meteo.com/v1/archive` (free, no key)
- Params: `latitude`, `longitude`, `start_date=2024-10-01`, `end_date=2026-09-30`, `hourly=temperature_2m,precipitation,rain`, `timezone=<city tz>`
- Save: `data/raw/weather_<city>.csv` and **commit it** (small files; lets cloud/mobile sessions work offline).
- If a cloud session can't reach the API, run `src/fetch_weather.py` locally and pushes.

### Calendar
- **Public holidays:** `holidays` Python library, countries MA, KE, NG.
- **Ramadan:** derive from Eid al-Fitr dates in the `holidays` library (Ramadan ≈ the 29-30 days before). Approximate, document it, sanity-check by eye. Rough reference: 2025 ≈ 1-30 March; 2026 ≈ 18 Feb-19 March.
  - Effect strength differs by city: strong in Casablanca, moderate in Lagos (mixed population), small in Nairobi. Make it a per-city parameter.
- **Paydays:** month-end for all; also the 25th in Nairobi (assumption, document it).
- **AFCON 2025 (Casablanca only, optional):** tournament held in Morocco ~21 Dec 2025-18 Jan 2026. Morocco match evenings → demand spike. Skip if dates are fiddly.

### Timezone trap (deliberate learning point)
Morocco runs UTC+1 most of the year and switches to UTC+0 during Ramadan. Use tz-aware timestamps (`Africa/Casablanca`) end to end and check for duplicated/missing hours at the switches. This is a real example of checklist step 1 ("timezone error").

---

## 4. Simulator spec (`src/simulate.py`)

```
orders[t] = base_level
          × hourly_profile[hour]          # lunch + dinner peaks
          × weekday_factor[dow]
          × rain_effect(precip[t])
          × holiday_effect
          × ramadan_effect(hour)           # daytime dip, post-iftar spike
          × payday_effect
          × growth_trend(t)
          → then count noise (negative binomial, or Poisson as a simpler start)

couriers_online[t] = supply_profile[hour, dow] × growth × rain_supply_penalty(precip[t]) → noise
```

**Illustrative starting values** (all fictional; every one goes into `docs/assumptions.md` with a one-line justification; they may be changed):

| Parameter | Suggested start | Notes |
|---|---|---|
| Avg daily orders | Casablanca 6,000 · Nairobi 5,000 · Lagos 8,000 | Arbitrary scale, keep round |
| Hourly profile | Low 01-08; lunch peak 12-14; dinner peak 19-22 (Casablanca later, ~20-22) | Smooth curve, sums to 1 |
| Weekday | Fri/Sat/Sun +10-20% | |
| Rain (precip > 0.5 mm/h) | Demand +15-25%; couriers −20-30% | The core supply/demand tension |
| Public holiday | ±10% (choose per city, justify) | |
| Ramadan | Daytime −30-40%; post-iftar window +40-60% | Strength scaled per city |
| Payday | +5-10% for ~3 days after | |
| Growth | +15-25% year on year | Linear or gentle exponential |
| Courier supply | ~1 courier online per 2-3 orders/hour at baseline | Lags demand slightly |
| Random seed | Fixed (e.g. 42) | Reproducibility |

### Planted anomalies (per city)
1. **Data outage:** a block of missing or zeroed hours (pipeline failure).
2. **Promo spike:** a few days of +30-50% the model has no feature for.
3. **Structural break:** a permanent step change (e.g. +15% from a "new zone launch").

Log each to `data/processed/anomalies_truth.csv` (city, type, start, end, magnitude). **Models and the investigation notebook must not read this file** until the investigation is written; it is the answer key.

Output: `data/processed/demand_<city>.parquet` with timestamp, orders, couriers_online, weather, calendar flags.

---

## 5. Modeling and evaluation

### Setup
- **Horizon:** 168 hours (next 7 days), issued weekly. Reason: ops plan rider shifts days ahead.
- **Backtest:** walk-forward (rolling origin) over the **last 8 weeks**. Strictly chronological, never shuffled.
- **Single harness:** every model exposes `fit_predict(history, horizon) -> forecast` so all are scored identically.

### Metrics
- **WMAPE** = Σ|actual − forecast| / Σ actual. Preferred over MAPE for demand because it doesn't blow up on small night-time denominators.
- **Bias** = Σ(forecast − actual) / Σ actual. Positive = over-forecasting (wasted incentive spend); negative = under-forecasting (courier shortage, late deliveries).
- **Optional:** peak-hour WMAPE (lunch + dinner only), the hours ops care about most.

### Models
1. **Seasonal-naive baseline:** forecast = same hour one week earlier. Everything must beat this.
2. **LightGBM** on hour, weekday, holiday, Ramadan, payday, rain, temperature, and lagged demand at **≥168h only** (so the 7-day horizon stays honest).
   - Limitation to state: weather features use *actuals* as a stand-in for a weather forecast ("perfect weather forecast" assumption), which flatters the model.
3. **TimesFM 2.5, zero-shot.** Install and call exactly as the official `google-research/timesfm` README says; do not guess the API. Add covariates only if the README supports it cleanly. CPU is fine.

### Effect-recovery check
After scoring: did the models capture the planted rain, Ramadan and payday effects? Compare LightGBM feature importance and residuals on rain/Ramadan/payday hours against the true multipliers.

### Expected story (whichever way it lands)
- TimesFM wins → zero-shot pre-training picks up patterns a small model misses.
- LightGBM wins → weather and calendar carry most of the signal; a cheaper, explainable model is the right call.
- Either way the point is **judgement**: a foundation model is a contender, kept only if it beats the baseline on held-out weeks.

---

## 6. TimesFM background

- **What it is:** Google Research's Time Series Foundation Model. Separate from Gemini; built only for forecasting. Pre-trained on a huge volume of time series, so it forecasts new series zero-shot.
- **TimesFM 2.5:** the practical version. Open source on GitHub / Hugging Face (permissive licence; check the licence file). Also built into **BigQuery as `AI.FORECAST` / `AI.EVALUATE`**, so a Google Cloud team can forecast in SQL with no ML infrastructure. **Use this one.**
- **TimesFM-3:** released 31 Aug 2026, 330M parameters, native multivariate forecasting, but public weights are **non-commercial, non-production only**. Fine to mention, not to build on.
- **Limits to state:** still needs clean history (doesn't solve cold start); forecasts numbers, doesn't make decisions; things like cash vs mobile money, informal addressing and regulation shape the business but aren't time-series problems.

---

## 7. Insight layer

### Forecast-miss investigation (`notebooks/03_miss_investigation`)
Pick the week with the largest error and walk this checklist **in order, writing out the reasoning at each step**:
1. **Data quality:** pipeline bug, missing/duplicate records, timezone error
2. **Known driver changed:** weather, local event, holiday, promotion the model didn't see
3. **Structural shift:** new zone/city launch, app or pricing change, competitor move
4. **Model drift:** the underlying pattern changed; model is stale
5. **Noise:** one-off blip, not worth re-tuning for

Only after writing the conclusion, open `anomalies_truth.csv` and check.

### Operational recommendation
Turn one finding into a decision with numbers, e.g.:
- *Rain:* demand +X%, couriers −Y% → trigger rider incentives ahead of forecast rain in the dinner window.
- *Ramadan (Casablanca):* peak shifts to post-iftar → reshape courier shifts, not just add more.

---

## 8. Deliverables and repo layout

```
CLAUDE.md                short working rules (auto-loaded by Claude Code)
docs/PROJECT_CONTEXT.md  this file
docs/assumptions.md      every simulation parameter + justification
docs/walkthrough.md      3-minute talk track
data/raw/                weather CSVs (committed)
data/processed/          demand_<city>.parquet, anomalies_truth.csv
src/                     config.py, fetch_weather.py, calendar_features.py, simulate.py, backtest.py, models.py
notebooks/               01_eda, 02_models, 03_miss_investigation (thin; call src/)
reports/                 charts + simple results page
```

**Every chart and the README label the data as semi-synthetic.**

---

## 9. Environment notes
- Python venv; `pip install -r requirements.txt`. TimesFM is installed separately per its README (check supported Python version first).
- Allowed stack: pandas, numpy, requests, holidays, lightgbm, matplotlib, pyarrow, jupyter, timesfm. Ask before adding anything else.
- Cloud sessions may block outbound requests (Open-Meteo, Hugging Face). If so: run that step on the laptop, commit the result, continue in the cloud.



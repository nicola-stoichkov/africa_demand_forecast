@docs/PROJECT_CONTEXT.md

# Africa delivery demand forecast: case study

## Why this exists
A forecasting case study for a delivery marketplace.
Priority 1: the author learns the logic and practice of demand forecasting by doing it.
Priority 2: a small, honest case study that can be presented if there is time.

## Rules for working in this repo
- The author must be able to explain every line live. Prefer plain pandas/numpy, small functions, readable code over clever abstractions. Briefly explain the *why* of each step during the session.
- Work issue by issue from the GitHub Project board. Reference the issue (`#N`) in commit messages. Move the card when done.
- Build everything for **Casablanca first, end to end**, then generalise to Nairobi and Lagos through the city config. Don't build three cities in parallel.
- The data is **semi-synthetic**: real weather and calendar inputs, simulated orders and couriers. Label it as such in every chart, README and notebook. Never present it as company data and never invent facts about any real company.
- Every simulation parameter is an assumption: record it in `docs/assumptions.md` with a one-line justification.
- Reproducible: fixed random seed; small raw files are committed so cloud sessions don't need network access.
- Allowed stack: pandas, numpy, requests, holidays, lightgbm, matplotlib, pyarrow, jupyter, timesfm. Ask before adding anything else.

## Cities (city-level hourly forecast, no zones)
| City | Country code | Lat | Lon | Timezone |
|---|---|---|---|---|
| Casablanca | MA | 33.57 | -7.59 | Africa/Casablanca |
| Nairobi | KE | -1.29 | 36.82 | Africa/Nairobi |
| Lagos | NG | 6.52 | 3.38 | Africa/Lagos |

Period: 2024-10-01 to 2026-09-30, hourly, local time (timezone-aware).
Note: Morocco shifts its clock during Ramadan. Handle timezones explicitly; this is also a good real example of the "timezone error" data-quality check.

## Data plan
1. **Weather (real):** Open-Meteo historical archive, `https://archive-api.open-meteo.com/v1/archive`, hourly `temperature_2m`, `precipitation`, `rain`. Free, no key. Save to `data/raw/weather_<city>.csv` and commit.
   If the cloud sandbox blocks the request, run `src/fetch_weather.py` on the laptop and commit the CSVs.
2. **Calendar (real):** public holidays from the `holidays` library (MA, KE, NG); Ramadan derived from Eid al-Fitr dates (approximate, document it); paydays (month-end; also the 25th for Nairobi as an assumption); AFCON 2025 match days for Casablanca if easy to source, otherwise skip.
3. **Simulated orders and couriers (`src/simulate.py`):**
   orders = base_level × hourly_profile (lunch + dinner peaks) × weekday × rain_effect × holiday_effect × ramadan_effect (daytime dip, post-iftar spike) × payday_effect × growth_trend, then Poisson/negative-binomial noise.
   couriers_online = supply driven by hour and weekday, reduced in rain.
   Plant 3 anomalies per city: a data outage (missing hours), a promo spike, a structural break (step change). Log them in `data/processed/anomalies_truth.csv`. Models must never see this file; it is only for checking the investigation.

## Modeling plan
- Forecast horizon: next 168 hours (7 days), issued weekly.
- Evaluation: walk-forward backtest over the last 8 weeks, never shuffled.
- Metrics: WMAPE = sum|actual − forecast| / sum actual; bias = sum(forecast − actual) / sum actual (positive = over-forecasting).
- Models, all scored in the same harness:
  1. Seasonal-naive: same hour, one week earlier.
  2. LightGBM on calendar + weather features. Weather uses actuals as a stand-in for a weather forecast ("perfect weather forecast" assumption); state this limitation.
  3. TimesFM 2.5 zero-shot, with covariates if supported. Install and call it exactly as the official `google-research/timesfm` README says; don't guess the API. Runs on CPU.
- Effect-recovery check: did the models pick up the rain, Ramadan and payday effects that were planted?

## Repo layout
```
data/raw/         real inputs (weather), committed
data/processed/   simulated dataset + anomalies_truth.csv
src/              config.py, fetch_weather.py, calendar_features.py, simulate.py, backtest.py, models.py
notebooks/        01_eda, 02_models, 03_miss_investigation (thin: call src/ functions)
reports/          charts + results page
docs/             assumptions.md, walkthrough.md
```

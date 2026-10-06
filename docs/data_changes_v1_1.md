# Data changes: v1.1

**Data note:** semi-synthetic. Real weather and calendar; order and courier volumes simulated from the stated assumptions in `docs/assumptions.md`. Not company data.

**v1** = commit `7f5f0cd` (see `docs/data_changes_v1.md`). **v1.1** = commit `32de126`, after a second, independent review of the data that re-ran everything and re-measured every documented number.

Regenerate with `python src/calendar_features.py` then `python src/simulate.py`. Re-running gives byte-identical files.

---

## 1. Summary

| # | Change | Type | File |
|---|---|---|---|
| 1 | Minimum fleet of 30 couriers online every hour | Bug fix (simulation artefact) | `src/simulate.py` |
| 2 | Pinned `tzdata` used on every OS, plus a check that fails loudly | Reproducibility | `src/calendar_features.py` |
| 3 | Python version noted | Reproducibility | `requirements.txt` |
| 4 | EDA fleet chart: demand and completed orders per courier, against the cap | Correctness | `notebooks/01_eda.ipynb` |
| 5 | Censoring result shown as dependent on the assumed cap | Defensibility | `docs/assumptions.md`, notebook section 7 |
| 6 | Wrong documented numbers corrected | Consistency | `docs/assumptions.md`, `docs/data_changes_v1.md` |
| 7 | Censoring outside rain, 2025 Ramadan end date and `rain_forecast` limits documented | Documentation | `docs/assumptions.md`, `src/calendar_features.py` |

---

## 2. Changes in detail

**1. Minimum fleet** (`MIN_COURIERS_ONLINE = 30`)
- Problem: at night only about 10 couriers were expected online. A Poisson count that small often falls below demand / 4 by chance, so `orders_completed` showed a night-time courier shortage in 8-10% of night hours. That was an artefact, not a planted effect.
- Fix: `supply_mean = np.maximum(supply_mean, MIN_COURIERS_ONLINE)`, applied **before** the rain penalty, so couriers still drop 25-30% in rain at every hour.
- Why 30: the smallest round value that brings night capping under about 1.5% in all three cities (20 left Lagos at 5.5%).
- Effect: night couriers carry about 1.2 orders an hour (spare capacity, as a platform's minimum coverage would have).

**2. Timezone database**
- Problem: on Linux and macOS, Python reads the system timezone database before the pinned `tzdata` package. An older system database lacks Morocco's move to permanent UTC+0 on 2026-09-20 and would shift Casablanca's local hours for the last 10 days, inside the backtest window.
- Fix: `zoneinfo.reset_tzpath(to=[])` (always use the pinned package), then a check that raises an error unless Casablanca is on UTC+0 on 2026-09-25.

**3. Python version**: tested on Python 3.13.1, noted in `requirements.txt`.

**4. Fleet chart (EDA section 4)**
- Problem: the chart showed 4.7 orders per courier in rain while the simulator caps a courier at 4 an hour, and the text said couriers "carry" 1.6x more.
- Fix: two bars, demand per courier and completed orders per courier, with the cap drawn. Demand per courier rises about 1.6x in rain; couriers carry only about 1.35x; the rest is lost.

**5. Cap sensitivity**
- The headline "censoring hides most of the rain effect" depends on the cap of 4 orders per courier-hour: at peak, rain lifts load from about 3.0 to about 4.8 per courier, above 4 almost by construction.
- Casablanca, rainy peak hours: cap 3.5 → 96% capped, completed uplift -1%; **cap 4 → 81%, +11%**; cap 5 → 15%, +23%; cap 6 → 0%, +24% (true demand uplift +24%).
- Framing: the **direction** is the finding (recorded orders under-state the rain effect when the fleet is short); the **size** is an assumption.

**6. Corrected numbers** (first versions did not match the data)

| Claim | Was | Measured |
|---|---|---|
| Dry orders per courier by hour, v0 | 1.15 to 7.5 | 0.3 to 7.4 |
| Dry orders per courier by hour, v1 | about 2.0 to 3.0 | about 1.6 to 3.0 (v1.1: 1.2 to 3.0, minimum fleet at night) |
| Day-level noise, Casablanca (v0 / v1) | 3.1% / 5.3% | 3.2% / 5.1% |
| Hour-to-hour correlation of errors | about 0.12 | about 0.07 (0.10 in peak hours) |
| Best possible WMAPE, v0 | about 8.5% | about 9.0% (v1: 9.5%, correct) |
| Demand lost in rainy peak hours (Casa / Nairobi / Lagos) | 18 / 14 / 23% | 11 / 12 / 21% (v1.1: 11 / 12 / 22%) |
| Net Ramadan effect outside Casablanca | roughly 0 | Lagos +4%, Nairobi +1.5% |

**7. Newly documented**
- **Censoring outside rain** (supply is planned on normal days): Ramadan evenings 37% of hours capped in Casablanca; known promo peaks 14-24%; last-8-week peaks 6-8% (after the structural break). This is the ops point of the Ramadan chart.
- **Ramadan 2025**: the window is 1-2 days early at both ends, so 30 March 2025, a real fasting day in Morocco, is treated as Eid (+10% holiday). 2026 starts 1 day early and ends on the right day.
- **`rain_forecast`**: false alarms are spread evenly over the year. In Casablanca's last 8 weeks there is 1 rainy hour and 16 of 17 forecast-rainy hours are false alarms (Nairobi: 17 rainy hours; Lagos: 184). The perfect-vs-forecast weather comparison only means something in Lagos or the February-March 2026 window (Casablanca: 65 rainy hours and all of Ramadan).

---

## 3. What changed in the data files

| Column | v1 → v1.1 |
|---|---|
| `orders` (the forecast target) | **Unchanged, value for value** |
| all calendar and weather columns | Unchanged |
| `couriers_online`, `orders_completed`, `rain_forecast` | **Redrawn** |

Why the redraw: numpy's Poisson sampler uses a variable number of random numbers, so changing any courier mean shifts every random draw after it, including `rain_forecast` (drawn last). The new values are the same kind of noise; all documented effects still hold. `anomalies_truth.csv` and `promo_calendar.csv` are unchanged.

Any result computed on v1 that used `couriers_online`, `orders_completed` or `rain_forecast` must be re-run. Results on `orders` alone (e.g. the seasonal-naive backtest) are unaffected.

---

## 4. Effect on the numbers (measured, v1 → v1.1)

| Measure | v1 | v1.1 |
|---|---|---|
| Night hours (00-07) capped by couriers (Casa / Nairobi / Lagos) | 7.6 / 10.4 / 8.6% | 0.2 / 0.1 / 1.5% |
| All hours capped | 4.6 / 5.2 / 7.4% | 1.4 / 1.3 / 4.8% |
| Rainy peak hours capped | 81 / 69 / 92% | 81 / 72 / 94% |
| Rain uplift in `orders_completed` (demand: +24 / +18 / +27%) | +9 / +6 / +4% | +11 / +5 / +4% |
| Casablanca fleet chart, rain: demand vs completed per courier | 4.70 vs 3.87 | 4.65 vs 3.84 |
| Ramadan evenings capped (Casablanca) | 44% | 37% |
| `rain_forecast` hit rate (Casa / Nairobi / Lagos; planted 0.70) | 0.70 / 0.69 / 0.70 | 0.75 / 0.68 / 0.72 |

---

## 5. Known limits (unchanged, still true)

- Weather actuals at one point per city; `rain` column is identical to `precipitation`.
- Supply does not react to Ramadan, the known promo or the structural break (documented, deliberate).
- Casablanca's local clock repeats an hour on 2026-09-20, inside the backtest window: anything "a week earlier" must be matched on local wall-clock time, not 168 rows back.
- Planted outages are logged as zeros: the backtest needs a rule for scoring them and for lags that fall on them.

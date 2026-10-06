# Data changes: v1

**Data note:** semi-synthetic. Real weather and calendar; order and courier volumes simulated from the stated assumptions in `docs/assumptions.md`. Not company data.

**v0** = the dataset from the first simulator commit (`8b19a19`). **v1** = this version, after a review of the data-creation method. Every change below was made to fix a bug, make an assumption more defensible, or add something a real delivery dataset would have. All parameters stay fictional and are listed in `docs/assumptions.md`.

Regenerate with `python src/calendar_features.py` then `python src/simulate.py` (pinned versions in `requirements.txt`). Re-running gives byte-identical files.

---

## 1. Summary

| # | Change | Type | Why |
|---|---|---|---|
| 1 | Courier supply: 1-hour lag → 3-hour smoothed demand | Bug fix | The lag gave impossible utilisation (7.5 orders per courier at 11:00, 1.15 at 15:00) |
| 2 | Hourly profile wraps around midnight | Bug fix | Orders fell 9x between 23:00 and 00:00 |
| 3 | Partial local days dropped | Bug fix | UTC-based fetch left incomplete first/last local days, including a fake "crash" on 2026-10-01 |
| 4 | Library versions pinned | Reproducibility | `holidays` and `tzdata` versions change Ramadan and Casablanca's clock |
| 5 | One random generator per city | Reproducibility | Removing a city changed another city's numbers |
| 6 | Payday window at the start of the data | Bug fix | 1-2 Oct 2024 were missing from the 30 Sept payday window |
| 7 | Holidays by type (Eid al-Adha, mourning day: no uplift) | Assumption | One +10% for every holiday was hard to defend |
| 8 | Post-iftar window starts 19:00, not 20:00 | Assumption | Iftar is about 18:20-19:00 in Casablanca |
| 9 | Lagos structural break moved off Mawlid | Anomaly placement | The break and a public holiday started the same day |
| 10 | Daily demand shock | Realism | Errors were independent hour by hour; real demand has busy and quiet days |
| 11 | A known promo in the history + promo calendar | Realism | The training history was perfectly clean |
| 12 | `orders_completed` (capped by courier capacity) | Realism | Shows censored demand, the biggest gap versus real data |
| 13 | `rain_forecast` (imperfect weather forecast) | Realism | Lets the backtest compare perfect weather with a realistic forecast |
| 14 | Docs and EDA notebook corrected | Consistency | Several claims did not match the data |

---

## 2. Changes in detail

### Bug fixes

**1. Courier supply** (`src/simulate.py`, courier block)
- v0: `baseline.shift(1).bfill() / 2.5`: couriers followed demand one hour late. Because demand rises 2-3x per hour at the start of each peak, the fleet was 3x short at noon and idle at 15:00 every normal day.
- v1: `baseline.rolling(3, center=True, min_periods=1).mean() / 2.5`. Couriers work shifts, so supply is a smoothed version of normal demand.
- Result: dry orders per courier now runs from about 2.0 on the shoulders to 3.0 at the peaks (v0: 1.15 to 7.5).

**2. Midnight cliff** (`hourly_profile`)
- v0: the dinner peak was measured on a straight line, so hour 0 got nothing from a 20:30 dinner peak.
- v1: distance on a 24-hour clock: `np.minimum(abs(h - peak), 24 - abs(h - peak))`.
- Result: hour 0 share 5.2‰ → 17.5‰; demand now fades gradually after 23:00.

**3. Partial days** (`build_calendar`)
- v0: weather is fetched by UTC day, so in local time the first day was incomplete (21-23 hours) and Nairobi/Lagos had a 1-3 hour stub of 2026-10-01 (flagged as Nigeria's National Day).
- v1: only full local days are kept.
- Result: the period is **2024-10-02 to 2026-09-30**, local time. Rows: 17,496 (Casablanca 17,497 because of its clock changes).

**6. Payday at the start** (`build_calendar`)
- v0: the day list started on the first data day, so the 30 Sept 2024 payday was unknown and 1-2 Oct 2024 were not in a window.
- v1: the day list starts 3 days early.

### Reproducibility

**4. Pinned versions** (`requirements.txt`): pandas 3.0.6, numpy 2.5.3, holidays 0.106, tzdata 2026.5, lightgbm 4.7.0, matplotlib 3.11.2, pyarrow 25.0.1, requests 2.34.2, jupyter 1.1.1. A newer `holidays` can move estimated Eid dates (and so Ramadan); `tzdata` sets Casablanca's clock changes, including the move to permanent UTC+0 on 2026-09-20.

**5. One random generator per city** (`main`)
- v0: one generator shared in sequence, so dropping Casablanca changed Nairobi by about 35 orders/hour.
- v1: `default_rng(SEED + offset)`: Casablanca 42, Nairobi 43, Lagos 44.

### Assumptions

**7. Holidays by type**
- New `holiday_name` column. Holidays matching "adha" or "mourning" get no uplift; all others keep +10%.
- Eid al-Adha is a home feast, so plausibly no delivery uplift; a mourning day is not a treat day.
- Affects 4 days in Casablanca and 6 in Lagos. Because `is_holiday` now mixes the two kinds, a model sees about +8 to +10% on average, not exactly +10%.

**8. Post-iftar window**: Ramadan evening uplift now covers 19:00-23:59 (v0: 20:00-23:59). Net effect of Ramadan on Casablanca's daily total: about +7% → about +11%.

**9. Lagos structural break**: 26 Aug → 27 Aug 2026, the day after Mawlid, so they don't overlap. Casablanca's busy August (break on 12 Aug, five holidays, outage on 27 Aug) is kept on purpose and documented.

### Realism

**10. Daily shock**: one lognormal multiplier per local day (sd 0.04), shared by all its hours.

**11. Known promo**: "autumn_promo", 21-23 Nov 2025, all cities, +30% every hour. New `is_promo` column and `data/processed/promo_calendar.csv`. Models **may** read the calendar (it gives dates, not the uplift). The answer key `anomalies_truth.csv` is unchanged in purpose: models must not read it.

**12. `orders_completed`** = min(`orders`, `couriers_online` x 4). `orders` stays true demand; `orders_completed` is what a real platform would record. 4 deliveries per courier-hour is an assumed maximum with batching.

**13. `rain_forecast`**: a rainy hour is forecast as rainy 70% of the time, a dry hour 1% of the time. Same skill at every horizon (a simplification). Drawn last, so it doesn't change any other column.

### Documentation and notebook

**14.** `docs/assumptions.md`:
- states the effective period;
- gives growth as "+20% of the starting level per year (about +18% year on year in year 2)";
- calls 2.5 orders per courier a daily-average, illustrative ratio;
- cites tzdata 2026.5;
- compares Ramadan dates with Morocco's official ones (the data starts 1-2 days early);
- adds every new parameter and a censored-demand table.

`notebooks/01_eda.ipynb`:
- new section 0 (timezone data-quality check: 5 clock shifts, 3 repeated local hours);
- rain threshold imported from the simulator, with rainy-hour counts shown;
- fleet chart uses ratio of sums;
- payday chart excludes Aug-Sep 2026, so the unexplained oddities don't leak in;
- Ramadan and payday takeaways reworded to match the data;
- new section 7 on censored demand.

---

## 3. New columns and files

| Name | Type | Meaning |
|---|---|---|
| `orders_completed` | int | Orders a platform would record: demand capped by courier capacity |
| `rain_forecast` | bool | Imperfect "forecast" of rain > 0.5 mm/h |
| `holiday_name` | str | Holiday name from the `holidays` library, "" on normal days |
| `is_promo` | bool | Known promo day (from the promo calendar) |
| `data/processed/promo_calendar.csv` | file | Known promos: city, name, start, end. Models may read it |

---

## 4. Effect on the numbers (measured)

| Measure | v0 | v1 |
|---|---|---|
| Rows per city | 17,520 | 17,496 (Casablanca 17,497) |
| Period (local) | partial 2024-10-01 to partial 2026-10-01 | 2024-10-02 to 2026-09-30, full days |
| Mean orders/day (Casa / Nairobi / Lagos) | 7,710 / 6,433 / 10,416 | 7,738 / 6,440 / 10,466 |
| Dry orders per courier, by hour | 1.15 to 7.5 | about 2.0 to 3.0 |
| Order share at 00:00 (Casablanca) | 5.2‰ | 17.5‰ |
| Ramadan effect on Casablanca's daily total | about +7% | about +11% |
| Day-level noise (sd of actual / true mean) | 3.1% | 5.3% |
| Hour-to-hour correlation of errors | about 0 | about 0.12 |
| Best possible WMAPE (true mean as forecast, clean weeks) | about 8.5% | about 9.5% |
| Rainy peak hours capped by couriers (Casablanca) | n/a | 81% (dry: 0.3%) |
| Rain uplift: demand vs completed (Casablanca) | n/a | +24% vs +9% |

Planted effects (rain, Ramadan, payday, holiday, courier penalty) still recover within a few points of their documented values.

---

## 5. Not changed

- Weather CSVs (not re-fetched; the archive revises recent values).
- All other effect sizes, the growth rate and the noise parameter (k = 100).
- The three planted anomalies per city (only the Lagos break date moved by one day).
- The redundant `rain` column, which is identical to `precipitation`.
- Known limits: weather actuals at one point per city; Ramadan dates 1-2 days early for Morocco; the backtest window (last 8 weeks) has almost no rain and no Ramadan, so a February-March window is planned for the effect-recovery check.

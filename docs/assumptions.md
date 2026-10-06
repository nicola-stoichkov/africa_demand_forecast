# Simulation assumptions

Every parameter used to simulate orders and couriers, with a one-line justification. All numbers are **fictional** and chosen for a clear, learnable signal. Edit freely, then re-run `python src/simulate.py`. These are also the "true" effects the models should recover.

Real inputs: hourly weather (Open-Meteo archive) and public calendars (`holidays` library). Simulated outputs: orders and couriers online. Random seed: 42.

## Shared by all cities

| Parameter | Value | Why |
|---|---|---|
| Hourly profile | 0.05 night floor + lunch peak (13:00, sd 1.3h) + dinner peak (weight 1.3x lunch, sd 1.6h), normalised to sum 1 | Typical food-delivery shape: quiet night, lunch bump, bigger dinner peak |
| Weekday factor | Mon-Wed 0.95, Thu 1.00, Fri-Sat 1.15, Sun 1.10 | Weekends/Fridays are busier |
| Rain threshold | precipitation > 0.5 mm/h | Light drizzle is ignored; clear "it is raining" signal |
| Public holiday | orders x1.10 | People at home order more (a choice, not a fact) |
| Payday | orders x1.07 on payday and the 2 days after; paydays = last day of month (+ the 25th in Nairobi) | Money in the account lifts spend; Nairobi 25th is an assumption |
| Growth | +20% per year, linear | Young market scaling up |
| Count noise | Negative binomial, k = 100 | Real orders are noisier than Poisson |
| Courier supply | baseline demand (no rain/holiday/Ramadan/payday) lagged 1h, / 2.5 orders per courier, Poisson noise | Couriers follow typical demand, they do not know about weather or events |
| Ramadan daytime hours | 09:00-16:59 | Fasting hours: daytime dip |
| Ramadan evening hours | 20:00-23:59 | Post-iftar window |
| Ramadan dip / spike | daytime -35% x strength, evening +50% x strength | Strength differs per city (below) |

## Per city

| Parameter | Casablanca | Nairobi | Lagos | Why |
|---|---|---|---|---|
| Base daily orders (at start, before growth/weekday) | 6,000 | 5,000 | 8,000 | Arbitrary round scale; Lagos is the biggest market |
| Dinner peak hour | 20:30 | 19:30 | 19:30 | Dinner is later in Morocco |
| Rain demand uplift | +20% | +20% | +25% | Rain keeps people at home; Lagos more traffic-bound |
| Rain courier penalty | -25% | -25% | -30% | Couriers avoid riding in rain |
| Ramadan strength | 1.0 | 0.2 | 0.5 | Strong in Morocco, mixed population in Lagos, small in Nairobi |

## Calendar notes

- **Ramadan** = the 30 days before the first day of Eid al-Fitr, from the `holidays` library (estimated dates). Approximate; can be off by about a day.
- **Timezones:** weather is downloaded in UTC (continuous, unambiguous) and converted to each city's real local time. Open-Meteo itself keeps Casablanca at UTC+1 during Ramadan, when Morocco is really on UTC+0, so its "local" weather would be an hour off for about 40 days a year. Casablanca's clock shifts in the data: back one hour on 2025-02-23 and 2026-02-15, forward on 2025-04-06 and 2026-03-22, and a permanent move to UTC+0 on 2026-09-20 (per the timezone database).
- **AFCON 2025:** skipped (match dates not sourced).

## Planted anomalies (answer key in `data/processed/anomalies_truth.csv`)

Models and the miss investigation must not read that file until the investigation is written. All fall inside the 8-week backtest window.

| City | Structural break (+15%, permanent) | Outage (orders and couriers logged as 0) | Promo spike |
|---|---|---|---|
| Casablanca | from 2026-08-12 | 2026-08-27 15:00 to 2026-08-28 03:00 | 2026-09-11 to 09-13, +40% |
| Nairobi | from 2026-08-19 | 2026-09-02 10:00 to 22:00 | 2026-09-18 to 09-20, +35% |
| Lagos | from 2026-08-26 | 2026-09-09 06:00 to 18:00 | 2026-09-04 to 09-06, +45% |

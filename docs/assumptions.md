# Simulation assumptions

Every parameter used to simulate orders and couriers, with a one-line justification. All numbers are **fictional** and chosen for a clear, learnable signal. Edit freely, then re-run `python src/simulate.py`. These are also the "true" effects the models should recover.

Real inputs: hourly weather (Open-Meteo archive) and public calendars (`holidays` library). Simulated outputs: orders and couriers online. Random seed: 42, one generator per city (Casablanca 42, Nairobi 43, Lagos 44), so adding or removing a city never changes another city's numbers.

**Period:** full local days from 2024-10-02 to 2026-09-30. The weather is fetched from 2024-10-01 to 2026-09-30 in UTC, so the first local day is incomplete (and Nairobi/Lagos get a stub of 2026-10-01); those partial days are dropped.

## Shared by all cities

| Parameter | Value | Why |
|---|---|---|
| Hourly profile | 0.05 night floor + lunch peak (13:00, sd 1.3h) + dinner peak (weight 1.3x lunch, sd 1.6h, measured on a 24h clock so it tails off past midnight), normalised to sum 1 | Typical food-delivery shape: quiet night, lunch bump, bigger dinner peak that fades gradually after 23:00 |
| Weekday factor | Mon-Wed 0.95, Thu 1.00, Fri-Sat 1.15, Sun 1.10 | Weekends/Fridays are busier |
| Rain threshold | precipitation > 0.5 mm/h | Light drizzle is ignored; clear "it is raining" signal |
| Public holiday | orders x1.10, except Eid al-Adha and Nigeria's 2025 Day of Mourning: x1.00 | People at home order more (a choice, not a fact). Eid al-Adha is a home feast, so plausibly no delivery uplift; a mourning day is not a treat day. The `is_holiday` flag mixes both kinds, so a model sees about +8% on average, not +10% |
| Payday | orders x1.07 on payday and the 2 days after; paydays = last day of month (+ the 25th in Nairobi) | Money in the account lifts spend; Nairobi 25th is an assumption. 30 Sept 2024 (just before the data) still counts, so 1-2 Oct 2024 are in a window |
| Growth | linear: +20% of the starting level per year (so about +18% year on year in the second year) | Young market scaling up |
| Count noise | Negative binomial, k = 100 | Real orders are noisier than Poisson |
| Daily shock | one lognormal multiplier per local day, sd 0.04, shared by all hours of that day | Real demand has busy and quiet days nobody can explain, so forecast errors are correlated within a day, not independent hour by hour |
| Known promo | "autumn_promo" 21-23 Nov 2025, all cities, orders x1.30 every hour; listed in `data/processed/promo_calendar.csv` | Real history contains promos. This one is known (on the marketing calendar), so models may use it, unlike the unexplained promo spike in the answer key. The calendar gives dates, not the uplift: the model has to learn the effect |
| Courier capacity (completed orders) | `orders_completed` = min(orders, couriers online x 4) | 4 is the most a courier can deliver in an hour with batching (an assumption, well above the planned 2.5). `orders` is true demand; a real platform only records completed orders, so demand is *censored* when couriers run out, mostly in rainy peaks |
| Rain forecast | `rain_forecast`: a rainy hour is forecast as rainy 70% of the time, a dry hour 1% of the time | A stand-in for a real weather forecast, so the backtest can compare "perfect weather" with "realistic forecast". Same skill at every horizon (a simplification: real forecasts get worse further out) |
| Courier supply | baseline demand (no rain/holiday/Ramadan/payday), 3-hour centred average, / 2.5, Poisson noise | Couriers work shifts and plan around typical demand, so supply is smoother than demand and does not know about events. 2.5 is a daily-average ratio, illustrative, not a productivity claim: per hour it runs about 2.0 on the shoulders to 3.0 at the peaks |
| Ramadan daytime hours | 09:00-16:59 | Fasting hours: daytime dip |
| Ramadan evening hours | 19:00-23:59 | Post-iftar window: iftar (sunset) is about 18:20-19:00 local in Casablanca during Ramadan 2025-26 |
| Ramadan dip / spike | daytime -35% x strength, evening +50% x strength | Strength differs per city (below). Net effect on the daily total: about +11% in Casablanca, roughly 0 elsewhere |

## Per city

| Parameter | Casablanca | Nairobi | Lagos | Why |
|---|---|---|---|---|
| Base daily orders (at start, before growth/weekday) | 6,000 | 5,000 | 8,000 | Arbitrary round scale; Lagos is the biggest market |
| Dinner peak hour | 20:30 | 19:30 | 19:30 | Dinner is later in Morocco |
| Rain demand uplift | +20% | +20% | +25% | Rain keeps people at home; Lagos more traffic-bound |
| Rain courier penalty | -25% | -25% | -30% | Couriers avoid riding in rain |
| Ramadan strength | 1.0 | 0.2 | 0.5 | Strong in Morocco, mixed population in Lagos, small in Nairobi |

## Calendar notes

- **Ramadan** = the 30 days before the first day of Eid al-Fitr, from the `holidays` library (estimated dates). Approximate. Checked against Morocco's official announcements: 2025 was really 2 March to 30 March (Eid 31 March), the data uses 28 Feb to 29 March; 2026 was really 19 Feb to 19 March (Eid 20 March), the data uses 18 Feb to 19 March. So the window starts 1-2 days early, partly because Ramadan lasted 29 days in both years, not 30.
- **Timezones:** weather is downloaded in UTC (continuous, unambiguous) and converted to each city's real local time. Open-Meteo itself keeps Casablanca at UTC+1 during Ramadan, when Morocco is really on UTC+0, so its "local" weather would be an hour off for about 40 days a year. Casablanca's clock shifts in the data: back one hour on 2025-02-23 and 2026-02-15, forward on 2025-04-06 and 2026-03-22, and a permanent move to UTC+0 on 2026-09-20 (per IANA tzdata 2026.5, pinned in requirements.txt; an older timezone database would not have this change and would give different local hours after 20 Sept).
- **AFCON 2025:** skipped (match dates not sourced).

## Censored demand: what it does to the rain effect (measured)

Rain lifts true demand, but couriers are scarce in rain, so most rainy peak hours hit the capacity cap. Measured on the simulated data (peak hours 12-14 and 19-22, same hour rainy vs dry, normal days, Oct 2024-Jul 2026; same method as section 7 of the EDA notebook):

| | Casablanca | Nairobi | Lagos |
|---|---|---|---|
| Rainy peak hours capped by couriers (dry: under 1%) | 81% | 69% | 92% |
| Demand lost in rainy peak hours | 18% | 14% | 23% |
| Rain uplift seen in `orders` (demand) | +24% | +18% | +27% |
| Rain uplift seen in `orders_completed` | +9% | +6% | +4% |

So a model trained on completed orders would learn well under half the true rain effect and under-forecast demand exactly when couriers are short. The forecasts in this project target `orders` (demand). (The measured demand uplift sits a little above the planted +20/+20/+25% because of noise and the small number of rainy hours.)

## Planted anomalies (answer key in `data/processed/anomalies_truth.csv`)

Models and the miss investigation must not read that file until the investigation is written. All fall inside the 8-week backtest window.

| City | Structural break (+15%, permanent) | Outage (orders and couriers logged as 0) | Promo spike |
|---|---|---|---|
| Casablanca | from 2026-08-12 | 2026-08-27 15:00 to 2026-08-28 03:00 | 2026-09-11 to 09-13, +40% |
| Nairobi | from 2026-08-19 | 2026-09-02 10:00 to 22:00 | 2026-09-18 to 09-20, +35% |
| Lagos | from 2026-08-27 | 2026-09-09 06:00 to 18:00 | 2026-09-04 to 09-06, +45% |

Placement notes: the Lagos break starts the day after Mawlid (26 Aug, a Nigerian holiday), so the two don't overlap. Casablanca's window is deliberately busy: after the 12 Aug break come five Moroccan holidays (14, 20, 21, 25, 26 Aug), then the outage on 27 Aug. The investigation has to separate them.

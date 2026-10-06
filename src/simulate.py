"""Simulate hourly orders and couriers online from real weather + calendar.

    orders[t] = base_level x hourly_profile[hour] x weekday[dow] x rain x holiday
                x ramadan(hour) x payday x promo x growth(t) x daily_shock   -> negative-binomial noise
    couriers[t] = max(supply (3h-smoothed baseline demand), min night fleet) x rain penalty -> Poisson noise
    orders_completed[t] = min(orders, couriers x 4)   (demand above courier capacity is lost)

All parameters are FICTIONAL assumptions, listed in docs/assumptions.md.
Run from the repo root:  python src/simulate.py
Outputs: data/processed/demand_<city>.parquet, anomalies_truth.csv (answer key, models must not
read it) and promo_calendar.csv (known promos, models may read it)
"""
from pathlib import Path

import numpy as np
import pandas as pd

from calendar_features import build_calendar
from config import CITIES, SEED

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
SEED_OFFSET = {"casablanca": 0, "nairobi": 1, "lagos": 2}  # city seed = SEED + offset

# ---- assumptions shared by all cities --------------------------------------------------
WEEKDAY = {0: 0.95, 1: 0.95, 2: 0.95, 3: 1.00, 4: 1.15, 5: 1.15, 6: 1.10}  # Mon..Sun
RAIN_MM = 0.5            # precipitation above this (mm/h) counts as "rain"
HOLIDAY_EFFECT = 1.10    # public holiday: more people at home ordering
NEUTRAL_HOLIDAYS = "adha|mourning"  # no uplift: Eid al-Adha is a home feast; a mourning day is not a treat day
PAYDAY_EFFECT = 1.07     # payday and the two days after
GROWTH_PER_YEAR = 0.20   # linear order growth
NB_DISPERSION = 100      # negative binomial k: bigger = less noise
ORDERS_PER_COURIER = 2.5  # baseline: 1 courier online per 2.5 orders/hour
MIN_COURIERS_ONLINE = 30  # minimum fleet kept online for coverage, so quiet night hours are not short of couriers
RAMADAN_DAY_HOURS = range(9, 17)      # daytime fast
RAMADAN_EVENING_HOURS = range(19, 24)  # post-iftar window (iftar is about 18:20-19:00 in Casablanca)
DAILY_SHOCK_SD = 0.04    # whole-day demand shock (lognormal sd): busy and quiet days nobody can explain
MAX_ORDERS_PER_COURIER = 4  # most a courier can deliver in an hour (with batching): caps completed orders
RAIN_FORECAST_HIT = 0.70    # a rainy hour is forecast as rainy 70% of the time ...
RAIN_FORECAST_FALSE = 0.01  # ... and 1% of dry hours are wrongly forecast as rainy

# ---- known promos: in the promo calendar, so models MAY use them (local dates) ----------
PROMO_EFFECT = 0.30
KNOWN_PROMOS = [("autumn_promo", "2025-11-21", "2025-11-23")]  # same dates in every city

# ---- per-city assumptions --------------------------------------------------------------
PARAMS = {
    "casablanca": dict(daily_orders=6000, dinner_peak=20.5, rain_demand=0.20, rain_supply=0.25,
                       ramadan_strength=1.0),
    "nairobi": dict(daily_orders=5000, dinner_peak=19.5, rain_demand=0.20, rain_supply=0.25,
                    ramadan_strength=0.2),
    "lagos": dict(daily_orders=8000, dinner_peak=19.5, rain_demand=0.25, rain_supply=0.30,
                  ramadan_strength=0.5),
}
RAMADAN_DAY_DIP = 0.35       # x strength: daytime orders -35% in Casablanca
RAMADAN_EVENING_SPIKE = 0.50  # x strength: post-iftar orders +50% in Casablanca

# ---- planted anomalies (local time). type -> (start, end, magnitude) -------------------
ANOMALIES = {
    "casablanca": [
        ("structural_break", "2026-08-12 00:00", None, 0.15),
        ("outage", "2026-08-27 15:00", "2026-08-28 03:00", None),
        ("promo_spike", "2026-09-11 00:00", "2026-09-13 23:00", 0.40),
    ],
    "nairobi": [
        ("structural_break", "2026-08-19 00:00", None, 0.15),
        ("outage", "2026-09-02 10:00", "2026-09-02 22:00", None),
        ("promo_spike", "2026-09-18 00:00", "2026-09-20 23:00", 0.35),
    ],
    "lagos": [
        ("promo_spike", "2026-09-04 00:00", "2026-09-06 23:00", 0.45),
        ("structural_break", "2026-08-27 00:00", None, 0.15),  # day after Mawlid, so they don't overlap
        ("outage", "2026-09-09 06:00", "2026-09-09 18:00", None),
    ],
}


def hourly_profile(dinner_peak):
    """Share of the day's orders in each hour (24 values summing to 1): lunch + dinner peaks."""
    h = np.arange(24)
    lunch = 1.0 * np.exp(-0.5 * ((h - 13) / 1.3) ** 2)
    # Distance on a 24h clock, so the late dinner tail runs past midnight (23:00 -> 00:00 -> 01:00).
    dist = np.minimum(np.abs(h - dinner_peak), 24 - np.abs(h - dinner_peak))
    dinner = 1.3 * np.exp(-0.5 * (dist / 1.6) ** 2)
    night_floor = 0.05
    w = night_floor + lunch + dinner
    return w / w.sum()


def simulate_city(city_key, rng):
    p = PARAMS[city_key]
    df = build_calendar(city_key)
    profile = hourly_profile(p["dinner_peak"])

    days_since_start = (df["timestamp_utc"] - df["timestamp_utc"].iloc[0]).dt.total_seconds() / 86400
    growth = 1 + GROWTH_PER_YEAR * days_since_start / 365
    raining = (df["precipitation"] > RAIN_MM).to_numpy()

    # Baseline = what you'd expect with no rain, holiday, Ramadan or payday. Also drives courier supply.
    baseline = p["daily_orders"] * profile[df["hour"]] * df["dow"].map(WEEKDAY) * growth

    ramadan_mult = np.ones(len(df))
    s = p["ramadan_strength"]
    ram = df["is_ramadan"].to_numpy()
    ramadan_mult[ram & df["hour"].isin(RAMADAN_DAY_HOURS).to_numpy()] = 1 - RAMADAN_DAY_DIP * s
    ramadan_mult[ram & df["hour"].isin(RAMADAN_EVENING_HOURS).to_numpy()] = 1 + RAMADAN_EVENING_SPIKE * s

    # Known promos (from the promo calendar): whole local days, same uplift every hour.
    local = df["timestamp"]
    local_date = local.dt.tz_localize(None).dt.normalize()
    df["is_promo"] = False
    for name, start, end in KNOWN_PROMOS:
        df.loc[(local_date >= start) & (local_date <= end), "is_promo"] = True

    neutral_holiday = df["holiday_name"].str.lower().str.contains(NEUTRAL_HOLIDAYS)
    mean_orders = (baseline
                   * np.where(raining, 1 + p["rain_demand"], 1.0)
                   * np.where(df["is_holiday"] & ~neutral_holiday, HOLIDAY_EFFECT, 1.0)
                   * ramadan_mult
                   * np.where(df["is_payday_window"], PAYDAY_EFFECT, 1.0)
                   * np.where(df["is_promo"], 1 + PROMO_EFFECT, 1.0))

    # Planted anomalies that change demand (outage is applied after noise).
    tz = CITIES[city_key]["tz"]
    truth = []
    for kind, start, end, magnitude in ANOMALIES[city_key]:
        t0 = pd.Timestamp(start, tz=tz)
        t1 = pd.Timestamp(end, tz=tz) if end else local.iloc[-1]
        mask = ((local >= t0) & (local <= t1)).to_numpy()
        if kind in ("structural_break", "promo_spike"):
            mean_orders = np.where(mask, mean_orders * (1 + magnitude), mean_orders)
        truth.append(dict(city=CITIES[city_key]["name"], type=kind, start=t0, end=t1, magnitude=magnitude))

    # Daily shock: one random multiplier per local day, shared by all its hours, so errors are
    # correlated within a day (a busy day is busy all day), like real demand.
    days = local_date.unique()
    shock = pd.Series(rng.lognormal(0, DAILY_SHOCK_SD, len(days)), index=days)
    mean_orders = mean_orders * local_date.map(shock).to_numpy()

    # Negative binomial: Poisson-like counts with extra spread (real demand is noisier than Poisson).
    k = NB_DISPERSION
    orders = rng.negative_binomial(k, k / (k + mean_orders))

    # Couriers work shifts, so supply follows a smoothed (3-hour centred average) version of
    # baseline demand, not each hourly jump. A minimum fleet stays online at night (without it, small
    # Poisson courier counts randomly fall below demand / 4 in about 1 night hour in 10).
    # Fewer couriers when it rains, at every hour.
    supply_mean = baseline.rolling(3, center=True, min_periods=1).mean() / ORDERS_PER_COURIER
    supply_mean = np.maximum(supply_mean, MIN_COURIERS_ONLINE)
    supply_mean = supply_mean * np.where(raining, 1 - p["rain_supply"], 1.0)
    couriers = rng.poisson(supply_mean)

    df["orders"] = orders
    df["couriers_online"] = couriers
    for t in truth:
        if t["type"] == "outage":  # pipeline failure: the feed logs zeros
            m = ((local >= t["start"]) & (local <= t["end"])).to_numpy()
            df.loc[m, ["orders", "couriers_online"]] = 0

    # `orders` is true (unconstrained) demand. What a real platform records is completed orders,
    # capped by how many the couriers online can carry: demand above the cap is lost (censored).
    df["orders_completed"] = np.minimum(df["orders"], df["couriers_online"] * MAX_ORDERS_PER_COURIER)

    # A stand-in weather forecast for the backtest: misses some rain, adds some false alarms.
    # Drawn last, so it does not change the orders or couriers above.
    u = rng.random(len(df))
    df["rain_forecast"] = np.where(raining, u < RAIN_FORECAST_HIT, u < RAIN_FORECAST_FALSE)

    cols = ["timestamp", "timestamp_utc", "orders", "orders_completed", "couriers_online",
            "temperature_2m", "precipitation", "rain", "rain_forecast", "hour", "dow", "is_holiday",
            "holiday_name", "is_ramadan", "is_payday_window", "is_promo"]
    return df[cols], pd.DataFrame(truth)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_truth = []
    for key in CITIES:
        # One random generator per city, so adding/removing a city never changes the others.
        rng = np.random.default_rng(SEED + SEED_OFFSET[key])
        df, truth = simulate_city(key, rng)
        df.to_parquet(OUT_DIR / f"demand_{key}.parquet", index=False)
        all_truth.append(truth)
        print(f"{CITIES[key]['name']}: {len(df)} rows, mean orders/day {df['orders'].sum() / (len(df) / 24):.0f}")
    pd.concat(all_truth).to_csv(OUT_DIR / "anomalies_truth.csv", index=False)
    # The promo calendar is NOT the answer key: models may read it (like a real marketing calendar).
    promos = [dict(city=CITIES[key]["name"], name=n, start=s, end=e)
              for key in CITIES for n, s, e in KNOWN_PROMOS]
    pd.DataFrame(promos).to_csv(OUT_DIR / "promo_calendar.csv", index=False)


if __name__ == "__main__":
    main()

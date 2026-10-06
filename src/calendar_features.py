"""Hourly calendar table per city: local time, holiday, Ramadan, payday flags.

Time handling: weather is stored in UTC (continuous, no gaps or repeats). We convert it to
the city's real local time with tz_convert, so clock changes (Morocco: Ramadan, and the move
to permanent UTC+0 on 2026-09-20) are handled by the timezone database, not by us.
"""
from pathlib import Path

import holidays
import pandas as pd

from config import CITIES, END_DATE, START_DATE

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# Paydays assumed per city: last day of the month for all, plus the 25th in Nairobi.
EXTRA_PAYDAY_DOM = {"nairobi": 25}
PAYDAY_WINDOW_DAYS = 3  # payday itself + the 2 days after


def load_weather(city_key):
    """Weather CSV (UTC) -> DataFrame with a tz-aware local-time column 'timestamp'."""
    df = pd.read_csv(RAW_DIR / f"weather_{city_key}.csv", parse_dates=["time"])
    df["timestamp_utc"] = df["time"].dt.tz_localize("UTC")
    df["timestamp"] = df["timestamp_utc"].dt.tz_convert(CITIES[city_key]["tz"])
    return df.drop(columns="time")


def ramadan_dates(country, years):
    """Approximate Ramadan: the 30 days before the first day of Eid al-Fitr.

    Eid dates in the `holidays` library are estimated from the Islamic calendar, so this can be
    off versus the real moon-sighting: for Morocco it is 1-2 days early in 2025 (start and end) and
    starts 1 day early in 2026
    (see docs/assumptions.md). Good enough for a demand effect.
    """
    hol = holidays.country_holidays(country, years=years, language="en_US")
    eid_days = sorted(d for d, name in hol.items() if "fitr" in name.lower())
    first_eid_per_year = {}
    for d in eid_days:
        first_eid_per_year.setdefault(d.year, d)
    return [(pd.Timestamp(e) - pd.Timedelta(days=30), pd.Timestamp(e) - pd.Timedelta(days=1))
            for e in first_eid_per_year.values()]


def payday_window_flag(dates, city_key):
    """True on a payday and the following days. `dates` is a Series of local calendar dates."""
    d = pd.to_datetime(dates)
    is_month_end = d.dt.is_month_end
    extra = EXTRA_PAYDAY_DOM.get(city_key)
    is_payday = is_month_end | (d.dt.day == extra if extra else False)
    window = is_payday.copy()
    for k in range(1, PAYDAY_WINDOW_DAYS):
        window |= is_payday.shift(k, fill_value=False)
    return window


def build_calendar(city_key):
    """One row per hour: weather + hour, dow, is_holiday, is_ramadan, is_payday_window."""
    city = CITIES[city_key]
    df = load_weather(city_key)
    local_date = df["timestamp"].dt.tz_localize(None).dt.normalize()  # local calendar date

    # Weather starts/ends at UTC midnight, so the first local day (and, east of UTC, a stub of
    # 2026-10-01) is incomplete. Keep full local days only: 2024-10-02 to 2026-09-30.
    keep = (local_date > START_DATE) & (local_date <= END_DATE)
    df = df[keep].reset_index(drop=True)
    local_date = local_date[keep].reset_index(drop=True)

    df["hour"] = df["timestamp"].dt.hour
    df["dow"] = df["timestamp"].dt.dayofweek  # Monday = 0

    years = range(local_date.dt.year.min() - 1, local_date.dt.year.max() + 2)
    hol = holidays.country_holidays(city["country"], years=years, language="en_US")
    df["is_holiday"] = local_date.dt.date.isin(set(hol.keys()))
    df["holiday_name"] = local_date.dt.date.map(hol.get).fillna("")  # "" on normal days

    df["is_ramadan"] = False
    for start, end in ramadan_dates(city["country"], years):
        df.loc[(local_date >= start) & (local_date <= end), "is_ramadan"] = True

    # Payday flag is computed per calendar day, then mapped back onto the hours. The day list
    # starts 3 days early so a payday just before the data (30 Sept 2024) still opens a window.
    days = pd.Series(pd.date_range(local_date.min() - pd.Timedelta(days=PAYDAY_WINDOW_DAYS), local_date.max()))
    flag_by_day = pd.Series(payday_window_flag(days, city_key).values, index=days)
    df["is_payday_window"] = local_date.map(flag_by_day).astype(bool)
    return df


def check_time_index(df):
    """Data-quality check: UTC must be gap-free; local clock may repeat/skip hours at shifts."""
    steps = df["timestamp_utc"].diff().dropna().unique()
    offset = df["timestamp"].dt.strftime("%z")
    shifts = df.loc[offset != offset.shift(), ["timestamp_utc", "timestamp"]].iloc[1:]
    return {"utc_steps": [str(s) for s in steps], "n_rows": len(df), "clock_shifts": shifts}


if __name__ == "__main__":
    for key in CITIES:
        cal = build_calendar(key)
        print(f"\n== {CITIES[key]['name']} ==")
        print(cal[["is_holiday", "is_ramadan", "is_payday_window"]].sum().to_string())
        r = cal.loc[cal["is_ramadan"], "timestamp"].dt.date
        for y in sorted({d.year for d in r}):
            ry = r[[d.year == y for d in r]]
            print(f"Ramadan {y}: {ry.min()} -> {ry.max()}")
        info = check_time_index(cal)
        print("UTC steps:", info["utc_steps"], "| clock shifts:", len(info["clock_shifts"]))

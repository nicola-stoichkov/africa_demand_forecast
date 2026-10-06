"""Walk-forward backtest: weekly forecast origins, 7-day horizon, strictly chronological.

Every model is a function  fit_predict(history, future) -> one forecast per future row.
  history = every row before the origin (what the forecaster knew that day). Hours the
            data-quality rule flags as missing have NaN orders (see missing_hours).
  future  = the next 7 local days of rows, with the target columns removed
So a model may use the future's calendar and weather, never the future's orders.

Run from the repo root:  python src/backtest.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

from config import CITIES

PROCESSED_DIR = Path(__file__).resolve().parents[1] / "data" / "processed"
TARGET = "orders"  # true demand (not orders_completed, which is capped by couriers)
HIDDEN = ["orders", "orders_completed", "couriers_online"]  # never shown for the future
N_WEEKS = 8
# Window name -> first local day AFTER the window. Each window has 8 weekly origins.
WINDOWS = {
    "last_8_weeks": "2026-10-01",  # 6 Aug - 30 Sep 2026: all three planted anomalies, a robustness test
    "winter_2026": "2026-03-30",   # 2 Feb - 29 Mar 2026: rainy season + Ramadan, the cleaner accuracy test
}
MISSING_MIN_TYPICAL = 10  # an hour with 0 orders counts as missing if at least this many were expected


def load_city(city_key):
    return pd.read_parquet(PROCESSED_DIR / f"demand_{city_key}.parquet")


def missing_hours(df):
    """Data-quality rule: True for hours that look like a feed failure, not real demand.

    An hour is MISSING if orders == 0 and the median of the same local wall-clock hour over the
    previous 4 weeks is at least MISSING_MIN_TYPICAL (10). Why 10: with about 10 orders expected,
    a genuine zero has a Poisson probability of about 5 in 100,000 (exp(-10)), so a zero there is
    a broken feed. The rule only uses past weeks, so it can be applied the day it happens.

    Limits: it catches total feed failures only. Partial outages (half the orders lost), missing
    rows, late-arriving data and genuinely quiet zones need alerts and a human.
    """
    wall = df["timestamp"].dt.tz_localize(None)
    by_wall = df["orders"].groupby(wall).mean()  # a repeated local hour is averaged
    weeks_back = {k: by_wall.reindex(wall - pd.Timedelta(weeks=k)).to_numpy() for k in (1, 2, 3, 4)}
    typical = pd.DataFrame(weeks_back).median(axis=1).to_numpy()  # NaN in the first 4 weeks
    return (df["orders"].to_numpy() == 0) & (typical >= MISSING_MIN_TYPICAL)


def wmape(actual, forecast):
    """Sum of absolute errors / sum of actuals. Big hours weigh more, so quiet nights can't blow it up."""
    return np.abs(actual - forecast).sum() / actual.sum()


def bias(actual, forecast):
    """Sum(forecast - actual) / sum(actual). Positive = over-forecast, negative = under-forecast."""
    return (forecast - actual).sum() / actual.sum()


def origins(window_end, tz, n_weeks=N_WEEKS):
    """Weekly forecast origins at local midnight, oldest first.

    Built on the local calendar, then given the timezone, so every origin is 00:00 local
    even when the clock changes inside the window.
    """
    end = pd.Timestamp(window_end)
    return [(end - pd.Timedelta(weeks=k)).tz_localize(tz) for k in range(n_weeks, 0, -1)]


def run_backtest(df, fit_predict, window_end, tz, hidden=HIDDEN, clean=True):
    """Forecast each week from its origin; return one row per forecast hour (actual + forecast).

    hidden = columns removed from `future`. A model that must not see the actual weather (the
    imperfect-forecast variant) passes HIDDEN + ["precipitation", "rain"].
    clean=True: models see NaN instead of the missing hours in history (data-quality step done).
    clean=False: models see the raw history, zeros included.
    """
    missing = pd.Series(missing_hours(df), index=df.index)
    seen = df.copy()
    if clean:
        seen.loc[missing, HIDDEN] = np.nan
    rows = []
    for origin in origins(window_end, tz):
        week_end = (origin.tz_localize(None) + pd.Timedelta(days=7)).tz_localize(tz)
        history = seen[seen["timestamp"] < origin]
        in_week = (df["timestamp"] >= origin) & (df["timestamp"] < week_end)
        target = df[in_week]
        forecast = np.asarray(fit_predict(history, target.drop(columns=hidden)), dtype=float)
        # A NaN would silently drop out of the sums and flatter the score, and orders can't be
        # negative (models clip at 0 themselves), so stop instead.
        if len(forecast) != len(target) or np.isnan(forecast).any() or (forecast < 0).any():
            raise ValueError(f"bad forecast for origin {origin}: wrong length, NaN or negative")
        rows.append(target[["timestamp", "hour", TARGET]].assign(
            origin=origin, forecast=forecast, missing=missing[in_week].to_numpy()))
    return pd.concat(rows, ignore_index=True)


def score_one(g, peak_hours):
    peak = g["hour"].isin(peak_hours)
    return pd.Series({
        "wmape": wmape(g[TARGET], g["forecast"]),
        "bias": bias(g[TARGET], g["forecast"]),
        "peak_wmape": wmape(g.loc[peak, TARGET], g.loc[peak, "forecast"]),
        "hours": len(g),
    })


def score(forecasts, peak_hours, exclude_missing=True):
    """One row per forecast week, plus 'all' for the whole window. peak_hours: the city's peak hours.

    exclude_missing=True drops the hours flagged as missing before scoring (a feed failure is not a
    forecast failure); 'excluded' says how many. False scores every hour as recorded.
    """
    week = forecasts["origin"].dt.strftime("%Y-%m-%d")
    kept = ~forecasts["missing"] if exclude_missing else pd.Series(True, index=forecasts.index)
    weekly = forecasts[kept].groupby(week[kept]).apply(score_one, peak_hours=peak_hours)
    weekly["excluded"] = (~kept).groupby(week).sum()
    weekly.loc["all"] = score_one(forecasts[kept], peak_hours)
    weekly.loc["all", "excluded"] = (~kept).sum()
    return weekly.astype({"hours": int, "excluded": int})


def compare(city_key, models, window):
    """Score several models on one city and window, with the unmasked score and weekly wins.

    models: {name: (fit_predict, hidden_columns)}. Include "seasonal_naive" and "seasonal_naive_4wk"
    (the two baselines) so that weekly wins against them can be counted.
    Masked = models see cleaned history and missing hours are not scored. Unmasked = raw history,
    every hour scored.
    Returns (summary table, weekly masked WMAPE per model).
    """
    df = load_city(city_key)
    tz = CITIES[city_key]["tz"]
    peak_hours = CITIES[city_key]["peak_hours"]
    summary, weekly = {}, {}
    for name, (fit_predict, hidden) in models.items():
        masked = score(run_backtest(df, fit_predict, WINDOWS[window], tz, hidden, clean=True), peak_hours)
        raw = score(run_backtest(df, fit_predict, WINDOWS[window], tz, hidden, clean=False), peak_hours,
                    exclude_missing=False)
        summary[name] = {"wmape": masked.loc["all", "wmape"], "bias": masked.loc["all", "bias"],
                         "peak_wmape": masked.loc["all", "peak_wmape"],
                         "wmape_unmasked": raw.loc["all", "wmape"],
                         "hours_excluded": masked.loc["all", "excluded"]}
        weekly[name] = masked["wmape"].iloc[:-1]  # drop the 'all' row
    weekly = pd.DataFrame(weekly)
    for base in ("seasonal_naive", "seasonal_naive_4wk"):
        if base in weekly:
            for name in summary:
                summary[name][f"wins_vs_{base}"] = None if name == base else int((weekly[name] < weekly[base]).sum())
    return pd.DataFrame(summary).T, weekly


if __name__ == "__main__":
    from models import seasonal_naive, seasonal_naive_4wk

    models = {"seasonal_naive": (seasonal_naive, HIDDEN), "seasonal_naive_4wk": (seasonal_naive_4wk, HIDDEN)}
    for key in CITIES:
        for window in WINDOWS:
            table, weekly = compare(key, models, window)
            print(f"\n== {CITIES[key]['name']} | {window} ==")
            print(table.round(3).to_string())

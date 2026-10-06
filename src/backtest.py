"""Walk-forward backtest: weekly forecast origins, 7-day horizon, strictly chronological.

Every model is a function  fit_predict(history, future) -> one forecast per future row.
  history = every row before the origin, with orders (what the forecaster knew that day)
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
    "last_8_weeks": "2026-10-01",  # 6 Aug - 30 Sep 2026: the headline test
    "winter_2026": "2026-03-30",   # 2 Feb - 29 Mar 2026: rainy season + Ramadan, for effect recovery
}


def load_city(city_key):
    return pd.read_parquet(PROCESSED_DIR / f"demand_{city_key}.parquet")


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


def run_backtest(df, fit_predict, window_end, tz):
    """Forecast each week from its origin; return one row per forecast hour (actual + forecast)."""
    rows = []
    for origin in origins(window_end, tz):
        week_end = (origin.tz_localize(None) + pd.Timedelta(days=7)).tz_localize(tz)
        history = df[df["timestamp"] < origin]
        target = df[(df["timestamp"] >= origin) & (df["timestamp"] < week_end)]
        forecast = np.asarray(fit_predict(history, target.drop(columns=HIDDEN)), dtype=float)
        # A NaN would silently drop out of the sums and flatter the score, so stop instead.
        if len(forecast) != len(target) or np.isnan(forecast).any():
            raise ValueError(f"bad forecast for origin {origin}: wrong length or NaN")
        rows.append(target[["timestamp", "hour", TARGET]].assign(origin=origin, forecast=forecast))
    return pd.concat(rows, ignore_index=True)


def score_one(g, peak_hours):
    peak = g["hour"].isin(peak_hours)
    return pd.Series({
        "wmape": wmape(g[TARGET], g["forecast"]),
        "bias": bias(g[TARGET], g["forecast"]),
        "peak_wmape": wmape(g.loc[peak, TARGET], g.loc[peak, "forecast"]),
        "hours": len(g),
    })


def score(forecasts, peak_hours):
    """One row per forecast week, plus 'all' for the whole window. peak_hours: the city's peak hours."""
    weekly = forecasts.groupby(forecasts["origin"].dt.strftime("%Y-%m-%d")).apply(score_one, peak_hours=peak_hours)
    weekly.loc["all"] = score_one(forecasts, peak_hours)
    weekly["hours"] = weekly["hours"].astype(int)
    return weekly


if __name__ == "__main__":
    from models import seasonal_naive

    key = "casablanca"  # Casablanca first; the other cities come later via config
    df = load_city(key)
    tz = CITIES[key]["tz"]
    for name, end in WINDOWS.items():
        print(f"\n== {CITIES[key]['name']} | seasonal-naive | {name} ==")
        print(score(run_backtest(df, seasonal_naive, end, tz), CITIES[key]["peak_hours"]).round(3).to_string())

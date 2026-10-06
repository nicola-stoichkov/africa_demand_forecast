"""Forecast models. Each is  fit_predict(history, future) -> one forecast per row of `future`.

history["orders"] is NaN for hours the data-quality rule flagged as missing (see backtest.missing_hours),
so every model here must cope with NaN history.
"""
import pandas as pd


def past_by_wall_clock(history):
    """Orders indexed by local wall-clock time (no timezone). A repeated local hour (clock put
    back) appears twice, so its two values are averaged; NaN hours stay NaN."""
    wall = history["timestamp"].dt.tz_localize(None)
    return history["orders"].groupby(wall).mean()


def weeks_earlier(past, future, weeks):
    """Orders at the same local wall-clock hour `weeks` weeks before each future row.

    Matched on local time, not "168 rows back": after a clock change (Casablanca has five),
    168 rows back is a different local hour. Hours with no history (a skipped spring-forward
    hour, a missing hour, or before the data starts) come back NaN.
    """
    wanted = future["timestamp"].dt.tz_localize(None) - pd.Timedelta(weeks=weeks)
    return past.reindex(wanted.to_numpy()).to_numpy()


def seasonal_naive(history, future):
    """Baseline: the same local hour, 7 days earlier. Every other model must beat this.

    If that hour is missing, use the same hour 2, then 3, then 4 weeks earlier. After that,
    ffill(limit=1) covers only a single skipped spring-forward hour; any longer gap stays NaN,
    so run_backtest stops instead of silently repeating a stale value.
    """
    past = past_by_wall_clock(history)
    forecast = pd.Series(weeks_earlier(past, future, 1))
    for weeks in (2, 3, 4):
        forecast = forecast.fillna(pd.Series(weeks_earlier(past, future, weeks)))
    return forecast.ffill(limit=1).to_numpy()


def seasonal_naive_4wk(history, future):
    """Baseline 2: the mean of the same local hour 1, 2, 3 and 4 weeks earlier (missing hours skipped).

    Averaging four weeks smooths out noise and one-off events, so it is a much stronger baseline
    than one week earlier, except when the weekly shape changes (e.g. Ramadan starts).
    """
    past = past_by_wall_clock(history)
    lags = pd.DataFrame({w: weeks_earlier(past, future, w) for w in (1, 2, 3, 4)})
    return lags.mean(axis=1).to_numpy()  # mean() skips NaN; all four missing -> NaN -> run_backtest stops

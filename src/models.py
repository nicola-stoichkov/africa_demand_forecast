"""Forecast models. Each is  fit_predict(history, future) -> one forecast per row of `future`."""
import pandas as pd


def seasonal_naive(history, future):
    """Baseline: the same local hour, 7 days earlier. Every other model must beat this.

    Matched on local wall-clock time, not "168 rows back": after a clock change (Casablanca
    has five), 168 rows back is a different local hour. At a fall-back a local hour appears
    twice, so its two values are averaged; if the hour a week earlier was skipped by a
    spring-forward, the hour before it is used instead.
    """
    wall = history["timestamp"].dt.tz_localize(None)  # local clock time, no timezone
    past = history["orders"].groupby(wall).mean()
    wanted = future["timestamp"].dt.tz_localize(None) - pd.Timedelta(days=7)
    return past.reindex(wanted.to_numpy()).ffill().to_numpy()

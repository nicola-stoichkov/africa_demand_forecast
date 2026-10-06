"""Download hourly weather per city from the Open-Meteo archive (free, no key).

Run from the repo root:  python src/fetch_weather.py
Output: data/raw/weather_<city>.csv  (columns: time [UTC], temperature_2m, precipitation, rain)
"""
from pathlib import Path

import pandas as pd
import requests

from config import CITIES, END_DATE, START_DATE

URL = "https://archive-api.open-meteo.com/v1/archive"
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def fetch_city(city):
    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "start_date": START_DATE,
        "end_date": END_DATE,
        "hourly": "temperature_2m,precipitation,rain",
        # UTC on purpose: Open-Meteo keeps Casablanca at UTC+1 even during Ramadan, when
        # Morocco is really on UTC+0. UTC is unambiguous; we convert to local time later.
        "timezone": "GMT",
    }
    response = requests.get(URL, params=params, timeout=60)
    response.raise_for_status()
    df = pd.DataFrame(response.json()["hourly"])
    df["time"] = pd.to_datetime(df["time"])  # UTC
    return df


def main():
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for key, city in CITIES.items():
        df = fetch_city(city)
        path = RAW_DIR / f"weather_{key}.csv"
        df.to_csv(path, index=False)
        print(f"{city['name']}: {len(df)} rows, {df['time'].min()} -> {df['time'].max()}, saved {path.name}")


if __name__ == "__main__":
    main()

"""Central settings: cities, period, seed. Every other script imports from here."""

START_DATE = "2024-10-01"
END_DATE = "2026-09-30"
SEED = 42

# key = lowercase city name, used in file names (data/raw/weather_<key>.csv)
# peak_hours = lunch + dinner hours (each >= ~7.5% of the daily orders), the hours ops care about most.
# Dinner is one hour later in Casablanca (20:30 peak vs 19:30).
CITIES = {
    "casablanca": {"name": "Casablanca", "country": "MA", "lat": 33.57, "lon": -7.59, "tz": "Africa/Casablanca",
        "peak_hours": [12, 13, 14, 19, 20, 21, 22]},
    "nairobi": {"name": "Nairobi", "country": "KE", "lat": -1.29, "lon": 36.82, "tz": "Africa/Nairobi",
        "peak_hours": [12, 13, 14, 18, 19, 20, 21]},
    "lagos": {"name": "Lagos", "country": "NG", "lat": 6.52, "lon": 3.38, "tz": "Africa/Lagos",
        "peak_hours": [12, 13, 14, 18, 19, 20, 21]},
}

# Shown on every chart and notebook
DATA_NOTE = "Semi-synthetic: real weather and calendar, simulated orders and couriers. Not company data."

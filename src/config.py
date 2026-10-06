"""Central settings: cities, period, seed. Every other script imports from here."""

START_DATE = "2024-10-01"
END_DATE = "2026-09-30"
SEED = 42

# key = lowercase city name, used in file names (data/raw/weather_<key>.csv)
CITIES = {
    "casablanca": {"name": "Casablanca", "country": "MA", "lat": 33.57, "lon": -7.59, "tz": "Africa/Casablanca"},
    "nairobi": {"name": "Nairobi", "country": "KE", "lat": -1.29, "lon": 36.82, "tz": "Africa/Nairobi"},
    "lagos": {"name": "Lagos", "country": "NG", "lat": 6.52, "lon": 3.38, "tz": "Africa/Lagos"},
}

# Shown on every chart and notebook
DATA_NOTE = "Semi-synthetic: real weather and calendar, simulated orders and couriers. Not company data."

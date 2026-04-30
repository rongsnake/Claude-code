"""
CDS (Copernicus Climate Data Store) scraper.

Downloads ERA5 reanalysis data via the CDS API. Requires a ~/.cdsapirc file
with your CDS credentials:

    url: https://cds.climate.copernicus.eu/api/v2
    key: <UID>:<API-KEY>

Run without credentials to generate demo data instead.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

CDSAPIRC = Path.home() / ".cdsapirc"
_HAS_CREDENTIALS = CDSAPIRC.exists() or (
    os.getenv("CDSAPI_URL") and os.getenv("CDSAPI_KEY")
)


def _demo_dates(days: int = 365) -> pd.DatetimeIndex:
    """Return a normalised (midnight) date range ending today."""
    today = pd.Timestamp.today().normalize()
    return pd.date_range(end=today, periods=days, freq="D")


def _demo_temperature_series(
    lat: float = 48.85,
    lon: float = 2.35,
    days: int = 365,
) -> pd.DataFrame:
    """Return a synthetic daily temperature series for demo purposes."""
    rng = np.random.default_rng(42)
    dates = _demo_dates(days)
    seasonal = 10 * np.sin(2 * np.pi * (dates.dayofyear / 365) - np.pi / 2)
    noise = rng.normal(0, 2, size=days)
    t2m = 15 + seasonal + noise  # °C
    return pd.DataFrame(
        {"date": dates, "t2m_celsius": t2m.round(2), "lat": lat, "lon": lon}
    )


def _demo_precipitation_series(days: int = 365) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = _demo_dates(days)
    precip = np.clip(rng.exponential(scale=2, size=days), 0, 50).round(2)
    return pd.DataFrame({"date": dates, "tp_mm": precip})


def fetch_era5_demo() -> dict[str, pd.DataFrame]:
    """Return demo datasets that mirror real ERA5 structure."""
    log.info("No CDS credentials found — generating demo data.")
    temp_df = _demo_temperature_series()
    precip_df = _demo_precipitation_series()
    merged = temp_df.merge(precip_df, on="date")
    path = DATA_DIR / "era5_demo.csv"
    merged.to_csv(path, index=False)
    log.info("Demo data written to %s", path)
    return {"era5": merged}


def fetch_era5_api(
    variable: str = "2m_temperature",
    year: int | None = None,
    month: int | None = None,
    area: list[float] | None = None,  # [N, W, S, E]
) -> dict[str, pd.DataFrame]:
    """Download ERA5 monthly means from CDS and return as DataFrame."""
    try:
        import cdsapi
        import xarray as xr
    except ImportError as exc:
        raise SystemExit("Run `pip install cdsapi xarray netCDF4` first.") from exc

    now = datetime.utcnow()
    year = year or (now.year if now.month > 3 else now.year - 1)
    month = month or 1
    area = area or [60, -10, 35, 30]  # Europe

    output_path = DATA_DIR / f"era5_{variable}_{year}_{month:02d}.nc"

    if not output_path.exists():
        client = cdsapi.Client()
        client.retrieve(
            "reanalysis-era5-single-levels-monthly-means",
            {
                "product_type": "monthly_averaged_reanalysis",
                "variable": variable,
                "year": str(year),
                "month": f"{month:02d}",
                "time": "00:00",
                "area": area,
                "format": "netcdf",
            },
            str(output_path),
        )
        log.info("Downloaded %s", output_path)
    else:
        log.info("Using cached %s", output_path)

    import xarray as xr

    ds = xr.open_dataset(output_path)
    df = ds.to_dataframe().reset_index()
    # Convert temperature from Kelvin to Celsius if needed
    for col in df.columns:
        if "t2m" in col or "temperature" in col.lower():
            if df[col].mean() > 200:
                df[col] = (df[col] - 273.15).round(2)
    csv_path = output_path.with_suffix(".csv")
    df.to_csv(csv_path, index=False)
    log.info("Saved CSV to %s", csv_path)
    return {"era5": df}


def run(use_demo: bool | None = None) -> dict[str, pd.DataFrame]:
    """Entry point. Auto-detects credentials unless `use_demo` is forced."""
    demo = use_demo if use_demo is not None else not _HAS_CREDENTIALS
    if demo:
        return fetch_era5_demo()
    return fetch_era5_api()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CDS scraper")
    parser.add_argument("--demo", action="store_true", help="Force demo data")
    parser.add_argument("--variable", default="2m_temperature")
    parser.add_argument("--year", type=int, default=None)
    parser.add_argument("--month", type=int, default=None)
    args = parser.parse_args()

    result = run(use_demo=args.demo)
    for name, df in result.items():
        log.info("%s: %d rows, columns: %s", name, len(df), list(df.columns))

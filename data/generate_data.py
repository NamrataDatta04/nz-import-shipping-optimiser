"""Generate the synthetic dataset for the fictional importer Kowhai Imports Ltd.

Every number here is made up. Ranges are chosen to look like Asia -> New Zealand
container shipping in late 2026, but no value is copied from a real quote,
carrier, warehouse or company.

Run:  python data/generate_data.py
Writes products.csv, demand.csv, sailings.csv and facilities.csv next to this file.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 2026
OUT = Path(__file__).resolve().parent

ORIGINS = {
    # origin: (direct transit days to NZ, feeder transit days to Singapore,
    #          direct 40ft base rate NZD, feeder 40ft base rate NZD)
    "China": (20, 7, 3600, 950),
    "India": (30, 6, 4900, 1050),
    "Japan": (19, 9, 3900, 1150),
}
PORTS = ["Auckland", "Tauranga", "Christchurch"]
# Extra transit days beyond Auckland for the other ports.
PORT_EXTRA_DAYS = {"Auckland": 0, "Tauranga": 1, "Christchurch": 3}
PORT_RATE_FACTOR = {"Auckland": 1.00, "Tauranga": 1.03, "Christchurch": 1.10}
TRUNK_DAYS_TO_AKL = 13       # Singapore -> Auckland
TRUNK_40FT_RATE = 2450       # NZD, Singapore -> Auckland

# Fictional carriers. Carrier D is the "new provider" tested in the analysis.
CARRIERS = {
    "Carrier A": {"rate_factor": 1.00, "weekday": 0},
    "Carrier B": {"rate_factor": 0.96, "weekday": 2},
    "Carrier C": {"rate_factor": 1.05, "weekday": 4},
    "Carrier D": {"rate_factor": 0.92, "weekday": 5},
}

PRODUCTS = [
    # id, name, origin, unit volume m3, unit price NZD
    ("P01", "Bamboo storage shelf", "China", 0.18, 62),
    ("P02", "Ceramic dinner set", "China", 0.06, 48),
    ("P03", "LED desk lamp", "China", 0.03, 35),
    ("P04", "Folding outdoor chair", "China", 0.22, 41),
    ("P05", "Cotton bed linen set", "India", 0.04, 55),
    ("P06", "Handwoven floor rug", "India", 0.12, 140),
    ("P07", "Brass serving bowl", "India", 0.02, 38),
    ("P08", "Cast-iron cookware set", "Japan", 0.05, 165),
    ("P09", "Ceramic tea set", "Japan", 0.02, 72),
    ("P10", "Kitchen knife block", "Japan", 0.015, 120),
]


def make_products() -> pd.DataFrame:
    return pd.DataFrame(
        PRODUCTS, columns=["product_id", "name", "origin", "unit_volume_m3", "unit_price_nzd"]
    )


def make_demand(rng: np.random.Generator, products: pd.DataFrame) -> pd.DataFrame:
    """Units each port needs in each fortnight of October 2026."""
    size = {"Auckland": 1.0, "Tauranga": 0.45, "Christchurch": 0.6}
    rows = []
    for _, p in products.iterrows():
        base = rng.integers(25, 90)
        for port in PORTS:
            for fortnight in (1, 2):
                units = int(round(base * size[port] * rng.uniform(0.7, 1.3) / 2))
                rows.append((p.product_id, port, fortnight, max(units, 2)))
    return pd.DataFrame(rows, columns=["product_id", "port", "fortnight", "units"])


def make_sailings(rng: np.random.Generator) -> pd.DataFrame:
    """Weekly sailings whose NZ arrival falls in October 2026.

    Days are counted from 1 October 2026 = day 1, so September departures are
    zero or negative.
    """
    rows = []
    sid = 0

    def add(carrier, leg, origin, dest, depart, transit, rate40):
        nonlocal sid
        sid += 1
        rate40 = round(rate40 * CARRIERS[carrier]["rate_factor"] * rng.uniform(0.95, 1.05), -1)
        rate20 = round(rate40 * rng.uniform(0.58, 0.66), -1)
        surcharge = round(rng.uniform(180, 320), -1)  # fuel, terminal and doc fees per container
        rows.append(
            dict(
                sailing_id=f"S{sid:03d}",
                carrier=carrier,
                leg=leg,
                origin=origin,
                destination=dest,
                depart_day=depart,
                arrive_day=depart + transit,
                rate_20ft_nzd=rate20,
                rate_40ft_nzd=rate40,
                surcharge_per_container_nzd=surcharge,
            )
        )

    for carrier, c in CARRIERS.items():
        # Direct services origin -> NZ port, arriving in October.
        for origin, (direct_days, feeder_days, direct40, feeder40) in ORIGINS.items():
            for port in PORTS:
                transit = direct_days + PORT_EXTRA_DAYS[port]
                for week in range(-6, 5):
                    depart = 7 * week + c["weekday"] + 1
                    if 1 <= depart + transit <= 31:
                        add(carrier, "direct", origin, port, depart, transit,
                            direct40 * PORT_RATE_FACTOR[port])
            # Feeder services origin -> Singapore.
            for week in range(-6, 3):
                depart = 7 * week + c["weekday"] + 1
                if depart + feeder_days <= 20:
                    add(carrier, "feeder", origin, "Singapore", depart, feeder_days, feeder40)
        # Trunk services Singapore -> NZ port.
        for port in PORTS:
            transit = TRUNK_DAYS_TO_AKL + PORT_EXTRA_DAYS[port]
            for week in range(-3, 5):
                depart = 7 * week + c["weekday"] + 2
                if 1 <= depart + transit <= 31:
                    add(carrier, "trunk", "Singapore", port, depart, transit,
                        TRUNK_40FT_RATE * PORT_RATE_FACTOR[port])
    return pd.DataFrame(rows)


def make_facilities() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # location, storage NZD per m3 per day, handling NZD per m3, capacity m3
            ("Singapore", 1.10, 14.0, 400),
            ("Auckland", 1.45, 22.0, 220),
            ("Tauranga", 1.25, 20.0, 150),
            ("Christchurch", 1.35, 21.0, 160),
        ],
        columns=["location", "storage_nzd_per_m3_day", "handling_nzd_per_m3", "capacity_m3"],
    )


def main() -> None:
    rng = np.random.default_rng(SEED)
    products = make_products()
    demand = make_demand(rng, products)
    sailings = make_sailings(rng)
    facilities = make_facilities()
    for name, df in {
        "products": products,
        "demand": demand,
        "sailings": sailings,
        "facilities": facilities,
    }.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
        print(f"{name}.csv: {len(df)} rows")


if __name__ == "__main__":
    main()

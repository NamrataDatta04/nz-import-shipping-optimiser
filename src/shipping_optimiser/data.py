"""Load the input CSVs into one container object."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


@dataclass
class Inputs:
    products: pd.DataFrame
    demand: pd.DataFrame
    sailings: pd.DataFrame
    facilities: pd.DataFrame

    def copy(self) -> "Inputs":
        return Inputs(
            self.products.copy(),
            self.demand.copy(),
            self.sailings.copy(),
            self.facilities.copy(),
        )


def load_inputs(data_dir: Path | str = DATA_DIR) -> Inputs:
    data_dir = Path(data_dir)
    return Inputs(
        products=pd.read_csv(data_dir / "products.csv"),
        demand=pd.read_csv(data_dir / "demand.csv"),
        sailings=pd.read_csv(data_dir / "sailings.csv"),
        facilities=pd.read_csv(data_dir / "facilities.csv"),
    )

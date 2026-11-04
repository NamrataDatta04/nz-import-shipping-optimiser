import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shipping_optimiser import Scenario, load_inputs, solve  # noqa: E402
from shipping_optimiser.model import CAPACITY_M3, FORTNIGHT_1_END  # noqa: E402


@pytest.fixture(scope="module")
def inputs():
    return load_inputs()


@pytest.fixture(scope="module")
def base(inputs):
    return solve(inputs, Scenario())


def _units_by_product(products_field: str) -> dict[str, int]:
    out = {}
    for item in products_field.split(";"):
        pid, units = item.split("x")
        out[pid] = int(units)
    return out


def test_base_is_optimal(base):
    assert base.status == "Optimal"
    assert base.total_cost == pytest.approx(sum(v for k, v in base.costs.items() if k != "total"))


def test_containers_never_overfilled(base):
    assert (base.shipments["utilisation"] <= 1.0 + 1e-6).all()


def test_singapore_to_nz_carries_one_container(base):
    trunk = base.shipments[base.shipments["leg"] == "trunk"]
    assert ((trunk["containers_20ft"] + trunk["containers_40ft"]) <= 1).all()


def test_each_port_gets_mixed_container_each_fortnight(base, inputs):
    trunk = base.shipments[base.shipments["leg"] == "trunk"].copy()
    trunk["fortnight"] = (trunk["arrive_day"] > FORTNIGHT_1_END).map({False: 1, True: 2})
    for port in inputs.demand["port"].unique():
        for f in (1, 2):
            assert ((trunk["destination"] == port) & (trunk["fortnight"] == f)).any(), (port, f)


def test_demand_met(base, inputs):
    arrivals = base.shipments[base.shipments["leg"].isin(["direct", "trunk"])]
    got = {}
    for _, r in arrivals.iterrows():
        for pid, u in _units_by_product(r["products"]).items():
            got[pid, r["destination"]] = got.get((pid, r["destination"]), 0) + u
    need = inputs.demand.groupby(["product_id", "port"])["units"].sum()
    for (pid, port), units in need.items():
        # unit flows are continuous in the model; allow rounding of up to 1 unit per sailing
        assert got.get((pid, port), 0) >= units - len(arrivals), (pid, port)


def test_minimum_order_quantity(base):
    assert (base.purchases["units"] >= 2).all()


def test_consolidation_beats_direct_only(inputs, base):
    direct = solve(inputs, Scenario("Direct only", allow_hub=False))
    assert direct.status == "Optimal"
    assert direct.logistics_cost > base.logistics_cost


def test_capacity_constants():
    assert CAPACITY_M3["20ft"] < CAPACITY_M3["40ft"]


def test_generated_data_shapes(inputs):
    assert len(inputs.products) == 10
    assert set(inputs.sailings["leg"]) == {"direct", "feeder", "trunk"}
    assert isinstance(inputs.demand, pd.DataFrame) and (inputs.demand["units"] >= 2).all()

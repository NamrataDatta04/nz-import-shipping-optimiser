"""Mixed-integer linear program for the October import plan.

The full formulation, with notation, is in docs/formulation.md. In short:
choose how many units of each product to buy, which sailings carry them
(direct origin -> NZ port, or origin -> Singapore -> NZ port), and how many
20ft / 40ft containers to book on each sailing, at minimum total cost.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import pulp

from .data import Inputs

# Usable load volume per container (m3), below the nominal 33 / 67 m3.
CAPACITY_M3 = {"20ft": 28.0, "40ft": 58.0}
LAST_DAY = 31            # 31 October 2026
FORTNIGHT_1_END = 14     # arrivals on days 1-14 count toward fortnight 1
MIN_SG_DWELL_DAYS = 2    # time to unload, consolidate and reload in Singapore
MIN_ORDER_UNITS = 2


@dataclass
class Scenario:
    """Switches and multipliers the cost-benefit analysis changes."""

    name: str = "Base"
    carriers: tuple[str, ...] = ("Carrier A", "Carrier B", "Carrier C")
    allow_direct: bool = True
    allow_hub: bool = True
    shipping_cost_factor: float = 1.0
    sg_storage_factor: float = 1.0
    require_mixed_containers: bool = True


@dataclass
class Solution:
    scenario: Scenario
    status: str
    costs: dict[str, float] = field(default_factory=dict)
    shipments: pd.DataFrame = field(default_factory=pd.DataFrame)
    purchases: pd.DataFrame = field(default_factory=pd.DataFrame)

    @property
    def total_cost(self) -> float:
        return self.costs.get("total", float("nan"))

    @property
    def logistics_cost(self) -> float:
        return self.total_cost - self.costs.get("purchase", 0.0)


def _fortnight(day: int) -> int:
    return 1 if day <= FORTNIGHT_1_END else 2


def solve(inputs: Inputs, scenario: Scenario | None = None, time_limit: int = 120,
          msg: bool = False) -> Solution:
    sc = scenario or Scenario()
    prods = inputs.products.set_index("product_id")
    fac = inputs.facilities.set_index("location")
    ports = sorted(inputs.demand["port"].unique())

    sail = inputs.sailings[inputs.sailings["carrier"].isin(sc.carriers)].copy()
    if not sc.allow_direct:
        sail = sail[sail["leg"] != "direct"]
    if not sc.allow_hub:
        sail = sail[sail["leg"] == "direct"]
    sail = sail.set_index("sailing_id")
    for col in ("rate_20ft_nzd", "rate_40ft_nzd", "surcharge_per_container_nzd"):
        sail[col] = sail[col] * sc.shipping_cost_factor

    direct = sail[sail["leg"] == "direct"]
    feeder = sail[sail["leg"] == "feeder"]
    trunk = sail[sail["leg"] == "trunk"]

    m = pulp.LpProblem("october_import_plan", pulp.LpMinimize)

    # ---- decision variables -------------------------------------------------
    buy = {p: pulp.LpVariable(f"buy_{p}", lowBound=MIN_ORDER_UNITS, cat="Integer")
           for p in prods.index}
    # units of product p on sailing s (only products from that sailing's origin)
    x = {}
    for s, r in sail.iterrows():
        for p in prods.index:
            if r.leg in ("direct", "feeder") and prods.at[p, "origin"] != r.origin:
                continue
            x[p, s] = pulp.LpVariable(f"x_{p}_{s}", lowBound=0)  # continuous; buy[] stays integer
    n20 = {s: pulp.LpVariable(f"n20_{s}", lowBound=0, cat="Integer") for s in sail.index}
    n40 = {s: pulp.LpVariable(f"n40_{s}", lowBound=0, cat="Integer") for s in sail.index}

    vol = prods["unit_volume_m3"].to_dict()

    def units_on(s):
        return [(p, x[p, s]) for p in prods.index if (p, s) in x]

    def volume_on(s):
        return pulp.lpSum(vol[p] * v for p, v in units_on(s))

    # ---- cost terms ---------------------------------------------------------
    purchase = pulp.lpSum(prods.at[p, "unit_price_nzd"] * buy[p] for p in prods.index)
    freight = pulp.lpSum(
        (r.rate_20ft_nzd + r.surcharge_per_container_nzd) * n20[s]
        + (r.rate_40ft_nzd + r.surcharge_per_container_nzd) * n40[s]
        for s, r in sail.iterrows()
    )
    sg = fac.loc["Singapore"]
    sg_rate = sg.storage_nzd_per_m3_day * sc.sg_storage_factor
    # Unit-days held in Singapore = sum(out x depart day) - sum(in x arrive day);
    # exact because every unit that arrives also leaves (flow balance below).
    sg_unit_days_m3 = (
        pulp.lpSum(vol[p] * v * trunk.at[s, "depart_day"] for s in trunk.index for p, v in units_on(s))
        - pulp.lpSum(vol[p] * v * feeder.at[s, "arrive_day"] for s in feeder.index for p, v in units_on(s))
    )
    sg_cost = sg_rate * sg_unit_days_m3 + sg.handling_nzd_per_m3 * pulp.lpSum(
        volume_on(s) for s in feeder.index)

    nz_legs = sail[sail["leg"].isin(["direct", "trunk"])]
    nz_cost = pulp.lpSum(
        volume_on(s) * (fac.at[r.destination, "handling_nzd_per_m3"]
                        + fac.at[r.destination, "storage_nzd_per_m3_day"]
                        * (LAST_DAY + 1 - r.arrive_day))
        for s, r in nz_legs.iterrows()
    )

    m += purchase + freight + sg_cost + nz_cost

    # ---- constraints --------------------------------------------------------
    for s in sail.index:
        m += volume_on(s) <= CAPACITY_M3["20ft"] * n20[s] + CAPACITY_M3["40ft"] * n40[s], f"cap_{s}"
    for s in trunk.index:
        # Singapore -> NZ: one container per sailing per port, either a 20ft or a 40ft.
        m += n20[s] + n40[s] <= 1, f"trunk_one_box_{s}"

    for p in prods.index:
        leaving_origin = [x[p, s] for s in sail.index
                          if (p, s) in x and sail.at[s, "leg"] in ("direct", "feeder")]
        m += buy[p] == pulp.lpSum(leaving_origin), f"buy_{p}"

        # Singapore flow balance: everything that arrives leaves, and a unit can only
        # leave on a trunk sailing departing at least MIN_SG_DWELL_DAYS after it arrived.
        feed_p = [(feeder.at[s, "arrive_day"], x[p, s]) for s in feeder.index if (p, s) in x]
        trunk_p = [(trunk.at[s, "depart_day"], x[p, s]) for s in trunk.index if (p, s) in x]
        m += pulp.lpSum(v for _, v in trunk_p) == pulp.lpSum(v for _, v in feed_p), f"sg_bal_{p}"
        for t in sorted({d for d, _ in trunk_p}):
            m += (pulp.lpSum(v for d, v in trunk_p if d <= t)
                  <= pulp.lpSum(v for d, v in feed_p if d <= t - MIN_SG_DWELL_DAYS)), f"sg_time_{p}_{t}"

    dem = inputs.demand.pivot_table(index=["product_id", "port"], columns="fortnight",
                                    values="units", aggfunc="sum").fillna(0)
    for (p, k), row in dem.iterrows():
        arrivals = [(nz_legs.at[s, "arrive_day"], x[p, s]) for s in nz_legs.index
                    if (p, s) in x and nz_legs.at[s, "destination"] == k]
        need1, need2 = row.get(1, 0), row.get(2, 0)
        m += pulp.lpSum(v for d, v in arrivals if d <= FORTNIGHT_1_END) >= need1, f"dem1_{p}_{k}"
        m += pulp.lpSum(v for _, v in arrivals) >= need1 + need2, f"dem_{p}_{k}"

    for k in ports:
        inbound = [s for s in nz_legs.index if nz_legs.at[s, "destination"] == k]
        m += pulp.lpSum(volume_on(s) for s in inbound) <= fac.at[k, "capacity_m3"], f"wh_cap_{k}"
        if sc.require_mixed_containers and sc.allow_hub:
            for f in (1, 2):
                boxes = [s for s in trunk.index
                         if trunk.at[s, "destination"] == k and _fortnight(trunk.at[s, "arrive_day"]) == f]
                m += pulp.lpSum(n20[s] + n40[s] for s in boxes) >= 1, f"mixed_{k}_{f}"

    m.solve(pulp.HiGHS(msg=msg, timeLimit=time_limit))
    status = pulp.LpStatus[m.status]
    sol = Solution(sc, status)
    if status != "Optimal":
        return sol

    val = lambda e: float(pulp.value(e) or 0.0)  # noqa: E731
    sol.costs = {
        "purchase": val(purchase),
        "freight": val(freight),
        "singapore_hub": val(sg_cost),
        "nz_warehousing": val(nz_cost),
    }
    sol.costs["total"] = sum(sol.costs.values())

    rows = []
    for s, r in sail.iterrows():
        c20, c40 = round(val(n20[s])), round(val(n40[s]))
        if c20 + c40 == 0:
            continue
        units = {p: round(val(v)) for p, v in units_on(s) if val(v) > 0.5}
        load = sum(vol[p] * u for p, u in units.items())
        cap = CAPACITY_M3["20ft"] * c20 + CAPACITY_M3["40ft"] * c40
        rows.append(dict(
            sailing_id=s, carrier=r.carrier, leg=r.leg, origin=r.origin,
            destination=r.destination, depart_day=r.depart_day, arrive_day=r.arrive_day,
            containers_20ft=c20, containers_40ft=c40, units=sum(units.values()),
            volume_m3=round(load, 2), utilisation=round(load / cap, 3) if cap else 0.0,
            freight_nzd=round(c20 * (r.rate_20ft_nzd + r.surcharge_per_container_nzd)
                              + c40 * (r.rate_40ft_nzd + r.surcharge_per_container_nzd), 2),
            products=";".join(f"{p}x{u}" for p, u in sorted(units.items())),
        ))
    sol.shipments = pd.DataFrame(rows).sort_values(["leg", "arrive_day", "destination"]) if rows else pd.DataFrame()
    sol.purchases = pd.DataFrame(
        [(p, prods.at[p, "name"], prods.at[p, "origin"], round(val(buy[p])),
          round(val(buy[p])) * prods.at[p, "unit_price_nzd"]) for p in prods.index],
        columns=["product_id", "name", "origin", "units", "cost_nzd"],
    )
    return sol

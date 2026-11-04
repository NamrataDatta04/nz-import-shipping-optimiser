"""Scenarios for the cost-benefit analysis."""
from __future__ import annotations

from .model import Scenario

ALL_CARRIERS = ("Carrier A", "Carrier B", "Carrier C", "Carrier D")

BASE = Scenario("Base: consolidate via Singapore or ship direct")
DIRECT_ONLY = Scenario("Direct shipping only", allow_hub=False)
ADD_CARRIER_D = Scenario("Base + new provider (Carrier D)", carriers=ALL_CARRIERS)

SENSITIVITY = [
    Scenario("Shipping costs -10%", shipping_cost_factor=0.9),
    Scenario("Shipping costs +10%", shipping_cost_factor=1.1),
    Scenario("Singapore storage -10%", sg_storage_factor=0.9),
    Scenario("Singapore storage +10%", sg_storage_factor=1.1),
]

ALL = [BASE, DIRECT_ONLY, ADD_CARRIER_D, *SENSITIVITY]

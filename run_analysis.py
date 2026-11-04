"""Solve every scenario, save result tables to results/ and charts to figures/.

Run:  python run_analysis.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from shipping_optimiser import load_inputs, solve  # noqa: E402
from shipping_optimiser.scenarios import ALL, BASE  # noqa: E402

RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"

# Colour roles (validated categorical slots 1-3 on a light surface).
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "xtick.color": INK_2, "ytick.color": INK_2,
    "text.color": INK, "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "axes.titlepad": 26, "axes.spines.top": False, "axes.spines.right": False,
})


def nzd(v: float) -> str:
    return f"${v:,.0f}"


def run() -> tuple[pd.DataFrame, dict]:
    inputs = load_inputs()
    rows, sols = [], {}
    for sc in ALL:
        sol = solve(inputs, sc)
        print(f"{sc.name:<48} {sol.status:<8} total {nzd(sol.total_cost)}")
        sols[sc.name] = sol
        rows.append({"scenario": sc.name, "status": sol.status, **{k: round(v, 2) for k, v in sol.costs.items()},
                     "logistics_total": round(sol.logistics_cost, 2)})
    summary = pd.DataFrame(rows)
    base = summary.loc[summary.scenario == BASE.name, "logistics_total"].iloc[0]
    summary["logistics_vs_base_nzd"] = (summary["logistics_total"] - base).round(2)
    summary["logistics_vs_base_pct"] = (100 * summary["logistics_vs_base_nzd"] / base).round(2)
    return summary, sols


def chart_cost_breakdown(summary: pd.DataFrame) -> None:
    names = ["Direct shipping only", "Base: consolidate via Singapore or ship direct",
             "Base + new provider (Carrier D)"]
    labels = ["Direct shipping only", "Optimised plan\n(Singapore hub allowed)", "Optimised plan\n+ Carrier D"]
    df = summary.set_index("scenario").loc[names]
    parts = [("freight", "Ocean freight", BLUE), ("singapore_hub", "Singapore hub", ORANGE),
             ("nz_warehousing", "NZ port warehousing", AQUA)]
    fig, ax = plt.subplots(figsize=(9, 3.3))
    left = pd.Series(0.0, index=df.index)
    for col, lab, colour in parts:
        ax.barh(labels, df[col], left=left, color=colour, label=lab, height=0.55,
                edgecolor=SURFACE, linewidth=2)
        left += df[col]
    for i, total in enumerate(left):
        ax.text(total + 300, i, nzd(total), va="center", color=INK, fontweight="bold")
    ax.invert_yaxis()
    ax.set_xlim(0, left.max() * 1.15)
    ax.xaxis.set_major_formatter(lambda v, _: f"${v/1000:,.0f}k")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    saving = df["logistics_total"].iloc[0] - df["logistics_total"].iloc[1]
    ax.set_title(f"Consolidating through Singapore cuts October logistics cost by {nzd(saving)}")
    ax.set_xlabel("Logistics cost, NZD (product purchase cost excluded, identical in every scenario)")
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False)
    fig.tight_layout()
    fig.savefig(FIGURES / "logistics_cost_by_scenario.png", dpi=160, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def chart_sensitivity(summary: pd.DataFrame) -> None:
    s = summary.set_index("scenario")["logistics_vs_base_nzd"]
    factors = [("Shipping costs", "Shipping costs -10%", "Shipping costs +10%"),
               ("Singapore storage", "Singapore storage -10%", "Singapore storage +10%")]
    fig, ax = plt.subplots(figsize=(9, 2.8))
    for i, (lab, lo, hi) in enumerate(factors):
        ax.barh(i, s[lo], color=BLUE, height=0.5, label="Cost -10%" if i == 0 else None)
        ax.barh(i, s[hi], color=ORANGE, height=0.5, label="Cost +10%" if i == 0 else None)
        for v in (s[lo], s[hi]):
            ax.text(v + (60 if v >= 0 else -60), i, f"{'+' if v >= 0 else '-'}{nzd(abs(v))}",
                    va="center", ha="left" if v >= 0 else "right", color=INK)
    ax.set_yticks(range(len(factors)), [f[0] for f in factors])
    ax.invert_yaxis()
    ax.axvline(0, color=INK_2, linewidth=1)
    lim = max(abs(s[[f[1] for f in factors] + [f[2] for f in factors]])) * 1.35
    ax.set_xlim(-lim, lim)
    ax.xaxis.set_major_formatter(lambda v, _: f"{'+' if v > 0 else ''}{v:,.0f}")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.set_title("Freight rates move total logistics cost far more than Singapore storage")
    ax.set_xlabel("Change in logistics cost vs optimised base plan, NZD")
    ax.legend(loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(FIGURES / "sensitivity.png", dpi=160, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def chart_plan_timeline(shipments: pd.DataFrame) -> None:
    df = shipments.copy()
    df["lane"] = df["origin"] + " → " + df["destination"] + "  (" + df["carrier"] + ")"
    df["leg_order"] = df["leg"].map({"feeder": 0, "direct": 1, "trunk": 2})
    df = df.sort_values(["leg_order", "destination", "origin", "depart_day"]).reset_index(drop=True)
    order = df["lane"].tolist()
    colours = {"feeder": BLUE, "trunk": ORANGE, "direct": AQUA}
    names = {"feeder": "Feeder to Singapore", "trunk": "Singapore to NZ port", "direct": "Direct to NZ port"}
    fig, ax = plt.subplots(figsize=(10, 0.45 * len(order) + 1.8))
    seen = set()
    for y, r in df.iterrows():
        ax.plot([r.depart_day, r.arrive_day], [y, y], color=colours[r.leg], linewidth=6,
                solid_capstyle="round", label=None if r.leg in seen else names[r.leg])
        seen.add(r.leg)
        box = f"{r.containers_20ft}×20ft" if r.containers_20ft else ""
        box += (" + " if box and r.containers_40ft else "") + (f"{r.containers_40ft}×40ft" if r.containers_40ft else "")
        ax.text(r.arrive_day + 0.6, y, f"{box}, {r.utilisation:.0%} full", va="center", fontsize=8, color=INK_2,
                bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1))
    for day, lab in [(1, "1 Oct"), (15, "15 Oct")]:
        ax.axvline(day, color=INK_2, linewidth=0.8, linestyle=(0, (3, 3)))
        ax.text(day, -0.75, lab, ha="center", fontsize=8, color=INK_2,
                bbox=dict(facecolor=SURFACE, edgecolor="none", pad=1))
    ax.set_yticks(range(len(order)), order)
    ax.invert_yaxis()
    ax.set_ylim(len(order) - 0.4, -1.1)
    ax.set_xlim(df.depart_day.min() - 1, 42)
    ax.set_xlabel("Day (1 = 1 October 2026; negative = September)")
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    n_feed = int((df.leg == "feeder").sum())
    n_trunk = int(df.loc[df.leg == "trunk", ["containers_20ft", "containers_40ft"]].sum().sum())
    n_direct = int((df.leg == "direct").sum())
    title = f"Optimised plan: {n_feed} feeder loads consolidate into {n_trunk} mixed containers for NZ"
    if n_direct:
        title += f", plus {n_direct} direct sailings"
    ax.set_title(title)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, frameon=False)
    fig.tight_layout()
    fig.savefig(FIGURES / "base_plan_timeline.png", dpi=160, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)


def main() -> None:
    RESULTS.mkdir(exist_ok=True)
    FIGURES.mkdir(exist_ok=True)
    summary, sols = run()
    summary.to_csv(RESULTS / "scenario_summary.csv", index=False)
    base = sols[BASE.name]
    base.shipments.to_csv(RESULTS / "base_plan_shipments.csv", index=False)
    base.purchases.to_csv(RESULTS / "base_plan_purchases.csv", index=False)
    chart_cost_breakdown(summary)
    chart_sensitivity(summary)
    chart_plan_timeline(base.shipments)
    print(summary[["scenario", "logistics_total", "logistics_vs_base_nzd", "logistics_vs_base_pct"]].to_string(index=False))


if __name__ == "__main__":
    main()

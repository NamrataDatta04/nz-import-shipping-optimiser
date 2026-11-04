# Model formulation

A mixed-integer linear program (MILP) that plans one month of imports for a fictional
New Zealand retailer, **Kōwhai Imports Ltd**. Goods come from suppliers in China, India and
Japan. Each lot either ships **direct** to a New Zealand port or travels on a **feeder**
service to Singapore, where it is consolidated with goods from the other origins and sent
on a **trunk** service to the New Zealand port.

The planning window is goods **arriving in New Zealand between 1 and 31 October 2026**.
Days are numbered from 1 October = day 1, so September departures have day ≤ 0.

## Sets

| Symbol | Meaning |
| --- | --- |
| $P$ | products (10), each with an origin $o(p)$ |
| $K$ | NZ ports: Auckland, Tauranga, Christchurch |
| $S$ | sailings, split into $S^{dir}$ (origin → NZ port), $S^{fd}$ (origin → Singapore), $S^{tr}$ (Singapore → NZ port) |
| $F$ | fortnights: arrivals on days 1–14 and 15–31 |

Products can only board a direct or feeder sailing that leaves from their own origin.

## Parameters

| Symbol | Meaning |
| --- | --- |
| $c_p$ | unit purchase price (NZD) |
| $v_p$ | unit volume (m³) |
| $d_{pkf}$ | units of $p$ needed at port $k$ in fortnight $f$ |
| $r^{20}_s, r^{40}_s$ | container rate for sailing $s$, including per-container surcharges |
| $a_s, \delta_s$ | arrival day, departure day of sailing $s$ |
| $Q^{20}=28, Q^{40}=58$ | usable container volume (m³) |
| $h^{SG}, g^{SG}$ | Singapore handling (per m³) and storage (per m³ per day) |
| $h_k, g_k, U_k$ | NZ port handling, storage rate and warehouse capacity |
| $\tau = 2$ | minimum days between arriving in and leaving Singapore |

## Decision variables

| Symbol | Type | Meaning |
| --- | --- | --- |
| $b_p$ | integer ≥ 2 | units of product $p$ purchased |
| $x_{ps}$ | continuous ≥ 0 | units of $p$ carried on sailing $s$ |
| $n^{20}_s, n^{40}_s$ | integer ≥ 0 | 20ft / 40ft containers booked on sailing $s$ |

## Objective

Minimise purchase + freight + Singapore hub + NZ warehousing cost:

$$
\min \sum_p c_p b_p
+ \sum_s \left(r^{20}_s n^{20}_s + r^{40}_s n^{40}_s\right)
+ h^{SG}\sum_{s\in S^{fd}}\sum_p v_p x_{ps}
+ g^{SG}\Big(\sum_{s\in S^{tr}}\sum_p v_p x_{ps}\,\delta_s - \sum_{s\in S^{fd}}\sum_p v_p x_{ps}\,a_s\Big)
+ \sum_{s\in S^{dir}\cup S^{tr}}\sum_p v_p x_{ps}\big(h_{k(s)} + g_{k(s)}(32 - a_s)\big)
$$

The Singapore storage term counts cubic-metre-days held at the hub. It is exact because
every unit that arrives in Singapore also leaves (flow balance below).

## Constraints

1. **Purchase = shipped from origin**: $b_p = \sum_{s\in S^{dir}\cup S^{fd}} x_{ps}$, and $b_p \ge 2$ (minimum order quantity).
2. **Container capacity**: $\sum_p v_p x_{ps} \le Q^{20} n^{20}_s + Q^{40} n^{40}_s$ for every sailing.
3. **Singapore → NZ container rule**: $n^{20}_s + n^{40}_s \le 1$ for $s \in S^{tr}$ — at most one container per trunk sailing per port, either a 20ft or a 40ft.
4. **Singapore flow balance**: $\sum_{s\in S^{tr}} x_{ps} = \sum_{s\in S^{fd}} x_{ps}$ for each product.
5. **Singapore timing**: for each product and each trunk departure day $t$, units that have left by $t$ ≤ units that arrived by $t-\tau$.
6. **Demand by fortnight**: arrivals of $p$ at port $k$ by day 14 ≥ $d_{pk1}$; arrivals by day 31 ≥ $d_{pk1}+d_{pk2}$.
7. **Mixed container every fortnight**: each port receives at least one Singapore container in each fortnight, $\sum_{s\in S^{tr}_{k,f}} (n^{20}_s + n^{40}_s) \ge 1$.
8. **Warehouse capacity**: total volume delivered to port $k$ ≤ $U_k$.

## Assumptions

- Goods arriving at a NZ port are stored until 31 October (conservative storage cost).
- Unit flows $x_{ps}$ are continuous. This keeps solve times to seconds. Purchases stay
  integer, and any rounding in the reported plan is under one unit per sailing.
- Freight is charged per container booked; there is no less-than-container (LCL) option.
- All carriers, rates, schedules, products and demand are synthetic (see `data/generate_data.py`).
- Solved with the open-source HiGHS solver through PuLP.

# Metrics Reference

This document explains the metrics produced by `run.py`, their formulas, and how to interpret them.

## 1) Data outputs

The batch runner writes:
- `batch_run_raw.csv`: all collected rows per run and step.
- `timeseries.csv`: same model-level time series used for curves.
- `summary.csv`: final row (last collected step) per run.
- `suspicious_runs.csv`: subset of runs flagged as timed out, deadlock-like, or stopped with waste.

## 2) Core state metrics (per step)

These are collected at every step and also available on the final row in `summary.csv`.

### Waste counts
- `green`, `yellow`, `red`: current number of wastes of each type still in the system.
- `total`: `green + yellow + red`.

Interpretation:
- Decreasing values indicate elimination/progression.
- `total == 0` means all waste has been eliminated from the system.

### Distance metric
- `cumulative_distance`: sum of Manhattan distances from each waste unit to the disposal zone.

Formula:

$$
D_t = \sum_{w \in \text{map}} d_1(w, depot) + \sum_{(a,w) \in \text{inventories}} d_1(a, depot)
$$

where $d_1((x_1,y_1),(x_2,y_2)) = |x_1-x_2| + |y_1-y_2|$.

Utility:
- Proxy for logistic effort remaining.
- Lower is better; should generally trend to 0 in successful runs.

## 3) Extinction / completion timing metrics

### First-zero step per waste type
- `step_green_zero`: first step where `green == 0`, only if green was present at least once in the run.
- `step_yellow_zero`: first step where `yellow == 0`, only if yellow was present at least once in the run.
- `step_red_zero`: first step where `red == 0`, only if red was present at least once in the run.
- `step_total_zero`: first step where `total == 0`.
- `step_all_zero`: alias of `step_total_zero`.

Important:
- If a type never appears during a run, its `step_*_zero` stays empty (`NaN` in CSV) and is excluded from extinction-step plots.

### Effective completion step
- `step_all_zero_effective`:
  - equals `step_all_zero` if the run cleaned;
  - otherwise equals `steps_executed`.

Utility:
- Enables fair boxplot comparison when some runs do not clean before max steps.

### Run completion flags
- `cleaned`: `step_total_zero is not None`.
- `steps_executed`: final step count of the run.
- `timed_out`: not cleaned and `steps_executed >= max_steps`.
- `stopped_with_waste`: `total > 0` on final row.
- `possible_deadlock`: no change in `total` during last `stall_window` steps and final `total > 0`.

## 4) Real compaction metrics (deposited waste counts)

These counts track what was actually deposited in the disposal zone during the run:
- `disposed_green`
- `disposed_yellow`
- `disposed_red`
- `disposed_total`

Formulas:

$$
disposed\_total = disposed\_green + disposed\_yellow + disposed\_red
$$

Utility:
- Direct measure of what was physically sent to the depot by type.
- This is the basis for compaction-quality evaluation.

## 5) Theoretical optimal compaction

Given initial counts:
- $G_0 =$ `n_green_waste`
- $Y_0 =$ `n_yellow_waste`
- $R_0 =$ `n_red_waste`

and transformation rules:
- $2\,green \rightarrow 1\,yellow$
- $2\,yellow \rightarrow 1\,red$

Optimal deposited counts are:

$$
G^* = G_0 \bmod 2
$$

$$
Y^* = \left(\left\lfloor \frac{G_0}{2} \right\rfloor + Y_0\right) \bmod 2
$$

$$
R^* = \left\lfloor \frac{\left\lfloor G_0/2 \right\rfloor + Y_0}{2} \right\rfloor + R_0
$$

$$
T^* = G^* + Y^* + R^*
$$

Saved columns in `summary.csv`:
- `optimal_green`, `optimal_yellow`, `optimal_red`, `optimal_total`
- `initial_total_waste = G_0 + Y_0 + R_0`

## 6) Compaction ratio metrics (delta vs optimum)

By design (your definition):
- Numerator: real deposited count of the type minus optimal deposited count of that type.
- Denominator: initial total waste spawned.

For each type $k \in \{green, yellow, red, total\}$:

$$
compaction\_ratio_k = \frac{disposed_k - optimal_k}{initial\_total\_waste}
$$

Saved columns:
- `compaction_ratio_green`
- `compaction_ratio_yellow`
- `compaction_ratio_red`
- `compaction_ratio_total`

Interpretation:
- `0`: exactly at theoretical optimum for that type.
- `> 0`: over-deposit of that type vs optimum (less compact than ideal for that channel).
- `< 0`: under-deposit of that type vs optimum.

Important note:
- The most informative global indicator is usually `compaction_ratio_total`, since it captures total compaction efficiency into final disposed units.

## 7) Plots and what they show

Generated figures:
- `extinction_steps_distribution.png`: distribution of first-zero steps.
- `total_waste_over_time.png`: mean + 95% interval over time for `green`, `yellow`, `red`, `total`.
- `cumulative_distance_over_time.png`: mean + 95% interval for cumulative distance.
- `compaction_ratio_distribution.png`: boxplot of compaction ratios (`green`, `yellow`, `red`, `total`) by configuration.

How to compare configurations for compaction:
- Prefer lower absolute spread around 0 for stability.
- Prefer median close to 0 for agreement with theoretical optimum.
- For global objective, prioritize `compaction_ratio_total`.

## 8) Caveats

- Ratios are normalized by initial total waste, so values are comparable across runs with different initial sizes.
- `possible_deadlock` is heuristic (stall window based), not a formal proof of deadlock.
- A run can have good compaction ratio but still be slow (check extinction-step and distance metrics jointly).

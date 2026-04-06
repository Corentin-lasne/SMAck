# Metrics Reference

This document explains the metrics produced by `run.py`, their formulas, and how to interpret them.

## 1) Data Outputs

The batch runner writes the following files for each batch:

- `batch_run_raw.csv`: all collected rows per run and per step.
- `timeseries.csv`: the filtered model-level time series used for plots and temporal analysis.
- `summary.csv`: one final row per run, used for comparison tables and boxplots.
- `suspicious_runs.csv`: runs flagged as timed out, possible deadlock, or stopped with remaining waste.

The current batch runner does not remove runs because of `cumulative_distance` stagnation anymore. All runs are kept in the outputs.

## 2) Core Per-Step Metrics

These metrics are collected at every step and also appear in the final row of `summary.csv`.

### Waste Counts

- `green`, `yellow`, `red`: number of wastes of each type still present in the system.
- `total`: `green + yellow + red`.

Interpretation:
- Lower values mean the system is progressing toward cleanup.
- `total == 0` means all waste has been eliminated from the system.

### Distance Metric

- `cumulative_distance`: sum of Manhattan distances from all remaining wastes and carried wastes to the disposal zone.

Formula:

$$
D_t = \sum_{w \in \text{map}} d_1(w, depot) + \sum_{(a,w) \in \text{inventories}} d_1(a, depot)
$$

with:

$$
d_1((x_1,y_1),(x_2,y_2)) = |x_1 - x_2| + |y_1 - y_2|
$$

Utility:
- Proxy for the remaining transport effort.
- Lower is better; in successful runs it should trend toward 0.

## 3) Completion and Robustness Metrics

### First-Zero Steps

- `step_green_zero`: first step where `green == 0`, if green ever appears.
- `step_yellow_zero`: first step where `yellow == 0`, if yellow ever appears.
- `step_red_zero`: first step where `red == 0`, if red ever appears.
- `step_total_zero`: first step where `total == 0`.
- `step_all_zero`: alias of `step_total_zero`.

If a waste type never appears during a run, its `step_*_zero` stays empty (`NaN` in CSV) and is excluded from extinction-step plots.

### Effective Cleanup Step

- `step_all_zero_effective`: equals `step_all_zero` when the run is cleaned, otherwise equals `steps_executed`.

This is the value used in the policy comparison boxplots, because it gives a single comparable “completion time” even for runs that do not finish.

### Run-Level Flags

- `cleaned`: `True` when `step_total_zero` is not `None`.
- `steps_executed`: final executed step count for the run.
- `timed_out`: `True` when the run is not cleaned and `steps_executed >= max_steps`.
- `stopped_with_waste`: `True` when the final `total` is still greater than 0.
- `possible_deadlock`: heuristic flag for runs whose `total` stays constant during the last `stall_window` steps and remains above 0.

## 4) Real Compaction Metrics

These counts track what was actually deposited in the disposal zone:

- `disposed_green`
- `disposed_yellow`
- `disposed_red`
- `disposed_total`

Formula:

$$
disposed_{total} = disposed_{green} + disposed_{yellow} + disposed_{red}
$$

These values measure the realized disposal output of the system.

## 5) Theoretical Optimal Compaction

Let the initial waste counts be:

- $G_0 =$ `n_green_waste`
- $Y_0 =$ `n_yellow_waste`
- $R_0 =$ `n_red_waste`

The transformation chain is:

- $2\,green \rightarrow 1\,yellow$
- $2\,yellow \rightarrow 1\,red$

The optimal deposited counts are:

$$
optimal_{green} = G_0 \bmod 2
$$

$$
green\_to\_yellow = \left\lfloor \frac{G_0}{2} \right\rfloor
$$

$$
yellow\_pool = green\_to\_yellow + Y_0
$$

$$
optimal_{yellow} = yellow\_pool \bmod 2
$$

$$
optimal_{red} = \left\lfloor \frac{yellow\_pool}{2} \right\rfloor + R_0
$$

$$
optimal_{total} = optimal_{green} + optimal_{yellow} + optimal_{red}
$$

Saved columns in `summary.csv`:

- `optimal_green`
- `optimal_yellow`
- `optimal_red`
- `optimal_total`
- `initial_total_waste = G_0 + Y_0 + R_0`

## 6) Compaction Ratio Metrics

The compaction ratio measures the gap between what was actually disposed and the theoretical optimum, normalized by the initial total waste.

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

- `0`: exactly at the theoretical optimum for that type.
- `> 0`: over-disposal vs optimum, or equivalently less compact than ideal for that channel.
- `< 0`: under-disposal vs optimum.

Important note:

- `red` is not compacted further in the model. For `compaction_ratio_red`, the metric measures how much red was disposed relative to the best possible result after compacting green into yellow and yellow into red.
- `compaction_ratio_total` is the most informative global indicator.

## 7) Plots and How to Read Them

Generated figures:

- `extinction_steps_distribution.png`: distribution of first-zero steps.
- `total_waste_over_time.png`: mean and 95% interval over time for `green`, `yellow`, `red`, and `total`.
- `cumulative_distance_over_time.png`: mean and 95% interval for cumulative distance.
- `compaction_ratio_distribution.png`: boxplot of compaction ratios by waste type and configuration.

For compaction comparisons:

- Prefer medians close to 0.
- Prefer a smaller spread around 0.
- Use `compaction_ratio_total` first, then inspect the type-specific ratios if needed.

## 8) Practical Notes

- Ratios are normalized by initial total waste, so they remain comparable across differently sized runs.
- `possible_deadlock` is a heuristic, not a formal proof of deadlock.
- A run can have a good compaction ratio and still be slow; check `step_all_zero_effective` and `cumulative_distance` together.

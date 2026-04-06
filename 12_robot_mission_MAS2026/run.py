"""Batch simulation runner for the robot mission model."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import datetime
from itertools import product
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from mesa.datacollection import DataCollector
from tqdm import tqdm

from model import Model
from config import DEFAULT_MODEL_PARAMS


DISTANCE_STALL_WINDOW = 200


def _add_filtered_runs_badge(ax: plt.Axes, filtered_runs: int, total_runs: int) -> None:
    """Add an annotation above the plot with the number of filtered runs."""
    if total_runs <= 0:
        return
    ax.text(
        0.5,
        1.1,
        (
            "Filtered out (cumulative_distance stalled "
            f"{DISTANCE_STALL_WINDOW}+ steps): {filtered_runs}/{total_runs} runs"
        ),
        transform=ax.transAxes,
        ha="center",
        va="bottom",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.25", "facecolor": "#f2f2f2", "edgecolor": "#999999"},
    )


def _plot_waste_composition(
    timeseries_df: pd.DataFrame,
    out_dir: Path,
    filtered_runs: int,
    total_runs: int,
) -> None:
    """Plot waste count over time for all types (green, yellow, red, total)."""
    if timeseries_df.empty:
        return

    metrics = ["green", "yellow", "red", "total"]
    for metric in metrics:
        if metric not in timeseries_df.columns:
            return

    # Group by config and step, compute mean and quantiles for each metric
    grouped_data = []
    for metric in metrics:
        grouped = (
            timeseries_df.groupby(["config", "Step"])[metric]
            .agg(
                mean="mean",
                q025=lambda s: s.quantile(0.025),
                q975=lambda s: s.quantile(0.975),
            )
            .reset_index()
        )
        grouped["metric"] = metric
        grouped_data.append(grouped)

    all_grouped = pd.concat(grouped_data, ignore_index=True)

    plt.figure(figsize=(12, 6))
    ax = plt.gca()

    # Color mapping for metrics
    colors = {"green": "green", "yellow": "gold", "red": "red", "total": "black"}

    for config in all_grouped["config"].unique():
        cfg_data = all_grouped[all_grouped["config"] == config]

        for metric in metrics:
            metric_data = cfg_data[cfg_data["metric"] == metric].sort_values("Step")
            if metric_data.empty:
                continue

            x = metric_data["Step"].to_numpy()
            y = metric_data["mean"].to_numpy()
            y_low = metric_data["q025"].to_numpy()
            y_high = metric_data["q975"].to_numpy()

            # Use dashed line for total to distinguish it
            linestyle = "--" if metric == "total" else "-"
            line = ax.plot(x, y, label=f"{config} - {metric}", color=colors[metric], linestyle=linestyle)[0]
            ax.fill_between(x, y_low, y_high, alpha=0.15, color=line.get_color())

    ax.set_title("Total waste over time (mean with 95% interval) by type")
    ax.set_xlabel("Step")
    ax.set_ylabel("Waste count")
    _add_filtered_runs_badge(ax, filtered_runs=filtered_runs, total_runs=total_runs)
    ax.legend(fontsize=8, loc="best")
    plt.tight_layout()
    plt.savefig(out_dir / "total_waste_over_time.png", dpi=150)
    plt.close()


def _has_stagnation_window(series: pd.Series, window_size: int) -> bool:
    """Return True if a series contains a flat window of at least window_size steps."""
    if window_size <= 1:
        return False
    values = series.to_numpy()
    if len(values) < window_size:
        return False
    for i in range(0, len(values) - window_size + 1):
        if values[i] == values[i + window_size - 1] and len(set(values[i : i + window_size])) == 1:
            return True
    return False


def parse_int_list(value: str) -> list[int]:
    return [int(v.strip()) for v in value.split(",") if v.strip()]


def parse_str_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _latest_count(model: Model, key: str) -> int:
    if not model.waste_count_history:
        counts = model._compute_waste_counts()  # pylint: disable=protected-access
        return counts[key]
    return model.waste_count_history[-1][key]


def _latest_distance(model: Model) -> int:
    if not model.cumulative_distance_history:
        return 0
    return model.cumulative_distance_history[-1]["distance"]


def _optimal_disposal_counts(n_green_waste: pd.Series, n_yellow_waste: pd.Series, n_red_waste: pd.Series) -> dict[str, pd.Series]:
    """Compute per-type optimal disposed counts after maximal compaction."""
    optimal_green = n_green_waste % 2
    green_to_yellow = n_green_waste // 2
    yellow_pool = green_to_yellow + n_yellow_waste
    optimal_yellow = yellow_pool % 2
    optimal_red = yellow_pool // 2 + n_red_waste
    optimal_total = optimal_green + optimal_yellow + optimal_red
    return {
        "green": optimal_green,
        "yellow": optimal_yellow,
        "red": optimal_red,
        "total": optimal_total,
    }


def _as_batch_values(value: object) -> list[object]:
    if isinstance(value, (str, bytes, bytearray)):
        return [value]
    if isinstance(value, Iterable):
        return list(value)
    return [value]


def _run_batch(
    parameters: dict[str, object],
    iterations: int,
    max_steps: int,
    display_progress: bool,
) -> list[dict[str, object]]:
    keys = list(parameters.keys())
    values = [_as_batch_values(parameters[k]) for k in keys]

    runs: list[tuple[int, int, dict[str, object]]] = []
    run_id = 0
    for iteration in range(iterations):
        for combo in product(*values):
            runs.append((run_id, iteration, dict(zip(keys, combo))))
            run_id += 1

    results: list[dict[str, object]] = []
    for run_id, iteration, kwargs in tqdm(runs, disable=not display_progress):
        model = BatchModel(**kwargs)

        # Use strict '<' to execute exactly max_steps calls at most.
        while model.running and model.steps < max_steps:
            model.step()

        run_df = pd.DataFrame(model.datacollector.model_vars)
        if run_df.empty:
            continue

        run_df.insert(0, "Step", range(len(run_df)))
        run_df.insert(0, "iteration", iteration)
        run_df.insert(0, "RunId", run_id)
        for key, value in kwargs.items():
            run_df[key] = value

        results.extend(run_df.to_dict(orient="records"))

    return results


class BatchModel(Model):
    """Model wrapper exposing DataCollector reporters for the custom batch runner."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.datacollector = DataCollector(
            model_reporters={
                "green": lambda m: _latest_count(m, "green"),
                "yellow": lambda m: _latest_count(m, "yellow"),
                "red": lambda m: _latest_count(m, "red"),
                "total": lambda m: _latest_count(m, "total"),
                "cumulative_distance": _latest_distance,
                "step_green_zero": lambda m: m.step_green_zero,
                "step_yellow_zero": lambda m: m.step_yellow_zero,
                "step_red_zero": lambda m: m.step_red_zero,
                "step_total_zero": lambda m: m.step_total_zero,
                "step_all_zero": lambda m: m.step_total_zero,
                "cleaned": lambda m: m.step_total_zero is not None,
                "steps_executed": lambda m: m.steps,
                "disposed_green": lambda m: m.disposed_counts["green"],
                "disposed_yellow": lambda m: m.disposed_counts["yellow"],
                "disposed_red": lambda m: m.disposed_counts["red"],
                "disposed_total": lambda m: m.disposed_counts["total"],
            }
        )
        self.datacollector.collect(self)

    def step(self):
        super().step()
        self.datacollector.collect(self)


def make_plots(
    summary_df: pd.DataFrame,
    timeseries_df: pd.DataFrame,
    out_dir: Path,
    filtered_runs: int,
    total_runs: int,
) -> None:
    sns.set_theme(style="whitegrid")

    total_step_effective_col = (
        "step_all_zero_effective"
        if "step_all_zero_effective" in summary_df.columns
        else ("step_all_zero" if "step_all_zero" in summary_df.columns else "step_total_zero")
    )

    def _plot_metric_with_band(metric: str, title: str, ylabel: str, filename: str) -> None:
        if timeseries_df.empty or metric not in timeseries_df.columns:
            return

        grouped = (
            timeseries_df.groupby(["config", "Step"])[metric]
            .agg(
                mean="mean",
                q025=lambda s: s.quantile(0.025),
                q975=lambda s: s.quantile(0.975),
            )
            .reset_index()
        )
        if grouped.empty:
            return

        plt.figure(figsize=(10, 5))
        ax = plt.gca()
        for config, cfg_df in grouped.groupby("config", sort=False):
            cfg_df = cfg_df.sort_values("Step")
            x = cfg_df["Step"].to_numpy()
            y = cfg_df["mean"].to_numpy()
            y_low = cfg_df["q025"].to_numpy()
            y_high = cfg_df["q975"].to_numpy()

            line = ax.plot(x, y, label=config)[0]
            ax.fill_between(x, y_low, y_high, alpha=0.15, color=line.get_color())

        ax.set_title(title)
        ax.set_xlabel("Step")
        ax.set_ylabel(ylabel)
        _add_filtered_runs_badge(ax, filtered_runs=filtered_runs, total_runs=total_runs)
        ax.legend(title="Configuration")
        plt.tight_layout()
        plt.savefig(out_dir / filename, dpi=150)
        plt.close()

    extinction_cols = [
        "step_green_zero",
        "step_yellow_zero",
        "step_red_zero",
        total_step_effective_col,
    ]
    melt_df = summary_df.melt(
        id_vars=["config", "RunId"],
        value_vars=[c for c in extinction_cols if c in summary_df.columns],
        var_name="metric",
        value_name="step",
    ).dropna(subset=["step"])
    if not melt_df.empty:
        melt_df["metric"] = melt_df["metric"].replace({total_step_effective_col: "step_all_zero"})
        plt.figure(figsize=(10, 5))
        ax = sns.boxplot(data=melt_df, x="metric", y="step")
        ax.set_title("Distribution of extinction steps by metric")
        ax.set_xlabel("Metric")
        ax.set_ylabel("Step")
        plt.tight_layout()
        plt.savefig(out_dir / "extinction_steps_distribution.png", dpi=150)
        plt.close()

    ratio_cols = [
        "compaction_ratio_green",
        "compaction_ratio_yellow",
        "compaction_ratio_red",
        "compaction_ratio_total",
    ]
    ratio_df = summary_df.melt(
        id_vars=["config", "RunId"],
        value_vars=[c for c in ratio_cols if c in summary_df.columns],
        var_name="metric",
        value_name="ratio",
    ).dropna(subset=["ratio"])
    if not ratio_df.empty:
        ratio_df["metric"] = ratio_df["metric"].replace(
            {
                "compaction_ratio_green": "green",
                "compaction_ratio_yellow": "yellow",
                "compaction_ratio_red": "red",
                "compaction_ratio_total": "total",
            }
        )
        plt.figure(figsize=(11, 6))
        ax = sns.boxplot(data=ratio_df, x="metric", y="ratio", hue="config")
        ax.axhline(0, color="black", linewidth=1, linestyle="--")
        ax.set_title("Compaction ratio delta vs theoretical optimum")
        ax.set_xlabel("Waste type")
        ax.set_ylabel("(real disposed - optimal disposed) / initial total waste")
        ax.legend(title="Configuration")
        plt.tight_layout()
        plt.savefig(out_dir / "compaction_ratio_distribution.png", dpi=150)
        plt.close()

    _plot_waste_composition(
        timeseries_df,
        out_dir,
        filtered_runs=filtered_runs,
        total_runs=total_runs,
    )
    _plot_metric_with_band(
        metric="cumulative_distance",
        title="Cumulative distance over time (mean with 95% interval)",
        ylabel="Cumulative distance",
        filename="cumulative_distance_over_time.png",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch runner for robot mission model")
    parser.add_argument("--green-agents", default=str(DEFAULT_MODEL_PARAMS["n_green_agents"]), help="Comma-separated values")
    parser.add_argument("--yellow-agents", default=str(DEFAULT_MODEL_PARAMS["n_yellow_agents"]), help="Comma-separated values")
    parser.add_argument("--red-agents", default=str(DEFAULT_MODEL_PARAMS["n_red_agents"]), help="Comma-separated values")
    parser.add_argument("--green-waste", default=str(DEFAULT_MODEL_PARAMS["n_green_waste"]), help="Comma-separated values")
    parser.add_argument("--yellow-waste", default=str(DEFAULT_MODEL_PARAMS["n_yellow_waste"]), help="Comma-separated values")
    parser.add_argument("--red-waste", default=str(DEFAULT_MODEL_PARAMS["n_red_waste"]), help="Comma-separated values")
    parser.add_argument("--width", default=str(DEFAULT_MODEL_PARAMS["width"]), help="Comma-separated values")
    parser.add_argument("--height", default=str(DEFAULT_MODEL_PARAMS["height"]), help="Comma-separated values")
    parser.add_argument("--exploration-share-interval-steps", default=str(DEFAULT_MODEL_PARAMS["exploration_share_interval_steps"]), help="Comma-separated values")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--number-processes", type=int, default=1)
    parser.add_argument("--seed-start", type=int, default=None, help="If set, run deterministic seeds from seed_start to seed_start + iterations - 1")
    parser.add_argument("--seeds", default=None, help="Comma-separated explicit seeds (requires --iterations 1)")
    parser.add_argument("--stall-window", type=int, default=200, help="Window size to flag no-progress runs")
    parser.add_argument("--policy-profile-green", default=str(DEFAULT_MODEL_PARAMS["policy_profile_green"]), help="Comma-separated policy profiles for green agents: no_communication, widespread, widespread_com_smart_explo")
    parser.add_argument("--policy-profile-yellow", default=str(DEFAULT_MODEL_PARAMS["policy_profile_yellow"]), help="Comma-separated policy profiles for yellow agents: no_communication, widespread, widespread_com_smart_explo")
    parser.add_argument("--policy-profile-red", default=str(DEFAULT_MODEL_PARAMS["policy_profile_red"]), help="Comma-separated policy profiles for red agents: no_communication, widespread, widespread_com_smart_explo")
    parser.add_argument("--output-dir", default="batch_outputs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.output_dir) / f"batch_{timestamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    parameters = {
        "n_green_agents": parse_int_list(args.green_agents),
        "n_yellow_agents": parse_int_list(args.yellow_agents),
        "n_red_agents": parse_int_list(args.red_agents),
        "n_green_waste": parse_int_list(args.green_waste),
        "n_yellow_waste": parse_int_list(args.yellow_waste),
        "n_red_waste": parse_int_list(args.red_waste),
        "width": parse_int_list(args.width),
        "height": parse_int_list(args.height),
        "exploration_share_interval_steps": parse_int_list(args.exploration_share_interval_steps),
        "policy_profile_green": parse_str_list(args.policy_profile_green),
        "policy_profile_yellow": parse_str_list(args.policy_profile_yellow),
        "policy_profile_red": parse_str_list(args.policy_profile_red),
    }

    batch_iterations = args.iterations
    if args.seed_start is not None and args.seeds is not None:
        raise ValueError("Use either --seed-start or --seeds, not both")
    if args.seeds is not None:
        if args.iterations != 1:
            raise ValueError("When using --seeds, set --iterations 1")
        parameters["seed"] = parse_int_list(args.seeds)
    elif args.seed_start is not None:
        parameters["seed"] = list(range(args.seed_start, args.seed_start + args.iterations))
        batch_iterations = 1

    print("Launching batch runner...")
    if args.number_processes != 1:
        print("Warning: custom runner currently executes sequentially; --number-processes is ignored.")
    results = _run_batch(
        parameters=parameters,
        iterations=batch_iterations,
        max_steps=args.max_steps,
        display_progress=True,
    )

    results_df = pd.DataFrame(results)
    raw_path = out_dir / "batch_run_raw.csv"
    results_df.to_csv(raw_path, index=False)

    model_rows = results_df.copy()

    model_rows["config"] = (
        "A(g"
        + model_rows["n_green_agents"].astype(str)
        + ",y"
        + model_rows["n_yellow_agents"].astype(str)
        + ",r"
        + model_rows["n_red_agents"].astype(str)
        + ")-W(g"
        + model_rows["n_green_waste"].astype(str)
        + ",y"
        + model_rows["n_yellow_waste"].astype(str)
        + ",r"
        + model_rows["n_red_waste"].astype(str)
        + ")-G("
        + model_rows["width"].astype(str)
        + "x"
        + model_rows["height"].astype(str)
        + ")"
        + "-P(g" 
        + model_rows["policy_profile_green"].astype(str)
        + ",y"
        + model_rows["policy_profile_yellow"].astype(str)
        + ",r"
        + model_rows["policy_profile_red"].astype(str)
        + ")"
    )

    run_distance_stagnation = (
        model_rows.sort_values(["RunId", "Step"])
        .groupby("RunId")["cumulative_distance"]
        .apply(lambda s: _has_stagnation_window(s, DISTANCE_STALL_WINDOW))
        .rename("distance_stagnation")
        .reset_index()
    )
    model_rows = model_rows.merge(run_distance_stagnation, on="RunId", how="left")
    model_rows["distance_stagnation"] = model_rows["distance_stagnation"].fillna(False)

    total_runs = int(model_rows["RunId"].nunique()) if not model_rows.empty else 0
    filtered_runs = int(run_distance_stagnation["distance_stagnation"].sum()) if not run_distance_stagnation.empty else 0

    usable_rows = model_rows[~model_rows["distance_stagnation"]].copy()

    # Summary: last collected row per run.
    summary_df = (
        usable_rows.sort_values(["RunId", "Step"]).groupby("RunId", as_index=False).tail(1).copy()
    )

    if "seed" not in summary_df.columns:
        summary_df["seed"] = pd.NA

    if "step_all_zero" not in summary_df.columns and "step_total_zero" in summary_df.columns:
        summary_df["step_all_zero"] = summary_df["step_total_zero"]
    if "step_all_zero" in summary_df.columns and "steps_executed" in summary_df.columns:
        summary_df["step_all_zero_effective"] = summary_df["step_all_zero"].fillna(
            summary_df["steps_executed"]
        )

    initial_total_waste = (
        summary_df["n_green_waste"] + summary_df["n_yellow_waste"] + summary_df["n_red_waste"]
    )
    summary_df["initial_total_waste"] = initial_total_waste

    optimal = _optimal_disposal_counts(
        summary_df["n_green_waste"],
        summary_df["n_yellow_waste"],
        summary_df["n_red_waste"],
    )
    summary_df["optimal_green"] = optimal["green"]
    summary_df["optimal_yellow"] = optimal["yellow"]
    summary_df["optimal_red"] = optimal["red"]
    summary_df["optimal_total"] = optimal["total"]

    denominator = summary_df["initial_total_waste"].replace(0, pd.NA)
    summary_df["compaction_ratio_green"] = (
        summary_df["disposed_green"] - summary_df["optimal_green"]
    ) / denominator
    summary_df["compaction_ratio_yellow"] = (
        summary_df["disposed_yellow"] - summary_df["optimal_yellow"]
    ) / denominator
    summary_df["compaction_ratio_red"] = (
        summary_df["disposed_red"] - summary_df["optimal_red"]
    ) / denominator
    summary_df["compaction_ratio_total"] = (
        summary_df["disposed_total"] - summary_df["optimal_total"]
    ) / denominator

    summary_df["timed_out"] = (
        (~summary_df["cleaned"].fillna(False)) & (summary_df["steps_executed"] >= args.max_steps)
    )

    if "total" in summary_df.columns:
        summary_df["stopped_with_waste"] = summary_df["total"].fillna(0) > 0
    else:
        summary_df["stopped_with_waste"] = pd.NA

    if "total" in usable_rows.columns and args.stall_window > 0:
        stall_by_run = (
            usable_rows.sort_values(["RunId", "Step"])
            .groupby("RunId")["total"]
            .apply(
                lambda s: (len(s) >= args.stall_window)
                and (s.iloc[-args.stall_window:].nunique() == 1)
                and (s.iloc[-1] > 0)
            )
            .rename("possible_deadlock")
            .reset_index()
        )
        summary_df = summary_df.merge(stall_by_run, on="RunId", how="left")
    else:
        summary_df["possible_deadlock"] = False

    if "seed" not in summary_df.columns:
        summary_df["seed"] = pd.NA

    if "step_all_zero" not in summary_df.columns and "step_total_zero" in summary_df.columns:
        summary_df["step_all_zero"] = summary_df["step_total_zero"]
    if "step_all_zero" in summary_df.columns and "steps_executed" in summary_df.columns:
        summary_df["step_all_zero_effective"] = summary_df["step_all_zero"].fillna(
            summary_df["steps_executed"]
        )

    initial_total_waste = (
        summary_df["n_green_waste"] + summary_df["n_yellow_waste"] + summary_df["n_red_waste"]
    )
    summary_df["initial_total_waste"] = initial_total_waste

    optimal = _optimal_disposal_counts(
        summary_df["n_green_waste"],
        summary_df["n_yellow_waste"],
        summary_df["n_red_waste"],
    )
    summary_df["optimal_green"] = optimal["green"]
    summary_df["optimal_yellow"] = optimal["yellow"]
    summary_df["optimal_red"] = optimal["red"]
    summary_df["optimal_total"] = optimal["total"]

    denominator = summary_df["initial_total_waste"].replace(0, pd.NA)
    summary_df["compaction_ratio_green"] = (
        summary_df["disposed_green"] - summary_df["optimal_green"]
    ) / denominator
    summary_df["compaction_ratio_yellow"] = (
        summary_df["disposed_yellow"] - summary_df["optimal_yellow"]
    ) / denominator
    summary_df["compaction_ratio_red"] = (
        summary_df["disposed_red"] - summary_df["optimal_red"]
    ) / denominator
    summary_df["compaction_ratio_total"] = (
        summary_df["disposed_total"] - summary_df["optimal_total"]
    ) / denominator

    summary_df["timed_out"] = (
        (~summary_df["cleaned"].fillna(False)) & (summary_df["steps_executed"] >= args.max_steps)
    )

    if "total" in summary_df.columns:
        summary_df["stopped_with_waste"] = summary_df["total"].fillna(0) > 0
    else:
        summary_df["stopped_with_waste"] = pd.NA

    if "total" in model_rows.columns and args.stall_window > 0:
        stall_by_run = (
            model_rows.sort_values(["RunId", "Step"])
            .groupby("RunId")["total"]
            .apply(
                lambda s: (len(s) >= args.stall_window)
                and (s.iloc[-args.stall_window:].nunique() == 1)
                and (s.iloc[-1] > 0)
            )
            .rename("possible_deadlock")
            .reset_index()
        )
        summary_df = summary_df.merge(stall_by_run, on="RunId", how="left")
    else:
        summary_df["possible_deadlock"] = False

    summary_keep = [
        "RunId",
        "iteration",
        "config",
        "n_green_agents",
        "n_yellow_agents",
        "n_red_agents",
        "n_green_waste",
        "n_yellow_waste",
        "n_red_waste",
        "steps_executed",
        "seed",
        "cleaned",
        "timed_out",
        "stopped_with_waste",
        "possible_deadlock",
        "step_green_zero",
        "step_yellow_zero",
        "step_red_zero",
        "step_total_zero",
        "step_all_zero",
        "step_all_zero_effective",
        "disposed_green",
        "disposed_yellow",
        "disposed_red",
        "disposed_total",
        "initial_total_waste",
        "optimal_green",
        "optimal_yellow",
        "optimal_red",
        "optimal_total",
        "compaction_ratio_green",
        "compaction_ratio_yellow",
        "compaction_ratio_red",
        "compaction_ratio_total",
        "green",
        "yellow",
        "red",
        "total",
        "cumulative_distance",
    ]
    summary_df = summary_df[[c for c in summary_keep if c in summary_df.columns]]
    timeseries_df = usable_rows.copy()

    summary_path = out_dir / "summary.csv"
    timeseries_path = out_dir / "timeseries.csv"
    suspicious_path = out_dir / "suspicious_runs.csv"
    filtered_runs_path = out_dir / "filtered_runs_distance_stall.csv"
    summary_df.to_csv(summary_path, index=False)
    timeseries_df.to_csv(timeseries_path, index=False)
    run_distance_stagnation[run_distance_stagnation["distance_stagnation"]].to_csv(
        filtered_runs_path,
        index=False,
    )
    summary_df[
        summary_df["timed_out"] | summary_df["possible_deadlock"] | summary_df["stopped_with_waste"]
    ].to_csv(suspicious_path, index=False)

    make_plots(
        summary_df,
        timeseries_df,
        out_dir,
        filtered_runs=filtered_runs,
        total_runs=total_runs,
    )

    cleaned_rate = summary_df["cleaned"].mean() if not summary_df.empty else 0.0
    print("\nBatch completed")
    print(f"Output directory: {out_dir}")
    print(
        "Runs filtered out due to cumulative_distance stagnation "
        f"({DISTANCE_STALL_WINDOW}+ steps): {filtered_runs} / {total_runs}"
    )
    print(f"Cleaned runs: {summary_df['cleaned'].sum()} / {len(summary_df)} ({cleaned_rate:.1%})")
    timeout_count = int(summary_df["timed_out"].sum())
    deadlock_count = int(summary_df["possible_deadlock"].sum())
    print(f"Timed-out runs (max_steps reached): {timeout_count}")
    print(f"Possible deadlocks (no progress over last {args.stall_window} steps): {deadlock_count}")
    if not summary_df["step_total_zero"].dropna().empty:
        mean_cleanup = summary_df["step_total_zero"].dropna().mean()
        print(f"Mean cleanup step (successful runs): {mean_cleanup:.2f}")

    repro_row = summary_df[summary_df["possible_deadlock"] | summary_df["timed_out"]]
    if not repro_row.empty and "seed" in repro_row.columns and repro_row["seed"].notna().any():
        first = repro_row[repro_row["seed"].notna()].iloc[0]
        iteration_value = int(first["iteration"]) if "iteration" in first and pd.notna(first["iteration"]) else -1
        print(
            "Repro candidate seed: "
            f"{int(first['seed'])} (RunId={int(first['RunId'])}, iteration={iteration_value})"
        )


if __name__ == "__main__":
    main()

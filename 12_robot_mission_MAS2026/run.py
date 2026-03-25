"""Batch simulation runner based on Mesa's batch_run."""

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


def parse_int_list(value: str) -> list[int]:
    return [int(v.strip()) for v in value.split(",") if v.strip()]


def _latest_count(model: Model, key: str) -> int:
    if not model.waste_count_history:
        counts = model._compute_waste_counts()  # pylint: disable=protected-access
        return counts[key]
    return model.waste_count_history[-1][key]


def _latest_distance(model: Model) -> int:
    if not model.cumulative_distance_history:
        return 0
    return model.cumulative_distance_history[-1]["distance"]


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
    """Model wrapper that exposes reporters for mesa.batch_run."""

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
            }
        )
        self.datacollector.collect(self)

    def step(self):
        super().step()
        self.datacollector.collect(self)


def make_plots(summary_df: pd.DataFrame, timeseries_df: pd.DataFrame, out_dir: Path) -> None:
    sns.set_theme(style="whitegrid")

    total_step_col = "step_all_zero" if "step_all_zero" in summary_df.columns else "step_total_zero"
    total_step_effective_col = (
        "step_all_zero_effective"
        if "step_all_zero_effective" in summary_df.columns
        else total_step_col
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
        ax.legend(title="Configuration")
        plt.tight_layout()
        plt.savefig(out_dir / filename, dpi=150)
        plt.close()

    cleaned_df = summary_df.dropna(subset=[total_step_col])
    if not cleaned_df.empty:
        plt.figure(figsize=(10, 5))
        ax = sns.boxplot(data=cleaned_df, x="config", y=total_step_col)
        ax.set_title("Distribution of cleanup step (total waste reaches 0)")
        ax.set_xlabel("Configuration")
        ax.set_ylabel("Step")
        ax.tick_params(axis="x", rotation=25)
        plt.tight_layout()
        plt.savefig(out_dir / "cleanup_step_distribution.png", dpi=150)
        plt.close()

    total_cleanup_df = summary_df[[total_step_effective_col]].dropna().copy()
    if not total_cleanup_df.empty:
        total_cleanup_df["metric"] = "step_all_zero"
        plt.figure(figsize=(6, 5))
        ax = sns.boxplot(data=total_cleanup_df, x="metric", y=total_step_effective_col)
        ax.set_title("Total cleanup step distribution")
        ax.set_xlabel("Metric")
        ax.set_ylabel("Step")
        plt.tight_layout()
        plt.savefig(out_dir / "total_cleanup_step_boxplot.png", dpi=150)
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

    _plot_metric_with_band(
        metric="total",
        title="Total waste over time (mean with 95% interval)",
        ylabel="Total waste",
        filename="total_waste_over_time.png",
    )
    _plot_metric_with_band(
        metric="cumulative_distance",
        title="Cumulative distance over time (mean with 95% interval)",
        ylabel="Cumulative distance",
        filename="cumulative_distance_over_time.png",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch runner for robot mission model (Mesa batch_run)")
    parser.add_argument("--green-agents", default="1", help="Comma-separated values")
    parser.add_argument("--yellow-agents", default="1", help="Comma-separated values")
    parser.add_argument("--red-agents", default="1", help="Comma-separated values")
    parser.add_argument("--green-waste", default="10", help="Comma-separated values")
    parser.add_argument("--yellow-waste", default="0", help="Comma-separated values")
    parser.add_argument("--red-waste", default="0", help="Comma-separated values")
    parser.add_argument("--width", default="30", help="Comma-separated values")
    parser.add_argument("--height", default="30", help="Comma-separated values")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--number-processes", type=int, default=1)
    parser.add_argument("--seed-start", type=int, default=None, help="If set, run deterministic seeds from seed_start to seed_start + iterations - 1")
    parser.add_argument("--seeds", default=None, help="Comma-separated explicit seeds (requires --iterations 1)")
    parser.add_argument("--stall-window", type=int, default=200, help="Window size to flag no-progress runs")
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

    # Keep only model-level rows (batch_run may include per-agent rows if AgentID exists).
    if "AgentID" in results_df.columns:
        model_rows = results_df[results_df["AgentID"].isna()].copy()
        if model_rows.empty:
            model_rows = results_df.copy()
    else:
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
    )

    # Summary: last collected row per run.
    summary_df = (
        model_rows.sort_values(["RunId", "Step"]).groupby("RunId", as_index=False).tail(1).copy()
    )

    if "seed" not in summary_df.columns:
        summary_df["seed"] = pd.NA

    if "step_all_zero" not in summary_df.columns and "step_total_zero" in summary_df.columns:
        summary_df["step_all_zero"] = summary_df["step_total_zero"]
    if "step_all_zero" in summary_df.columns and "steps_executed" in summary_df.columns:
        summary_df["step_all_zero_effective"] = summary_df["step_all_zero"].fillna(
            summary_df["steps_executed"]
        )

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
        "green",
        "yellow",
        "red",
        "total",
        "cumulative_distance",
    ]
    summary_df = summary_df[[c for c in summary_keep if c in summary_df.columns]]
    timeseries_df = model_rows.copy()

    summary_path = out_dir / "summary.csv"
    timeseries_path = out_dir / "timeseries.csv"
    suspicious_path = out_dir / "suspicious_runs.csv"
    summary_df.to_csv(summary_path, index=False)
    timeseries_df.to_csv(timeseries_path, index=False)
    summary_df[
        summary_df["timed_out"] | summary_df["possible_deadlock"] | summary_df["stopped_with_waste"]
    ].to_csv(suspicious_path, index=False)

    make_plots(summary_df, timeseries_df, out_dir)

    cleaned_rate = summary_df["cleaned"].mean() if not summary_df.empty else 0.0
    print("\nBatch completed")
    print(f"Output directory: {out_dir}")
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

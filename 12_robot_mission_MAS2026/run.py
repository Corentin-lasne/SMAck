"""Batch simulation runner based on Mesa's batch_run."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
import mesa
import pandas as pd
import seaborn as sns
from mesa.datacollection import DataCollector

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

    cleaned_df = summary_df.dropna(subset=["step_total_zero"])
    if not cleaned_df.empty:
        plt.figure(figsize=(10, 5))
        ax = sns.boxplot(data=cleaned_df, x="config", y="step_total_zero")
        ax.set_title("Distribution of cleanup step (total waste reaches 0)")
        ax.set_xlabel("Configuration")
        ax.set_ylabel("Step")
        ax.tick_params(axis="x", rotation=25)
        plt.tight_layout()
        plt.savefig(out_dir / "cleanup_step_distribution.png", dpi=150)
        plt.close()

    extinction_cols = ["step_green_zero", "step_yellow_zero", "step_red_zero", "step_total_zero"]
    melt_df = summary_df.melt(
        id_vars=["config", "RunId"],
        value_vars=extinction_cols,
        var_name="metric",
        value_name="step",
    ).dropna(subset=["step"])
    if not melt_df.empty:
        plt.figure(figsize=(10, 5))
        ax = sns.boxplot(data=melt_df, x="metric", y="step")
        ax.set_title("Distribution of extinction steps by metric")
        ax.set_xlabel("Metric")
        ax.set_ylabel("Step")
        plt.tight_layout()
        plt.savefig(out_dir / "extinction_steps_distribution.png", dpi=150)
        plt.close()

    if not timeseries_df.empty:
        plt.figure(figsize=(10, 5))
        ax = sns.lineplot(
            data=timeseries_df,
            x="Step",
            y="total",
            hue="config",
            errorbar=("ci", 95),
        )
        ax.set_title("Total waste over time (mean with 95% CI)")
        ax.set_xlabel("Step")
        ax.set_ylabel("Total waste")
        plt.tight_layout()
        plt.savefig(out_dir / "total_waste_over_time.png", dpi=150)
        plt.close()

        plt.figure(figsize=(10, 5))
        ax = sns.lineplot(
            data=timeseries_df,
            x="Step",
            y="cumulative_distance",
            hue="config",
            errorbar=("ci", 95),
        )
        ax.set_title("Cumulative distance over time (mean with 95% CI)")
        ax.set_xlabel("Step")
        ax.set_ylabel("Cumulative distance")
        plt.tight_layout()
        plt.savefig(out_dir / "cumulative_distance_over_time.png", dpi=150)
        plt.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch runner for robot mission model (Mesa batch_run)")
    parser.add_argument("--green-agents", default="1", help="Comma-separated values")
    parser.add_argument("--yellow-agents", default="1", help="Comma-separated values")
    parser.add_argument("--red-agents", default="1", help="Comma-separated values")
    parser.add_argument("--green-waste", default="10", help="Comma-separated values")
    parser.add_argument("--yellow-waste", default="0", help="Comma-separated values")
    parser.add_argument("--red-waste", default="0", help="Comma-separated values")
    parser.add_argument("--width", type=int, default=30)
    parser.add_argument("--height", type=int, default=30)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--max-steps", type=int, default=1000)
    parser.add_argument("--number-processes", type=int, default=1)
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
        "width": args.width,
        "height": args.height,
    }

    print("Launching mesa.batch_run...")
    results = mesa.batch_run(
        BatchModel,
        parameters=parameters,
        iterations=args.iterations,
        max_steps=args.max_steps,
        number_processes=args.number_processes,
        data_collection_period=1,
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
        + ")"
    )

    # Summary: last collected row per run.
    summary_df = (
        model_rows.sort_values(["RunId", "Step"]).groupby("RunId", as_index=False).tail(1).copy()
    )

    summary_keep = [
        "RunId",
        "config",
        "n_green_agents",
        "n_yellow_agents",
        "n_red_agents",
        "n_green_waste",
        "n_yellow_waste",
        "n_red_waste",
        "steps_executed",
        "cleaned",
        "step_green_zero",
        "step_yellow_zero",
        "step_red_zero",
        "step_total_zero",
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
    summary_df.to_csv(summary_path, index=False)
    timeseries_df.to_csv(timeseries_path, index=False)

    make_plots(summary_df, timeseries_df, out_dir)

    cleaned_rate = summary_df["cleaned"].mean() if not summary_df.empty else 0.0
    print("\nBatch completed")
    print(f"Output directory: {out_dir}")
    print(f"Cleaned runs: {summary_df['cleaned'].sum()} / {len(summary_df)} ({cleaned_rate:.1%})")
    if not summary_df["step_total_zero"].dropna().empty:
        mean_cleanup = summary_df["step_total_zero"].dropna().mean()
        print(f"Mean cleanup step (successful runs): {mean_cleanup:.2f}")


if __name__ == "__main__":
    main()

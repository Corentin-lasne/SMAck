"""
Advanced batch analysis example - inspired by PW3_Data_MABS_2026_Subject.

This file demonstrates how to use run.py's batch_run output for plotting
and statistical analysis, similar to the notebook workbook.

Usage:
    # 1. Generate batch data
    python run.py --batch --iterations 20 --steps 80 --output results.csv
    
    # 2. Analyze the data
    python batch_analyzer.py --input results.csv
"""

import argparse
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from pathlib import Path


def analyze_batch_results(csv_file, output_dir="batch_analysis"):
    """
    Analyze batch simulation results and generate plots.
    
    Args:
        csv_file (str): Path to results CSV file from run.py --batch
        output_dir (str): Directory to save analysis plots
    """
    # Create output directory
    Path(output_dir).mkdir(exist_ok=True)
    
    print(f"\n{'='*80}")
    print(f"Analyzing batch results from: {csv_file}")
    print(f"{'='*80}\n")
    
    # Load data
    df = pd.read_csv(csv_file)
    print(f"✓ Loaded {len(df)} simulation runs")
    print(f"✓ Unique yellow agents: {sorted(df['n_yellow_agents'].unique())}")
    print(f"✓ Unique red agents: {sorted(df['n_red_agents'].unique())}")
    print()
    
    # --- Plot 1: Red waste disposal by configuration ---
    print("Generating plot 1: Red waste disposal efficiency...")
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Group by configuration and average
    disposal_by_config = df.groupby(['n_yellow_agents', 'n_red_agents'])['red_waste_disposed'].agg(['mean', 'std', 'count']).reset_index()
    
    # Pivot for plotting
    disposal_pivot = disposal_by_config.pivot(index='n_yellow_agents', columns='n_red_agents', values='mean')
    
    sns.heatmap(disposal_pivot, annot=True, fmt='.1f', cmap='YlGn', ax=ax, cbar_kws={'label': 'Avg Red Waste Disposed'})
    ax.set_title('Red Waste Disposed by Agent Configuration\n(averaged over iterations)', fontsize=12, fontweight='bold')
    ax.set_xlabel('Number of Red Agents')
    ax.set_ylabel('Number of Yellow Agents')
    plt.tight_layout()
    plt.savefig(f"{output_dir}/01_disposal_heatmap.png", dpi=150)
    print(f"  ✓ Saved to: {output_dir}/01_disposal_heatmap.png\n")
    plt.close()
    
    # --- Plot 2: Waste remaining by configuration ---
    print("Generating plot 2: Waste remaining in environment...")
    fig, ax = plt.subplots(figsize=(10, 6))
    
    waste_by_config = df.groupby(['n_yellow_agents', 'n_red_agents'])['waste_remaining'].agg(['mean', 'std']).reset_index()
    
    # Line plot showing trend
    for n_red in sorted(df['n_red_agents'].unique()):
        subset = waste_by_config[waste_by_config['n_red_agents'] == n_red]
        ax.plot(subset['n_yellow_agents'], subset['waste_remaining'], 
               marker='o', label=f'{n_red} Red Agents', linewidth=2, markersize=8)
        ax.fill_between(subset['n_yellow_agents'], 
                        subset['waste_remaining'] - subset['std'],
                        subset['waste_remaining'] + subset['std'],
                        alpha=0.2)
    
    ax.set_xlabel('Number of Yellow Agents', fontsize=11, fontweight='bold')
    ax.set_ylabel('Waste Remaining (items)', fontsize=11, fontweight='bold')
    ax.set_title('Remaining Waste in Environment\n(mean ± std dev across iterations)', fontsize=12, fontweight='bold')
    ax.legend(title='Configuration')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/02_waste_remaining.png", dpi=150)
    print(f"  ✓ Saved to: {output_dir}/02_waste_remaining.png\n")
    plt.close()
    
    # --- Plot 3: Efficiency metric ---
    print("Generating plot 3: Processing efficiency...")
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Calculate efficiency = (wastes disposed / total wastes)
    # First, estimate total wastes (from original simulation setup)
    # Assuming 5 red wastes total (as per model defaults)
    total_red_waste = 5
    
    df['efficiency'] = (df['red_waste_disposed'] / total_red_waste * 100).clip(0, 100)
    
    efficiency_by_config = df.groupby(['n_yellow_agents', 'n_red_agents'])['efficiency'].agg(['mean', 'std']).reset_index()
    
    for n_red in sorted(df['n_red_agents'].unique()):
        subset = efficiency_by_config[efficiency_by_config['n_red_agents'] == n_red]
        ax.plot(subset['n_yellow_agents'], subset['efficiency'], 
               marker='s', label=f'{n_red} Red Agents', linewidth=2, markersize=8)
    
    ax.set_xlabel('Number of Yellow Agents', fontsize=11, fontweight='bold')
    ax.set_ylabel('Disposal Efficiency (%)', fontsize=11, fontweight='bold')
    ax.set_title('Waste Processing Efficiency\n(% of red waste disposed)', fontsize=12, fontweight='bold')
    ax.set_ylim([0, 105])
    ax.axhline(y=100, color='green', linestyle='--', alpha=0.5, label='Perfect efficiency')
    ax.legend()
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(f"{output_dir}/03_efficiency.png", dpi=150)
    print(f"  ✓ Saved to: {output_dir}/03_efficiency.png\n")
    plt.close()
    
    # --- Plot 4: Scatter - All runs ---
    print("Generating plot 4: All simulation runs scatter plot...")
    fig, ax = plt.subplots(figsize=(11, 7))
    
    # Color by configuration, size by waste remaining
    scatter = ax.scatter(df['n_yellow_agents'] + df['n_red_agents'] * 0.01,  # Slight jitter
                        df['red_waste_disposed'],
                        s=df['waste_remaining']*50 + 50,
                        c=df['efficiency'],
                        cmap='RdYlGn',
                        alpha=0.6,
                        edgecolors='black',
                        linewidth=0.5)
    
    ax.set_xlabel('Total Agents (Yellow + Red)', fontsize=11, fontweight='bold')
    ax.set_ylabel('Red Waste Disposed (items)', fontsize=11, fontweight='bold')
    ax.set_title('All Simulation Runs\n(size = waste remaining, color = efficiency %)', fontsize=12, fontweight='bold')
    
    cbar = plt.colorbar(scatter, ax=ax, label='Efficiency (%)')
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f"{output_dir}/04_all_runs_scatter.png", dpi=150)
    print(f"  ✓ Saved to: {output_dir}/04_all_runs_scatter.png\n")
    plt.close()
    
    # --- Statistics Summary ---
    print("Statistical Summary")
    print(f"{'='*80}")
    print(f"\nOverall statistics:")
    print(f"  - Total runs: {len(df)}")
    print(f"  - Average red waste disposed: {df['red_waste_disposed'].mean():.2f} ± {df['red_waste_disposed'].std():.2f}")
    print(f"  - Average waste remaining: {df['waste_remaining'].mean():.2f} ± {df['waste_remaining'].std():.2f}")
    print(f"  - Average efficiency: {df['efficiency'].mean():.1f}% ± {df['efficiency'].std():.1f}%\n")
    
    print(f"Breakdown by number of yellow agents:")
    yellow_group = df.groupby('n_yellow_agents')[['red_waste_disposed', 'waste_remaining', 'efficiency']].agg(['mean', 'std'])
    for n_yellow in sorted(df['n_yellow_agents'].unique()):
        subset = df[df['n_yellow_agents'] == n_yellow]
        print(f"  Yellow={n_yellow}: disposal={subset['red_waste_disposed'].mean():.1f}±{subset['red_waste_disposed'].std():.1f}, "
              f"remaining={subset['waste_remaining'].mean():.1f}±{subset['waste_remaining'].std():.1f}, "
              f"efficiency={subset['efficiency'].mean():.0f}%±{subset['efficiency'].std():.0f}%")
    
    print(f"\nBreakdown by number of red agents:")
    for n_red in sorted(df['n_red_agents'].unique()):
        subset = df[df['n_red_agents'] == n_red]
        print(f"  Red={n_red}: disposal={subset['red_waste_disposed'].mean():.1f}±{subset['red_waste_disposed'].std():.1f}, "
              f"remaining={subset['waste_remaining'].mean():.1f}±{subset['waste_remaining'].std():.1f}, "
              f"efficiency={subset['efficiency'].mean():.0f}%±{subset['efficiency'].std():.0f}%")
    
    print(f"\n{'='*80}")
    print(f"✓ Analysis complete! All plots saved to: {output_dir}/\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyze batch simulation results",
        epilog="Example:\n  python batch_analyzer.py --input results.csv --output analysis/"
    )
    
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Input CSV file from 'python run.py --batch'",
    )
    
    parser.add_argument(
        "--output", "-o",
        default="batch_analysis",
        help="Output directory for plots (default: batch_analysis/)",
    )
    
    args = parser.parse_args()
    
    if not Path(args.input).exists():
        print(f"✗ Error: File not found: {args.input}")
        print(f"\nFirst, generate batch data with:")
        print(f"  python run.py --batch --iterations 20 --output {args.input}")
        exit(1)
    
    analyze_batch_results(args.input, args.output)

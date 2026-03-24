"""
Command-line interface for running simulations.

Usage:
    python run.py                           # Default single run with debug logs
    python run.py --steps 100               # Custom number of steps
    python run.py --debug                   # Enable verbose debug logging
    python run.py --seed 42                 # Fixed seed for reproducibility
    python run.py --batch                   # Run batch simulations (parameter sweep)
    python run.py --help                    # Show all options
"""

import argparse
import sys
from model import Model
import pandas as pd


def run_single_simulation(
    n_green_agents=1,
    n_yellow_agents=1,
    n_red_agents=1,
    n_green_waste=2,
    n_yellow_waste=0,
    n_red_waste=0,
    steps=100,
    debug=True,
    seed=None,
    verbose=True,
):
    """
    Run a single simulation instance.
    
    Args:
        n_green_agents (int): Number of green agents
        n_yellow_agents (int): Number of yellow agents
        n_red_agents (int): Number of red agents
        n_green_waste (int): Number of green waste items
        n_yellow_waste (int): Number of yellow waste items
        n_red_waste (int): Number of red waste items
        steps (int): Number of simulation steps to run
        debug (bool): Enable debug logging
        seed (int): Random seed for reproducibility
        verbose (bool): Print status messages
        
    Returns:
        model (Model): The completed simulation model
    """
    if verbose:
        print("\n" + "=" * 80)
        print("SINGLE SIMULATION RUN")
        print("=" * 80)
        print(f"\nConfiguration:")
        print(f"  - Green agents: {n_green_agents}, Yellow agents: {n_yellow_agents}, Red agents: {n_red_agents}")
        print(f"  - Green waste: {n_green_waste}, Yellow waste: {n_yellow_waste}, Red waste: {n_red_waste}")
        print(f"  - Simulation steps: {steps}")
        print(f"  - Debug mode: {'ENABLED' if debug else 'disabled'}")
        if seed is not None:
            print(f"  - Random seed: {seed}")
        print("\n" + "=" * 80)
        if debug:
            print("Starting simulation with debug logs...\n")
        else:
            print("Starting simulation...\n")
    
    # Create and configure model
    model = Model(
        n_green_agents=n_green_agents,
        n_yellow_agents=n_yellow_agents,
        n_red_agents=n_red_agents,
        n_green_waste=n_green_waste,
        n_yellow_waste=n_yellow_waste,
        n_red_waste=n_red_waste,
        width=24,
        height=18,
        seed=seed,
    )
    
    # Enable debug mode if requested
    if debug:
        model.debug = True
    
    # Run simulation
    for step_num in range(steps):
        model.step()
        if verbose and step_num % 10 == 0 and step_num > 0:
            print(f"  Step {step_num}/{steps} completed")
    
    if verbose:
        print(f"\n" + "=" * 80)
        print(f"Simulation completed after {steps} steps")
        print("=" * 80)
        
        # Print final statistics
        print(f"\nFinal Statistics:")
        print(f"  - Waste agents remaining: {len(model.wasteAgents)}")
        print(f"  - Red waste disposed: {model.disposed_red_count}")
        
        # Print agent inventories
        print(f"\nAgent Inventories (end state):")
        for agent in model.robotAgents:
            inv_str = f"{len(agent.inventory)} items"
            if agent.inventory:
                waste_types = {}
                for waste in agent.inventory:
                    wtype = waste.waste_type
                    waste_types[wtype] = waste_types.get(wtype, 0) + 1
                inv_str += f" {waste_types}"
            print(f"  - Agent {agent.unique_id:2d} ({agent.agent_role:6s}): {inv_str}")
        print()
    
    return model


def run_batch_simulation(
    param_ranges=None,
    iterations=5,
    steps=100,
    seed_start=0,
    verbose=True,
):
    """
    Run multiple simulations with parameter sweeps (batch mode).
    
    Similar to mesa.batch_run() but simpler, without multiprocessing.
    
    Args:
        param_ranges (dict): Dictionary of parameters to vary, e.g. {"n_green_agents": [1,2,3], "n_yellow_agents": [2,3]}
        iterations (int): Number of iterations per parameter combination
        steps (int): Number of steps per simulation
        seed_start (int): Starting seed value for reproducibility
        verbose (bool): Print progress
        
    Returns:
        results (list): List of dictionaries containing results
    """
    if param_ranges is None:
        # Default batch configuration: yellow→red communication focus
        param_ranges = {
            "n_yellow_agents": [2, 3, 4],
            "n_red_agents": [2, 3, 4],
        }
    
    if verbose:
        print("\n" + "=" * 80)
        print("BATCH SIMULATION RUN")
        print("=" * 80)
        print(f"\nBatch Configuration:")
        print(f"  - Parameter ranges: {param_ranges}")
        print(f"  - Iterations per combination: {iterations}")
        print(f"  - Steps per iteration: {steps}")
        print(f"  - Starting seed: {seed_start}")
        
        # Calculate total runs
        import math
        total_combinations = 1
        for values in param_ranges.values():
            if isinstance(values, (list, range)):
                total_combinations *= len(values)
            else:
                total_combinations *= 1
        total_runs = total_combinations * iterations
        print(f"  - Total simulation runs: {total_runs} (= {total_combinations} combinations × {iterations} iterations)")
        print("\n" + "=" * 80 + "\n")
    
    results = []
    run_count = 0
    total_combinations = 1
    for values in param_ranges.values():
        if isinstance(values, (list, range)):
            total_combinations *= len(values)
    
    total_runs = total_combinations * iterations
    
    # Generate all parameter combinations
    import itertools
    param_names = list(param_ranges.keys())
    param_values = [param_ranges[name] for name in param_names]
    
    for combo_idx, param_combo in enumerate(itertools.product(*param_values)):
        params = dict(zip(param_names, param_combo))
        
        for iteration in range(iterations):
            seed = seed_start + run_count if seed_start is not None else None
            
            if verbose:
                run_count += 1
                combo_str = ", ".join([f"{k}={v}" for k, v in params.items()])
                print(f"[{run_count}/{total_runs}] Running: {combo_str}, iteration={iteration+1}/{iterations}, seed={seed}")
            
            # Default fixed parameters
            fixed_params = {
                "n_green_agents": 0,
                "n_yellow_waste": 0,
                "n_red_waste": 0,
                "steps": steps,
                "debug": False,
                "seed": seed,
                "verbose": False,
            }
            # Override with swept parameters
            fixed_params.update(params)
            
            # Run simulation
            model = run_single_simulation(**fixed_params)
            
            # Store results
            result = {
                "iteration": iteration,
                "seed": seed,
                "n_yellow_agents": model.num_yellow_agents,
                "n_red_agents": model.num_red_agents,
                "waste_remaining": len(model.wasteAgents),
                "red_waste_disposed": model.disposed_red_count,
                "steps": steps,
            }
            # Add agent inventory details
            for agent in model.robotAgents:
                inv_count = sum(1 for w in agent.inventory if w.waste_type in ["yellow", "red"])
                result[f"agent_{agent.unique_id}_inventory_{agent.agent_role}"] = inv_count
            
            results.append(result)
    
    if verbose:
        print("\n" + "=" * 80)
        print(f"Batch simulation completed: {total_runs} runs finished")
        print("=" * 80 + "\n")
    
    return results


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description="Multi-Agent Waste Processing Simulation Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                              # Single run with debug logs (default)
  python run.py --steps 100                  # 100 simulation steps
  python run.py --seed 42                    # Fixed seed for reproducibility
  python run.py --no-debug                   # Run without debug logs
  python run.py --batch                      # Run batch parameter sweep
  python run.py --batch --iterations 10      # Batch with 10 iterations per combination
        """,
    )
    
    parser.add_argument(
        "--mode",
        choices=["single", "batch"],
        default="single",
        help="Simulation mode: single run or batch sweep (default: single)",
    )
    
    parser.add_argument(
        "--steps",
        type=int,
        default=40,
        help="Number of simulation steps (default: 40)",
    )
    
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility (default: None = random)",
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        default=True,
        help="Enable debug logging (default: enabled for single runs)",
    )
    
    parser.add_argument(
        "--no-debug",
        action="store_false",
        dest="debug",
        help="Disable debug logging",
    )
    
    parser.add_argument(
        "--batch",
        action="store_true",
        dest="batch_mode",
        help="Run batch simulations with parameter sweep",
    )
    
    parser.add_argument(
        "--iterations",
        type=int,
        default=5,
        help="Number of iterations per parameter combination in batch mode (default: 5)",
    )
    
    parser.add_argument(
        "--green-agents",
        type=int,
        default=3,
        help="Number of green agents (default: 3)",
    )
    
    parser.add_argument(
        "--yellow-agents",
        type=int,
        default=3,
        help="Number of yellow agents (default: 3)",
    )
    
    parser.add_argument(
        "--red-agents",
        type=int,
        default=3,
        help="Number of red agents (default: 3)",
    )
    
    parser.add_argument(
        "--green-waste",
        type=int,
        default=6,
        help="Number of green waste items (default: 6)",
    )
    
    parser.add_argument(
        "--yellow-waste",
        type=int,
        default=3,
        help="Number of yellow waste items (default: 3)",
    )
    
    parser.add_argument(
        "--red-waste",
        type=int,
        default=5,
        help="Number of red waste items (default: 5)",
    )
    
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Save batch results to CSV file (batch mode only)",
    )
    
    args = parser.parse_args()
    
    try:
        if args.batch_mode:
            # Batch mode
            results = run_batch_simulation(
                iterations=args.iterations,
                steps=args.steps,
                seed_start=args.seed if args.seed is not None else 0,
                verbose=True,
            )
            
            # Save results if requested
            if args.output:
                df = pd.DataFrame(results)
                df.to_csv(args.output, index=False)
                print(f"✓ Results saved to: {args.output}\n")
        else:
            # Single run mode (default)
            model = run_single_simulation(
                n_green_agents=args.green_agents,
                n_yellow_agents=args.yellow_agents,
                n_red_agents=args.red_agents,
                n_green_waste=args.green_waste,
                n_yellow_waste=args.yellow_waste,
                n_red_waste=args.red_waste,
                steps=args.steps,
                debug=args.debug,
                seed=args.seed,
                verbose=True,
            )
        
        return 0
    
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

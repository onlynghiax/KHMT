"""
N-Queens Benchmark Suite
========================
Benchmarks 7 solving methods across a wide range of board sizes (N).
- 3 SAT Encodings: Binomial, Binary, Sequential Counter
- 4 Optimization Solvers: CPLEX CP, CPLEX MIP, Gurobi MIP, OR-Tools CP-SAT

Features:
  - Configurable timeout per run
  - Graceful exception/license/OOM handling
  - CSV export of results
  - Log-scale timing plots
"""

import csv
import os
import sys
import time
import traceback
import signal
import multiprocessing
from datetime import datetime
from functools import partial

# ----------------------------------------------
# Helper: run a solver in a separate process
# ----------------------------------------------

def _run_solver_in_process(solver_func, n, timeout, result_queue):
    """Worker function that runs the solver and puts the result in a queue."""
    try:
        start = time.perf_counter()
        solution = solver_func(n) if 'timeout' not in solver_func.__code__.co_varnames else solver_func(n, timeout=timeout)
        elapsed = time.perf_counter() - start
        valid = _validate_solution(solution, n) if solution is not None else False
        result_queue.put(("ok", elapsed, valid))
    except Exception as e:
        elapsed = time.perf_counter() - start
        result_queue.put(("error", elapsed, str(e)))


def _validate_solution(board, n):
    """Validate that a board is a correct N-Queens solution."""
    if board is None:
        return False
    if len(board) != n:
        return False
    queens = []
    for i in range(n):
        if len(board[i]) != n:
            return False
        count = sum(board[i])
        if count != 1:
            return False
        col = board[i].index(1)
        queens.append((i, col))
    # Check no two queens attack each other
    for a in range(len(queens)):
        for b in range(a + 1, len(queens)):
            r1, c1 = queens[a]
            r2, c2 = queens[b]
            if c1 == c2:
                return False
            if abs(r1 - r2) == abs(c1 - c2):
                return False
    return True


def run_with_timeout(solver_func, n, timeout):
    """
    Run solver_func(n) in a separate process with a timeout.
    Returns (elapsed_time, status_str, is_valid).
    """
    result_queue = multiprocessing.Queue()
    p = multiprocessing.Process(
        target=_run_solver_in_process,
        args=(solver_func, n, timeout, result_queue)
    )
    p.start()
    p.join(timeout=timeout + 5)  # extra 5s grace

    if p.is_alive():
        p.terminate()
        p.join(timeout=5)
        if p.is_alive():
            p.kill()
            p.join()
        return timeout, "TIMEOUT", False

    if not result_queue.empty():
        status, elapsed, extra = result_queue.get_nowait()
        if status == "ok":
            return elapsed, "OK" if extra else "INVALID", extra
        else:
            return elapsed, f"ERROR: {extra}", False
    else:
        return timeout, "CRASH", False


# ----------------------------------------------
# Solver wrappers (importable)
# ----------------------------------------------

def solve_sat_binomial(n):
    from binomial import solve_n_queens
    return solve_n_queens(n)


def solve_sat_binary(n):
    from binary import solve_n_queens
    return solve_n_queens(n)


def solve_sat_sequential(n):
    from sequential import solve_n_queens
    return solve_n_queens(n)


def solve_cplex_cp(n, timeout=300):
    from cplex_cp import solve_n_queens
    return solve_n_queens(n, timeout=timeout)


def solve_cplex_mip(n, timeout=300):
    from cplex_mip import solve_n_queens
    return solve_n_queens(n, timeout=timeout)


def solve_gurobi_mip(n, timeout=300):
    from gurobi_mip import solve_n_queens
    return solve_n_queens(n, timeout=timeout)


def solve_cpsat(n, timeout=300):
    from cpsat import solve_n_queens
    return solve_n_queens(n, timeout=timeout)


# ----------------------------------------------
# Solver registry
# ----------------------------------------------

# Format: (display_name, function, category, max_n_recommended)
# max_n_recommended is the upper N above which we skip (to avoid wasting time)
ALL_SOLVERS = [
    ("SAT-Binomial",   solve_sat_binomial,   "SAT",    128),
    ("SAT-Binary",     solve_sat_binary,     "SAT",    512),
    ("SAT-Sequential", solve_sat_sequential, "SAT",    128),
    ("CPLEX-CP",       solve_cplex_cp,       "Solver", 4096),
    ("CPLEX-MIP",      solve_cplex_mip,      "Solver", 512),
    ("Gurobi-MIP",     solve_gurobi_mip,     "Solver", 512),
    ("CP-SAT",         solve_cpsat,          "Solver", 4096),
]

# ----------------------------------------------
# Benchmark configuration
# ----------------------------------------------

# Default board sizes -- covers small to very large
DEFAULT_N_VALUES = [4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048]

# Timeout per solver per N (seconds)
DEFAULT_TIMEOUT = 120


def check_solver_availability():
    """Check which solvers are actually available on this system."""
    availability = {}

    # pysat (for SAT solvers)
    try:
        from pysat.solvers import Glucose3
        availability["pysat"] = True
    except ImportError:
        availability["pysat"] = False

    # docplex CP
    try:
        from docplex.cp.model import CpoModel
        availability["docplex_cp"] = True
    except ImportError:
        availability["docplex_cp"] = False

    # docplex MIP
    try:
        from docplex.mp.model import Model
        availability["docplex_mip"] = True
    except ImportError:
        availability["docplex_mip"] = False

    # gurobipy
    try:
        import gurobipy
        availability["gurobipy"] = True
    except ImportError:
        availability["gurobipy"] = False

    # ortools
    try:
        from ortools.sat.python import cp_model
        availability["ortools"] = True
    except ImportError:
        availability["ortools"] = False

    return availability


def get_active_solvers(availability):
    """Filter ALL_SOLVERS to only those whose dependencies are available."""
    dep_map = {
        "SAT-Binomial":   "pysat",
        "SAT-Binary":     "pysat",
        "SAT-Sequential": "pysat",
        "CPLEX-CP":       "docplex_cp",
        "CPLEX-MIP":      "docplex_mip",
        "Gurobi-MIP":     "gurobipy",
        "CP-SAT":         "ortools",
    }
    active = []
    skipped = []
    for name, func, cat, max_n in ALL_SOLVERS:
        dep = dep_map[name]
        if availability.get(dep, False):
            active.append((name, func, cat, max_n))
        else:
            skipped.append((name, dep))
    return active, skipped


# ----------------------------------------------
# Main benchmark
# ----------------------------------------------

def run_benchmark(n_values=None, timeout=None, output_dir=None):
    """
    Run the full benchmark suite.

    Args:
        n_values: list of N values to test (default: DEFAULT_N_VALUES)
        timeout: per-run timeout in seconds (default: DEFAULT_TIMEOUT)
        output_dir: directory for output files (default: current directory)
    """
    if n_values is None:
        n_values = DEFAULT_N_VALUES
    if timeout is None:
        timeout = DEFAULT_TIMEOUT
    if output_dir is None:
        output_dir = os.path.dirname(os.path.abspath(__file__))

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(output_dir, f"benchmark_results_{timestamp}.csv")
    plot_path = os.path.join(output_dir, f"benchmark_plot_{timestamp}.png")

    print("=" * 70)
    print("  N-Queens Benchmark Suite")
    print("=" * 70)
    print(f"  Board sizes (N): {n_values}")
    print(f"  Timeout per run: {timeout}s")
    print(f"  Output CSV:      {csv_path}")
    print(f"  Output Plot:     {plot_path}")
    print()

    # Check availability
    availability = check_solver_availability()
    active_solvers, skipped_solvers = get_active_solvers(availability)

    print("  Available solvers:")
    for name, _, cat, max_n in active_solvers:
        print(f"    [OK] {name} [{cat}] (max recommended N={max_n})")
    if skipped_solvers:
        print("  Unavailable solvers (missing dependencies):")
        for name, dep in skipped_solvers:
            print(f"    [--] {name} (needs '{dep}')")
    print()

    if not active_solvers:
        print("ERROR: No solvers available. Please install at least one of:")
        print("  pip install python-sat ortools docplex gurobipy")
        return

    # Results storage: list of dicts
    results = []

    # Run benchmarks
    total_runs = sum(1 for _ in active_solvers for _ in n_values)
    run_count = 0

    for n in n_values:
        print(f"{'-' * 70}")
        print(f"  N = {n}")
        print(f"{'-' * 70}")
        for name, func, cat, max_n in active_solvers:
            run_count += 1
            progress = f"[{run_count}/{total_runs}]"

            if n > max_n:
                print(f"  {progress} {name:20s} -> SKIPPED (N > recommended max {max_n})")
                results.append({
                    "N": n,
                    "Solver": name,
                    "Category": cat,
                    "Time_s": None,
                    "Status": "SKIPPED",
                    "Valid": False,
                })
                continue

            print(f"  {progress} {name:20s} -> ", end="", flush=True)

            elapsed, status, valid = run_with_timeout(func, n, timeout)

            if status == "OK":
                print(f"{elapsed:10.4f}s  [VALID]")
            elif status == "TIMEOUT":
                print(f"{elapsed:10.1f}s  [TIMEOUT]")
            elif status == "INVALID":
                print(f"{elapsed:10.4f}s  [INVALID solution!]")
            else:
                short_status = status[:60] if len(status) > 60 else status
                print(f"{elapsed:10.4f}s  [FAIL] {short_status}")

            results.append({
                "N": n,
                "Solver": name,
                "Category": cat,
                "Time_s": round(elapsed, 6) if status in ("OK", "INVALID") else None,
                "Status": status,
                "Valid": valid,
            })

    print(f"\n{'=' * 70}")
    print(f"  Benchmark complete! ({run_count} runs)")
    print(f"{'=' * 70}")

    # -- Save CSV --
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["N", "Solver", "Category", "Time_s", "Status", "Valid"])
        writer.writeheader()
        writer.writerows(results)
    print(f"\n  Results saved to: {csv_path}")

    # -- Print summary table --
    print_summary_table(results, n_values, active_solvers)

    # -- Plot --
    try:
        generate_plot(results, n_values, active_solvers, plot_path)
        print(f"  Plot saved to:    {plot_path}")
    except Exception as e:
        print(f"  Could not generate plot: {e}")
        print("  (Install matplotlib: pip install matplotlib)")

    return results


def print_summary_table(results, n_values, active_solvers):
    """Print a nice summary table to stdout."""
    solver_names = [s[0] for s in active_solvers]

    # Build lookup: (N, solver_name) -> time_str
    lookup = {}
    for r in results:
        key = (r["N"], r["Solver"])
        if r["Status"] == "OK":
            t = r["Time_s"]
            if t < 0.001:
                lookup[key] = f"{t*1000:.2f}ms"
            elif t < 1:
                lookup[key] = f"{t:.4f}s"
            else:
                lookup[key] = f"{t:.2f}s"
        elif r["Status"] == "TIMEOUT":
            lookup[key] = "TIMEOUT"
        elif r["Status"] == "SKIPPED":
            lookup[key] = "---"
        else:
            lookup[key] = "ERROR"

    # Header
    col_width = max(12, max(len(s) for s in solver_names) + 2)
    header = f"\n{'N':>8s}"
    for sn in solver_names:
        header += f" | {sn:>{col_width}s}"
    print(header)
    print("-" * len(header))

    # Rows
    for n in n_values:
        row = f"{n:>8d}"
        for sn in solver_names:
            val = lookup.get((n, sn), "")
            row += f" | {val:>{col_width}s}"
        print(row)


def generate_plot(results, n_values, active_solvers, plot_path):
    """Generate a log-scale timing plot."""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.ticker as ticker

    solver_names = [s[0] for s in active_solvers]
    categories = {s[0]: s[2] for s in active_solvers}

    # Style markers/colors by category
    sat_styles = {
        "SAT-Binomial":   {"color": "#e74c3c", "marker": "o", "ls": "-"},
        "SAT-Binary":     {"color": "#e67e22", "marker": "s", "ls": "-"},
        "SAT-Sequential": {"color": "#f1c40f", "marker": "D", "ls": "-"},
    }
    solver_styles = {
        "CPLEX-CP":   {"color": "#2ecc71", "marker": "^", "ls": "--"},
        "CPLEX-MIP":  {"color": "#3498db", "marker": "v", "ls": "--"},
        "Gurobi-MIP": {"color": "#9b59b6", "marker": "<", "ls": "--"},
        "CP-SAT":     {"color": "#1abc9c", "marker": ">", "ls": "--"},
    }
    all_styles = {**sat_styles, **solver_styles}

    fig, ax = plt.subplots(figsize=(14, 8))

    for sn in solver_names:
        ns = []
        times = []
        for r in results:
            if r["Solver"] == sn and r["Status"] == "OK" and r["Time_s"] is not None:
                ns.append(r["N"])
                times.append(r["Time_s"])
        if not ns:
            continue
        style = all_styles.get(sn, {"color": "gray", "marker": "x", "ls": ":"})
        ax.plot(ns, times,
                label=sn,
                color=style["color"],
                marker=style["marker"],
                linestyle=style["ls"],
                linewidth=2,
                markersize=8,
                alpha=0.85)

    ax.set_xscale('log', base=2)
    ax.set_yscale('log')
    ax.set_xlabel('Board Size (N)', fontsize=13)
    ax.set_ylabel('Solve Time (seconds)', fontsize=13)
    ax.set_title('N-Queens Benchmark: Solve Time vs Board Size', fontsize=15, fontweight='bold')
    ax.legend(fontsize=11, loc='upper left', framealpha=0.9)
    ax.grid(True, which='both', linestyle='--', alpha=0.4)

    # Format x-axis ticks to show actual N values
    ax.xaxis.set_major_formatter(ticker.ScalarFormatter())
    ax.xaxis.set_tick_params(which='both', labelsize=10)

    plt.tight_layout()
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close(fig)


# ----------------------------------------------
# CLI entry point
# ----------------------------------------------

def parse_args():
    """Parse command-line arguments."""
    import argparse
    parser = argparse.ArgumentParser(
        description="N-Queens Benchmark Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python benchmark.py
  python benchmark.py --n 4 8 16 32 64 --timeout 60
  python benchmark.py --n 32 64 128 256 512 1024 2048 --timeout 300
  python benchmark.py --large   # Uses predefined large-scale test set
        """)
    parser.add_argument("--n", type=int, nargs="+",
                        help="List of N values to benchmark")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Timeout per solver per N (seconds, default: {DEFAULT_TIMEOUT})")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Directory for output files")
    parser.add_argument("--large", action="store_true",
                        help="Use large-scale test set (N=32,64,128,256,512,1024,2048,4096)")
    parser.add_argument("--quick", action="store_true",
                        help="Quick test with small N values (4,8,16,32)")
    return parser.parse_args()


if __name__ == "__main__":
    multiprocessing.freeze_support()

    args = parse_args()

    if args.large:
        n_values = [32, 64, 128, 256, 512, 1024, 2048, 4096]
    elif args.quick:
        n_values = [4, 8, 16, 32]
    elif args.n:
        n_values = sorted(args.n)
    else:
        n_values = DEFAULT_N_VALUES

    run_benchmark(
        n_values=n_values,
        timeout=args.timeout,
        output_dir=args.output_dir,
    )

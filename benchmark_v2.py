"""
N-Queens benchmark v2
=====================
Extension of benchmark.py that addresses the main weaknesses of a single-run benchmark:

  * every cell (N, solver, threads) is run --repeats times (default 5): median / mean / std / min / max
  * no cell is skipped: every (N, solver) pair is attempted at least once (a cell whose first run
    times out is not repeated)
  * time is split into Import_s, Build_s (model / CNF generation) and Solve_s (pure solving);
    Total_s is the sum of the three and PeakMB is the peak resident memory of the worker process
    and its children (needs `pip install psutil`)
  * SAT solvers: conflicts / decisions / propagations / restarts (PySAT accum_stats), optional
    randomised initial phases (--randomize-phases) so that repetitions are not identical
  * thread control: --threads 1 0  runs the multi-threaded-capable solvers (Gurobi, CPLEX MIP,
    CPLEX CP, CP-SAT) with 1 thread and with the solver's automatic setting (0 = all cores);
    SAT solvers are single-threaded and are run once
  * non-power-of-two sizes and larger N in the default size list, default time limit 300 s

Examples
--------
  python benchmark_v2.py --quick
  python benchmark_v2.py --n 100 200 500 1000 --repeats 5 --timeout 300 --threads 1 0
  python benchmark_v2.py --solvers SAT-Binary SAT-Sequential --randomize-phases

Outputs (in --output-dir, default: this folder):
  benchmark_v2_runs_<stamp>.csv     one row per run
  benchmark_v2_summary_<stamp>.csv  one row per (N, solver, threads) with statistics
  benchmark_v2_plot_<stamp>.png     median total time with min-max bars (log-log)
  benchmark_v2_env_<stamp>.json     machine and library versions
"""
import argparse
import csv
import importlib
import json
import math
import multiprocessing as mp
import os
import platform
import random
import statistics
import threading
import time
from datetime import datetime

DEFAULT_N = [32, 64, 100, 128, 200, 256, 500, 512, 1000, 1024, 2048, 4096]

# name -> (kind, category, can_use_threads)
SOLVERS = {
    "SAT-Binomial":   ("sat:binomial",   "SAT",      False),
    "SAT-Binary":     ("sat:binary",     "SAT",      False),
    "SAT-Sequential": ("sat:sequential", "SAT",      False),
    "CPLEX-CP":       ("cplex_cp",       "Solver",   True),
    "CPLEX-MIP":      ("cplex_mip",      "Solver",   True),
    "Gurobi-MIP":     ("gurobi",         "Solver",   True),
    "CP-SAT":         ("cpsat",          "Solver",   True),
}


# --------------------------------------------------------------------------- helpers
def board_to_cols(board):
    return [row.index(1) for row in board]


def valid_cols(cols, n):
    """Independent O(n) check that cols[r] (column of the queen in row r) is a valid placement."""
    if cols is None or len(cols) != n or sorted(cols) != list(range(n)):
        return False
    return (len({r + c for r, c in enumerate(cols)}) == n
            and len({r - c for r, c in enumerate(cols)}) == n)


def _now():
    return time.perf_counter()


# --------------------------------------------------------------------------- workers
def _w_sat(mod_name, n, timeout, seed, randomize):
    t = _now()
    mod = importlib.import_module(mod_name)
    from pysat.solvers import Glucose3
    imp = _now() - t

    t = _now()
    variables = mod.generate_variables(n)
    clauses = mod.generate_clauses(n, variables)
    solver = Glucose3()
    for c in clauses:
        solver.add_clause(c)
    nclauses = len(clauses)
    del clauses
    build = _now() - t

    if randomize:
        rng = random.Random(seed)
        solver.set_phases([v if rng.random() < 0.5 else -v for v in range(1, n * n + 1)])

    budget = max(1.0, timeout - imp - build)
    timer = threading.Timer(budget, solver.interrupt)
    timer.start()
    t = _now()
    res = solver.solve_limited(expect_interrupt=True)
    solve = _now() - t
    timer.cancel()

    stats = {}
    try:
        stats = solver.accum_stats()
    except Exception:
        pass
    out = dict(Import_s=imp, Build_s=build, Solve_s=solve, Clauses=nclauses,
               Conflicts=stats.get("conflicts"), Decisions=stats.get("decisions"),
               Propagations=stats.get("propagations"), Restarts=stats.get("restarts"))
    if res is True:
        model = solver.get_model()
        cols = [0] * n
        for lit in model:
            if 0 < lit <= n * n:
                r, c = divmod(lit - 1, n)
                cols[r] = c
        out.update(Status="OK", cols=cols)
    elif res is None:
        out.update(Status="TIMEOUT")
    else:
        out.update(Status="UNSAT")
    solver.delete()
    return out


def _w_cpsat(n, timeout, threads):
    t = _now()
    from ortools.sat.python import cp_model
    imp = _now() - t
    t = _now()
    m = cp_model.CpModel()
    q = [m.new_int_var(0, n - 1, f"q{i}") for i in range(n)]
    m.add_all_different(q)
    m.add_all_different([q[i] + i for i in range(n)])
    m.add_all_different([q[i] - i for i in range(n)])
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = timeout
    s.parameters.num_workers = threads          # 0 = automatic (all cores)
    build = _now() - t
    t = _now()
    st = s.solve(m)
    solve = _now() - t
    out = dict(Import_s=imp, Build_s=build, Solve_s=solve,
               Conflicts=s.num_conflicts, Decisions=s.num_branches)
    if st in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        out.update(Status="OK", cols=[s.value(v) for v in q])
    elif st == cp_model.UNKNOWN:
        out.update(Status="TIMEOUT")
    else:
        out.update(Status="UNSAT")
    return out


def _w_cplex_cp(n, timeout, threads):
    t = _now()
    from docplex.cp.model import CpoModel
    import cplex_cp
    imp = _now() - t
    t = _now()
    m = CpoModel(name=f"NQ{n}")
    q = [m.integer_var(0, n - 1, name=f"q{i}") for i in range(n)]
    m.add(m.all_diff(q))
    m.add(m.all_diff([q[i] + i for i in range(n)]))
    m.add(m.all_diff([q[i] - i for i in range(n)]))
    kw = dict(TimeLimit=timeout, LogVerbosity="Quiet")
    if threads > 0:
        kw["Workers"] = threads
    exe = cplex_cp._find_cpoptimizer()
    if exe:
        kw["execfile"] = exe
    build = _now() - t
    t = _now()
    res = m.solve(**kw)
    wall = _now() - t
    try:
        solve = res.get_solve_time()
    except Exception:
        solve = wall
    out = dict(Import_s=imp, Build_s=build, Solve_s=solve, Overhead_s=max(0.0, wall - solve))
    if res.is_solution():
        out.update(Status="OK", cols=[res.get_value(v) for v in q])
    else:
        out.update(Status="TIMEOUT" if "Feasible" not in str(res.get_solve_status()) and
                   "Infeasible" not in str(res.get_solve_status()) else "UNSAT")
    return out


def _w_cplex_mip(n, timeout, threads):
    t = _now()
    from docplex.mp.model import Model
    imp = _now() - t
    t = _now()
    mdl = Model(name="nq")
    x = {(i, j): mdl.binary_var(name=f"x_{i}_{j}") for i in range(n) for j in range(n)}
    for i in range(n):
        mdl.add_constraint(mdl.sum(x[i, j] for j in range(n)) == 1)
    for j in range(n):
        mdl.add_constraint(mdl.sum(x[i, j] for i in range(n)) == 1)
    for d in range(2 * n - 1):
        mdl.add_constraint(mdl.sum(x[i, j] for i in range(n) for j in range(n) if i + j == d) <= 1)
        mdl.add_constraint(mdl.sum(x[i, j] for i in range(n) for j in range(n) if i - j == d - n + 1) <= 1)
    mdl.parameters.timelimit = timeout
    if threads > 0:
        mdl.parameters.threads = threads
    build = _now() - t
    t = _now()
    sol = mdl.solve(log_output=False)
    wall = _now() - t
    try:
        solve = mdl.solve_details.time
    except Exception:
        solve = wall
    out = dict(Import_s=imp, Build_s=build, Solve_s=solve, Overhead_s=max(0.0, wall - solve))
    if sol:
        cols = [0] * n
        for i in range(n):
            for j in range(n):
                if sol.get_value(x[i, j]) > 0.5:
                    cols[i] = j
        out.update(Status="OK", cols=cols)
    else:
        out.update(Status="TIMEOUT")
    return out


def _w_gurobi(n, timeout, threads):
    t = _now()
    import gurobipy as gp
    from gurobipy import GRB
    imp = _now() - t
    t = _now()
    env = gp.Env(empty=True)
    env.setParam("OutputFlag", 0)
    env.start()
    m = gp.Model("nq", env=env)
    m.Params.TimeLimit = timeout
    m.Params.Threads = threads                   # 0 = automatic
    x = m.addVars(n, n, vtype=GRB.BINARY, name="x")
    m.addConstrs((x.sum(i, "*") == 1 for i in range(n)))
    m.addConstrs((x.sum("*", j) == 1 for j in range(n)))
    m.addConstrs((gp.quicksum(x[i, i - d] for i in range(max(0, d), min(n, n + d))) <= 1
                  for d in range(-n + 1, n)))
    m.addConstrs((gp.quicksum(x[i, d - i] for i in range(max(0, d - n + 1), min(n, d + 1))) <= 1
                  for d in range(2 * n - 1)))
    m.update()
    build = _now() - t
    t = _now()
    m.optimize()
    wall = _now() - t
    out = dict(Import_s=imp, Build_s=build, Solve_s=m.Runtime, Overhead_s=max(0.0, wall - m.Runtime))
    if m.SolCount > 0:
        cols = [0] * n
        for i in range(n):
            for j in range(n):
                if x[i, j].X > 0.5:
                    cols[i] = j
        out.update(Status="OK", cols=cols)
    else:
        out.update(Status="TIMEOUT")
    return out


def worker(kind, n, timeout, threads, seed, randomize, q):
    try:
        if kind.startswith("sat:"):
            out = _w_sat(kind[4:], n, timeout, seed, randomize)
        elif kind == "cpsat":
            out = _w_cpsat(n, timeout, threads)
        elif kind == "cplex_cp":
            out = _w_cplex_cp(n, timeout, threads)
        elif kind == "cplex_mip":
            out = _w_cplex_mip(n, timeout, threads)
        elif kind == "gurobi":
            out = _w_gurobi(n, timeout, threads)
        else:
            raise ValueError(kind)
        cols = out.pop("cols", None)
        out["Valid"] = bool(out.get("Status") == "OK" and valid_cols(cols, n))
        if out.get("Status") == "OK" and not out["Valid"]:
            out["Status"] = "INVALID"
        q.put(out)
    except MemoryError:
        q.put(dict(Status="MEMOUT", Valid=False))
    except Exception as e:                                   # noqa: BLE001
        q.put(dict(Status=f"ERROR: {type(e).__name__}: {e}"[:120], Valid=False))


# --------------------------------------------------------------------------- parent side
def _peak_memory_sampler(pid, stop, box):
    try:
        import psutil
    except ImportError:
        box["peak"] = float("nan")
        return
    peak = 0
    try:
        root = psutil.Process(pid)
    except psutil.Error:
        return
    while not stop.is_set():
        try:
            procs = [root] + root.children(recursive=True)
            peak = max(peak, sum(p.memory_info().rss for p in procs if p.is_running()))
        except psutil.Error:
            pass
        stop.wait(0.05)
    box["peak"] = peak / 2 ** 20


def run_one(kind, n, timeout, threads, seed, randomize):
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=worker, args=(kind, n, timeout, threads, seed, randomize, q))
    box, stop = {"peak": float("nan")}, threading.Event()
    t0 = _now()
    p.start()
    th = threading.Thread(target=_peak_memory_sampler, args=(p.pid, stop, box), daemon=True)
    th.start()
    out = None
    deadline = t0 + timeout + 30
    while _now() < deadline:
        try:
            out = q.get(timeout=0.2)
            break
        except Exception:                                    # queue.Empty
            if not p.is_alive():
                try:
                    out = q.get(timeout=1)
                except Exception:
                    out = dict(Status="CRASH", Valid=False)  # e.g. killed by the OS (out of memory)
                break
    if out is None:
        out = dict(Status="TIMEOUT", Valid=False)            # stuck outside the solver (e.g. CNF generation)
    p.join(5)
    if p.is_alive():
        p.terminate()
        p.join(5)
        if p.is_alive():
            p.kill()
    stop.set()
    th.join(2)
    out["PeakMB"] = box["peak"]
    out["Wall_s"] = _now() - t0
    return out


FIELDS = ["N", "Solver", "Category", "Threads", "Rep", "Status", "Valid", "Import_s", "Build_s",
          "Solve_s", "Overhead_s", "Total_s", "Wall_s", "PeakMB", "Clauses", "Conflicts",
          "Decisions", "Propagations", "Restarts"]


def _stats(vals):
    vals = [v for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not vals:
        return dict(median=None, mean=None, std=None, min=None, max=None)
    return dict(median=statistics.median(vals), mean=statistics.fmean(vals),
                std=statistics.stdev(vals) if len(vals) > 1 else 0.0, min=min(vals), max=max(vals))


def summarise(rows):
    groups = {}
    for r in rows:
        groups.setdefault((r["N"], r["Solver"], r["Threads"]), []).append(r)
    out = []
    for (n, sname, th), rs in groups.items():
        ok = [r for r in rs if r["Status"] == "OK"]
        row = dict(N=n, Solver=sname, Threads=th, Runs=len(rs), OK=len(ok),
                   Status="OK" if len(ok) == len(rs) else rs[0]["Status"] if not ok else "PARTIAL")
        for field in ("Total_s", "Build_s", "Solve_s", "PeakMB", "Conflicts", "Decisions"):
            for k, v in _stats([r.get(field) for r in ok]).items():
                row[f"{field}_{k}"] = v
        out.append(row)
    return out


def write_csv(path, rows, fields):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def plot(summary, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 6.5))
    series = {}
    for r in summary:
        if r["OK"] and r["Total_s_median"] is not None:
            series.setdefault((r["Solver"], r["Threads"]), []).append(r)
    for (sname, th), rs in sorted(series.items()):
        rs.sort(key=lambda r: r["N"])
        ns = [r["N"] for r in rs]
        med = [r["Total_s_median"] for r in rs]
        lo = [r["Total_s_median"] - r["Total_s_min"] for r in rs]
        hi = [r["Total_s_max"] - r["Total_s_median"] for r in rs]
        label = sname + (f" ({th} thr)" if SOLVERS[sname][2] else "")
        ax.errorbar(ns, med, yerr=[lo, hi], marker="o", capsize=3, label=label)
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xlabel("Board size N")
    ax.set_ylabel("Median total time (s), bars = min-max")
    ax.grid(True, which="both", ls="--", alpha=0.4)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def environment():
    info = dict(platform=platform.platform(), python=platform.python_version(),
                machine=platform.machine(), processor=platform.processor(),
                cpu_count=os.cpu_count())
    try:
        import psutil
        info["ram_gb"] = round(psutil.virtual_memory().total / 2 ** 30, 2)
    except ImportError:
        pass
    from importlib import metadata
    for pkg in ("python-sat", "gurobipy", "docplex", "cplex", "ortools", "psutil"):
        try:
            info[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            info[pkg] = None
    return info


def main():
    ap = argparse.ArgumentParser(description="N-Queens benchmark v2")
    ap.add_argument("--n", type=int, nargs="+", default=DEFAULT_N)
    ap.add_argument("--solvers", nargs="+", default=list(SOLVERS), choices=list(SOLVERS))
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--threads", type=int, nargs="+", default=[1],
                    help="thread settings for Gurobi/CPLEX/CP-SAT: 1 = single thread, 0 = automatic")
    ap.add_argument("--randomize-phases", action="store_true",
                    help="random initial phases for the SAT solver (seed = repetition index)")
    ap.add_argument("--quick", action="store_true", help="N = 8 16 32, 2 repeats, 20 s")
    ap.add_argument("--output-dir", default=os.path.dirname(os.path.abspath(__file__)))
    a = ap.parse_args()
    if a.quick:
        a.n, a.repeats, a.timeout = [8, 16, 32], 2, 20

    os.makedirs(a.output_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    env = environment()
    with open(os.path.join(a.output_dir, f"benchmark_v2_env_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump(env, f, indent=2)
    print(json.dumps(env, indent=2))

    rows = []
    runs_path = os.path.join(a.output_dir, f"benchmark_v2_runs_{stamp}.csv")
    for n in sorted(a.n):
        for sname in a.solvers:
            kind, cat, multi = SOLVERS[sname]
            for th in (a.threads if multi else [1]):
                for rep in range(a.repeats):
                    res = run_one(kind, n, a.timeout, th, rep, a.randomize_phases)
                    res.update(N=n, Solver=sname, Category=cat, Threads=th if multi else 1, Rep=rep)
                    res["Total_s"] = sum(res.get(k) or 0.0 for k in ("Import_s", "Build_s", "Solve_s")) + \
                        (res.get("Overhead_s") or 0.0)
                    rows.append(res)
                    t = res["Total_s"]
                    print(f"N={n:5d} {sname:15s} thr={res['Threads']} rep={rep} {res['Status']:8s} "
                          f"total={t:8.3f}s build={res.get('Build_s') or 0:7.3f}s "
                          f"solve={res.get('Solve_s') or 0:8.3f}s mem={res['PeakMB']:8.1f}MB", flush=True)
                    write_csv(runs_path, rows, FIELDS)                 # save after every run
                    if res["Status"] != "OK":
                        break                                          # do not repeat failed cells

    summ = summarise(rows)
    sfields = ["N", "Solver", "Threads", "Runs", "OK", "Status"] + [
        f"{f}_{k}" for f in ("Total_s", "Build_s", "Solve_s", "PeakMB", "Conflicts", "Decisions")
        for k in ("median", "mean", "std", "min", "max")]
    write_csv(os.path.join(a.output_dir, f"benchmark_v2_summary_{stamp}.csv"), summ, sfields)
    try:
        plot(summ, os.path.join(a.output_dir, f"benchmark_v2_plot_{stamp}.png"))
    except Exception as e:                                               # noqa: BLE001
        print("Plot not generated:", e)
    print("Done. Files written to", a.output_dir)


if __name__ == "__main__":
    mp.freeze_support()
    main()

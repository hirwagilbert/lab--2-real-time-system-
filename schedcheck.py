"""
schedcheck.py - RM versus EDF schedulability comparison tool (Mini Project 2.2).

Given a periodic task set (name, C, T, optional D) it:
  1. computes u_i and total U,
  2. applies the Liu & Layland sufficient bound n(2^(1/n) - 1)       (Section 2.2.1)
     - with Deadline Monotonic ordering whenever some D_i < T_i      (Section 2.4)
  3. falls back to Response Time Analysis when the bound test fails  (Section 2.5.2)
  4. gives the EDF verdict (U <= 1, exact for implicit deadlines)    (Section 2.3.1)
  5. cross-checks both verdicts by simulation and draws a two-panel
     RM/EDF Gantt chart over one hyperperiod (capped at 500 units).

Usage
-----
    python schedcheck.py tasksets/ex_2_3_2.csv            # one file
    python schedcheck.py tasksets/*.csv --out figures     # many files
or from Python:
    from schedcheck import analyze, Task
    report = analyze([Task("t1", 1, 4), Task("t2", 2, 6)])
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from rts_sim import (Task, total_utilization, rm_bound, hyperperiod, is_constrained, rm_order,
                     dm_order, rta, simulate_fp, simulate_edf, plot_schedule, color_map)

MAX_HORIZON = 500


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

def load_csv(path: str) -> list[Task]:
    """CSV with header name,C,T[,D]. Blank D defaults to T."""
    tasks = []
    with open(path, newline="") as f:
        rows = [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]
    for r in rows:
        r = {k.strip(): (v or "").strip() for k, v in r.items() if k}
        try:
            C, T = int(r["C"]), int(r["T"])
            D = int(r["D"]) if r.get("D") else None
        except (KeyError, ValueError) as e:
            raise ValueError(f"{path}: bad row {r}: {e}") from None
        tasks.append(Task(r["name"], C, T, D))
    return validate(tasks)


def validate(tasks: list[Task]) -> list[Task]:
    if not tasks:
        raise ValueError("empty task set")
    names = [t.name for t in tasks]
    if len(set(names)) != len(names):
        raise ValueError("task names must be unique")
    for t in tasks:
        if t.D > t.T:
            raise ValueError(f"{t.name}: D > T (arbitrary deadlines) is outside the "
                             f"constrained-deadline model of Section 2.1.2")
        if t.C > t.D:
            # Not a crash: the task is trivially infeasible; keep it and report.
            pass
    return tasks


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def edf_demand_test(tasks: list[Task]) -> tuple[bool, int | None]:
    """Exact EDF test for constrained deadlines: processor-demand criterion.

    dbf(L) = sum max(0, floor((L - D_i)/T_i) + 1) * C_i <= L for every absolute
    deadline L in (0, H + max D]. Returns (ok, first failing L)."""
    if total_utilization(tasks) > 1 + 1e-12:
        return False, None
    H = hyperperiod(tasks)
    horizon = H + max(t.D for t in tasks)
    points = sorted({k * t.T + t.D for t in tasks for k in range(0, horizon // t.T + 1)
                     if k * t.T + t.D <= horizon})
    for L in points:
        dbf = sum(max(0, (L - t.D) // t.T + 1) * t.C for t in tasks)
        if dbf > L:
            return False, L
    return True, None


def analyze(tasks: list[Task], always_rta: bool = False) -> dict:
    tasks = validate(list(tasks))
    n = len(tasks)
    U = total_utilization(tasks)
    density = sum(t.C / t.D for t in tasks)
    constrained = is_constrained(tasks)
    order_fn = dm_order if constrained else rm_order
    policy = "DM" if constrained else "RM"
    bound = rm_bound(n)
    # For constrained deadlines the L&L bound is applied to density sum(C/D),
    # which is a valid sufficient test for DM; for implicit deadlines density == U.
    test_value = density if constrained else U
    bound_pass = test_value <= bound + 1e-12
    rep = {"n": n, "U": U, "density": density, "constrained": constrained, "fp_policy": policy,
           "bound": bound, "bound_metric": "density" if constrained else "U",
           "bound_pass": bound_pass, "infeasible": U > 1 + 1e-12,
           "tasks": [{"name": t.name, "C": t.C, "T": t.T, "D": t.D, "u": t.U} for t in tasks]}

    rta_rows = None
    if (not bound_pass) or always_rta:
        ordered = order_fn(tasks)
        rta_rows = []
        for i, t in enumerate(ordered):
            R, it, ok = rta(t, ordered[:i])
            rta_rows.append({"task": t.name, "priority": i + 1, "R": R, "D": t.D,
                             "iterations": it, "ok": ok})
    rep["rta"] = rta_rows
    if bound_pass:
        rep["fp_verdict"] = "SCHEDULABLE (utilization bound)"
        rep["fp_ok"] = True
    else:
        ok = all(r["ok"] for r in rta_rows)
        rep["fp_ok"] = ok
        rep["fp_verdict"] = "SCHEDULABLE (exact RTA)" if ok else "NOT SCHEDULABLE (RTA: deadline miss)"

    rep["edf_u_test"] = U <= 1 + 1e-12
    if constrained:
        ok, L = edf_demand_test(tasks)
        rep["edf_ok"] = ok
        rep["edf_verdict"] = ("SCHEDULABLE" if ok else
                              f"NOT SCHEDULABLE" + (f" (demand exceeds supply at L={L})" if L else " (U > 1)"))
    else:
        rep["edf_ok"] = rep["edf_u_test"]
        rep["edf_verdict"] = "SCHEDULABLE (U <= 1)" if rep["edf_ok"] else "INFEASIBLE (U > 1)"

    H = hyperperiod(tasks)
    rep["hyperperiod"] = H
    horizon = min(H, MAX_HORIZON)
    rep["horizon"] = horizon
    rep["sim_fp"] = simulate_fp(tasks, horizon)
    rep["sim_edf"] = simulate_edf(tasks, horizon)
    rep["sim_agrees"] = {
        "fp": (len(rep["sim_fp"].misses) == 0) == rep["fp_ok"] or horizon < H,
        "edf": (len(rep["sim_edf"].misses) == 0) == rep["edf_ok"] or horizon < H,
    }
    return rep


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def format_report(rep: dict, title: str = "") -> str:
    L = []
    w = L.append
    w("=" * 74)
    w(f"SCHEDULABILITY REPORT  {title}")
    w("=" * 74)
    w(f"{'Task':<8}{'C':>5}{'T':>6}{'D':>6}{'u_i':>9}")
    for t in rep["tasks"]:
        w(f"{t['name']:<8}{t['C']:>5}{t['T']:>6}{t['D']:>6}{t['u']:>9.4f}")
    w("-" * 74)
    w(f"n = {rep['n']}   U = {rep['U']:.4f}   hyperperiod = {rep['hyperperiod']}"
      + ("   (constrained deadlines -> Deadline Monotonic)" if rep["constrained"] else ""))
    if rep["constrained"]:
        w(f"density sum(C/D) = {rep['density']:.4f}")
    w(f"Liu & Layland bound n(2^(1/n)-1) = {rep['bound']:.4f}   "
      f"{rep['bound_metric']} <= bound ? {'PASS' if rep['bound_pass'] else 'FAIL'}")
    if rep["rta"]:
        w(f"Response Time Analysis ({rep['fp_policy']} priority order):")
        w(f"   {'Task':<8}{'prio':>5}{'R_i':>6}{'D_i':>6}{'iter':>6}  verdict")
        for r in rep["rta"]:
            Rs = f"{r['R']}" if r["ok"] else f">{r['D']}" if r['R'] > r['D'] else f"{r['R']}"
            w(f"   {r['task']:<8}{r['priority']:>5}{Rs:>6}{r['D']:>6}{r['iterations']:>6}  "
              f"{'OK' if r['ok'] else 'MISS'}")
    w(f"{rep['fp_policy']} verdict : {rep['fp_verdict']}")
    w(f"EDF verdict: {rep['edf_verdict']}" +
      ("" if not rep["constrained"] else f"   [U <= 1: {'yes' if rep['edf_u_test'] else 'no'}; "
                                         f"exact processor-demand test used]"))
    if rep["infeasible"]:
        w("!! U > 1: the task set is infeasible on one processor under ANY algorithm.")
    fp, ed = rep["sim_fp"], rep["sim_edf"]
    w(f"Simulation over {rep['horizon']} units: {rep['fp_policy']} misses = {len(fp.misses)}, "
      f"EDF misses = {len(ed.misses)}; ctx switches {rep['fp_policy']} = {fp.context_switches}, "
      f"EDF = {ed.context_switches}")
    if rep["horizon"] < rep["hyperperiod"]:
        w(f"(horizon capped at {MAX_HORIZON}; hyperperiod is {rep['hyperperiod']})")
    return "\n".join(L)


def plot_comparison(rep: dict, path: str, title: str = ""):
    tasks = rep["sim_fp"].tasks
    colors = color_map([t.name for t in tasks])
    H = rep["horizon"]
    h = 1.0 + 0.42 * len(tasks)
    width = 11 if H <= 60 else 14
    fig, axes = plt.subplots(2, 1, figsize=(width, 2 * h + 1.2), sharex=True)
    fp, ed = rep["sim_fp"], rep["sim_edf"]
    plot_schedule(axes[0], fp, colors, f"{rep['fp_policy']}  -  {rep['fp_verdict']}"
                  f"  ({len(fp.misses)} misses in simulation)", H, show_releases=H <= 120)
    plot_schedule(axes[1], ed, colors, f"EDF  -  {rep['edf_verdict']}"
                  f"  ({len(ed.misses)} misses in simulation)", H, show_releases=H <= 120)
    axes[1].set_xlabel("time")
    fig.suptitle(f"{title}   n = {rep['n']}, U = {rep['U']:.3f}, L&L bound = {rep['bound']:.3f}"
                 f"   (red X = deadline miss)", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main(argv=None):
    ap = argparse.ArgumentParser(description="RM vs EDF schedulability comparison tool")
    ap.add_argument("csv", nargs="+", help="task-set CSV file(s): name,C,T[,D]")
    ap.add_argument("--out", default="figures", help="directory for comparison charts")
    ap.add_argument("--always-rta", action="store_true", help="run RTA even when the bound passes")
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    status = 0
    for path in a.csv:
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            rep = analyze(load_csv(path), a.always_rta)
        except ValueError as e:
            print(f"[{name}] input error: {e}", file=sys.stderr)
            status = 1
            continue
        print(format_report(rep, f"[{name}]"))
        out = os.path.join(a.out, f"mp22_{name}.png")
        plot_comparison(rep, out, name)
        print(f"chart -> {out}\n")
    return status


if __name__ == "__main__":
    sys.exit(main())

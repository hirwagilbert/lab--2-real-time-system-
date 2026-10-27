"""
partition.py - Partitioned multiprocessor RM scheduling simulator (Mini Project 2.3).

Assigns a periodic, implicit-deadline task set to m cores with four bin-packing
heuristics (Section 2.8.3) and uses the Liu & Layland bound, recomputed for the
task count on each core, as the admission ("does it fit") predicate (Section 2.2.1):

    core k admits task i  <=>  load_k + u_i <= rm_bound(n_k + 1)

Heuristics (shared signature  heuristic(tasks, m) -> Partition):
    first_fit                 FF : input order, first admissible core
    first_fit_decreasing      FFD: sort by decreasing u, then FF
    best_fit_decreasing       BFD: sort by decreasing u, admissible core with LEAST remaining capacity
    worst_fit                 WF : input order, admissible core with MOST remaining capacity

"Remaining capacity" of core k for task i = rm_bound(n_k + 1) - (load_k + u_i),
i.e. the slack that would be left under the bound after placing the task.

Usage:  python partition.py           -> runs all test sets, writes results/ and figures/
"""
from __future__ import annotations

import io
import math
import os
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Callable, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from rts_sim import Task, rm_bound, total_utilization, hyperperiod, simulate_rm, runs, PALETTE

EPS = 1e-12


@dataclass
class Partition:
    heuristic: str
    m: int
    cores: list[list[Task]]
    unplaced: list[Task] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.unplaced

    @property
    def cores_used(self) -> int:
        return sum(1 for c in self.cores if c)

    def loads(self) -> list[float]:
        return [total_utilization(c) for c in self.cores]

    def placed_utilization(self) -> float:
        return sum(self.loads())

    def mapping(self) -> dict:
        return {t.name: k for k, c in enumerate(self.cores) for t in c}


def admits(core: list[Task], task: Task) -> bool:
    """Per-core RM admission test with the bound for the RESULTING task count."""
    return total_utilization(core) + task.U <= rm_bound(len(core) + 1) + EPS


def remaining_capacity(core: list[Task], task: Task) -> float:
    return rm_bound(len(core) + 1) - (total_utilization(core) + task.U)


def _place(tasks: list[Task], m: int, name: str,
           choose: Callable[[list[list[Task]], Task], Optional[int]]) -> Partition:
    cores: list[list[Task]] = [[] for _ in range(m)]
    unplaced = []
    for t in tasks:
        k = choose(cores, t)
        if k is None:
            unplaced.append(t)
        else:
            cores[k].append(t)
    return Partition(name, m, cores, unplaced)


def _first(cores, t):
    return next((k for k, c in enumerate(cores) if admits(c, t)), None)


def _best(cores, t):
    cand = [(remaining_capacity(c, t), k) for k, c in enumerate(cores) if admits(c, t)]
    return min(cand)[1] if cand else None


def _worst(cores, t):
    cand = [(-remaining_capacity(c, t), k) for k, c in enumerate(cores) if admits(c, t)]
    return min(cand)[1] if cand else None


def by_decreasing_u(tasks):
    return sorted(tasks, key=lambda t: -t.U)


def first_fit(tasks, m):
    return _place(list(tasks), m, "FF", _first)


def first_fit_decreasing(tasks, m):
    return _place(by_decreasing_u(tasks), m, "FFD", _first)


def best_fit_decreasing(tasks, m):
    return _place(by_decreasing_u(tasks), m, "BFD", _best)


def worst_fit(tasks, m):
    return _place(list(tasks), m, "WF", _worst)


HEURISTICS = [first_fit, first_fit_decreasing, best_fit_decreasing, worst_fit]


def cores_needed(heuristic, tasks) -> int:
    """Cores the heuristic needs with an unlimited supply (one per task is always enough)."""
    return heuristic(tasks, len(tasks)).cores_used


# ---------------------------------------------------------------------------
# Test sets (m = 4, periods chosen from {10, 20, 40} so per-core hyperperiods stay small)
# ---------------------------------------------------------------------------

def mk(prefix, specs):
    return [Task(f"{prefix}{i + 1}", C, T) for i, (C, T) in enumerate(specs)]


TEST_SETS = {
    # A: many small, near-equal utilizations
    "A_balanced": mk("a", [(3, 20), (4, 20), (6, 40), (2, 10), (7, 40), (3, 20), (6, 40),
                           (2, 10), (4, 20), (7, 40), (3, 20), (6, 40), (2, 10), (7, 40)]),
    # B: a few large tasks (u > 0.5) plus many small ones
    "B_skewed": mk("b", [(1, 10), (2, 20), (11, 20), (3, 40), (6, 10), (1, 10), (2, 20),
                         (26, 40), (3, 40), (1, 10), (2, 20), (4, 40)]),
    # C: total utilization just under m with tight (0.375) individual sizes
    "C_tight": mk("c", [(15, 40)] * 10),
    # D: order-sensitive - small tasks listed first, large ones last
    "D_order_sensitive": mk("d", [(1, 5)] * 4 + [(3, 5)] * 4),
    # E: adversarial - five tasks of u = 0.55, total far below m
    "E_adversarial": mk("e", [(11, 20)] * 5),
}
M = 4


def describe(tasks):
    U = total_utilization(tasks)
    return f"n={len(tasks)}, U={U:.3f} ({100 * U / M:.1f}% of m={M}), max u={max(t.U for t in tasks):.3f}"


def run_all():
    table = []
    parts = {}
    for sname, tasks in TEST_SETS.items():
        print("=" * 78)
        print(f"Test set {sname}: {describe(tasks)}")
        print("  tasks: " + ", ".join(f"{t.name}({t.C}/{t.T}={t.U:.3f})" for t in tasks))
        print("=" * 78)
        U = total_utilization(tasks)
        lb = math.ceil(U - 1e-9)
        for h in HEURISTICS:
            p = h(tasks, M)
            parts[(sname, p.heuristic)] = p
            need = cores_needed(h, tasks)
            loads = p.loads()
            print(f"  {p.heuristic:<4} {'OK  ' if p.success else 'FAIL'} cores used={p.cores_used}/{M}"
                  f"  per-core U=[{', '.join(f'{x:.3f}' for x in loads)}]"
                  f"  placed U={p.placed_utilization():.3f} ({100 * p.placed_utilization() / M:.1f}% of m)"
                  + (f"  unplaced={[t.name for t in p.unplaced]}" if p.unplaced else "")
                  + f"  | cores needed (unlimited)={need}, lower bound ceil(U)={lb}")
            for k, c in enumerate(p.cores):
                if c:
                    print(f"        core {k}: {[t.name for t in c]}  n={len(c)}  U={total_utilization(c):.3f}"
                          f"  bound={rm_bound(len(c)):.3f}")
            table.append({"set": sname, "heuristic": p.heuristic, "success": p.success,
                          "cores_used": p.cores_used, "loads": loads, "placed_U": p.placed_utilization(),
                          "total_U": U, "pct_of_m": 100 * p.placed_utilization() / M,
                          "unplaced": len(p.unplaced), "cores_needed": need, "lower_bound": lb})
    return table, parts


def print_table(table):
    print("=" * 78)
    print("Summary table (m = 4)")
    print("=" * 78)
    print(f"{'Set':<20}{'Heur':<6}{'Result':<8}{'Cores':>6}{'Placed U':>10}{'% of m':>8}"
          f"{'Unpl.':>7}{'Need':>6}{'ceil(U)':>8}")
    for r in table:
        print(f"{r['set']:<20}{r['heuristic']:<6}{'OK' if r['success'] else 'FAIL':<8}{r['cores_used']:>6}"
              f"{r['placed_U']:>10.3f}{r['pct_of_m']:>7.1f}%{r['unplaced']:>7}{r['cores_needed']:>6}"
              f"{r['lower_bound']:>8}")


def plot_per_core(p: Partition, path: str, title: str):
    """Stacked Gantt: one row per core, each core simulated independently under RM."""
    cores = [c for c in p.cores if c]
    names = [t.name for c in cores for t in c]
    colors = {n: PALETTE[i % len(PALETTE)] for i, n in enumerate(names)}
    H = max(hyperperiod(c) for c in cores)
    fig, ax = plt.subplots(figsize=(13, 1.0 + 0.85 * len(cores)))
    verdicts = []
    for k, core in enumerate(cores):
        res = simulate_rm(core, H)
        verdicts.append((k, len(res.misses), res))
        y = (len(cores) - 1 - k) * 10
        for t in core:
            for (s, l) in runs(res.timeline, t.name):
                ax.broken_barh([(s, l)], (y + 1.5, 7), facecolors=colors[t.name], edgecolor="white", lw=0.5)
                if l >= 2:
                    ax.text(s + l / 2, y + 5, t.name, ha="center", va="center", fontsize=6.5, color="white")
        for (s, l) in runs(res.timeline, None):
            ax.broken_barh([(s, l)], (y + 3.5, 3), facecolors="#dddddd", edgecolor="none")
        for (nm, jn, d) in res.misses:
            ax.plot(d, y + 5, "rx", ms=8, mew=2)
    ax.set_yticks([(len(cores) - 1 - k) * 10 + 5 for k in range(len(cores))])
    ax.set_yticklabels([f"core {k}\nU={total_utilization(c):.3f}, misses={verdicts[k][1]}"
                        for k, c in enumerate(cores)], fontsize=8)
    ax.set_xlim(0, H); ax.set_xticks(range(0, H + 1, 2 if H <= 40 else 5))
    ax.tick_params(labelsize=7.5)
    ax.grid(axis="x", color="#eee"); ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_xlabel("time (ms) - one hyperperiod; grey = idle")
    ax.set_title(title, loc="left", fontsize=10, fontweight="bold")
    fig.tight_layout(); fig.savefig(path, dpi=160); plt.close(fig)
    return verdicts


def plot_summary(table, path):
    sets = list(TEST_SETS)
    hs = [h(TEST_SETS[sets[0]], M).heuristic for h in HEURISTICS]
    fig, axes = plt.subplots(1, len(sets), figsize=(15, 3.6), sharey=True)
    for ax, s in zip(axes, sets):
        rows = [r for r in table if r["set"] == s]
        for i, r in enumerate(rows):
            bottom = 0
            for k, ld in enumerate(r["loads"]):
                ax.bar(i, ld, bottom=bottom, color=PALETTE[k], edgecolor="white", width=0.7)
                bottom += ld
            if not r["success"]:
                ax.text(i, bottom + 0.05, "FAIL", ha="center", color="red", fontsize=8, fontweight="bold")
        ax.axhline(rows[0]["total_U"], color="black", ls="--", lw=1)
        ax.set_xticks(range(len(hs))); ax.set_xticklabels(hs, fontsize=8)
        ax.set_title(f"{s}\nU = {rows[0]['total_U']:.2f}", fontsize=9)
        ax.set_ylim(0, M)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    axes[0].set_ylabel("placed utilization (stacked per core)")
    fig.suptitle("Placed utilization per heuristic, stacked by core (colour = core 0..3); "
                 "dashed = total task-set U", fontsize=10)
    fig.tight_layout(); fig.savefig(path, dpi=150); plt.close(fig)


def main():
    os.makedirs("figures", exist_ok=True); os.makedirs("results", exist_ok=True)
    buf = io.StringIO()
    with redirect_stdout(buf):
        table, parts = run_all()
        print_table(table)
        p = parts[("A_balanced", "FFD")]
        v = plot_per_core(p, "figures/mp23_per_core_gantt_FFD_A.png",
                          "FFD partition of set A on 4 cores - each core scheduled by RM independently")
        print("=" * 78)
        print("Per-core RM simulation of A_balanced / FFD over one hyperperiod (40 ms):")
        for k, miss, res in v:
            print(f"  core {k}: tasks={[t.name for t in res.tasks]} misses={miss} worst R={res.worst_response()}")
        p2 = parts[("B_skewed", "FFD")]
        plot_per_core(p2, "figures/mp23_per_core_gantt_FFD_B.png",
                      "FFD partition of set B (skewed) on 4 cores - RM per core")
        plot_summary(table, "figures/mp23_summary.png")
    out = buf.getvalue()
    print(out)
    with open("results/mp23_results.txt", "w") as f:
        f.write(out)
    return table


if __name__ == "__main__":
    main()

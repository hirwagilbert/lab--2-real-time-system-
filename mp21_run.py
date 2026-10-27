"""
Mini Project 2.1 - driver script.

Runs every procedure step and lab task of Mini Project 2.1 and writes:
  results/mp21_results.txt   printed utilization / bound / RTA / blocking tables
  figures/mp21_*.png         Gantt-style charts
Usage:  python mp21_run.py
"""
from __future__ import annotations

import io
import math
import os
from contextlib import redirect_stdout

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

from rts_sim import (Task, RTask, total_utilization, rm_bound, edf_test, hyperperiod,
                     rta, rta_all, rm_order, dm_order, simulate_rm, simulate_edf, simulate_dm,
                     simulate_llf, simulate_resources, plot_schedule, color_map, runs)

FIG, RES = "figures", "results"
os.makedirs(FIG, exist_ok=True)
os.makedirs(RES, exist_ok=True)

EX1 = [Task("t1", 1, 4), Task("t2", 2, 6), Task("t3", 2, 12)]            # Section 2.2.2
EX2 = EX1 + [Task("t4", 1, 8)]                                            # Section 2.3.2


def line(c="-", n=72):
    print(c * n)


def utilization_report(tasks, label):
    line("=")
    print(label)
    line("=")
    print(f"{'Task':<6}{'C':>4}{'T':>5}{'D':>5}{'u_i':>9}")
    for t in tasks:
        print(f"{t.name:<6}{t.C:>4}{t.T:>5}{t.D:>5}{t.U:>9.4f}")
    U, n = total_utilization(tasks), len(tasks)
    b = rm_bound(n)
    print(f"Total U = {U:.4f}   rm_bound({n}) = {b:.4f}")
    print(f"RM sufficient test (U <= bound): {'PASS - guaranteed' if U <= b else 'FAIL - inconclusive'}")
    print(f"EDF exact test (U <= 1):        {'PASS - schedulable' if edf_test(tasks) else 'FAIL - infeasible'}")
    return U, b


def step_2_3():
    U1, b1 = utilization_report(EX1, "Step 2 - Section 2.2.2 three-task example")
    assert abs(U1 - 0.75) < 1e-9 and abs(b1 - 0.7798) < 1e-3
    U2, b2 = utilization_report(EX2, "Step 3 - Section 2.3.2 four-task example (adds t4: C=1, T=8)")
    assert abs(U2 - 0.875) < 1e-9 and abs(b2 - 0.7568) < 1e-3


def step_4_6():
    H = hyperperiod(EX2)
    rm, edf = simulate_rm(EX2, H), simulate_edf(EX2, H)
    line("=")
    print(f"Steps 4-6 - RM and EDF simulation of the four-task set, hyperperiod = {H}")
    line("=")
    for res in (rm, edf):
        tl = "".join((x[-1] if x else ".") for x in res.timeline)
        print(f"{res.policy:<4} {tl}   misses={len(res.misses)} ctx-switches={res.context_switches} "
              f"preemptions={res.preemptions}")
        print("     worst response times:", res.worst_response())
    diff = [t for t in range(H) if rm.timeline[t] != edf.timeline[t]]
    print(f"Ticks where RM and EDF differ: {diff}")
    print(f"t1 identical in both schedules: "
          f"{[x == 't1' for x in rm.timeline] == [x == 't1' for x in edf.timeline]}")

    colors = color_map([t.name for t in EX2])
    fig, axes = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True)
    plot_schedule(axes[0], rm, colors, "Rate Monotonic (static priority: t1 > t2 > t4 > t3)")
    plot_schedule(axes[1], edf, colors, "Earliest Deadline First (dynamic priority)")
    axes[1].set_xlabel("time (ms)")
    fig.suptitle(f"Four-task set, U = 0.875, one hyperperiod (24 ms)  -  ^ = job release",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(f"{FIG}/mp21_rm_vs_edf.png", dpi=160)
    # Separate RM and EDF charts (deliverable asks for individual PNGs too)
    for res, name, ttl in ((rm, "mp21_rm.png", "Rate Monotonic schedule"),
                           (edf, "mp21_edf.png", "EDF schedule")):
        f, a = plt.subplots(figsize=(11, 3.0))
        plot_schedule(a, res, colors, f"{ttl} - four-task set (U = 0.875), H = 24 ms")
        a.set_xlabel("time (ms)")
        f.tight_layout(); f.savefig(f"{FIG}/{name}", dpi=160); plt.close(f)
    plt.close(fig)
    return rm, edf


def step_7():
    line("=")
    print("Step 7 - Response Time Analysis, RM priorities (Section 2.5.2)")
    line("=")
    order = rm_order(EX2)
    print("RM priority order:", " > ".join(t.name for t in order))
    # Show the iteration trace for t4 and t3
    for target in ("t4", "t3"):
        i = [t.name for t in order].index(target)
        task, hp = order[i], order[:i]
        R, trace = task.C, [task.C]
        while True:
            Rn = task.C + sum(math.ceil(R / h.T) * h.C for h in hp)
            trace.append(Rn)
            if Rn == R or Rn > task.D:
                break
            R = Rn
        print(f"  {target}: higher-priority = {[h.name for h in hp]}  iterations R: "
              f"{' -> '.join(map(str, trace))}   R = {trace[-1]} <= D = {task.D}: {trace[-1] <= task.D}")
    rows = rta_all(EX2)
    print(f"{'Task':<5}{'Prio':>5}{'C':>4}{'T':>4}{'D':>4}{'R':>5}{'iter':>6}  verdict")
    for r in rows:
        print(f"{r['task']:<5}{r['priority']:>5}{r['C']:>4}{r['T']:>4}{r['D']:>4}{r['R']:>5}"
              f"{r['iterations']:>6}  {'OK' if r['schedulable'] else 'MISS'}")
    print("Conclusion: every R_i <= D_i, so the set IS RM-schedulable even though U = 0.875 > 0.757.")
    return rows


# --- Steps 8-10: priority inversion -----------------------------------------------------

def inversion_tasks(second_medium=False):
    ts = [RTask("L", 1, 0, [("CS", 6, "S")]),
          RTask("H", 3, 1, [("CS", 2, "S")]),
          RTask("M", 2, 2, [("N", 4)])]
    if second_medium:
        ts.append(RTask("M2", 2, 3, [("N", 3)]))   # arrives during M's execution
    return ts


def plot_inversion(ax, res, tasks, title):
    order = sorted(tasks, key=lambda x: -x.prio)
    names = [x.name for x in order]
    cols = {"H": "#b8405e", "M": "#e07b39", "M2": "#c9a227", "L": "#1b5e8c"}
    T = len(res.timeline)
    for row, x in enumerate(order):
        y = (len(order) - 1 - row) * 10
        for kind, hatch, alpha in (("N", None, 1.0), ("CS", "///", 1.0), ("CS*", "xxx", 1.0)):
            iv = runs([n if (n == x.name and k == kind) else None
                       for n, k in zip(res.timeline, res.kind)], x.name)
            if iv:
                ax.broken_barh(iv, (y + 1.5, 7), facecolors=cols[x.name], edgecolor="white",
                               hatch=hatch, alpha=alpha, linewidth=0.6)
        ax.plot(x.arrival, y + 9.6, marker="^", color="#333", ms=5)
        # blocked interval (ready but not running) for H
        if x.name == "H":
            bl = []
            fin = res.finish.get("H", T)
            for t in range(x.arrival, fin):
                if res.timeline[t] != "H":
                    bl.append(t)
            for (s, l) in runs([1 if t in bl else 0 for t in range(T)], 1):
                ax.broken_barh([(s, l)], (y + 4, 2), facecolors="#ff4d4d", alpha=0.6)
        if x.name in res.finish:
            ax.text(res.finish[x.name] + 0.1, y + 5, f"done {res.finish[x.name]}",
                    va="center", fontsize=7.5)
    ax.set_yticks([(len(order) - 1 - r) * 10 + 5 for r in range(len(order))])
    ax.set_yticklabels([f"{n} (p={x.prio})" for n, x in zip(names, order)])
    ax.set_xlim(0, T); ax.set_xticks(range(0, T + 1))
    ax.grid(axis="x", color="#ddd", lw=0.6); ax.set_axisbelow(True)
    ax.tick_params(labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_title(title, loc="left", fontsize=10, fontweight="bold")


def step_8_10():
    rows = []
    figs = {}
    for second in (False, True):
        tasks = inversion_tasks(second)
        none = simulate_resources(tasks, 20 if second else 16, "none")
        pip = simulate_resources(tasks, 20 if second else 16, "pip")
        for res in (none, pip):
            H_block = res.blocked_ticks["H"]
            rows.append((("2 medium" if second else "1 medium"), res.protocol.upper(),
                         res.finish["H"], res.finish["H"] - 1, H_block,
                         res.resource_wait["H"]))
        legend = [Patch(facecolor="#999", label="normal execution"),
                  Patch(facecolor="#999", hatch="///", label="critical section (holds S)"),
                  Patch(facecolor="#999", hatch="xxx", label="critical section at inherited priority"),
                  Patch(facecolor="#ff4d4d", alpha=0.6, label="H ready but blocked")]
        sfx = "_2medium" if second else ""
        # combined
        fig, axes = plt.subplots(2, 1, figsize=(11, 5.4 if not second else 6.2), sharex=True)
        plot_inversion(axes[0], none, tasks, "No protocol - unbounded priority inversion")
        plot_inversion(axes[1], pip, tasks, "Priority Inheritance Protocol (PIP)")
        axes[1].set_xlabel("time (ticks)")
        fig.legend(handles=legend, loc="lower center", ncol=4, fontsize=8, frameon=False)
        fig.tight_layout(rect=(0, 0.06, 1, 1))
        fig.savefig(f"{FIG}/mp21_inversion_vs_pip{sfx}.png", dpi=160)
        plt.close(fig)
        if not second:
            for res, name, ttl in ((none, "mp21_inversion_unprotected.png",
                                    "Unprotected: H waits for L's critical section AND all of M"),
                                   (pip, "mp21_inversion_pip.png",
                                    "PIP: L inherits H's priority, M is deferred")):
                f, a = plt.subplots(figsize=(11, 3.0))
                plot_inversion(a, res, tasks, ttl)
                a.set_xlabel("time (ticks)")
                f.legend(handles=legend, loc="lower center", ncol=4, fontsize=7.5, frameon=False)
                f.tight_layout(rect=(0, 0.1, 1, 1)); f.savefig(f"{FIG}/{name}", dpi=160); plt.close(f)
            figs["base"] = (none, pip)
        else:
            figs["two"] = (none, pip)
        line("=")
        print(f"Steps 8-9 - priority inversion scenario ({'with second medium task M2' if second else 'base'})")
        line("=")
        for res in (none, pip):
            tl = " ".join(f"{(n or '.'):>2}" for n in res.timeline)
            print(f"{res.protocol.upper():<5}{tl}")
            print(f"      finish times: {res.finish}")
    line("=")
    print("Step 10 - blocking time of H (arrival t=1, C_H=2)")
    line("=")
    print(f"{'Scenario':<10}{'Protocol':<10}{'H done':>8}{'R_H':>6}{'blocked':>9}{'mutex-wait':>12}  bound(PIP)")
    for sc, p, fin, R, b, w in rows:
        print(f"{sc:<10}{p:<10}{fin:>8}{R:>6}{b:>9}{w:>12}  {'<= 6 (one CS of L)':>s}")
    print("PIP bound (Section 2.7.1): one critical section per lower-priority task sharing S = |CS_L| = 6.")
    return rows, figs


# --- Lab tasks ---------------------------------------------------------------------------

def lab_dm():
    line("=")
    print("Lab task 1 - Deadline Monotonic versus RM")
    line("=")
    H = hyperperiod(EX2)
    same = simulate_rm(EX2, H).timeline == simulate_dm(EX2, H).timeline
    print(f"Implicit deadlines (four-task set): DM schedule identical to RM? {same}")
    CON = [Task("t1", 1, 4), Task("t2", 2, 6), Task("t3", 2, 12, 3)]
    H = hyperperiod(CON)
    rm, dm = simulate_rm(CON, H), simulate_dm(CON, H)
    print("Constrained set: t1(C=1,T=4,D=4) t2(C=2,T=6,D=6) t3(C=2,T=12,D=3)")
    print("  RM order:", " > ".join(t.name for t in rm_order(CON)),
          "  DM order:", " > ".join(t.name for t in dm_order(CON)))
    for res in (rm, dm):
        print(f"  {res.policy}: {''.join((x[-1] if x else '.') for x in res.timeline)}  misses={res.misses}")
    for name, order in (("RM", rm_order), ("DM", dm_order)):
        print(f"  RTA under {name}: " + ", ".join(f"{r['task']}: R={r['R']} (D={r['D']}) "
                                                f"{'OK' if r['schedulable'] else 'MISS'}"
                                                for r in rta_all(CON, order)))
    colors = color_map([t.name for t in CON])
    fig, axes = plt.subplots(2, 1, figsize=(11, 4.8), sharex=True)
    plot_schedule(axes[0], rm, colors, "RM on constrained set (t3 lowest priority) - X = deadline miss")
    plot_schedule(axes[1], dm, colors, "Deadline Monotonic (t3 highest priority, D3 = 3)")
    axes[1].set_xlabel("time (ms)  -  red v = absolute deadline when D < T")
    fig.tight_layout(); fig.savefig(f"{FIG}/mp21_lab_dm.png", dpi=160); plt.close(fig)


def lab_bound_sweep():
    line("=")
    print("Lab task 2 - rm_bound(n) sweep, n = 1..10")
    line("=")
    ns = list(range(1, 11))
    bs = [rm_bound(n) for n in ns]
    for n, b in zip(ns, bs):
        print(f"  n={n:<3} bound={b:.4f}")
    print(f"  ln 2 = {math.log(2):.4f}")
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(ns, bs, "o-", color="#1b5e8c", label="RM bound  n(2^(1/n) - 1)")
    ax.axhline(1.0, color="#e07b39", lw=2, label="EDF bound = 1.0")
    ax.axhline(math.log(2), color="#666", ls="--", lw=1, label="ln 2 = 0.693")
    for n, b in zip(ns, bs):
        ax.annotate(f"{b:.3f}", (n, b), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=7)
    ax.set_xlabel("number of tasks n"); ax.set_ylabel("utilization bound")
    ax.set_ylim(0.6, 1.05); ax.set_xticks(ns); ax.grid(color="#eee")
    ax.legend(fontsize=8, loc="center right")
    ax.set_title("Liu & Layland RM bound versus EDF bound", loc="left", fontweight="bold", fontsize=10)
    fig.tight_layout(); fig.savefig(f"{FIG}/mp21_lab_bound_sweep.png", dpi=160); plt.close(fig)


def lab_llf():
    line("=")
    print("Lab task 3 - Least Laxity First and context switches over one hyperperiod")
    line("=")
    HEAVY = [Task("a", 4, 10), Task("b", 5, 12), Task("c", 2, 15)]
    out = {}
    for label, ts, fname in (("Four-task set (U = 0.875), H = 24", EX2, "mp21_lab_llf.png"),
                             ("Heavier set a(4,10) b(5,12) c(2,15), U = 0.95, H = 60", HEAVY,
                              "mp21_lab_llf_heavy.png")):
        H = hyperperiod(ts)
        results = [simulate_rm(ts, H), simulate_edf(ts, H), simulate_llf(ts, H)]
        print(f" {label}")
        for r in results:
            print(f"  {r.policy:<4} switches={r.context_switches:>3} preemptions={r.preemptions:>3} "
                  f"misses={len(r.misses)}  {''.join((x[-1] if x else '.') for x in r.timeline)}")
        colors = color_map([t.name for t in ts])
        fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
        for ax, r in zip(axes, results):
            plot_schedule(ax, r, colors, f"{r.policy}: {r.context_switches} context switches, "
                                         f"{r.preemptions} preemptions, {len(r.misses)} deadline misses")
        axes[-1].set_xlabel("time (ms)")
        fig.suptitle(label, fontsize=10)
        fig.tight_layout(); fig.savefig(f"{FIG}/{fname}", dpi=160); plt.close(fig)
        out[label] = results
    return out


def main():
    buf = io.StringIO()
    with redirect_stdout(buf):
        step_2_3()
        step_4_6()
        step_7()
        step_8_10()
        lab_dm()
        lab_bound_sweep()
        lab_llf()
    out = buf.getvalue()
    print(out)
    with open(f"{RES}/mp21_results.txt", "w") as f:
        f.write(out)


if __name__ == "__main__":
    main()

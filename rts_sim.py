"""
rts_sim.py - Discrete-event (tick-based) real-time scheduling simulator.

Real-Time Systems, Unit 2 - Mini Project 2.1 (and shared core for 2.2 / 2.3)
University of Rwanda, Gako Campus - Computer Engineering, Year 4

Contents
--------
* Task model (Section 2.1): C, T, D (implicit deadline D = T by default), U = C / T
* Utilization tests: Liu & Layland RM bound (2.2.1), EDF U <= 1 (2.3.1)
* Response Time Analysis (2.5.2)
* Tick simulators: RM, DM (2.4), EDF (2.3), LLF (2.4)
* Resource-sharing simulator with/without Priority Inheritance (2.6, 2.7)
* Gantt-style plotting helpers using matplotlib broken_barh
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import reduce
from typing import Callable, Optional

# ---------------------------------------------------------------------------
# 1. Task model
# ---------------------------------------------------------------------------


@dataclass
class Task:
    """Periodic task tau_i = (C_i, T_i, D_i)."""

    name: str
    C: int
    T: int
    D: Optional[int] = None

    def __post_init__(self) -> None:
        if self.D is None:
            self.D = self.T  # implicit-deadline model
        if self.C <= 0 or self.T <= 0 or self.D <= 0:
            raise ValueError(f"{self.name}: C, T and D must be positive integers")

    @property
    def U(self) -> float:
        return self.C / self.T


def total_utilization(tasks: list[Task]) -> float:
    return sum(t.U for t in tasks)


def rm_bound(n: int) -> float:
    """Liu & Layland sufficient bound n(2^(1/n) - 1)."""
    if n <= 0:
        return 1.0
    return n * (2 ** (1 / n) - 1)


def edf_test(tasks: list[Task]) -> bool:
    """Exact EDF test for implicit deadlines: U <= 1."""
    return total_utilization(tasks) <= 1.0 + 1e-12


def hyperperiod(tasks: list[Task]) -> int:
    return reduce(lambda a, b: a * b // math.gcd(a, b), (t.T for t in tasks), 1)


def is_constrained(tasks: list[Task]) -> bool:
    return any(t.D < t.T for t in tasks)


# ---------------------------------------------------------------------------
# 2. Fixed-priority orderings and Response Time Analysis
# ---------------------------------------------------------------------------


def rm_order(tasks: list[Task]) -> list[Task]:
    """Rate Monotonic: shorter period = higher priority (stable on ties)."""
    return sorted(tasks, key=lambda t: t.T)


def dm_order(tasks: list[Task]) -> list[Task]:
    """Deadline Monotonic: shorter relative deadline = higher priority."""
    return sorted(tasks, key=lambda t: (t.D, t.T))


def rta(task: Task, higher: list[Task], max_iter: int = 10_000) -> tuple[int, int, bool]:
    """Response Time Analysis R = C + sum ceil(R/Tj) Cj.

    Returns (R, iterations, schedulable). Iteration stops at convergence or
    as soon as R exceeds the deadline D.
    """
    R = task.C
    for it in range(1, max_iter + 1):
        R_new = task.C + sum(math.ceil(R / hp.T) * hp.C for hp in higher)
        if R_new == R:
            return R, it, R <= task.D
        if R_new > task.D:
            return R_new, it, False
        R = R_new
    return R, max_iter, False


def rta_all(tasks: list[Task], order: Callable[[list[Task]], list[Task]] = rm_order):
    """Run RTA for every task in priority order. Returns list of dicts."""
    ordered = order(tasks)
    rows = []
    for i, t in enumerate(ordered):
        R, it, ok = rta(t, ordered[:i])
        rows.append({"task": t.name, "priority": i + 1, "C": t.C, "T": t.T, "D": t.D,
                     "R": R, "iterations": it, "schedulable": ok})
    return rows


# ---------------------------------------------------------------------------
# 3. Tick-by-tick uniprocessor simulator
# ---------------------------------------------------------------------------


@dataclass
class Job:
    task: Task
    idx: int          # index of the task in the task list (for tie-breaks)
    release: int
    deadline: int     # absolute deadline
    remaining: int
    job_no: int


@dataclass
class SimResult:
    policy: str
    tasks: list[Task]
    timeline: list[Optional[str]]          # task name executing at each tick, or None
    misses: list[tuple[str, int, int]] = field(default_factory=list)  # (task, job, deadline)
    context_switches: int = 0
    preemptions: int = 0
    response_times: dict = field(default_factory=dict)  # task -> list of response times

    @property
    def sim_time(self) -> int:
        return len(self.timeline)

    def worst_response(self) -> dict:
        return {k: max(v) if v else None for k, v in self.response_times.items()}


def _simulate(tasks: list[Task], sim_time: int, key: Callable[[Job, int], tuple],
              policy: str) -> SimResult:
    jobs: list[Job] = []
    timeline: list[Optional[str]] = []
    res = SimResult(policy, tasks, timeline)
    res.response_times = {t.name: [] for t in tasks}
    counters = {t.name: 0 for t in tasks}
    prev: Optional[Job] = None
    missed_ids = set()

    for t in range(sim_time):
        # releases
        for i, task in enumerate(tasks):
            if t % task.T == 0:
                counters[task.name] += 1
                jobs.append(Job(task, i, t, t + task.D, task.C, counters[task.name]))
        # deadline-miss detection (jobs keep running late; misses are recorded once)
        for j in jobs:
            if j.remaining > 0 and t >= j.deadline and id(j) not in missed_ids:
                missed_ids.add(id(j))
                res.misses.append((j.task.name, j.job_no, j.deadline))
        ready = [j for j in jobs if j.remaining > 0]
        if not ready:
            timeline.append(None)
            prev = None
            continue
        run = min(ready, key=lambda j: key(j, t))
        if prev is not None and run is not prev:
            res.context_switches += 1
            if prev.remaining > 0:
                res.preemptions += 1
        elif prev is None and timeline and timeline[-1] is None:
            pass
        run.remaining -= 1
        timeline.append(run.task.name)
        if run.remaining == 0:
            res.response_times[run.task.name].append(t + 1 - run.release)
        prev = run
        jobs = [j for j in jobs if j.remaining > 0]
    # unfinished jobs whose deadline lies inside the window
    for j in jobs:
        if j.remaining > 0 and j.deadline <= sim_time and id(j) not in missed_ids:
            res.misses.append((j.task.name, j.job_no, j.deadline))
    return res


def simulate_rm(tasks: list[Task], sim_time: int) -> SimResult:
    """Rate Monotonic: static priority by period (index breaks ties)."""
    prio = {t.name: p for p, t in enumerate(rm_order(tasks))}
    return _simulate(tasks, sim_time, lambda j, t: (prio[j.task.name], j.release), "RM")


def simulate_dm(tasks: list[Task], sim_time: int) -> SimResult:
    """Deadline Monotonic: static priority by relative deadline."""
    prio = {t.name: p for p, t in enumerate(dm_order(tasks))}
    return _simulate(tasks, sim_time, lambda j, t: (prio[j.task.name], j.release), "DM")


def simulate_fp(tasks: list[Task], sim_time: int) -> SimResult:
    """Fixed priority: DM if any D < T, otherwise RM (Mini Project 2.2 rule)."""
    return simulate_dm(tasks, sim_time) if is_constrained(tasks) else simulate_rm(tasks, sim_time)


def simulate_edf(tasks: list[Task], sim_time: int) -> SimResult:
    """Earliest Deadline First: smallest absolute deadline first.

    Ties on absolute deadline are broken in favour of the task listed first
    (i.e. the shorter-period task in the unit's examples), then by release time.
    """
    return _simulate(tasks, sim_time, lambda j, t: (j.deadline, j.idx, j.release), "EDF")


def simulate_llf(tasks: list[Task], sim_time: int) -> SimResult:
    """Least Laxity First: laxity = d - t - remaining. Ties broken by task index."""
    return _simulate(tasks, sim_time, lambda j, t: (j.deadline - t - j.remaining, j.idx), "LLF")


# ---------------------------------------------------------------------------
# 4. Resource-sharing simulator: priority inversion and PIP
# ---------------------------------------------------------------------------


@dataclass
class RTask:
    """A one-shot job with segments ('N', n) = normal or ('CS', n, res) = critical section.

    Larger `prio` = more urgent.
    """

    name: str
    prio: int
    arrival: int
    segments: list[tuple]


@dataclass
class ResResult:
    protocol: str
    timeline: list[Optional[str]]
    kind: list[Optional[str]]               # 'N', 'CS' or 'CS*' (CS run under inherited priority)
    finish: dict
    blocked_ticks: dict                     # ticks a job was ready but not running
    resource_wait: dict                     # ticks a job waited on a mutex
    eff_prio_log: list[dict]


def simulate_resources(rtasks: list[RTask], sim_time: int, protocol: str = "none") -> ResResult:
    """Simulate jobs sharing mutexes under protocol 'none' or 'pip'."""
    state = {t.name: {"seg": 0, "left": t.segments[0][1], "done": False} for t in rtasks}
    owner: dict[str, str] = {}              # resource -> holder
    byname = {t.name: t for t in rtasks}
    timeline, kind, log = [], [], []
    finish, blocked, rwait = {}, {t.name: 0 for t in rtasks}, {t.name: 0 for t in rtasks}

    def cur_seg(name):
        return byname[name].segments[state[name]["seg"]]

    def waiting_on(name) -> Optional[str]:
        seg = cur_seg(name)
        if seg[0] == "CS":
            holder = owner.get(seg[2])
            if holder is not None and holder != name:
                return seg[2]
        return None

    for t in range(sim_time):
        active = [x for x in rtasks if x.arrival <= t and not state[x.name]["done"]]
        eff = {x.name: x.prio for x in active}
        if protocol == "pip":
            # Inheritance (transitive): a holder runs at the max priority of jobs it blocks.
            changed = True
            while changed:
                changed = False
                for x in active:
                    r = waiting_on(x.name)
                    if r is not None:
                        h = owner[r]
                        if eff[h] < eff[x.name]:
                            eff[h] = eff[x.name]
                            changed = True
        log.append(dict(eff))
        runnable = [x for x in active if waiting_on(x.name) is None]
        for x in active:
            if waiting_on(x.name) is not None:
                rwait[x.name] += 1
        if not runnable:
            timeline.append(None); kind.append(None)
            for x in active:
                blocked[x.name] += 1
            continue
        run = max(runnable, key=lambda x: (eff[x.name], -x.arrival))
        for x in active:
            if x is not run:
                blocked[x.name] += 1
        st = state[run.name]
        seg = cur_seg(run.name)
        if seg[0] == "CS":
            owner[seg[2]] = run.name          # acquire (no-op if already held)
        timeline.append(run.name)
        kind.append("CS*" if seg[0] == "CS" and eff[run.name] > run.prio else seg[0])
        st["left"] -= 1
        if st["left"] == 0:
            if seg[0] == "CS":
                owner.pop(seg[2], None)       # release, priority restored next tick
            st["seg"] += 1
            if st["seg"] == len(run.segments):
                st["done"] = True
                finish[run.name] = t + 1
            else:
                st["left"] = run.segments[st["seg"]][1]
    return ResResult(protocol, timeline, kind, finish, blocked, rwait, log)


# ---------------------------------------------------------------------------
# 5. Plotting helpers
# ---------------------------------------------------------------------------

PALETTE = ["#1b5e8c", "#e07b39", "#3a9d5d", "#b8405e", "#7a5cb8", "#c9a227",
           "#2aa6a6", "#8c5a3c", "#5f6b7a", "#d16fb0", "#4e79a7", "#9c755f"]


def color_map(names: list[str]) -> dict:
    return {n: PALETTE[i % len(PALETTE)] for i, n in enumerate(names)}


def runs(timeline: list, value) -> list[tuple[int, int]]:
    """Contiguous (start, length) intervals where timeline == value."""
    out, start = [], None
    for t, v in enumerate(timeline + [object()]):
        if v == value and start is None:
            start = t
        elif v != value and start is not None:
            out.append((start, t - start)); start = None
    return out


def plot_schedule(ax, res: SimResult, colors: dict, title: str = "", horizon: Optional[int] = None,
                  show_releases: bool = True):
    tasks = res.tasks
    H = horizon or res.sim_time
    names = [t.name for t in tasks]
    for row, task in enumerate(tasks):
        y = (len(tasks) - 1 - row) * 10
        ax.broken_barh(runs(res.timeline[:H], task.name), (y + 1.5, 7),
                       facecolors=colors[task.name], edgecolor="white", linewidth=0.6)
        if show_releases:
            for r in range(0, H + 1, task.T):
                ax.plot([r, r], [y + 8.5, y + 9.8], color="#333", lw=0.8)
                ax.plot(r, y + 9.8, marker="^", ms=3.5, color="#333")
            if task.D != task.T:
                for r in range(0, H, task.T):
                    if r + task.D <= H:
                        ax.plot(r + task.D, y + 1.0, marker="v", ms=4, color="#b8405e")
        for (nm, jn, d) in res.misses:
            if nm == task.name and d <= H:
                ax.plot(d, y + 5, marker="x", ms=9, mew=2.2, color="red")
    idle = runs(res.timeline[:H], None)
    ax.broken_barh(idle, (-8, 5), facecolors="#cccccc", hatch="///", edgecolor="#999")
    ax.set_yticks([(len(tasks) - 1 - r) * 10 + 5 for r in range(len(tasks))] + [-5.5])
    ax.set_yticklabels(names + ["idle"])
    ax.set_xlim(0, H)
    ax.set_ylim(-10, len(tasks) * 10 + 1)
    step = 1 if H <= 30 else (2 if H <= 60 else (5 if H <= 150 else max(10, H // 25)))
    ax.set_xticks(range(0, H + 1, step))
    ax.grid(axis="x", color="#ddd", lw=0.6)
    ax.set_axisbelow(True)
    ax.tick_params(labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    if title:
        ax.set_title(title, loc="left", fontsize=10, fontweight="bold")

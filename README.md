# Real-Time Systems – Unit 2 Lab: Scheduling Mini Projects 2.1 – 2.3

**University of Rwanda – Gako Campus · Computer Engineering · Year 4, Semester I**
Group assignment – Real-Time Systems

| Name | Registration number |
|---|---|
| Janvier NSHIMIYIMANA | 223026679 |
| Blandon ASHIMIRWE | 223026675 |
| Gilbert HIRWA NTWALI | 223026689 |

📄 **Report:** [`report/RTS_Unit2_Lab_Report.pdf`](report/RTS_Unit2_Lab_Report.pdf)

## Contents

| Path | What it is |
|---|---|
| `rts_sim.py` | Core library: task model, Liu & Layland bound, EDF test, RTA, RM / DM / EDF / LLF tick simulators, mutex simulator with and without Priority Inheritance, Gantt helpers |
| `mp21_run.py` | **Mini Project 2.1** – every procedure step and lab task |
| `schedcheck.py` | **Mini Project 2.2** – RM (or DM) vs EDF schedulability tool, CSV or Python-list input |
| `tasksets/` | Seven task sets used for Mini Project 2.2 |
| `partition.py` | **Mini Project 2.3** – FF, FFD, BFD, WF partitioning with per-core RM admission |
| `tests/test_all.py` | Hand-computed checks |
| `figures/` | All generated charts (PNG) |
| `results/` | Printed output of each script |
| `report/` | Final report (PDF) and the script that builds it |

## Running

```bash
pip install matplotlib
python mp21_run.py                                 # Mini Project 2.1
python schedcheck.py tasksets/*.csv --out figures  # Mini Project 2.2
python partition.py                                # Mini Project 2.3
python tests/test_all.py                           # checks
```

CSV format for `schedcheck.py` (D optional, defaults to T):

```csv
name,C,T,D
t1,1,4,
t2,2,6,
t3,2,12,3
```

## Key results

* Section 2.2.2 set: U = 0.750 ≤ rm_bound(3) = 0.780 → RM guaranteed.
* Section 2.3.2 set: U = 0.875 > rm_bound(4) = 0.757 (inconclusive), EDF U ≤ 1 passes; RTA gives R = 1, 3, 4, 11 → RM-schedulable.
* Priority inversion: H blocked 9 ticks without a protocol (12 with a second medium task); 5 ticks with PIP, within the one-critical-section bound of 6.
* LLF on a U = 0.95 set: 31 context switches vs 15 for EDF (thrashing).
* Partitioning (m = 4): FFD succeeds where FF fails on an order-sensitive set; five tasks of u = 0.55 (U = 2.75, 69 % of m) cannot be partitioned by any heuristic.

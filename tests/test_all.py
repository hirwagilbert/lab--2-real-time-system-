"""Hand-computed checks for all three mini projects.  Run:  python -m pytest -q  (or python tests/test_all.py)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rts_sim import (Task, RTask, total_utilization, rm_bound, rta_all, simulate_rm, simulate_edf,
                     simulate_resources, hyperperiod)
from schedcheck import analyze
from partition import (first_fit, first_fit_decreasing, best_fit_decreasing, worst_fit, admits,
                       TEST_SETS)

EX1 = [Task("t1", 1, 4), Task("t2", 2, 6), Task("t3", 2, 12)]
EX2 = EX1 + [Task("t4", 1, 8)]


def test_utilization_and_bounds():
    assert abs(total_utilization(EX1) - 0.75) < 1e-9
    assert abs(rm_bound(3) - 0.7798) < 1e-4
    assert abs(total_utilization(EX2) - 0.875) < 1e-9
    assert abs(rm_bound(4) - 0.7568) < 1e-4
    assert rm_bound(1) == 1.0


def test_rta_hand_values():
    R = {r["task"]: r["R"] for r in rta_all(EX2)}
    assert R == {"t1": 1, "t2": 3, "t4": 4, "t3": 11}


def test_simulators_meet_deadlines():
    H = hyperperiod(EX2)
    assert simulate_rm(EX2, H).misses == [] and simulate_edf(EX2, H).misses == []


def test_pip_bounds_blocking():
    ts = [RTask("L", 1, 0, [("CS", 6, "S")]), RTask("H", 3, 1, [("CS", 2, "S")]),
          RTask("M", 2, 2, [("N", 4)])]
    none, pip = simulate_resources(ts, 16, "none"), simulate_resources(ts, 16, "pip")
    assert none.blocked_ticks["H"] == 9 and none.finish["H"] == 12
    assert pip.blocked_ticks["H"] == 5 and pip.finish["H"] == 8
    assert pip.blocked_ticks["H"] <= 6


def test_tool_verdicts():
    assert analyze(EX1)["bound_pass"]
    r = analyze(EX2)
    assert not r["bound_pass"] and r["fp_ok"] and r["edf_ok"]
    over = analyze([Task("a", 2, 4), Task("b", 3, 6), Task("c", 2, 8)])
    assert over["infeasible"] and not over["edf_ok"] and not over["fp_ok"]
    con = analyze([Task("t1", 1, 4), Task("t2", 2, 6), Task("t3", 2, 12, 3)])
    assert con["fp_policy"] == "DM" and con["fp_ok"] and con["edf_ok"]


def test_partition():
    assert admits([], Task("x", 11, 20))
    assert not admits([Task("y", 11, 20)], Task("x", 11, 20))
    for h in (first_fit, first_fit_decreasing, best_fit_decreasing, worst_fit):
        assert not h(TEST_SETS["E_adversarial"], 4).success
    assert not first_fit(TEST_SETS["D_order_sensitive"], 4).success
    assert first_fit_decreasing(TEST_SETS["D_order_sensitive"], 4).success
    assert not worst_fit(TEST_SETS["B_skewed"], 4).success


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("PASS", name)

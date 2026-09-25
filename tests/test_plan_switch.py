"""POST /api/green-wave/plan-switch-windows 的算法与接口测试。"""

import random

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.greenwave import compute_plan_switch_windows
from app.main import green_wave_plan_switch_windows
from app.schemas import PlanSwitchRequest


def make_request(payload):
    return PlanSwitchRequest.model_validate(payload)


def base_node(**overrides):
    node = {
        "cycle": 60,
        "offset": 0,
        "green_start": 0,
        "green_end": 0,  # 默认常绿
        "travel": 0,
        "next_plan": {
            "cycle": 60, "offset": 0, "green_start": 0, "green_end": 0,
        },
    }
    node.update(overrides)
    return node


# ---------- 逐秒暴力参考实现 ----------


def _segment_contained(nodeside, arrival_lo, arrival_hi, hi_is_arrival):
    """抵达段（绝对时间，未含 offset）是否整体落入某条连续绿灯分量。

    左端恒为真实到达时刻，须 ``>= a``；右端语义由 ``hi_is_arrival`` 决定：
    右端为真实可达到达时刻（闭）时须严格 ``< b``；右端恰为切换点 S（半开
    段不含 S）时允许 ``== b``，因为实际到达可任意逼近 S。
    """
    c = nodeside["cycle"]
    gs, ge = nodeside["green_start"], nodeside["green_end"]
    o = nodeside["offset"]
    lo, hi = arrival_lo + o, arrival_hi + o
    if gs == ge:
        return True
    q0 = lo // c - 2
    for q in range(q0, q0 + 6):
        if gs < ge:
            a, b = q * c + gs, q * c + ge
        else:  # 跨零点：连续分量 [qC+gs, (q+1)C+ge)
            a, b = q * c + gs, (q + 1) * c + ge
        right_ok = hi < b if hi_is_arrival else hi <= b
        if a <= lo and right_ok:
            return True
    return False


def brute_force(nodes, lo, hi, switch_at):
    """逐整数出发秒 × 逐侧抵达段判定的参考实现。"""
    result = []
    run_start = None
    for t in range(lo, hi + 1):
        ok = t < hi
        if ok:
            for n in nodes:
                travel = n["travel"]
                tmax = n.get("travel_max", travel)
                arrive_lo = t + travel
                arrive_hi = t + tmax
                # 旧计划侧：到达严格小于 S。段上确界 min(arrive_hi, S)
                # 真实可达当且仅当 arrive_hi < S（否则右端恰为不含的 S，
                # 允许等于绿灯分量终点）。
                if arrive_lo < switch_at:
                    upper = min(arrive_hi, switch_at)
                    if not _segment_contained(
                        n, arrive_lo, upper, hi_is_arrival=(arrive_hi < switch_at)
                    ):
                        ok = False
                        break
                # 新计划侧：闭抵达段 [max(arrive_lo, S), arrive_hi]，
                # 两端均为真实可达到达，右端严格小于绿灯终点。
                new_lo = max(arrive_lo, switch_at)
                if ok and new_lo <= arrive_hi:
                    if not _segment_contained(
                        n["next_plan"], new_lo, arrive_hi, True
                    ):
                        ok = False
                        break
        if ok:
            if run_start is None:
                run_start = t
        else:
            if run_start is None:
                pass
            else:
                result.append([run_start, t])
                run_start = None
    if run_start is not None:
        result.append([run_start, hi])
    return result


def to_algo_nodes(nodes):
    return [
        {
            "cycle": n["cycle"],
            "offset": n["offset"],
            "green_start": n["green_start"],
            "green_end": n["green_end"],
            "travel": n["travel"],
            "travel_max": n.get("travel_max", n["travel"]),
            "next_plan": dict(n["next_plan"]),
        }
        for n in nodes
    ]


# ---------- 基本语义 ----------


def test_switch_before_all_arrivals_uses_new_plan():
    # S=0：所有到达 >= 0，全部按新计划判灯；旧计划全红也不影响。
    node = base_node(
        cycle=60, offset=0, green_start=20, green_end=30, travel=0,
        next_plan={"cycle": 60, "offset": 0, "green_start": 0, "green_end": 30},
    )
    req = make_request(
        {"depart_from": 0, "depart_to": 60, "switch_at": 0,
         "intersections": [node]}
    )
    windows = green_wave_plan_switch_windows(req)
    assert [[w.start, w.end] for w in windows] == [[0, 30]]


def test_switch_after_all_arrivals_uses_old_plan():
    # S 远在发车范围之后：全部按旧计划判灯。
    node = base_node(
        cycle=60, offset=0, green_start=0, green_end=30, travel=0,
        next_plan={"cycle": 60, "offset": 0, "green_start": 20, "green_end": 30},
    )
    req = make_request(
        {"depart_from": 0, "depart_to": 60, "switch_at": 10_000,
         "intersections": [node]}
    )
    windows = green_wave_plan_switch_windows(req)
    assert [[w.start, w.end] for w in windows] == [[0, 30]]


def test_boundary_arrival_exactly_at_switch_uses_new_plan():
    # slack=0，到达恰为 S 时按新计划：旧绿灯 [0,30)、新绿灯 [30,50)。
    # t=28,29 旧绿；t=30 起按新计划，新相位 (t-30) 落在 [0,20) ⇒ 全绿。
    node = base_node(
        cycle=60, offset=0, green_start=0, green_end=30, travel=0,
        next_plan={"cycle": 60, "offset": 0, "green_start": 30, "green_end": 50},
    )
    req = make_request(
        {"depart_from": 28, "depart_to": 33, "switch_at": 30,
         "intersections": [node]}
    )
    windows = green_wave_plan_switch_windows(req)
    assert [[w.start, w.end] for w in windows] == [[28, 33]]


def test_boundary_arrival_exactly_at_new_green_end_is_red():
    # 新绿灯 [30,50)：到达恰为 50 时不含，按新计划遇红。
    node = base_node(
        cycle=60, offset=0, green_start=0, green_end=30, travel=0,
        next_plan={"cycle": 60, "offset": 0, "green_start": 30, "green_end": 50},
    )
    req = make_request(
        {"depart_from": 48, "depart_to": 53, "switch_at": 30,
         "intersections": [node]}
    )
    windows = green_wave_plan_switch_windows(req)
    assert [[w.start, w.end] for w in windows] == [[48, 50]]


def test_mixed_region_must_check_both_sides():
    # travel [0,10]，S=100。
    # 旧计划 offset=21 ⇒ S 的旧相位为 1（rho=1），S 前紧邻时刻在旧绿灯
    # [0,30) 内；新计划 offset=30 ⇒ S 新相位 10 也在新绿灯 [0,30) 内。
    # 两侧都绿时混合段才有解；旧侧给出下界 t >= S-T-rho = 99，新侧给出
    # 上界 t <= S+30-10-1-10 = 109，故混合段 [99,100) 与新-only
    # [100,110) 端点相接合并为 [99,110)。
    node = base_node(
        cycle=60, offset=21, green_start=0, green_end=30,
        travel=0, travel_max=10,
        next_plan={"cycle": 60, "offset": 30, "green_start": 0, "green_end": 30},
    )
    got = compute_plan_switch_windows(to_algo_nodes([node]), 50, 150, 100)
    assert got == brute_force([node], 50, 150, 100)
    assert got == [[50, 59], [99, 110]]


def test_mixed_region_old_side_red_gives_nothing():
    # 只按最晚抵达（新计划）会误判 t∈[90,100) 可行；S 紧邻前方旧计划为红。
    # 旧 offset=20 ⇒ S 的旧相位恰为 0（rho=0，绿灯起点，前方是红灯）。
    node = base_node(
        cycle=60, offset=20, green_start=0, green_end=30,
        travel=0, travel_max=10,
        next_plan={"cycle": 60, "offset": 30, "green_start": 0, "green_end": 30},
    )
    got = compute_plan_switch_windows(to_algo_nodes([node]), 50, 150, 100)
    assert got == brute_force([node], 50, 150, 100)
    # 混合段全空：旧-only [50,60)，新-only [100,110)。
    assert got == [[50, 60], [100, 110]]


def test_mixed_region_new_side_red_gives_nothing():
    # 只按最早抵达（旧计划）会误判混合段可行；新计划在 S 为红：新 offset=50
    # ⇒ S 新相位 30，rho=30=L，恰为绿灯终点不含。
    node = base_node(
        cycle=60, offset=21, green_start=0, green_end=30,
        travel=0, travel_max=10,
        next_plan={"cycle": 60, "offset": 50, "green_start": 0, "green_end": 30},
    )
    got = compute_plan_switch_windows(to_algo_nodes([node]), 50, 150, 100)
    assert got == brute_force([node], 50, 150, 100)
    # 新计划 eroded 窗口为 [130,150)：混合段被新侧掐掉。
    assert got == [[50, 59], [130, 150]]


def test_mixed_region_old_component_ending_at_switch_allowed():
    # rho=L 时 S 恰为旧绿灯分量右端（不含）：半开段 [t+T, S) 仍可整体落入
    # 该分量（实际行驶时间为实数，最晚到达可任意逼近 S），但闭端的新侧
    # 遇到绿灯终点则不含。旧绿灯 [0,30)、offset=0、S=30：S 旧相位 30
    # 恰为旧分量右端；新计划整周期常绿。travel [0,10] ⇒ 混合整数段
    # t ∈ [20,30)，旧侧下界 t >= S-T-L = 0，不增加约束，故 t=20..29 均
    # 可行（新侧常绿）。
    node = base_node(
        cycle=60, offset=0, green_start=0, green_end=30,
        travel=0, travel_max=10,
        next_plan={"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0},
    )
    got = compute_plan_switch_windows(to_algo_nodes([node]), 0, 80, 30)
    assert got == brute_force([node], 0, 80, 30)
    # 旧-only（t+10<30 ⇒ t<=19）窗口 [0,20)；混合段 [20,30) 全可行；
    # 新-only t>=30 常绿 ⇒ [30,80)，合并为 [0,80)。
    assert got == [[0, 80]]


def test_mixed_region_new_component_starting_at_switch_allowed():
    # rho=0 时 S 恰为新绿灯分量起点（含），新侧闭段可行；但旧侧半开段在
    # S 紧邻前方为红灯。新绿灯 [0,30)、offset=0、S=30：新侧 rho=0 可行，
    # 旧绿灯 [30,60) 使 S 旧相位 30 恰为旧分量起点（旧侧 rho=0 不可行）。
    node = base_node(
        cycle=60, offset=30, green_start=0, green_end=30,
        travel=0, travel_max=10,
        next_plan={"cycle": 60, "offset": 0, "green_start": 0, "green_end": 30},
    )
    got = compute_plan_switch_windows(to_algo_nodes([node]), 0, 80, 30)
    assert got == brute_force([node], 0, 80, 30)
    # 混合段旧侧全红被掐掉：t=20..29 不可行；t∈[30,50) 时按新计划到达
    # 相位落在 [30,50) 红灯段也不可行；新计划 eroded 窗口自 60 起。
    assert got == [[60, 80]]


def test_always_green_plans_unaffected_by_switch():
    node = base_node(
        travel=0, travel_max=20,
        next_plan={"cycle": 30, "offset": 7, "green_start": 5, "green_end": 5},
    )
    req = make_request(
        {"depart_from": 0, "depart_to": 100, "switch_at": 50,
         "intersections": [node]}
    )
    windows = green_wave_plan_switch_windows(req)
    assert [[w.start, w.end] for w in windows] == [[0, 100]]


def test_wrapping_green_mixed_region():
    # 旧计划跨零点绿灯 [50,60)∪[0,10)，offset=0，S=100（旧相位 40，红）；
    # 选 S=60：旧相位 0（绿灯段 [0,10) 起点，rho=0，旧侧不可行）。
    node = base_node(
        cycle=60, offset=0, green_start=50, green_end=10,
        travel=0, travel_max=10,
        next_plan={"cycle": 60, "offset": 0, "green_start": 50, "green_end": 10},
    )
    for s in (60, 65, 100, -7, 0):
        got = compute_plan_switch_windows(to_algo_nodes([node]), 0, 130, s)
        assert got == brute_force([node], 0, 130, s)


def test_different_cycles_old_and_new():
    node = {
        "cycle": 60, "offset": 3, "green_start": 10, "green_end": 40,
        "travel": 5, "travel_max": 12,
        "next_plan": {"cycle": 45, "offset": 20, "green_start": 5, "green_end": 33},
    }
    got = compute_plan_switch_windows(to_algo_nodes([node]), 0, 400, 197)
    assert got == brute_force([node], 0, 400, 197)


def test_no_solution_returns_empty():
    # 旧、新计划各只有 10 秒绿灯且互补，slack=10：任何出发都无法保证遇绿。
    node = base_node(
        cycle=60, offset=0, green_start=0, green_end=10,
        travel=0, travel_max=10,
        next_plan={"cycle": 60, "offset": 0, "green_start": 30, "green_end": 40},
    )
    req = make_request(
        {"depart_from": 0, "depart_to": 120, "switch_at": 57,
         "intersections": [node]}
    )
    assert green_wave_plan_switch_windows(req) == []


def test_multi_intersection_switch():
    nodes = [
        base_node(
            cycle=60, offset=21, green_start=0, green_end=30,
            travel=0, travel_max=10,
            next_plan={"cycle": 60, "offset": 30, "green_start": 0, "green_end": 30},
        ),
        base_node(
            cycle=70, offset=40, green_start=20, green_end=55,
            travel=3, travel_max=9,
            next_plan={"cycle": 50, "offset": 12, "green_start": 0, "green_end": 25},
        ),
    ]
    got = compute_plan_switch_windows(to_algo_nodes(nodes), 0, 500, 233)
    assert got == brute_force(nodes, 0, 500, 233)


# ---------- 随机用例对照 ----------


def _random_node(rng):
    def plan(c):
        return {
            "cycle": c,
            "offset": rng.randint(0, c - 1),
            "green_start": rng.randint(0, c - 1),
            "green_end": rng.randint(0, c - 1),
        }

    c_old = rng.randint(1, 90)
    c_new = rng.randint(1, 90)
    travel = rng.randint(0, 120)
    node = {"travel": travel, **plan(c_old), "next_plan": plan(c_new)}
    if rng.random() < 0.6:
        node["travel_max"] = travel + rng.randint(0, 30)
    return node


def test_brute_force_equivalence_on_random_cases():
    rng = random.Random(20260925)
    for _ in range(3000):
        n_nodes = rng.randint(1, 4)
        nodes = [_random_node(rng) for _ in range(n_nodes)]
        length = rng.randint(1, 600)
        lo = rng.randint(0, 300)
        hi = lo + length
        switch_at = rng.randint(lo - 150, hi + 150)
        got = compute_plan_switch_windows(to_algo_nodes(nodes), lo, hi, switch_at)
        expected = brute_force(nodes, lo, hi, switch_at)
        assert got == expected, (nodes, lo, hi, switch_at)


# ---------- 校验 ----------


def test_reuses_green_wave_validation():
    node = base_node()
    # 发车范围超过 3600 秒仍返回 422。
    req = make_request(
        {"depart_from": 0, "depart_to": 3601, "switch_at": 100,
         "intersections": [node]}
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_plan_switch_windows(req)
    assert exc.value.status_code == 422

    # 旧计划 offset 越界同样 422。
    bad = base_node(offset=60)
    req2 = make_request(
        {"depart_from": 0, "depart_to": 60, "switch_at": 100,
         "intersections": [bad]}
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_plan_switch_windows(req2)
    assert exc.value.status_code == 422

    # travel_max < travel 沿用旧校验。
    bad2 = base_node(travel=10, travel_max=9)
    req3 = make_request(
        {"depart_from": 0, "depart_to": 60, "switch_at": 100,
         "intersections": [bad2]}
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_plan_switch_windows(req3)
    assert exc.value.status_code == 422


def test_next_plan_field_level_validation():
    # next_plan.cycle 越界 / 缺失由 Pydantic 在字段层返回 422。
    with pytest.raises(ValidationError):
        make_request(
            {"depart_from": 0, "depart_to": 60, "switch_at": 100,
             "intersections": [base_node(
                 next_plan={"cycle": 0, "offset": 0,
                            "green_start": 0, "green_end": 0})]}
        )
    with pytest.raises(ValidationError):
        make_request(
            {"depart_from": 0, "depart_to": 60, "switch_at": 100,
             "intersections": [{
                 "cycle": 60, "offset": 0, "green_start": 0, "green_end": 0,
                 "travel": 0,
             }]}
        )


def test_next_plan_phase_validation():
    cases = [
        {"cycle": 60, "offset": 60, "green_start": 0, "green_end": 0},
        {"cycle": 60, "offset": 0, "green_start": 60, "green_end": 0},
        {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 60},
    ]
    for plan in cases:
        req = make_request(
            {"depart_from": 0, "depart_to": 60, "switch_at": 100,
             "intersections": [base_node(next_plan=plan)]}
        )
        with pytest.raises(HTTPException) as exc:
            green_wave_plan_switch_windows(req)
        assert exc.value.status_code == 422


def test_next_plan_validation_error_mentions_intersection_name():
    named = base_node(name="中山路", next_plan={
        "cycle": 60, "offset": 60, "green_start": 0, "green_end": 0})
    req = make_request(
        {"depart_from": 0, "depart_to": 60, "switch_at": 100,
         "intersections": [named]}
    )
    with pytest.raises(HTTPException) as exc:
        req.validate_ranges()
    assert any("中山路" in msg for msg in exc.value.detail)


def test_negative_switch_at_accepted():
    node = base_node(
        cycle=60, offset=0, green_start=0, green_end=30, travel=0,
        next_plan={"cycle": 60, "offset": 30, "green_start": 0, "green_end": 30},
    )
    req = make_request(
        {"depart_from": 0, "depart_to": 60, "switch_at": -100,
         "intersections": [node]}
    )
    req.validate_ranges()  # 不抛异常
    windows = green_wave_plan_switch_windows(req)
    # S 在范围前：全部按新计划，shift=30，绿灯 [0,30) ⇒ [30,60)
    assert [[w.start, w.end] for w in windows] == [[30, 60]]


def test_route_is_in_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/green-wave/plan-switch-windows" in paths
    assert "post" in paths["/api/green-wave/plan-switch-windows"]

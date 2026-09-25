"""整段时隙可调 offset 核心算法测试。

确定性用例覆盖：单路口整段可行弧长度、跨零点分段、常绿、波动收缩后弧长
不足、n >= cycle、行驶时间整体旋转、范围起点非 0、固定路口无法覆盖整段、
建议值环形最近与等距取小。另含 3000+ 组随机参数下与逐 offset 暴力实现的
逐项对照（含可行区间与建议值）。
"""

import random

from app.greenwave import compute_slot_offsets


def it(name=None, **kw):
    # 默认 green_start == green_end 表示整周期常绿，所有取值均满足 schema 约束。
    return {
        "cycle": 60, "offset": 0, "green_start": 0, "green_end": 0,
        "travel": 0, **kw,
    }


# ---------- 确定性用例 ----------

def test_single_plain_green_arc():
    # 绿灯 [0,30)，范围 [0,10)：连续 10 个相位点都须在绿灯内 ⇔ offset∈[0,21)
    nodes = [it(cycle=60, green_start=0, green_end=30, travel=0, offset=0)]
    assert compute_slot_offsets(nodes, 0, 10, 0) == ([[0, 21]], 0)


def test_wrapping_feasible_arc_is_split():
    # 跨零点绿灯 [50,60)∪[0,10)（连续长 20），范围 [0,5)：
    # M = 20-5+1 = 16，起点 50 ⇔ [50,66) mod 60 = [50,60)∪[0,6)
    nodes = [it(cycle=60, green_start=50, green_end=10, travel=0, offset=30)]
    intervals, recommended = compute_slot_offsets(nodes, 0, 5, 0)
    assert intervals == [[0, 6], [50, 60]]
    # 原 offset=30 不可行：正向最近 50（环距 20），反向最近 5（环距 25）
    assert recommended == 50


def test_always_green_any_offset():
    nodes = [it(cycle=60, offset=23)]
    assert compute_slot_offsets(nodes, 10, 200, 0) == ([[0, 60]], 23)


def test_range_longer_than_green_is_empty():
    # 绿灯长 10、范围 20 秒：任何 offset 都无法让 20 个连续相位点全绿
    nodes = [it(cycle=60, green_start=0, green_end=10, travel=0, offset=0)]
    assert compute_slot_offsets(nodes, 0, 20, 0) == ([], None)


def test_range_spanning_full_cycle_non_always_green_is_empty():
    # n == C 而绿灯不是整圆：连续 C 个相位点必有红灯
    nodes = [it(cycle=10, green_start=0, green_end=9, travel=0, offset=0)]
    assert compute_slot_offsets(nodes, 0, 10, 0) == ([], None)


def test_fixed_intersection_unable_to_cover_range_yields_empty():
    # 可调路口常绿，但固定路口绿灯 [0,10) 无法覆盖整个 [0,30)
    nodes = [
        it(cycle=60, offset=0),
        it(cycle=60, offset=0, green_start=0, green_end=10, travel=0),
    ]
    assert compute_slot_offsets(nodes, 0, 30, 0) == ([], None)


def test_fixed_intersection_covering_full_range_passes():
    # 固定路口在范围 [10,20) 内全程可行（绿灯 [0,50)），可调路口常绿
    nodes = [
        it(cycle=60, offset=0),
        it(cycle=60, offset=0, green_start=0, green_end=50, travel=0),
    ]
    assert compute_slot_offsets(nodes, 10, 20, 0) == ([[0, 60]], 0)


def test_slack_erodes_arc_before_counting():
    # 绿灯 [20,50) 长 30，slack=10 收缩为 [20,40) 长 20；范围 15 秒：
    # M = 20-15+1 = 6，起点 (20-0) mod 60 = 20 ⇔ [20,26)
    nodes = [
        it(cycle=60, green_start=20, green_end=50, travel=0,
           travel_max=10, offset=23)
    ]
    intervals, recommended = compute_slot_offsets(nodes, 0, 15, 0)
    assert intervals == [[20, 26]]
    # 原 offset 23 在可行弧内部，建议值即自身
    assert recommended == 23


def test_wrapping_green_continuous_then_eroded():
    # 跨零点连续段 [50,70) 收缩 slack=10 为 [50,60) 长 10；范围 5 秒：
    # M=6，起点 50 ⇔ [50,56)（若错误地拆两段收缩会得到不同结果）
    nodes = [
        it(cycle=60, green_start=50, green_end=10, travel=0,
           travel_max=10, offset=0)
    ]
    assert compute_slot_offsets(nodes, 0, 5, 0) == ([[50, 56]], 55)


def test_travel_rotates_offset_arc():
    # 绿灯 [0,30)，travel=10：shift=(10+o) mod 60，可行 shift 弧 [0,21)
    # ⇔ offset 弧 [50,60)∪[0,11)
    nodes = [it(cycle=60, green_start=0, green_end=30, travel=10, offset=5)]
    assert compute_slot_offsets(nodes, 0, 10, 0) == (
        [[0, 11], [50, 60]], 5
    )


def test_range_not_starting_at_zero():
    # 范围 [100,110)：t 的本地相位为 40..49；绿灯 [0,30)
    # 起点 r0 = (0-100) mod 60 = 20，M=21 ⇔ [20,41)
    nodes = [it(cycle=60, green_start=0, green_end=30, travel=0, offset=0)]
    assert compute_slot_offsets(nodes, 100, 110, 0) == ([[20, 41]], 20)


def test_recommendation_equidistant_takes_smaller():
    # 仅 offset 0 可行，原 offset=30：正反向环距均为 30，取较小者 0
    nodes = [it(cycle=60, green_start=0, green_end=10, travel=0, offset=30)]
    assert compute_slot_offsets(nodes, 0, 10, 0) == ([[0, 1]], 0)

    # 对称情形：仅 offset 30 可行、原 offset=0，等距仍取较小 ⇔ 30
    nodes = [it(cycle=60, green_start=30, green_end=40, travel=0, offset=0)]
    assert compute_slot_offsets(nodes, 0, 10, 0) == ([[30, 31]], 30)


def test_only_adjustable_intersection_offset_is_free():
    # 两个非常绿路口：固定路口 0 在 [0,10) 全程可行；可调路口 1 绿灯
    # [0,30)，其可行 offset 弧与路口 0 无关（路口 0 不被调整）。
    nodes = [
        it(cycle=60, offset=0, green_start=0, green_end=30, travel=0),
        it(cycle=60, offset=0, green_start=0, green_end=30, travel=0),
    ]
    assert compute_slot_offsets(nodes, 0, 10, 1) == ([[0, 21]], 0)


def test_half_open_endpoint_offset_21_infeasible():
    # 绿灯 [0,30)、范围 [0,10)：offset=21 时 t=9 抵达相位 30（终点不含）为红
    nodes = [it(cycle=60, green_start=0, green_end=30, travel=0, offset=21)]
    assert compute_slot_offsets(nodes, 0, 10, 0) == ([[0, 21]], 20)


# ---------- 随机参数与逐 offset 暴力实现对照 ----------

def _brute_force(nodes, adjustable, lo, hi):
    """逐 offset × 逐秒的参考实现，并压缩为极大半开整数区间与建议值。"""
    target = nodes[adjustable]
    cycle = target["cycle"]

    def feasible(t, node):
        gs, ge, c = node["green_start"], node["green_end"], node["cycle"]
        if gs == ge:
            return True
        arrive_lo = t + node["travel"] + node["offset"]
        arrive_hi = t + node.get("travel_max", node["travel"]) + node["offset"]
        for q in range(arrive_lo // c - 2, arrive_lo // c + 4):
            if gs < ge:
                a, b = q * c + gs, q * c + ge
            else:  # 跨零点：连续分量 [qC+gs, (q+1)C+ge)
                a, b = q * c + gs, (q + 1) * c + ge
            if a <= arrive_lo and arrive_hi < b:
                return True
        return False

    good = []
    for offset in range(cycle):
        candidate = [dict(node) for node in nodes]
        candidate[adjustable]["offset"] = offset
        if all(
            feasible(t, node)
            for t in range(lo, hi)
            for node in candidate
        ):
            good.append(offset)

    intervals: list[list[int]] = []
    for offset in good:
        if intervals and intervals[-1][1] == offset:
            intervals[-1][1] = offset + 1
        else:
            intervals.append([offset, offset + 1])
    if not good:
        return [], None

    original = target["offset"]

    def ring_distance(value):
        delta = (value - original) % cycle
        return min(delta, cycle - delta)

    recommended = min(good, key=lambda value: (ring_distance(value), value))
    return intervals, recommended


def test_matches_brute_force_random():
    random.seed(20260924)
    for _ in range(3000):
        n_nodes = random.randint(1, 6)
        nodes = []
        for _ in range(n_nodes):
            c = random.randint(1, 60)
            travel = random.randint(0, 120)
            kwargs = dict(
                cycle=c,
                offset=random.randint(0, c - 1),
                green_start=random.randint(0, c - 1),
                green_end=random.randint(0, c - 1),
                travel=travel,
            )
            if random.random() < 0.6:
                kwargs["travel_max"] = travel + random.randint(0, 40)
            nodes.append(it(**kwargs))
        adjustable = random.randint(0, n_nodes - 1)
        lo = random.randint(0, 200)
        hi = lo + random.randint(1, 300)
        assert compute_slot_offsets(nodes, lo, hi, adjustable) == (
            _brute_force(nodes, adjustable, lo, hi)
        )

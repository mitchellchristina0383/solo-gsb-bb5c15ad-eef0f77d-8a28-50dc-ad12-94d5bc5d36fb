"""车队首车发车窗口核心算法测试。

确定性用例覆盖：基本平移求交、中间车辆被绿灯间隙卡住（不能只验首末车）、
跨零点绿灯、行驶时间波动、多路口联动、首车范围裁剪与半开边界、常绿、无解。
另含 3000 组随机参数下与逐首车时刻 × 逐车暴力参考实现的逐项对照。
"""

import random

from app.greenwave import compute_convoy_starts


def it(name=None, **kw):
    # 默认 green_start == green_end 表示整周期常绿，所有取值均满足 schema 约束。
    return {
        "cycle": 60, "offset": 0, "green_start": 0, "green_end": 0,
        "travel": 0, **kw,
    }


# ---------- 确定性用例 ----------

def test_convoy_basic_shift_intersect():
    # 绿灯 [0,30) 周期 60：3 辆车间隔 10 秒，首车 t 须让 t、t+10、t+20
    # 同落某个 [60q, 60q+30) ⇔ t ∈ [60q, 60q+10)
    nodes = [it(green_start=0, green_end=30)]
    assert compute_convoy_starts(nodes, 0, 300, 3, 10) == [
        [0, 10], [60, 70], [120, 130], [180, 190], [240, 250],
    ]


def test_convoy_middle_vehicle_can_block():
    # 绿灯 [0,30) 周期 60、间隔 40 秒：只验首末车会误判 [0,10) 可行，
    # 但第 2 辆车在 t+40 ∈ [40,50) 必遇红灯，正确解为空。
    nodes = [it(green_start=0, green_end=30)]
    assert compute_convoy_starts(nodes, 0, 120, 3, 40) == []


def test_convoy_always_green_full_first_vehicle_range():
    # 常绿路口：首车范围即 [depart_from, depart_to - (n-1)*h)
    nodes = [it()]
    assert compute_convoy_starts(nodes, 10, 110, 5, 4) == [[10, 94]]


def test_convoy_last_vehicle_must_stay_inside_range():
    # 绿灯 [0,50) 周期 60，n=2、h=7：t 与 t+7 同落某个 [60q, 60q+50)
    # ⇔ t ∈ [60q, 60q+43)；且 t+7 < 100（末车不得越出范围）截断第二段
    nodes = [it(green_start=0, green_end=50)]
    assert compute_convoy_starts(nodes, 0, 100, 2, 7) == [[0, 43], [60, 93]]


def test_convoy_wrapping_green():
    # 跨零点绿灯 [50,60)∪[0,10) 先连续为 [50,70)：单车窗口含绕回范围起点的
    # [0,10) 段；n=2、h=5 ⇔ t 与 t+5 同落某个 [60q+50, 60q+70)
    nodes = [it(green_start=50, green_end=10)]
    assert compute_convoy_starts(nodes, 0, 130, 2, 5) == [
        [0, 5], [50, 65], [110, 125],
    ]


def test_convoy_travel_max_fluctuation():
    # 绿灯 [20,40)、行驶 [0,10]：单车窗口 [20,30) 周期 60；
    # n=2、h=5 ⇔ t ∈ [20,25) 周期 60
    nodes = [it(green_start=20, green_end=40, travel=0, travel_max=10)]
    assert compute_convoy_starts(nodes, 0, 120, 2, 5) == [[20, 25], [80, 85]]


def test_convoy_two_intersections_green_band():
    # 两路口绿波带（README 示例 1 的参数），n=2、h=10：
    # 单车公共窗口 [60q, 60q+30)，t 与 t+10 都可行 ⇔ t ∈ [60q, 60q+20)
    nodes = [
        it(green_start=0, green_end=30, travel=0, offset=0),
        it(green_start=0, green_end=30, travel=30, offset=30),
    ]
    assert compute_convoy_starts(nodes, 0, 300, 2, 10) == [
        [0, 20], [60, 80], [120, 140], [180, 200], [240, 260],
    ]


def test_convoy_no_solution_returns_empty():
    # 两路口单车窗口互不相交，车队自然无解
    nodes = [
        it(green_start=0, green_end=10),
        it(green_start=20, green_end=30),
    ]
    assert compute_convoy_starts(nodes, 0, 60, 2, 5) == []


def test_convoy_half_open_end_boundary():
    # 首车终点为半开：t=10 时末车在 30（绿灯终点，不含）遇红
    nodes = [it(green_start=0, green_end=30)]
    starts = compute_convoy_starts(nodes, 0, 60, 3, 10)
    assert starts == [[0, 10]]
    # 首车范围终点同样半开：常绿时 [0, 20) 不含 20（末车恰在 depart_to）
    assert compute_convoy_starts([it()], 0, 60, 3, 20) == [[0, 20]]


def test_convoy_minimum_span_boundary():
    # (n-1)*h 恰好比范围长度小 1：首车只剩一个整数时刻
    nodes = [it()]
    assert compute_convoy_starts(nodes, 0, 20, 3, 9) == [[0, 2]]
    assert compute_convoy_starts(nodes, 5, 25, 2, 19) == [[5, 6]]


def test_convoy_merges_adjacent_shifted_windows():
    # 相邻车辆的平移窗口端点相接时，求交后不会出现假缝隙：
    # 绿灯 [0,40) 周期 60，n=2、h=20 ⇔ t ∈ [60q, 60q+20)
    nodes = [it(green_start=0, green_end=40)]
    assert compute_convoy_starts(nodes, 0, 120, 2, 20) == [[0, 20], [60, 80]]


# ---------- 随机参数与暴力参考实现对照 ----------

def _brute_force(nodes, lo, hi, n, h):
    """逐首车时刻 × 逐车的参考实现（测试本身才允许逐秒试探）。"""

    def feasible(node, t):
        """整数出发时刻 t 在任意实数行驶时间下是否对该路口可行。"""
        tmax = node.get("travel_max", node["travel"])
        arrive_lo = t + node["travel"] + node["offset"]
        arrive_hi = t + tmax + node["offset"]
        gs, ge, c = node["green_start"], node["green_end"], node["cycle"]
        if gs == ge:
            return True
        for q in range(arrive_lo // c - 2, arrive_lo // c + 4):
            if gs < ge:
                a, b = q * c + gs, q * c + ge
            else:  # 跨零点：连续分量 [qC+gs, (q+1)C+ge)
                a, b = q * c + gs, (q + 1) * c + ge
            if a <= arrive_lo and arrive_hi < b:
                return True
        return False

    span = (n - 1) * h
    expected: list[list[int]] = []
    run_start = None
    for t in range(lo, hi - span):
        ok = all(
            feasible(node, t + k * h)
            for k in range(n)
            for node in nodes
        )
        if ok:
            if run_start is None:
                run_start = t
        else:
            if run_start is not None:
                expected.append([run_start, t])
                run_start = None
    if run_start is not None:
        expected.append([run_start, hi - span])
    return expected


def test_matches_brute_force_random():
    random.seed(20260924)
    for _ in range(3000):
        n_nodes = random.randint(1, 6)
        nodes = []
        for _ in range(n_nodes):
            c = random.randint(1, 90)
            travel = random.randint(0, 120)
            kwargs = dict(
                cycle=c,
                offset=random.randint(0, c - 1),
                green_start=random.randint(0, c - 1),
                green_end=random.randint(0, c - 1),
                travel=travel,
            )
            if random.random() < 0.5:
                kwargs["travel_max"] = travel + random.randint(0, 30)
            nodes.append(it(**kwargs))
        lo = random.randint(0, 300)
        hi = lo + random.randint(2, 600)
        n = random.randint(2, 8)
        h = random.randint(1, 60)
        if (n - 1) * h >= hi - lo:
            continue  # 请求侧 422 的情形，算法层不覆盖
        assert compute_convoy_starts(nodes, lo, hi, n, h) == (
            _brute_force(nodes, lo, hi, n, h)
        )

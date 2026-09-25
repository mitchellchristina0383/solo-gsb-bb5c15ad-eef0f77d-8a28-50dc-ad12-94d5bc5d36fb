"""班次重排核心算法测试。

确定性用例覆盖：基本平移、headway 顶破原时刻、容限 0、遇绿窗口收缩、
逐班贪心陷阱、字典序 tie-break、半开窗口边界、跨零点绿灯、行驶时间波动、
多路口联动、无解返回 None、50 班边界与性能。另含 3000 组随机参数下与
逐班候选枚举的动态规划暴力参考实现的逐项对照（含结果与总平移成本）。
"""

import random
import time

from app.greenwave import compute_timetable_reschedule


def it(name=None, **kw):
    # 默认 green_start == green_end 表示整周期常绿，所有取值均满足 schema 约束。
    return {
        "cycle": 60, "offset": 0, "green_start": 0, "green_end": 0,
        "travel": 0, **kw,
    }


# ---------- 确定性用例 ----------

def test_always_green_keep_original_when_headway_allows():
    nodes = [it()]
    assert compute_timetable_reschedule(nodes, 0, 60, [0, 10], 5, 5) == [0, 10]


def test_headway_forces_shift():
    # 原时刻 0、3 间隔不足 headway=10：[0,10] 成本 7（另一端被范围下界挡住）
    nodes = [it()]
    assert compute_timetable_reschedule(nodes, 0, 60, [0, 3], 10, 10) == [0, 10]
    # 两侧都可平移且成本同为 7：[5,15] 与 [10,20]，字典序最早取 [5,15]
    assert compute_timetable_reschedule(nodes, 5, 60, [10, 13], 10, 10) == [
        5, 15
    ]


def test_tolerance_zero_infeasible_returns_none():
    # 容限 0 且原时刻间隔不足 headway：无法平移，无解
    nodes = [it()]
    assert compute_timetable_reschedule(nodes, 0, 60, [0, 3], 0, 10) is None


def test_tolerance_zero_on_green_kept():
    # 容限 0 且原时刻本身遇绿、间隔达标：全部保持
    nodes = [it(green_start=0, green_end=30)]
    assert compute_timetable_reschedule(
        nodes, 0, 120, [0, 10, 20], 0, 5
    ) == [0, 10, 20]


def test_greedy_nearest_trap():
    # 逐班贪心选最近点会失败：绿灯 [0,30) 周期 60，原时刻 25、30，容限 5、
    # headway 5。贪心第一班留在 25（成本 0）后，第二班窗口 [25,35)∩绿
    # ={25..29} 中没有 >= 30 的点 ⇒ 误判无解；DP 整体优化得 [24,29]（成本 2）。
    nodes = [it(green_start=0, green_end=30)]
    assert compute_timetable_reschedule(
        nodes, 0, 120, [25, 30], 5, 5
    ) == [24, 29]


def test_lexicographic_tiebreak_single_trip():
    # 两路口公共窗口为 {0..4,10..14}（周期 60 绿灯 [0,20) ∩ 周期 10 绿灯
    # [0,5)）：原时刻 7、容限 5 时 4 与 10 成本同为 3，字典序最早取 4。
    nodes = [
        it(green_start=0, green_end=20),
        it(cycle=10, green_start=0, green_end=5),
    ]
    assert compute_timetable_reschedule(nodes, 0, 60, [7], 5, 1) == [4]


def test_lexicographic_tiebreak_multi_trip():
    # 常绿：原 [10,12]、headway 10、容限 10。可行最优成本为 8：
    # [2,12]（8+0）与 [10,20]（0+8）等同成本，字典序最早取 [2,12]。
    nodes = [it()]
    assert compute_timetable_reschedule(
        nodes, 0, 60, [10, 12], 10, 10
    ) == [2, 12]


def test_half_open_green_endpoint_not_feasible():
    # 绿灯 [0,30)：原时刻恰为终点 30、容限 5，候选仅 25..29（30 不含；
    # 下一窗口 60 超出容限），最近可行点为 29。
    nodes = [it(green_start=0, green_end=30)]
    assert compute_timetable_reschedule(nodes, 0, 120, [30], 5, 1) == [29]


def test_range_boundary_half_open():
    # 范围右端不含：常绿、原时刻靠近 depart_to 时不得越界
    nodes = [it()]
    assert compute_timetable_reschedule(nodes, 0, 60, [55], 10, 1) == [55]
    # 两班被 headway 顶向范围边界：最优 [53,58]（成本 2+0），不得取到 60
    assert compute_timetable_reschedule(
        nodes, 0, 60, [55, 58], 10, 5
    ) == [53, 58]
    # headway 超出容限可调整幅度：无解（[55]、[59] 间隔 4 < 5 且容限 0）
    assert compute_timetable_reschedule(
        nodes, 0, 60, [55, 59], 0, 5
    ) is None


def test_wrapping_green_window():
    # 跨零点绿灯 [50,60)∪[0,10)，无波动：原时刻 8、容限 5 的候选为 0..9
    # （50 等超出容限），最近点 8 本身可行
    nodes = [it(green_start=50, green_end=10)]
    assert compute_timetable_reschedule(nodes, 0, 130, [8, 58], 5, 10) == [
        8, 58
    ]
    # 原时刻 48（红灯）、容限 5：可行候选 50..53，最近为 50
    assert compute_timetable_reschedule(nodes, 0, 130, [48], 5, 1) == [50]


def test_travel_max_fluctuation_shrinks_candidates():
    # 绿灯 [20,40)、行驶 [0,10]：遇绿窗口收缩为 [20,30)（周期 60）。
    # 原时刻 28、容限 5：候选 23..30（30 已不可行），最近为 28；
    # 原时刻 32、容限 5：候选仅 27..29，最近为 29（成本 3）。
    nodes = [it(green_start=20, green_end=40, travel=0, travel_max=10)]
    assert compute_timetable_reschedule(nodes, 0, 120, [28], 5, 1) == [28]
    assert compute_timetable_reschedule(nodes, 0, 120, [32], 5, 1) == [29]


def test_two_intersections_green_band():
    # README 绿波带两路口：公共窗口 [60q, 60q+30)；原时刻 30、容限 5 时
    # 最近可行点为 29（下一窗口起点 60 超出容限）。
    nodes = [
        it(green_start=0, green_end=30, travel=0, offset=0),
        it(green_start=0, green_end=30, travel=30, offset=30),
    ]
    assert compute_timetable_reschedule(nodes, 0, 300, [30], 5, 1) == [29]


def test_no_green_window_at_all_returns_none():
    # 行驶波动吃光绿灯：任何时刻都不可行
    nodes = [it(green_start=20, green_end=40, travel=0, travel_max=30)]
    assert compute_timetable_reschedule(nodes, 0, 120, [25], 30, 1) is None


def test_shifts_respect_tolerance():
    # 绿灯窗口稀疏：原时刻 15、55，容限 10、headway 30。公共绿灯点
    # 0..9、60..69：第一班候选 5..9，第二班候选仅 60；成本最优为
    # [9,60]（成本 6+5=11；若第一班取字典序更小的 5 则成本 10+5=15）。
    nodes = [it(green_start=0, green_end=10)]
    result = compute_timetable_reschedule(
        nodes, 0, 120, [15, 55], 10, 30
    )
    assert result == [9, 60]
    assert all(abs(x - o) <= 10 for x, o in zip(result, [15, 55]))
    assert result[1] - result[0] >= 30


def test_50_trips_boundary_and_performance():
    # 50 班（上界）、常绿、每班间隔 5 秒：范围 300 秒内容得下，原样可行
    nodes = [it()]
    trips = list(range(0, 250, 5))
    assert len(trips) == 50
    started = time.perf_counter()
    result = compute_timetable_reschedule(nodes, 0, 300, trips, 0, 5)
    elapsed = time.perf_counter() - started
    assert result == trips
    assert elapsed < 2.0

    # 紧容限 + 大 headway 的最坏规模仍须快速返回（无解情形）
    sparse = [it(green_start=0, green_end=2)]
    started = time.perf_counter()
    assert compute_timetable_reschedule(
        sparse, 0, 3000, list(range(10, 2010, 40)), 60, 30
    ) is None
    assert time.perf_counter() - started < 2.0


# ---------- 随机参数与暴力参考实现对照 ----------


def _brute_force(nodes, lo, hi, trips, tol, h):
    """逐班枚举候选秒的 DP 参考实现（测试本身才允许逐组合判定）。

    状态存 (最小成本, 取到该成本的字典序最早时刻表)，与被测实现的目标
    函数完全一致；遇绿判定逐路口、逐行驶波动按区间包含直接验算。
    """

    def feasible(node, t):
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

    greens = {
        t for t in range(lo, hi) if all(feasible(node, t) for node in nodes)
    }

    # best: dict t -> (cost, schedule tuple)
    best: dict[int, tuple[int, tuple]] = {}
    o0 = trips[0]
    for t in range(max(lo, o0 - tol), min(hi, o0 + tol + 1)):
        if t in greens:
            best[t] = (abs(t - o0), (t,))
    for j in range(1, len(trips)):
        nxt: dict[int, tuple[int, tuple]] = {}
        oj = trips[j]
        for t in range(max(lo, oj - tol), min(hi, oj + tol + 1)):
            if t not in greens:
                continue
            chosen: tuple[int, tuple] | None = None
            for s, (cost, schedule) in best.items():
                if s <= t - h:
                    candidate = (cost + abs(t - oj), schedule + (t,))
                    if chosen is None or candidate < chosen:
                        chosen = candidate
            if chosen is not None:
                nxt[t] = chosen
        best = nxt
        if not best:
            return None
    if not best:
        return None
    _, schedule = min(best.values())
    return list(schedule)


def test_matches_brute_force_random():
    random.seed(20260925)
    for _ in range(3000):
        n_nodes = random.randint(1, 4)
        nodes = []
        for _ in range(n_nodes):
            c = random.randint(1, 90)
            travel = random.randint(0, 60)
            kwargs = dict(
                cycle=c,
                offset=random.randint(0, c - 1),
                green_start=random.randint(0, c - 1),
                green_end=random.randint(0, c - 1),
                travel=travel,
            )
            if random.random() < 0.5:
                kwargs["travel_max"] = travel + random.randint(0, 20)
            nodes.append(it(**kwargs))
        lo = random.randint(0, 200)
        hi = lo + random.randint(10, 300)
        n = random.randint(1, 6)
        gap = random.randint(1, 40)
        # 保证原时刻本身落在范围内（schema 层亦如此要求）
        if (n - 1) * gap >= hi - lo:
            gap = max(1, (hi - lo - 1) // max(1, n - 1)) if n > 1 else 1
        first = random.randint(lo, hi - 1 - (n - 1) * gap)
        trips = [first + k * gap for k in range(n)]
        tol = random.randint(0, 30)
        h = random.randint(1, 40)
        expected = _brute_force(nodes, lo, hi, trips, tol, h)
        actual = compute_timetable_reschedule(nodes, lo, hi, trips, tol, h)
        assert actual == expected
        if expected is not None:
            assert len(actual) == n
            assert all(abs(x - o) <= tol for x, o in zip(actual, trips))
            assert all(
                actual[j] - actual[j - 1] >= h for j in range(1, n)
            )
            assert sum(abs(x - o) for x, o in zip(actual, trips)) == sum(
                abs(x - o) for x, o in zip(expected, trips)
            )

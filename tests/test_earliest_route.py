"""最早到达路径核心算法测试。

确定性用例覆盖：基本等灯、起点红灯等待、跨零点绿灯（等待与放行）、常绿、
终点不查灯色、半开绿灯端点、同到达时刻道路数优先、字典序 tie-break、
Pareto 前沿（晚到但道路更少的标号在红灯等待中追平反超）、字典序更小
路径在中间路口更晚到达、不可达、起点即终点、并行道路与自环。
另含 3000 组随机参数下与枚举全部简单路径的暴力参考实现的逐项对照。
"""

import random

from app.greenwave import (
    compute_earliest_route,
    latest_green_departure,
    next_green_departure,
)


def sig(name=None, **kw):
    # 默认 green_start == green_end 表示整周期常绿，所有取值均满足 schema 约束。
    return {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0, **kw}


# ---------- 单次放行 / 回退时刻 ----------

def test_next_green_departure_plain():
    # 绿灯 [20,40)：红灯等待到 20，绿灯内立即放行
    assert next_green_departure(60, 0, 20, 40, 0) == 20
    assert next_green_departure(60, 0, 20, 40, 20) == 20
    assert next_green_departure(60, 0, 20, 40, 39) == 39
    # 半开端点：40 已红灯，等到下一周期起点 80
    assert next_green_departure(60, 0, 20, 40, 40) == 80


def test_next_green_departure_wrapping_and_offset():
    # 跨零点绿灯 [50,60)∪[0,10)：45 等到 50，55 与 5 直接放行
    assert next_green_departure(60, 0, 50, 10, 45) == 50
    assert next_green_departure(60, 0, 50, 10, 55) == 55
    assert next_green_departure(60, 0, 50, 10, 5) == 5
    assert next_green_departure(60, 0, 50, 10, 10) == 50
    # offset 参与相位：(t+30)%60 落在 [0,30) 内 ⇔ t%60 ∈ [30,60)
    assert next_green_departure(60, 30, 0, 30, 0) == 30
    assert next_green_departure(60, 30, 0, 30, 30) == 30
    # 常绿：任何时刻立即放行
    assert next_green_departure(60, 0, 0, 0, 123) == 123


def test_latest_green_departure_plain_and_wrapping():
    # 绿灯 [20,40)：45 回退到 39，10 回退到上一周期的 39（即 -21）
    assert latest_green_departure(60, 0, 20, 40, 45) == 39
    assert latest_green_departure(60, 0, 20, 40, 39) == 39
    assert latest_green_departure(60, 0, 20, 40, 10) == -21
    # 跨零点绿灯 [50,60)∪[0,10)：30 回退到 9
    assert latest_green_departure(60, 0, 50, 10, 30) == 9
    assert latest_green_departure(60, 0, 50, 10, 55) == 55
    # 常绿：任何时刻都是绿灯
    assert latest_green_departure(60, 0, 0, 0, 123) == 123


# ---------- 确定性用例 ----------

def readme_signals():
    return [
        sig(green_start=0, green_end=30),   # 0：绿灯 [0,30)
        sig(green_start=20, green_end=50),  # 1：绿灯 [20,50)
        sig(),                              # 2：常绿（终点）
    ]


def test_basic_wait_at_intersection():
    # 0→1→2：0 秒出发遇绿，10 秒到路口 1 遇红等到 20，30 秒到终点；
    # 直达 0→2 行驶 35 秒更慢：等灯反而更快
    roads = [(0, 1, 10), (1, 2, 10), (0, 2, 35)]
    assert compute_earliest_route(readme_signals(), roads, 0, 2, 0) == (
        30, [0, 1, 2]
    )


def test_tie_prefers_fewer_roads():
    # 直达 0→2 行驶 30 秒：与 0→1→2 同时到达（30），道路数更少者胜
    roads = [(0, 1, 10), (1, 2, 10), (0, 2, 30)]
    assert compute_earliest_route(readme_signals(), roads, 0, 2, 0) == (
        30, [0, 2]
    )


def test_tie_prefers_lexicographic_path():
    # 全常绿：[0,1,3] 与 [0,2,3] 同为 10 秒、2 条道路，取字典序更小者
    signals = [sig() for _ in range(4)]
    roads = [(0, 1, 5), (1, 3, 5), (0, 2, 3), (2, 3, 7)]
    assert compute_earliest_route(signals, roads, 0, 3, 0) == (10, [0, 1, 3])


def test_wait_at_start_when_red():
    # 起点路口绿灯 [10,20)：0 秒出发须等到 10 秒才能驶入道路
    signals = [sig(green_start=10, green_end=20), sig()]
    assert compute_earliest_route(signals, [(0, 1, 5)], 0, 1, 0) == (
        15, [0, 1]
    )


def test_wrapping_green_wait_and_pass():
    # 跨零点绿灯 [50,60)∪[0,10)：45 秒出发等到 50；55 秒出发直接放行
    signals = [sig(green_start=50, green_end=10), sig()]
    roads = [(0, 1, 5)]
    assert compute_earliest_route(signals, roads, 0, 1, 45) == (55, [0, 1])
    assert compute_earliest_route(signals, roads, 0, 1, 55) == (60, [0, 1])


def test_destination_light_not_checked():
    # 终点绿灯 [30,40)：5 秒到达时虽为红灯，到达即完成
    signals = [sig(), sig(green_start=30, green_end=40)]
    assert compute_earliest_route(signals, [(0, 1, 5)], 0, 1, 0) == (5, [0, 1])


def test_half_open_green_end_boundary():
    # 绿灯 [0,30) 半开：30 秒到达起点路口已红灯，等到下一周期 60
    signals = [sig(green_start=0, green_end=30), sig()]
    assert compute_earliest_route(signals, [(0, 1, 5)], 0, 1, 30) == (
        65, [0, 1]
    )


def test_arrive_exactly_at_green_start():
    # 10 秒出发、20 秒到达路口 1 恰为绿灯起点（含），立即放行
    signals = [sig(), sig(green_start=20, green_end=50), sig()]
    roads = [(0, 1, 10), (1, 2, 5)]
    assert compute_earliest_route(signals, roads, 0, 2, 10) == (25, [0, 1, 2])


def test_pareto_frontier_later_but_fewer_roads_wins():
    # 路口 2 处两个标号：(50 秒, 2 条路) 经 [0,1,2] 与 (55 秒, 1 条路) 经
    # [0,2]；路口 2 绿灯 [100,200)，两者都等到 100 放行、同时到达终点，
    # 道路数更少的 [0,2,3] 胜——只保留最早标号的单标号 Dijkstra 会答错
    signals = [sig(), sig(), sig(cycle=300, green_start=100, green_end=200), sig()]
    roads = [(0, 1, 25), (1, 2, 25), (0, 2, 55), (2, 3, 10)]
    assert compute_earliest_route(signals, roads, 0, 3, 0) == (110, [0, 2, 3])


def test_lexicographic_path_with_later_intermediate_arrival():
    # 字典序更小的路径在中间路口 2 反而更晚到达（7 秒 vs 5 秒）：
    # 两者都在路口 2 等到 10 秒放行、同时到达终点，[0,1,2,4] 字典序更小
    signals = [
        sig(), sig(), sig(cycle=100, green_start=10, green_end=20),
        sig(), sig(),
    ]
    roads = [(0, 1, 6), (1, 2, 1), (0, 3, 4), (3, 2, 1), (2, 4, 1)]
    assert compute_earliest_route(signals, roads, 0, 4, 0) == (
        11, [0, 1, 2, 4]
    )


def test_unreachable_returns_none():
    signals = [sig(), sig(), sig()]
    assert compute_earliest_route(signals, [(0, 1, 5)], 0, 2, 0) is None
    # 没有任何道路
    assert compute_earliest_route(signals, [], 0, 2, 0) is None


def test_start_equals_end():
    signals = [sig(green_start=10, green_end=20), sig()]
    # 起点即终点：不检查灯色、不需要道路，到达时刻即出发时刻
    assert compute_earliest_route(signals, [], 0, 0, 7) == (7, [0])


def test_parallel_roads_use_min_travel():
    signals = [sig(), sig()]
    roads = [(0, 1, 10), (0, 1, 5)]
    assert compute_earliest_route(signals, roads, 0, 1, 0) == (5, [0, 1])


def test_self_loop_never_helps():
    signals = [sig(), sig()]
    roads = [(0, 0, 1), (0, 1, 5)]
    assert compute_earliest_route(signals, roads, 0, 1, 0) == (5, [0, 1])


def test_detour_beats_direct_when_direct_is_slow():
    signals = [sig(), sig(), sig()]
    roads = [(0, 1, 5), (1, 2, 5), (0, 2, 20)]
    assert compute_earliest_route(signals, roads, 0, 2, 0) == (10, [0, 1, 2])


def test_depart_at_large_value():
    # 出发时刻很大时相位取模仍正确：周期 60 绿灯 [0,30)，
    # t=3605 相位 5 遇绿直接放行
    signals = [sig(green_start=0, green_end=30), sig()]
    assert compute_earliest_route(signals, [(0, 1, 5)], 0, 1, 3605) == (
        3610, [0, 1]
    )
    # t=3640 相位 40 红灯，等到 3660（相位 0）
    assert compute_earliest_route(signals, [(0, 1, 5)], 0, 1, 3640) == (
        3665, [0, 1]
    )


# ---------- 随机对照：枚举全部简单路径的暴力参考 ----------

def _brute_force(signals, roads, start, end, depart_at):
    """枚举全部简单路径，取 (到达时刻, 道路数, 路径) 字典序最小者。

    最优路径必为简单路径（绕行只增加时间与道路数），故枚举是精确的。
    """
    n = len(signals)
    adj = [[] for _ in range(n)]
    for fr, to, w in roads:
        adj[fr].append((to, w))

    def depart(node, t):
        s = signals[node]
        c, o = s["cycle"], s["offset"]
        gs, ge = s["green_start"], s["green_end"]
        if gs == ge:
            return t
        p = (t + o) % c
        green = (gs <= p < ge) if gs < ge else (p >= gs or p < ge)
        return t if green else t + (gs - p) % c

    best = None

    def dfs(u, t, path):
        nonlocal best
        if u == end:
            key = (t, len(path) - 1, tuple(path))
            if best is None or key < best:
                best = key
            return
        d = depart(u, t)
        for v, w in adj[u]:
            if v in path:
                continue
            dfs(v, d + w, path + [v])

    dfs(start, depart_at, [start])
    if best is None:
        return None
    t, _, path = best
    return t, list(path)


def test_matches_brute_force_random():
    rng = random.Random(20260925)
    for _ in range(3000):
        n = rng.randint(2, 6)
        signals = []
        for _ in range(n):
            c = rng.randint(1, 60)
            signals.append(
                {
                    "cycle": c,
                    "offset": rng.randint(0, c - 1),
                    "green_start": rng.randint(0, c - 1),
                    "green_end": rng.randint(0, c - 1),
                }
            )
        roads = []
        for _ in range(rng.randint(0, 14)):
            roads.append(
                (
                    rng.randrange(n),
                    rng.randrange(n),
                    rng.randint(1, 60),
                )
            )
        start = rng.randrange(n)
        end = rng.randrange(n)
        depart_at = rng.randint(0, 500)
        assert compute_earliest_route(
            signals, roads, start, end, depart_at
        ) == _brute_force(signals, roads, start, end, depart_at)

"""offset 诊断核心算法测试：事件扫描结果与逐 offset 暴力实现逐项对照。"""

import random
import time

import pytest

from app.greenwave import (
    _mismatch_intervals_for_observation,
    _shifted_circle_intervals,
    offset_diagnostics,
)


def brute_force(cycle, green_start, green_end, observations):
    """逐 offset × 观测的参考实现，并压缩为极大半开整数区间。"""

    def is_green(phase: int) -> bool:
        if green_start == green_end:
            return True
        if green_start < green_end:
            return green_start <= phase < green_end
        return phase >= green_start or phase < green_end

    best: int | None = None
    best_offsets: list[int] = []
    for offset in range(cycle):
        mismatches = sum(
            1
            for arrival, observed in observations
            if is_green((arrival + offset) % cycle) != observed
        )
        if best is None or mismatches < best:
            best, best_offsets = mismatches, [offset]
        elif mismatches == best:
            best_offsets.append(offset)

    intervals: list[list[int]] = []
    run: list[int] | None = None
    for offset in best_offsets:
        if run is None:
            run = [offset, offset + 1]
        elif offset == run[1]:
            run[1] = offset + 1
        else:
            intervals.append(run)
            run = [offset, offset + 1]
    if run is not None:
        intervals.append(run)
    return best, intervals


# ---------- 平移辅助函数 ----------

def test_shifted_plain_green():
    # 绿灯 [20,40)，arrival 相位 0：预测绿 offset ∈ [20,40)
    assert _shifted_circle_intervals(60, 20, 40, 0) == [[20, 40]]
    # arrival 相位 50：平移 -50 ⇒ [-30,-10) mod 60 = [30,50)
    assert _shifted_circle_intervals(60, 20, 40, 50) == [[30, 50]]


def test_shifted_interval_wraps_zero_into_two_pieces():
    # 绿灯 [10,30)，arrival 相位 20：[-10,10) mod 60 = [50,60) ∪ [0,10)
    assert _shifted_circle_intervals(60, 10, 30, 20) == [[0, 10], [50, 60]]


def test_shifted_wrapping_green():
    # 跨零点绿灯 [50,60)∪[0,10)（连续段 [50,70)），arrival 0
    assert _shifted_circle_intervals(60, 50, 10, 0) == [[0, 10], [50, 60]]
    # arrival 相位 5：连续段平移为 [45,65) mod 60 = [45,60) ∪ [0,5)
    assert _shifted_circle_intervals(60, 50, 10, 5) == [[0, 5], [45, 60]]


def test_shifted_always_green_covers_whole_cycle():
    assert _shifted_circle_intervals(60, 30, 30, 47) == [[0, 60]]


def test_shifted_cycle_one():
    assert _shifted_circle_intervals(1, 0, 0, 0) == [[0, 1]]


# ---------- 单条观测错配集合 ----------

def test_mismatch_sets_observed_colors():
    # 观测为绿：错配在预测红处（绿灯补集）
    assert _mismatch_intervals_for_observation(60, 20, 40, 0, True) == [
        [0, 20], [40, 60]
    ]
    # 观测为红：错配在预测绿处
    assert _mismatch_intervals_for_observation(60, 20, 40, 0, False) == [
        [20, 40]
    ]


def test_mismatch_always_green():
    # 常绿 + 观测绿：无错配 offset；常绿 + 观测红：全部 offset 均错
    assert _mismatch_intervals_for_observation(60, 0, 0, 9, True) == []
    assert _mismatch_intervals_for_observation(60, 0, 0, 9, False) == [
        [0, 60]
    ]


# ---------- 端到端基本语义 ----------

def test_single_green_observation_plain():
    # 观测绿，arrival=0：零错配 offset 恰为绿灯段 [20,40)
    assert offset_diagnostics(60, 20, 40, [(0, True)]) == (0, [[20, 40]])


def test_single_red_observation_uses_complement():
    # 观测红，arrival=0：零错配 offset 为绿灯补集
    assert offset_diagnostics(60, 20, 40, [(0, False)]) == (
        0, [[0, 20], [40, 60]]
    )


def test_wrapping_optimal_set_is_split_in_linear_pieces():
    # 跨零点绿灯 [50,60)∪[0,10)，观测绿：最优集合在 [0,60) 内分两段
    assert offset_diagnostics(60, 50, 10, [(0, True)]) == (
        0, [[0, 10], [50, 60]]
    )
    # 观测红：零错配为中间的红段 [10,50)
    assert offset_diagnostics(60, 50, 10, [(0, False)]) == (0, [[10, 50]])


def test_half_open_endpoint_offset_30_is_red():
    # 绿灯 [0,30)：arrival=0 观测绿时，offset=30 预测相位 30 为红灯
    minimum, intervals = offset_diagnostics(60, 0, 30, [(0, True)])
    assert (minimum, intervals) == (0, [[0, 30]])
    # offset=0 预测相位 0 为绿灯（左端点含）
    assert _mismatch_intervals_for_observation(60, 0, 30, 0, True) == [
        [30, 60]
    ]


def test_always_green_phase():
    assert offset_diagnostics(60, 20, 20, [(123, True)]) == (0, [[0, 60]])
    # 观测红：每个整数 offset 都恰好错配 1 条
    assert offset_diagnostics(60, 20, 20, [(123, False)]) == (1, [[0, 60]])


def test_negative_arrival_time_uses_modulo():
    # arrival=-1 观测绿：(-1 + offset) mod 60 ∈ [20,40) ⇔ offset ∈ [21,41)
    assert offset_diagnostics(60, 20, 40, [(-1, True)]) == (0, [[21, 41]])


def test_cycle_of_one_second():
    assert offset_diagnostics(1, 0, 0, [(5, True)]) == (0, [[0, 1]])
    assert offset_diagnostics(1, 0, 0, [(5, False)]) == (1, [[0, 1]])


def test_contradictory_observations_every_offset_mismatches_once():
    got = offset_diagnostics(60, 20, 40, [(0, True), (0, False)])
    assert got == (1, [[0, 60]])


def test_intervals_sorted_and_disjoint():
    observations = [
        (0, True), (7, False), (13, True), (42, False), (59, True),
    ]
    minimum, intervals = offset_diagnostics(60, 50, 10, observations)
    assert intervals == sorted(intervals)
    for (a, b), (c, d) in zip(intervals, intervals[1:]):
        assert b <= c  # 已合并相邻段，不会出现 b == c
        assert 0 <= a < b <= 60
    assert minimum >= 0


def test_large_input_is_fast_event_sweep():
    # 2000 条观测、86400 秒周期：事件扫描应在百毫秒级完成，
    # 且结果与扫一遍 cycle 的错配数一致（此处 cycle 过大只验证结果自洽）。
    random.seed(2026)
    cycle = 86_400
    observations = [
        (random.randint(-10**9, 10**9), random.random() < 0.5)
        for _ in range(2000)
    ]
    start = time.perf_counter()
    minimum, intervals = offset_diagnostics(cycle, 50_000, 10_000, observations)
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0
    assert intervals == sorted(intervals)
    assert all(0 <= a < b <= cycle for a, b in intervals)

    # 抽样校验区间内错配数确实等于最小值，区间外不小于最小值
    def mismatch_count(offset: int) -> int:
        total = 0
        for arrival, observed in observations:
            phase = (arrival + offset) % cycle
            predicted_green = phase >= 50_000 or phase < 10_000
            if predicted_green != observed:
                total += 1
        return total

    sample_inside = {a for a, _ in intervals} | {
        (a + b) // 2 for a, b in intervals
    }
    for offset in sample_inside:
        assert mismatch_count(offset) == minimum


# ---------- 随机参数与暴力实现对照 ----------

@pytest.mark.parametrize("seed", range(100))
def test_matches_brute_force_random(seed):
    random.seed(seed)
    cycle = random.randint(1, 50)
    green_start = random.randint(0, cycle - 1)
    green_end = random.randint(0, cycle - 1)
    n = random.randint(1, 25)
    observations = [
        (random.randint(-300, 300), random.random() < 0.5)
        for _ in range(n)
    ]
    got = offset_diagnostics(cycle, green_start, green_end, observations)
    expected = brute_force(cycle, green_start, green_end, observations)
    assert got == expected


def test_matches_brute_force_dense_random():
    """更大批量的随机对照（非参数化，避免用例爆炸）。"""
    random.seed(4242)
    for _ in range(2000):
        cycle = random.randint(1, 40)
        green_start = random.randint(0, cycle - 1)
        green_end = random.randint(0, cycle - 1)
        observations = [
            (random.randint(-100, 100), random.random() < 0.5)
            for _ in range(random.randint(1, 20))
        ]
        assert offset_diagnostics(
            cycle, green_start, green_end, observations
        ) == brute_force(cycle, green_start, green_end, observations)

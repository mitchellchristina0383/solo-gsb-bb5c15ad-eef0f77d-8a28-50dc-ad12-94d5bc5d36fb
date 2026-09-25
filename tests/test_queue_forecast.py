"""单路口排队预测核心算法测试：与逐秒 × 逐辆暴力模拟逐项对照。"""

import random
import time

import pytest

from app.greenwave import compute_queue_forecast, is_green_at


def brute_force(
    cycle,
    offset,
    green_start,
    green_end,
    forecast_from,
    forecast_to,
    discharge_per_second,
    initial_queue,
    arrivals,
):
    """逐秒逐辆的 FIFO 参考实现。

    队列中每辆车记录所属批次（-1 为期初车辆）；按秒先入队后放行，记录
    每个批次被放行的车辆数，仅当整批都被放行时才给出最后一辆通过秒。
    """

    def is_green(t):
        if green_start == green_end:
            return True
        phase = (t + offset) % cycle
        if green_start < green_end:
            return green_start <= phase < green_end
        return phase >= green_start or phase < green_end

    by_second: dict[int, list[int]] = {}
    for index, (arrival_time, count) in enumerate(arrivals):
        by_second.setdefault(arrival_time, []).extend([index] * count)

    queue: list[int] = [-1] * initial_queue
    served_counts = [0] * len(arrivals)
    last_pass: dict[int, int] = {}
    max_queue = initial_queue
    for t in range(forecast_from, forecast_to):
        queue.extend(by_second.get(t, ()))
        max_queue = max(max_queue, len(queue))
        if is_green(t):
            served = queue[:discharge_per_second]
            del queue[:discharge_per_second]
            for batch_index in served:
                if batch_index < 0:
                    continue
                served_counts[batch_index] += 1
                last_pass[batch_index] = t
    pass_times = [
        last_pass[index]
        if served_counts[index] == arrivals[index][1]
        else None
        for index in range(len(arrivals))
    ]
    return pass_times, len(queue), max_queue


def test_is_green_basic_semantics():
    # 普通绿灯 [20,40)：端点半开
    assert is_green_at(60, 0, 20, 40, 20)
    assert is_green_at(60, 0, 20, 40, 39)
    assert not is_green_at(60, 0, 20, 40, 40)
    assert not is_green_at(60, 0, 20, 40, 19)
    # offset：相位 (t + o) mod C
    assert not is_green_at(60, 5, 20, 40, 14)  # 相位 19
    assert is_green_at(60, 5, 20, 40, 15)  # 相位 20
    # 跨零点 [50,60) ∪ [0,10)
    assert is_green_at(60, 0, 50, 10, 50)
    assert is_green_at(60, 0, 50, 10, 9)
    assert not is_green_at(60, 0, 50, 10, 10)
    assert not is_green_at(60, 0, 50, 10, 49)
    # 常绿
    assert is_green_at(60, 33, 0, 0, 12345)
    assert is_green_at(1, 0, 0, 0, 0)


def test_basic_fifo_drain():
    # 周期 10、绿灯 [0,5)、每秒放 2 辆；期初 3 辆
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 5, 0, 10, 2, 3, [(2, 2), (8, 1)]
    )
    # 期初：t0 放 2、t1 放 1；第 0 批 t2 到达时队列为空，t2 放 2 一次放完 → 2；
    # 第 1 批 t8 到达时相位 8 为红，t9 仍红，范围内未通过 → None，剩 1 辆。
    assert pass_times == [2, None]
    assert remaining == 1
    # 期初 3 辆（t0 放行前统计）为全程最大；t2/t8 到达后队列分别仅 2、1。
    assert maximum == 3


def test_initial_queue_drains_before_arrivals():
    # 常绿、每秒 1 辆、期初 2 辆、t0 再到 1 辆：期初两辆 t0/t1 通过，批次 t2 通过
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 0, 0, 5, 1, 2, [(0, 1)]
    )
    assert pass_times == [2]
    assert remaining == 0
    assert maximum == 3  # t0 到达后队列 3 辆


def test_red_light_serves_nothing():
    # 周期 10、绿灯仅 [0,1)、范围 [0,4)、每秒放 100：t0 清空期初，
    # t1..t3 到达全部积压到期末
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 1, 0, 4, 100, 1, [(1, 1), (2, 1), (3, 1)]
    )
    assert pass_times == [None, None, None]
    assert remaining == 3
    assert maximum == 3


def test_same_second_multiple_batches_keep_input_order():
    # 常绿、每秒 1 辆；同秒两批 2 辆与 3 辆，严格按输入顺序先到先走
    pass_times, remaining, maximum = compute_queue_forecast(
        5, 0, 0, 0, 0, 6, 1, 0, [(0, 2), (0, 3)]
    )
    assert pass_times == [1, 4]
    assert remaining == 0
    assert maximum == 5


def test_batch_partially_served_then_completed_later():
    # 常绿、每秒 3 辆：一批 5 辆在 t0 到达，t0 放 3、t1 放 2，
    # 最后一辆通过秒为 1（不是 0）
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 0, 0, 3, 3, 0, [(0, 5)]
    )
    assert pass_times == [1]
    assert remaining == 0
    assert maximum == 5


def test_discharge_larger_than_queue_clears_all():
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 0, 0, 2, 100, 0, [(0, 7), (1, 2)]
    )
    assert pass_times == [0, 1]
    assert remaining == 0
    assert maximum == 7  # t0 到达后 7 辆；t1 到达时队列为 0、入队 2 辆


def test_max_queue_counted_after_arrival_before_discharge():
    # 绿灯 [0,10) 常绿、每秒放 1 辆；t0 到 5 辆 → 最大 5（而非放行后的 4）
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 10, 0, 10, 1, 0, [(0, 5)]
    )
    assert maximum == 5
    assert pass_times == [4]
    assert remaining == 0
    # t4 到达 10 辆（峰值 10），t4 放 2；t5..t7 红；t8 到达时余 8，
    # 入队 10 → 18（峰值 18），t8、t9 为红不放行；范围恰在 t9 结束，剩 18
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 5, 0, 10, 2, 0, [(4, 10), (8, 10)]
    )
    assert maximum == 18
    assert remaining == 18
    assert pass_times == [None, None]


def test_batch_completed_exactly_at_last_second_passes():
    # 常绿、每秒 1 辆；一批 3 辆 t0 到达，范围 [0,3)：最后一辆 t2 通过（含）
    pass_times, remaining, _maximum = compute_queue_forecast(
        10, 0, 0, 0, 0, 3, 1, 0, [(0, 3)]
    )
    assert pass_times == [2]
    assert remaining == 0


def test_arrival_at_forecast_to_never_enqueued_by_algorithm():
    # 算法层不校验范围外到达：forecast_to 秒不模拟，批次从未入队。
    # （请求层对这种输入返回 422，见 tests/test_api.py。）
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 0, 0, 5, 100, 0, [(5, 1)]
    )
    assert pass_times == [None]
    assert remaining == 0
    assert maximum == 0


def test_empty_arrivals_with_initial_queue():
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 5, 0, 10, 2, 5, []
    )
    # t0..t2 每秒 2 辆清空期初队列
    assert pass_times == []
    assert remaining == 0
    assert maximum == 5


def test_no_queues_everything_zero():
    assert compute_queue_forecast(10, 0, 0, 5, 0, 10, 1, 0, []) == ([], 0, 0)


def test_batch_partially_served_at_range_end_is_null():
    # 绿灯 [0,2)、每秒 3 辆：t0 到 7 辆放 3、t1 放 3，范围 [0,2) 结束时
    # 还剩 1 辆：该批通过秒为 None、期末待行 1 辆
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 2, 0, 2, 3, 0, [(0, 7)]
    )
    assert pass_times == [None]
    assert remaining == 1
    assert maximum == 7


def test_backlog_spans_multiple_cycles():
    # 周期 10、绿灯 [0,2)（每秒放 2 辆）= 每周期放 4 辆；
    # 期初 10 辆：周期 0 放 4 余 6，周期 1（t10..t11）放 4 余 2，
    # 周期 2（t20）放完最后 2 辆 → 期初队列不产生逐批结果，t20 时队列为空
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 2, 0, 22, 2, 10, []
    )
    assert pass_times == []
    assert remaining == 0
    assert maximum == 10
    # 再来一批 t20 到达 3 辆：t20 先放期初 2 辆（FIFO，期初在前），
    # 能力耗尽，该批 t21 放 2、余 1，需等到 t30（范围外）→ None、剩 1
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 2, 0, 22, 2, 10, [(20, 3)]
    )
    assert pass_times == [None]
    assert remaining == 1
    # 峰值是首秒期初的 10 辆；t20 到达时仅余 2 + 3 = 5，未超过期初峰值
    assert maximum == 10


def test_wrapping_green_drains_across_cycle_boundary():
    # 绿灯本地相位 [8,10) ∪ [0,2)；offset=5 后绿灯绝对秒为 t mod 10 ∈ {3,4,5,6}
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 5, 8, 2, 0, 15, 100, 0, [(9, 1), (11, 1)]
    )
    # t9、t11 均红，积压 2 辆；首个绿灯秒 t13 一次放完，两批最后一辆都在 13
    assert pass_times == [13, 13]
    assert remaining == 0
    assert maximum == 2


def test_always_green_cycle_one():
    pass_times, remaining, maximum = compute_queue_forecast(
        1, 0, 0, 0, 0, 5, 1, 0, [(t, 1) for t in range(5)]
    )
    assert pass_times == [0, 1, 2, 3, 4]
    assert remaining == 0
    assert maximum == 1


def test_large_counts_not_expanded_per_vehicle():
    # 每批 10^9 辆：批次计数推进，结果与规模无关地快速完成
    start = time.perf_counter()
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 5, 0, 20, 10**6, 0, [(0, 10**9), (5, 10**9)]
    )
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0
    # 绿灯为 [0,5)：t0..t4 放 5×10^6（批 0 余 995,000,000）；t5 红，批 1 入队
    # 后队列达峰 1,995,000,000；t5..t9 红不放行；t10..t14 再放 5×10^6，
    # 全部消费批 0（仍余 990,000,000），批 1 一辆未动；t15..t19 红，期末共
    # 放 10×10^6；两批通过秒均为 None。
    assert pass_times == [None, None]
    assert remaining == 2 * 10**9 - 10 * 10**6
    assert maximum == 10**9 - 5 * 10**6 + 10**9

    # 常绿场景：t5 到达时批 0 尚未放完，峰值为两批在队之和
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 0, 0, 20, 10**6, 0, [(0, 10**9), (5, 10**9)]
    )
    assert maximum == 2 * 10**9 - 5 * 10**6
    assert remaining == 2 * 10**9 - 20 * 10**6


def test_forecast_range_does_not_start_at_zero():
    # 预测范围 [100,104)，相位按绝对秒取模：绿灯 [0,2) 周期 10
    pass_times, remaining, maximum = compute_queue_forecast(
        10, 0, 0, 2, 100, 104, 100, 0,
        [(100, 1), (101, 1), (102, 1), (103, 1)],
    )
    # t100 相位 0 绿、t101 相位 1 绿；t102/t103 红 → 后两批未通过
    assert pass_times == [100, 101, None, None]
    assert remaining == 2
    assert maximum == 2


def test_86400_second_range_performance():
    # 最大范围 86400 秒 + 1000 批：秒级事件驱动，亚秒完成
    rng = random.Random(7)
    arrivals = [(rng.randrange(86400), rng.randrange(1, 20)) for _ in range(1000)]
    start = time.perf_counter()
    compute_queue_forecast(
        86400, 123, 100, 200, 0, 86400, 7, 50, arrivals
    )
    assert time.perf_counter() - start < 2.0


# ---------- 随机参数下与逐秒逐辆暴力实现对照 ----------


@pytest.mark.parametrize("seed", range(400))
def test_matches_brute_force_random(seed):
    rng = random.Random(seed)
    cycle = rng.randint(1, 40)
    green_start = rng.randrange(cycle)
    # 约 1/8 概率常绿（端点相等），其余随机普通 / 跨零点绿灯
    if rng.random() < 0.125:
        green_end = green_start
    else:
        green_end = rng.randrange(cycle)
    offset = rng.randrange(cycle)
    forecast_from = rng.randrange(0, 30)
    forecast_to = forecast_from + rng.randint(1, 60)
    discharge_per_second = rng.randint(1, 6)
    initial_queue = rng.randrange(0, 12)
    arrivals = [
        (
            rng.randrange(forecast_from, forecast_to),
            rng.randint(1, 5),
        )
        for _ in range(rng.randrange(0, 12))
    ]

    expected = brute_force(
        cycle, offset, green_start, green_end,
        forecast_from, forecast_to, discharge_per_second,
        initial_queue, arrivals,
    )
    actual = compute_queue_forecast(
        cycle, offset, green_start, green_end,
        forecast_from, forecast_to, discharge_per_second,
        initial_queue, arrivals,
    )
    assert actual == expected


@pytest.mark.parametrize("seed", range(200))
def test_matches_brute_force_always_green(seed):
    rng = random.Random(seed + 9000)
    cycle = rng.randint(1, 30)
    point = rng.randrange(cycle)  # green_start == green_end：常绿
    forecast_from = rng.randrange(0, 20)
    forecast_to = forecast_from + rng.randint(1, 40)
    rate = rng.randint(1, 8)
    initial = rng.randrange(0, 10)
    arrivals = [
        (rng.randrange(forecast_from, forecast_to), rng.randint(1, 4))
        for _ in range(rng.randrange(0, 15))
    ]
    expected = brute_force(
        cycle, rng.randrange(cycle), point, point,
        forecast_from, forecast_to, rate, initial, arrivals,
    )
    actual = compute_queue_forecast(
        cycle, rng.randrange(cycle), point, point,
        forecast_from, forecast_to, rate, initial, arrivals,
    )
    assert actual == expected

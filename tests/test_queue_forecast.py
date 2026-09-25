"""单路口排队预测核心算法测试。

确定性用例覆盖：基本放行、红灯不放行、同秒多批按输入顺序入队、期初队列、
跨零点绿灯、常绿、offset 相位、半开绿灯端点、批内部分通过（范围内未全部
通过为 None）、最大排队数在到达后放行前统计、全天范围与 1000 批次。
另含 2000 组随机参数下与逐辆展开暴力参考实现的逐项对照。
"""

import random
from collections import deque

from app.greenwave import compute_queue_forecast, is_green


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
    """逐辆展开的参考实现：队列中每辆车记录所属批次下标（期初为 -1）。"""

    def green(now):
        if green_start == green_end:
            return True
        phase = (now + offset) % cycle
        if green_start < green_end:
            return green_start <= phase < green_end
        return phase >= green_start or phase < green_end

    queue = deque([-1] * initial_queue)
    by_second = {}
    for index, (moment, _count) in enumerate(arrivals):
        by_second.setdefault(moment, []).append(index)
    remaining = [count for _moment, count in arrivals]
    pass_times = [None] * len(arrivals)
    max_queue = 0
    for now in range(forecast_from, forecast_to):
        for index in by_second.get(now, []):
            queue.extend([index] * arrivals[index][1])
        max_queue = max(max_queue, len(queue))
        if queue and green(now):
            for _ in range(min(discharge_per_second, len(queue))):
                batch = queue.popleft()
                if batch >= 0:
                    remaining[batch] -= 1
                    if remaining[batch] == 0:
                        pass_times[batch] = now
    return pass_times, len(queue), max_queue


def forecast(**kw):
    """以常绿默认值调用 compute_queue_forecast，关键字覆盖。"""
    params = {
        "cycle": 60,
        "offset": 0,
        "green_start": 0,
        "green_end": 0,  # 常绿
        "forecast_from": 0,
        "forecast_to": 10,
        "discharge_per_second": 1,
        "initial_queue": 0,
        "arrivals": [],
    }
    params.update(kw)
    return compute_queue_forecast(**params)


# ---------- is_green 灯色判定 ----------

def test_is_green_plain_wrapping_and_always():
    # 绿灯 [20,40)：端点含 20、不含 40
    assert is_green(60, 0, 20, 40, 20)
    assert not is_green(60, 0, 20, 40, 40)
    # 跨零点绿灯 [50,60)∪[0,10)
    assert is_green(60, 0, 50, 10, 55)
    assert is_green(60, 0, 50, 10, 5)
    assert not is_green(60, 0, 50, 10, 30)
    # 常绿与 offset 相位
    assert is_green(60, 0, 0, 0, 123)
    assert is_green(60, 30, 0, 10, 35)  # (35+30)%60=5 ∈ [0,10)
    assert not is_green(60, 30, 0, 10, 25)


# ---------- 确定性用例 ----------

def test_basic_initial_queue_and_batch():
    # 常绿、每秒放行 1：期初 2 辆先走，t=1 到达的 3 辆批次在 t=4 走完
    pass_times, final_queue, max_queue = forecast(
        initial_queue=2, arrivals=[(1, 3)]
    )
    assert pass_times == [4]
    assert final_queue == 0
    assert max_queue == 4  # t=1 到达后：期初余 1 + 新到 3


def test_red_light_never_discharges():
    # 绿灯 [0,10)：t=20 到达的批次在范围 [0,60) 内一直遇红，全部待行
    pass_times, final_queue, max_queue = forecast(
        green_start=0,
        green_end=10,
        forecast_to=60,
        discharge_per_second=5,
        arrivals=[(20, 3)],
    )
    assert pass_times == [None]
    assert final_queue == 3
    assert max_queue == 3


def test_batch_partially_passed_is_null():
    # 常绿每秒放行 1：t=8 到达 5 辆，范围内只走 2 辆
    pass_times, final_queue, max_queue = forecast(
        arrivals=[(8, 5)]
    )
    assert pass_times == [None]
    assert final_queue == 3
    assert max_queue == 5


def test_same_second_batches_keep_input_order():
    # 同秒两批按输入顺序入队：先到的批先走完
    pass_times, final_queue, max_queue = forecast(
        arrivals=[(0, 2), (0, 1)]
    )
    assert pass_times == [1, 2]
    assert final_queue == 0
    assert max_queue == 3
    # 输入顺序对调后通过秒随之对调
    pass_times, _, _ = forecast(arrivals=[(0, 1), (0, 2)])
    assert pass_times == [0, 2]


def test_max_queue_measured_after_arrival_before_discharge():
    # 放行能力再大，最大排队数仍统计到到达后、放行前的峰值
    pass_times, final_queue, max_queue = forecast(
        discharge_per_second=10, arrivals=[(5, 7)]
    )
    assert pass_times == [5]
    assert final_queue == 0
    assert max_queue == 7


def test_initial_queue_only_all_red():
    # 范围内全程红灯：期初队列原样留到期末，无到达批次
    pass_times, final_queue, max_queue = forecast(
        green_start=0,
        green_end=10,
        forecast_from=20,
        forecast_to=40,
        initial_queue=5,
    )
    assert pass_times == []
    assert final_queue == 5
    assert max_queue == 5


def test_wrapping_green_discharge():
    # 跨零点绿灯 [50,60)∪[0,10)：t=55 到达 3 辆，每秒放行 2
    pass_times, final_queue, max_queue = forecast(
        green_start=50,
        green_end=10,
        forecast_from=50,
        forecast_to=60,
        discharge_per_second=2,
        arrivals=[(55, 3)],
    )
    assert pass_times == [56]
    assert final_queue == 0
    assert max_queue == 3


def test_offset_shifts_green_window():
    # offset=30、绿灯 [0,10)：绝对时刻 t%60 ∈ [30,40) 为绿
    pass_times, final_queue, max_queue = forecast(
        offset=30,
        green_start=0,
        green_end=10,
        forecast_from=30,
        forecast_to=45,
        arrivals=[(35, 2)],
    )
    assert pass_times == [36]
    assert final_queue == 0
    assert max_queue == 2


def test_half_open_green_end_boundary():
    # 绿灯 [0,10) 半开：t=10 已红灯，批次等到下一周期 t=60 才放行
    pass_times, final_queue, max_queue = forecast(
        green_start=0,
        green_end=10,
        forecast_from=0,
        forecast_to=70,
        arrivals=[(10, 1)],
    )
    assert pass_times == [60]
    assert final_queue == 0
    assert max_queue == 1


def test_arrival_at_last_second_can_pass():
    # 范围最后一秒到达且放行能力足够：当秒即通过
    pass_times, final_queue, max_queue = forecast(
        discharge_per_second=3, arrivals=[(9, 2)]
    )
    assert pass_times == [9]
    assert final_queue == 0
    assert max_queue == 2


def test_empty_arrivals_drains_initial_queue():
    pass_times, final_queue, max_queue = forecast(
        discharge_per_second=2, initial_queue=3
    )
    assert pass_times == []
    assert final_queue == 0
    assert max_queue == 3


def test_full_day_range_with_1000_batches():
    # 常绿每秒放行 1：1000 批各 3 辆、间隔 80 秒到达，互不积压
    arrivals = [(80 * i, 3) for i in range(1000)]
    pass_times, final_queue, max_queue = forecast(
        forecast_to=86400, arrivals=arrivals
    )
    assert pass_times == [80 * i + 2 for i in range(1000)]
    assert final_queue == 0
    assert max_queue == 3


def test_large_counts_without_per_vehicle_expansion():
    # 大车辆数只按批次计数推进：10**12 辆的批次不会逐辆展开
    pass_times, final_queue, max_queue = forecast(
        forecast_to=5,
        discharge_per_second=10**9,
        initial_queue=10**6,
        arrivals=[(0, 10**12)],
    )
    # 5 秒共放行 5×10**9 辆，批次远未走完
    assert pass_times == [None]
    assert final_queue == 10**12 + 10**6 - 5 * 10**9
    assert max_queue == 10**12 + 10**6
    # 常绿每秒放行 10**9：10**12 辆恰在第 1000 秒（t=999）走完
    pass_times, final_queue, max_queue = forecast(
        forecast_to=1001,
        discharge_per_second=10**9,
        arrivals=[(0, 10**12)],
    )
    assert pass_times == [999]
    assert final_queue == 0
    assert max_queue == 10**12


# ---------- 随机对照：逐辆展开暴力实现 ----------

def test_random_against_per_vehicle_brute_force():
    rng = random.Random(20260925)
    for _ in range(2000):
        cycle = rng.choice([1, 2, 3, 7, 12, 60, 90])
        offset = rng.randrange(cycle)
        kind = rng.randrange(3)
        if kind == 0:  # 常绿
            green_start = green_end = rng.randrange(cycle)
        elif kind == 1:  # 普通绿灯
            green_start = rng.randrange(cycle)
            green_end = rng.randrange(cycle)
            if green_start == green_end:
                green_end = (green_end + 1) % cycle
            if green_start > green_end:
                green_start, green_end = green_end, green_start
        else:  # 跨零点绿灯
            green_start = rng.randrange(cycle)
            green_end = rng.randrange(cycle)
            if green_start == green_end:
                green_start = (green_start + 1) % cycle
            if green_start < green_end:
                green_start, green_end = green_end, green_start
        forecast_from = rng.randrange(0, 50)
        forecast_to = forecast_from + rng.randrange(1, 120)
        discharge = rng.randrange(1, 4)
        initial = rng.randrange(0, 6)
        arrivals = [
            (rng.randrange(forecast_from, forecast_to), rng.randrange(1, 5))
            for _ in range(rng.randrange(0, 9))
        ]
        expected = brute_force(
            cycle, offset, green_start, green_end,
            forecast_from, forecast_to, discharge, initial, arrivals,
        )
        actual = compute_queue_forecast(
            cycle=cycle,
            offset=offset,
            green_start=green_start,
            green_end=green_end,
            forecast_from=forecast_from,
            forecast_to=forecast_to,
            discharge_per_second=discharge,
            initial_queue=initial,
            arrivals=arrivals,
        )
        assert actual == expected

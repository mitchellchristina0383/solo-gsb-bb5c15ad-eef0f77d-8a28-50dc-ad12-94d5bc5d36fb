"""FastAPI 应用入口。"""

from __future__ import annotations

from fastapi import FastAPI

from .greenwave import (
    compute_convoy_starts,
    compute_earliest_route,
    compute_max_coverage,
    compute_plan_switch_windows,
    compute_queue_forecast,
    compute_slot_offsets,
    compute_timetable_reschedule,
    compute_windows,
    offset_diagnostics,
)
from .schemas import (
    ConvoyStartsRequest,
    EarliestRouteRequest,
    EarliestRouteResponse,
    GreenWaveRequest,
    MaxCoverageResponse,
    OffsetDiagnosticsRequest,
    OffsetDiagnosticsResponse,
    OffsetInterval,
    PlanSwitchRequest,
    QueueForecastRequest,
    QueueForecastResponse,
    SlotOffsetsRequest,
    SlotOffsetsResponse,
    TimetableRescheduleRequest,
    TimetableRescheduleResponse,
    Window,
)

app = FastAPI(
    title="干线绿波发车窗口 API",
    description=(
        "给定干线上至多 8 个路口的信号周期、相位偏移、周期内绿灯半开区间"
        "（可跨周期零点）及行驶秒数（可选上限 travel_max，表示行驶时间可取"
        "[travel, travel_max] 内任意实数），计算在指定发车范围（<= 3600 秒）"
        "内、对所有可能的行驶时间抵达每个路口均遇绿灯的全部极大半开"
        "发车区间。\n\n"
        "另提供单路口偏移诊断接口 `POST /api/green-wave/offset-diagnostics`："
        "给定一个路口的周期、绿灯相位及 1..2000 条（到达时刻, 实际灯色）"
        "观测，对整数 offset∈[0,cycle) 按 (arrival_time+offset) mod cycle "
        "预测灯色，返回最少错配条数与取到该值的全部极大半开 offset 区间"
        "（周期区间事件扫描，不逐一计算 offset×观测）。\n\n"
        "另有最大覆盖接口 `POST /api/green-wave/max-coverage`：对范围内每个"
        "出发时刻统计（任意行驶时长抵达都）遇绿的路口数，返回全局最大路口数"
        "及取到该值的全部极大半开发车区间（复用单路口可行窗口并按区间端点"
        "扫描覆盖数，不逐秒统计）。\n\n"
        "整段时隙接口 `POST /api/green-wave/slot-offsets`：复用路口参数与"
        "发车范围，另传 adjustable_index 指定唯一可调路口，求使范围内每个"
        "整数秒都能发车（其余路口保持原 offset、各路口均须对 travel 到 "
        "travel_max 的任意实际行驶时间遇绿）的全部可行整数 offset（按极大"
        "半开区间输出，跨零点分段），并给出距原 offset 环形最近的建议值"
        "（等距取较小者，无可行值为 null）。\n\n"
        "车队接口 `POST /api/green-wave/convoy-starts`：复用路口参数与发车"
        "范围，另传 vehicle_count（2..50）与 headway（正整数秒，要求 "
        "(vehicle_count-1)×headway 小于范围长度）。车队按固定间隔发车，"
        "每辆车都在给定范围内且在每个路口对任意实际行驶时间遇绿；基于单车"
        "可行窗口平移、求交并合并相邻区间（不只检查首末车），返回全部极大"
        "半开首车发车区间，无解时返回空数组。\n\n"
        "计划切换接口 `POST /api/green-wave/plan-switch-windows`：复用路口"
        "旧计划参数与发车范围，另传全局整数秒 switch_at，并为每个路口传 "
        "next_plan（cycle、offset、green_start、green_end）。车辆到达时刻"
        "严格小于 switch_at 用旧计划，等于或大于时用新计划；切换点落在"
        "[travel, travel_max] 抵达波动区间内时两侧分别检查，不能只按最早"
        "或最晚抵达选择计划。返回范围内全部极大半开发车窗口，无解返回空数组。\n\n"
        "班次重排接口 `POST /api/green-wave/timetable-reschedule`：复用路口"
        "信号、行驶时间波动与发车范围，另传 1..50 个按原时刻严格递增的班次 "
        "original_departures、每班最大平移秒数 tolerance（0..3600）与最小"
        "发车间隔 headway（1..3600）。为每班选择范围内的整数出发秒：处于全"
        "路口遇绿窗口、相对原时刻平移不超过 tolerance、相邻班次至少间隔 "
        "headway；在可行时刻表中最小化总绝对平移秒数，同成本取按班次顺序"
        "字典序最早的结果；基于遇绿窗口与动态规划求解（不逐班贪心选最近"
        "时刻），无解返回 null。\n\n"
        "最早到达路径接口 `POST /api/green-wave/earliest-route`：给定 "
        "2..30 个按下标编号的路口信号（cycle、offset、green_start、"
        "green_end）、至多 120 条有向道路（from、to、travel 正整数秒）、"
        "起终点下标与非负出发秒。车辆到达路口后可等待，只能在该路口绿灯"
        "时驶入下一条路；到终点即完成，不检查终点灯色。返回最早到达秒数"
        "与路口下标路径；同到达时间先取道路数少者，再取路径字典序小者，"
        "不可达返回 null。求解分 (到达时刻,道路数) Pareto Dijkstra、倒推"
        "最晚可行到达与字典序贪心重建三个阶段，不枚举路径。\n\n"
        "排队预测接口 `POST /api/green-wave/queue-forecast`：给定单路口的"
        "周期、offset 与绿灯半开区间（跨零点与常绿语义同上）、最长 86400 "
        "秒的半开预测范围、每绿灯秒放行量、期初队列与至多 1000 条到达批次"
        "（时刻、正整数车辆数，同秒可多批）。每秒先按输入顺序将到达批次"
        "入队，再判灯并按先到先走放行，红灯不放行；用批次计数推进队列，"
        "不逐辆展开。返回各批最后一辆的通过秒（范围内未全部通过为 null）、"
        "期末待行车辆数与最大排队数（每秒到达后、放行前统计）。"
    ),
    version="1.8.0",
)


def _intersection_payload(item) -> dict:
    """把请求中的路口模型转换为算法层使用的参数字典。"""
    return {
        "cycle": item.cycle,
        "offset": item.offset,
        "green_start": item.green_start,
        "green_end": item.green_end,
        "travel": item.travel,
        "travel_max": item.effective_travel_max,
    }


def _plan_switch_payload(item) -> dict:
    """计划切换路口参数：旧计划字段之外另附 next_plan 新信号计划。"""
    return {
        **_intersection_payload(item),
        "next_plan": {
            "cycle": item.next_plan.cycle,
            "offset": item.next_plan.offset,
            "green_start": item.next_plan.green_start,
            "green_end": item.next_plan.green_end,
        },
    }


@app.get("/health", tags=["系统"], summary="健康检查")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post(
    "/api/green-wave/windows",
    response_model=list[Window],
    tags=["绿波"],
    summary="计算全部极大绿波发车窗口",
)
def green_wave_windows(request: GreenWaveRequest) -> list[Window]:
    request.validate_ranges()
    windows = compute_windows(
        intersections=[
            _intersection_payload(item) for item in request.intersections
        ],
        depart_from=request.depart_from,
        depart_to=request.depart_to,
    )
    return [Window(start=start, end=end) for start, end in windows]


@app.post(
    "/api/green-wave/max-coverage",
    response_model=MaxCoverageResponse,
    tags=["绿波"],
    summary="计算最大遇绿路口数及取到该值的全部极大发车区间",
)
def green_wave_max_coverage(request: GreenWaveRequest) -> MaxCoverageResponse:
    request.validate_ranges()
    maximum, intervals = compute_max_coverage(
        intersections=[
            _intersection_payload(item) for item in request.intersections
        ],
        depart_from=request.depart_from,
        depart_to=request.depart_to,
    )
    return MaxCoverageResponse(
        max_coverage=maximum,
        optimal_intervals=[
            Window(start=start, end=end) for start, end in intervals
        ],
    )


@app.post(
    "/api/green-wave/offset-diagnostics",
    response_model=OffsetDiagnosticsResponse,
    tags=["绿波"],
    summary="单路口 offset 诊断：最少错配条数与最优 offset 区间",
)
def green_wave_offset_diagnostics(
    request: OffsetDiagnosticsRequest,
) -> OffsetDiagnosticsResponse:
    request.validate_ranges()
    minimum, intervals = offset_diagnostics(
        cycle=request.cycle,
        green_start=request.green_start,
        green_end=request.green_end,
        observations=(
            (item.arrival_time, item.observed_green)
            for item in request.observations
        ),
    )
    return OffsetDiagnosticsResponse(
        min_mismatches=minimum,
        optimal_intervals=[
            OffsetInterval(start=start, end=end) for start, end in intervals
        ],
    )


@app.post(
    "/api/green-wave/slot-offsets",
    response_model=SlotOffsetsResponse,
    tags=["绿波"],
    summary="整段时隙：求唯一可调路口的全部可行 offset 与最近建议值",
)
def green_wave_slot_offsets(
    request: SlotOffsetsRequest,
) -> SlotOffsetsResponse:
    request.validate_ranges()
    intervals, recommended = compute_slot_offsets(
        intersections=[
            _intersection_payload(item) for item in request.intersections
        ],
        depart_from=request.depart_from,
        depart_to=request.depart_to,
        adjustable_index=request.adjustable_index,
    )
    return SlotOffsetsResponse(
        adjustable_index=request.adjustable_index,
        feasible_intervals=[
            OffsetInterval(start=start, end=end) for start, end in intervals
        ],
        recommended_offset=recommended,
    )


@app.post(
    "/api/green-wave/convoy-starts",
    response_model=list[Window],
    tags=["绿波"],
    summary="计算车队首车发车的全部极大半开区间",
)
def green_wave_convoy_starts(request: ConvoyStartsRequest) -> list[Window]:
    request.validate_ranges()
    starts = compute_convoy_starts(
        intersections=[
            _intersection_payload(item) for item in request.intersections
        ],
        depart_from=request.depart_from,
        depart_to=request.depart_to,
        vehicle_count=request.vehicle_count,
        headway=request.headway,
    )
    return [Window(start=start, end=end) for start, end in starts]


@app.post(
    "/api/green-wave/plan-switch-windows",
    response_model=list[Window],
    tags=["绿波"],
    summary="计划在 switch_at 切换时的全部极大绿波发车窗口",
)
def green_wave_plan_switch_windows(request: PlanSwitchRequest) -> list[Window]:
    request.validate_ranges()
    windows = compute_plan_switch_windows(
        intersections=[
            _plan_switch_payload(item) for item in request.intersections
        ],
        depart_from=request.depart_from,
        depart_to=request.depart_to,
        switch_at=request.switch_at,
    )
    return [Window(start=start, end=end) for start, end in windows]


@app.post(
    "/api/green-wave/timetable-reschedule",
    response_model=TimetableRescheduleResponse | None,
    tags=["绿波"],
    summary="班次重排：总绝对平移最小、字典序最早的可行时刻表",
)
def green_wave_timetable_reschedule(
    request: TimetableRescheduleRequest,
) -> TimetableRescheduleResponse | None:
    request.validate_ranges()
    departures = compute_timetable_reschedule(
        intersections=[
            _intersection_payload(item) for item in request.intersections
        ],
        depart_from=request.depart_from,
        depart_to=request.depart_to,
        original_departures=request.original_departures,
        tolerance=request.tolerance,
        headway=request.headway,
    )
    if departures is None:
        return None
    shifts = [
        new - original
        for new, original in zip(departures, request.original_departures)
    ]
    return TimetableRescheduleResponse(
        departures=departures,
        shifts=shifts,
        total_absolute_shift=sum(abs(shift) for shift in shifts),
    )


@app.post(
    "/api/green-wave/earliest-route",
    response_model=EarliestRouteResponse | None,
    tags=["绿波"],
    summary="路网等灯最早到达：到达秒数与路口下标路径",
)
def green_wave_earliest_route(
    request: EarliestRouteRequest,
) -> EarliestRouteResponse | None:
    request.validate_ranges()
    result = compute_earliest_route(
        signals=[
            {
                "cycle": item.cycle,
                "offset": item.offset,
                "green_start": item.green_start,
                "green_end": item.green_end,
            }
            for item in request.intersections
        ],
        roads=[
            (road.from_, road.to, road.travel) for road in request.roads
        ],
        start=request.start,
        end=request.end,
        depart_at=request.depart_at,
    )
    if result is None:
        return None
    arrival, path = result
    return EarliestRouteResponse(arrival=arrival, path=path)


@app.post(
    "/api/green-wave/queue-forecast",
    response_model=QueueForecastResponse,
    tags=["绿波"],
    summary="单路口排队预测：各批最后通过秒、期末待行与最大排队",
)
def green_wave_queue_forecast(
    request: QueueForecastRequest,
) -> QueueForecastResponse:
    request.validate_ranges()
    pass_times, final_queue, max_queue = compute_queue_forecast(
        cycle=request.cycle,
        offset=request.offset,
        green_start=request.green_start,
        green_end=request.green_end,
        forecast_from=request.forecast_from,
        forecast_to=request.forecast_to,
        discharge_per_second=request.discharge_per_second,
        initial_queue=request.initial_queue,
        arrivals=((item.time, item.vehicles) for item in request.arrivals),
    )
    return QueueForecastResponse(
        batch_pass_times=pass_times,
        final_queue=final_queue,
        max_queue=max_queue,
    )

"""请求与响应的 Pydantic 模型及输入校验。"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .greenwave import (
    MAX_ARRIVAL_BATCHES,
    MAX_CONVOY_VEHICLES,
    MAX_CYCLE,
    MAX_INTERSECTIONS,
    MAX_OBSERVATIONS,
    MAX_QUEUE_FORECAST_SECONDS,
    MAX_RESCHEDULE_TRIPS,
    MAX_ROADS,
    MAX_ROUTE_INTERSECTIONS,
    MAX_WINDOW_SECONDS,
)


class Intersection(BaseModel):
    """单个路口的信号与行程参数，全部为整数秒。"""

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(
        default=None, max_length=64, description="可选的路口名称，仅用于辨识"
    )
    cycle: int = Field(
        ..., ge=1, le=MAX_CYCLE, description="信号周期 C（秒），1..86400"
    )
    offset: int = Field(..., ge=0, description="相位偏移 o（秒），需满足 0 <= o < C")
    green_start: int = Field(
        ..., ge=0, description="绿灯起点（本地相位秒），需满足 0 <= g_start < C"
    )
    green_end: int = Field(
        ..., ge=0, description="绿灯终点（本地相位秒，不含），需满足 0 <= g_end < C"
    )
    travel: int = Field(
        ..., ge=0, le=MAX_CYCLE, description="从起点到该路口的行驶秒数下限 T"
    )
    travel_max: int | None = Field(
        default=None,
        ge=0,
        description=(
            "行驶秒数上限 T_max（可选，缺省等于 travel）；实际行驶时间可取"
            "闭区间 [travel, travel_max] 内任意实数秒"
        ),
    )

    @property
    def effective_travel_max(self) -> int:
        """缺省时 travel_max 等于 travel。"""
        return self.travel if self.travel_max is None else self.travel_max

    def validate_against_cycle(self) -> None:
        """校验所有以周期为上界的字段；不合法时抛出 HTTP 422。"""
        errors: list[str] = []
        label = self.name or f"cycle={self.cycle}"
        if not 0 <= self.offset < self.cycle:
            errors.append(f"offset 必须满足 0 <= offset < cycle（路口 {label}）")
        if not 0 <= self.green_start < self.cycle:
            errors.append(
                f"green_start 必须满足 0 <= green_start < cycle（路口 {label}）"
            )
        if not 0 <= self.green_end < self.cycle:
            errors.append(
                f"green_end 必须满足 0 <= green_end < cycle（路口 {label}）"
            )
        if self.effective_travel_max > MAX_CYCLE:
            errors.append(
                f"travel_max 不得大于 86400（路口 {label}）"
            )
        if self.effective_travel_max < self.travel:
            errors.append(
                f"travel_max 不得小于 travel（路口 {label}）"
            )
        if errors:
            raise HTTPException(status_code=422, detail=errors)


class GreenWaveRequest(BaseModel):
    """绿波发车窗口请求。"""

    model_config = ConfigDict(extra="ignore")

    depart_from: int = Field(
        ..., ge=0, le=MAX_CYCLE, description="发车范围起点（秒，含）"
    )
    depart_to: int = Field(
        ..., ge=1, le=2 * MAX_CYCLE, description="发车范围终点（秒，不含）"
    )
    intersections: list[Intersection] = Field(
        ..., min_length=1, max_length=MAX_INTERSECTIONS,
        description="路口列表，1..8 个",
    )

    def validate_ranges(self) -> None:
        """跨字段校验：相位上界与发车范围长度。"""
        errors: list[str] = []
        length = self.depart_to - self.depart_from
        if length <= 0:
            errors.append("depart_to 必须大于 depart_from（半开发车范围）")
        elif length > MAX_WINDOW_SECONDS:
            errors.append("发车范围长度不得超过 3600 秒（一小时）")

        for intersection in self.intersections:
            try:
                intersection.validate_against_cycle()
            except HTTPException as exc:
                detail = exc.detail
                if isinstance(detail, list):
                    errors.extend(detail)
                else:
                    errors.append(str(detail))

        if errors:
            raise HTTPException(status_code=422, detail=errors)


class Window(BaseModel):
    """一个极大半开发车区间 [start, end)。"""

    start: int = Field(..., description="窗口起点（秒，含）")
    end: int = Field(..., description="窗口终点（秒，不含）")


GreenWaveResponse = list[Window]


class MaxCoverageResponse(BaseModel):
    """最大绿波覆盖结果：全局最大遇绿路口数及取到该值的全部极大发车区间。"""

    max_coverage: int = Field(
        ..., ge=0, description="发车范围内任意出发时刻可遇绿路口数的全局最大值"
    )
    optimal_intervals: list[Window] = Field(
        ...,
        description=(
            "覆盖数取到最大值的全部极大半开发车区间 [start,end)，按起点升序；"
            "最大值为 0 时为完整的请求发车范围 "
            "[depart_from, depart_to)"
        ),
    )


class OffsetObservation(BaseModel):
    """一条车辆到达观测：整数秒绝对到达时刻与当时是否绿灯。"""

    model_config = ConfigDict(extra="ignore")

    arrival_time: int = Field(
        ..., description="车辆到达时刻 t（整数秒，可为任意整数，按周期取模）"
    )
    observed_green: bool = Field(
        ..., description="到达时刻该路口实际灯色：true=绿，false=红"
    )


class OffsetDiagnosticsRequest(BaseModel):
    """单路口 offset 诊断请求。"""

    model_config = ConfigDict(extra="ignore")

    cycle: int = Field(
        ..., ge=1, le=MAX_CYCLE, description="信号周期 C（秒），1..86400"
    )
    green_start: int = Field(
        ..., ge=0, description="绿灯起点（本地相位秒），需满足 0 <= green_start < C"
    )
    green_end: int = Field(
        ..., ge=0, description="绿灯终点（本地相位秒，不含），需满足 0 <= green_end < C"
    )
    observations: list[OffsetObservation] = Field(
        ..., min_length=1, max_length=MAX_OBSERVATIONS,
        description="到达观测列表，1..2000 条",
    )

    def validate_ranges(self) -> None:
        """跨字段校验：绿灯相位端点必须在一个周期内；非法时抛 HTTP 422。"""
        errors: list[str] = []
        if not 0 <= self.green_start < self.cycle:
            errors.append("green_start 必须满足 0 <= green_start < cycle")
        if not 0 <= self.green_end < self.cycle:
            errors.append("green_end 必须满足 0 <= green_end < cycle")
        if errors:
            raise HTTPException(status_code=422, detail=errors)


class OffsetInterval(BaseModel):
    """一个取到最少错配数的极大半开 offset 区间 [start, end)。"""

    start: int = Field(..., ge=0, description="offset 区间起点（秒，含）")
    end: int = Field(..., ge=1, description="offset 区间终点（秒，不含）")


class OffsetDiagnosticsResponse(BaseModel):
    """offset 诊断结果：最少错配条数及取到该值的全部极大半开 offset 区间。"""

    min_mismatches: int = Field(
        ..., ge=0, description="所有整数 offset∈[0,cycle) 中最少的预测错配观测条数"
    )
    optimal_intervals: list[OffsetInterval] = Field(
        ...,
        description=(
            "取到最少错配数的全部极大半开 offset 区间 [start,end)，"
            "整数 offset 满足 start <= offset < end；按起点升序；"
            "跨零点的最优集合在 [0,cycle) 内分段表示"
        ),
    )


class SlotOffsetsRequest(GreenWaveRequest):
    """整段时隙可调 offset 请求：在绿波请求基础上指定唯一可调路口下标。"""

    model_config = ConfigDict(extra="ignore")

    adjustable_index: int = Field(
        ..., ge=0, description="唯一允许调整 offset 的路口下标，从 0 起，须小于路口数"
    )

    def validate_ranges(self) -> None:
        """复用全部绿波 422 校验，并额外校验可调路口下标范围。"""
        super().validate_ranges()
        if self.adjustable_index >= len(self.intersections):
            raise HTTPException(
                status_code=422,
                detail=[
                    "adjustable_index 必须满足 0 <= adjustable_index < 路口数"
                ],
            )


class SlotOffsetsResponse(BaseModel):
    """整段时隙可调 offset 结果：可行 offset 区间与距原值环形最近的建议值。"""

    adjustable_index: int = Field(
        ..., ge=0, description="请求中指定的可调路口下标"
    )
    feasible_intervals: list[OffsetInterval] = Field(
        ...,
        description=(
            "使发车范围内每个整数秒都能在所有路口遇绿的全部极大半开整数 "
            "offset 区间 [start,end)（0 <= start < end <= cycle），按起点升序；"
            "跨零点的可行集合在 [0,cycle) 内分段表示；无可行值时为空数组"
        ),
    )
    recommended_offset: int | None = Field(
        ...,
        description=(
            "距该路口原 offset 环形距离最小的可行整数 offset；正反向等距时取"
            "较小者；无可行值时为 null"
        ),
    )


class ConvoyStartsRequest(GreenWaveRequest):
    """车队首车发车窗口请求：在绿波请求基础上增加车队规模与发车间隔。"""

    model_config = ConfigDict(extra="ignore")

    vehicle_count: int = Field(
        ..., ge=2, le=MAX_CONVOY_VEHICLES,
        description="车队车辆数 n，2..50；首车之后还有 n-1 辆车依次发车",
    )
    headway: int = Field(
        ..., ge=1, le=MAX_WINDOW_SECONDS,
        description="相邻车辆的发车间隔 h（秒，正整数）；第 k 辆在首车之后 k*h 秒出发",
    )

    def validate_ranges(self) -> None:
        """复用全部绿波 422 校验，并要求车队首尾跨度小于发车范围长度。"""
        super().validate_ranges()
        span = (self.vehicle_count - 1) * self.headway
        if span >= self.depart_to - self.depart_from:
            raise HTTPException(
                status_code=422,
                detail=[
                    "(vehicle_count - 1) × headway 必须小于发车范围长度"
                ],
            )


class NextPlan(BaseModel):
    """路口在 switch_at 之后启用的新信号计划（仅信号参数，行驶时间沿用旧值）。"""

    model_config = ConfigDict(extra="ignore")

    cycle: int = Field(
        ..., ge=1, le=MAX_CYCLE, description="新计划信号周期 C'（秒），1..86400"
    )
    offset: int = Field(
        ..., ge=0, description="新计划相位偏移 o'（秒），需满足 0 <= o' < C'"
    )
    green_start: int = Field(
        ..., ge=0, description="新计划绿灯起点（本地相位秒），需满足 0 <= g_start < C'"
    )
    green_end: int = Field(
        ..., ge=0, description="新计划绿灯终点（本地相位秒，不含），需满足 0 <= g_end < C'"
    )

    def validate_against_cycle(self, label: str) -> list[str]:
        """校验相位与绿灯端点；返回中文错误信息列表（空列表表示合法）。"""
        errors: list[str] = []
        if not 0 <= self.offset < self.cycle:
            errors.append(
                f"next_plan.offset 必须满足 0 <= offset < cycle（路口 {label}）"
            )
        if not 0 <= self.green_start < self.cycle:
            errors.append(
                f"next_plan.green_start 必须满足 0 <= green_start < cycle（路口 {label}）"
            )
        if not 0 <= self.green_end < self.cycle:
            errors.append(
                f"next_plan.green_end 必须满足 0 <= green_end < cycle（路口 {label}）"
            )
        return errors


class PlanSwitchIntersection(Intersection):
    """带切换后新计划的路口：旧计划字段与普通路口完全一致。"""

    model_config = ConfigDict(extra="ignore")

    next_plan: NextPlan = Field(
        ...,
        description=(
            "到达时刻 >= switch_at 时适用的新信号计划（cycle / offset / "
            "green_start / green_end）；行驶时间 travel / travel_max 沿用旧值"
        ),
    )

    def validate_against_cycle(self) -> None:
        """旧计划校验沿用父类，并追加 next_plan 的相位上界校验。"""
        errors: list[str] = []
        try:
            super().validate_against_cycle()
        except HTTPException as exc:
            detail = exc.detail
            if isinstance(detail, list):
                errors.extend(detail)
            else:
                errors.append(str(detail))
        label = self.name or f"cycle={self.cycle}"
        errors.extend(self.next_plan.validate_against_cycle(label))
        if errors:
            raise HTTPException(status_code=422, detail=errors)


class PlanSwitchRequest(GreenWaveRequest):
    """计划切换发车窗口请求：绿波请求基础上增加全局切换时刻与逐路口新计划。"""

    model_config = ConfigDict(extra="ignore")

    switch_at: int = Field(
        ...,
        description=(
            "全局计划切换时刻 S（整数秒）：车辆到达时刻严格小于 S 用旧计划，"
            "等于或大于 S 用新计划；可取任意整数（可为负或落在发车范围外）"
        ),
    )
    intersections: list[PlanSwitchIntersection] = Field(
        ..., min_length=1, max_length=MAX_INTERSECTIONS,
        description="路口列表，1..8 个，每个路口均须携带 next_plan",
    )


# ---------- 班次重排 ----------


class TimetableRescheduleRequest(GreenWaveRequest):
    """班次重排请求：绿波请求基础上增加原班次时刻、平移容限与最小发车间隔。"""

    model_config = ConfigDict(extra="ignore")

    original_departures: list[int] = Field(
        ...,
        min_length=1,
        max_length=MAX_RESCHEDULE_TRIPS,
        description=(
            "各班原计划出发时刻（整数秒），1..50 个，必须严格递增；"
            "且每个原时刻均须落在半开发车范围 [depart_from, depart_to) 内"
        ),
    )
    tolerance: int = Field(
        ..., ge=0, le=MAX_WINDOW_SECONDS,
        description="每班最大平移秒数 tol（0..3600）：新时刻须满足 |x - 原时刻| <= tol",
    )
    headway: int = Field(
        ..., ge=1, le=MAX_WINDOW_SECONDS,
        description="相邻班次最小发车间隔 h（1..3600 秒）：相邻新时刻之差须 >= h",
    )

    def validate_ranges(self) -> None:
        """复用全部绿波 422 校验，并校验原班次时刻严格递增且处于发车范围内。"""
        super().validate_ranges()
        errors: list[str] = []
        trips = self.original_departures
        for index, value in enumerate(trips):
            if not self.depart_from <= value < self.depart_to:
                errors.append(
                    f"original_departures[{index}] = {value} 必须落在发车范围 "
                    f"[{self.depart_from}, {self.depart_to}) 内"
                )
        for index in range(1, len(trips)):
            if trips[index] <= trips[index - 1]:
                errors.append(
                    "original_departures 必须按原时刻严格递增"
                    f"（第 {index - 1} 班 {trips[index - 1]} 之后第 {index} 班 "
                    f"{trips[index]} 未严格增大）"
                )
                break
        if errors:
            raise HTTPException(status_code=422, detail=errors)


class TimetableRescheduleResponse(BaseModel):
    """班次重排结果：新出发时刻、逐班平移秒数与总绝对平移秒数。"""

    departures: list[int] = Field(
        ...,
        description=(
            "各班重排后的整数出发时刻（秒），与 original_departures 一一对应、"
            "严格递增、相邻间隔 >= headway，每班均在全路口遇绿窗口内且相对原时刻"
            "平移不超过 tolerance；总绝对平移最小，同成本取字典序最早"
        ),
    )
    shifts: list[int] = Field(
        ...,
        description=(
            "逐班平移秒数 departures[j] - original_departures[j]（正=延后、"
            "负=提前、0=保持原时刻），绝对值均不超过 tolerance"
        ),
    )
    total_absolute_shift: int = Field(
        ..., ge=0, description="总绝对平移秒数 sum(abs(shift))，所有可行时刻表中的最小值"
    )


# ---------- 最早到达路径 ----------


class RouteIntersection(BaseModel):
    """路网中单个路口的信号参数（行驶时间由道路携带），全部为整数秒。"""

    model_config = ConfigDict(extra="ignore")

    name: str | None = Field(
        default=None, max_length=64, description="可选的路口名称，仅用于辨识"
    )
    cycle: int = Field(
        ..., ge=1, le=MAX_CYCLE, description="信号周期 C（秒），1..86400"
    )
    offset: int = Field(..., ge=0, description="相位偏移 o（秒），需满足 0 <= o < C")
    green_start: int = Field(
        ..., ge=0, description="绿灯起点（本地相位秒），需满足 0 <= g_start < C"
    )
    green_end: int = Field(
        ..., ge=0, description="绿灯终点（本地相位秒，不含），需满足 0 <= g_end < C"
    )

    def validate_against_cycle(self, index: int) -> list[str]:
        """校验相位与绿灯端点；返回中文错误信息列表（空列表表示合法）。"""
        errors: list[str] = []
        label = self.name or f"下标 {index}"
        if not 0 <= self.offset < self.cycle:
            errors.append(f"offset 必须满足 0 <= offset < cycle（路口 {label}）")
        if not 0 <= self.green_start < self.cycle:
            errors.append(
                f"green_start 必须满足 0 <= green_start < cycle（路口 {label}）"
            )
        if not 0 <= self.green_end < self.cycle:
            errors.append(
                f"green_end 必须满足 0 <= green_end < cycle（路口 {label}）"
            )
        return errors


class Road(BaseModel):
    """一条有向道路：from 路口驶向 to 路口，行驶 travel 秒（正整数）。"""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    from_: int = Field(
        ..., alias="from", ge=0, description="起点路口下标，须小于路口数"
    )
    to: int = Field(..., ge=0, description="终点路口下标，须小于路口数")
    travel: int = Field(
        ..., ge=1, le=MAX_CYCLE, description="行驶秒数（正整数），1..86400"
    )


class EarliestRouteRequest(BaseModel):
    """最早到达路径请求：路口信号、有向道路、起终点下标与出发秒。"""

    model_config = ConfigDict(extra="ignore")

    depart_at: int = Field(..., ge=0, description="出发时刻（整数秒，非负）")
    start: int = Field(..., ge=0, description="起点路口下标，须小于路口数")
    end: int = Field(..., ge=0, description="终点路口下标，须小于路口数")
    intersections: list[RouteIntersection] = Field(
        ..., min_length=2, max_length=MAX_ROUTE_INTERSECTIONS,
        description="路口列表，2..30 个，按下标编号（0 起）",
    )
    roads: list[Road] = Field(
        ..., max_length=MAX_ROADS,
        description="有向道路列表，0..120 条；同一 (from,to) 取最小 travel，自环不影响结果",
    )

    def validate_ranges(self) -> None:
        """跨字段校验：相位上界、起终点与道路端点下标；不合法时抛出 HTTP 422。"""
        errors: list[str] = []
        count = len(self.intersections)
        for index, item in enumerate(self.intersections):
            errors.extend(item.validate_against_cycle(index))
        if self.start >= count:
            errors.append(
                f"start 必须满足 0 <= start < 路口数（当前 {count} 个）"
            )
        if self.end >= count:
            errors.append(
                f"end 必须满足 0 <= end < 路口数（当前 {count} 个）"
            )
        for index, road in enumerate(self.roads):
            if road.from_ >= count:
                errors.append(
                    f"roads[{index}].from 必须满足 0 <= from < 路口数"
                    f"（当前 {count} 个）"
                )
            if road.to >= count:
                errors.append(
                    f"roads[{index}].to 必须满足 0 <= to < 路口数"
                    f"（当前 {count} 个）"
                )
        if errors:
            raise HTTPException(status_code=422, detail=errors)


class EarliestRouteResponse(BaseModel):
    """最早到达路径结果：最早到达秒数与路口下标路径。"""

    arrival: int = Field(
        ..., description="最早到达终点的时刻（整数秒）；起点即终点时为 depart_at"
    )
    path: list[int] = Field(
        ...,
        description=(
            "取得最早到达的路口下标路径（含起点与终点）；同到达时刻先取道路数"
            "更少者，再取路径字典序更小者"
        ),
    )


# ---------- 单路口排队预测 ----------


class ArrivalBatch(BaseModel):
    """一条到达批次：整数秒到达时刻与正整数车辆数。"""

    model_config = ConfigDict(extra="ignore")

    time: int = Field(
        ..., description="到达时刻（整数秒），须落在预测范围 [forecast_from, forecast_to) 内"
    )
    vehicles: int = Field(
        ..., ge=1, description="该批到达的车辆数（正整数）"
    )


class QueueForecastRequest(BaseModel):
    """单路口排队预测请求。"""

    model_config = ConfigDict(extra="ignore")

    forecast_from: int = Field(
        ..., ge=0, description="预测范围起点（秒，含）"
    )
    forecast_to: int = Field(
        ..., ge=1, description="预测范围终点（秒，不含）；范围长度 1..86400"
    )
    cycle: int = Field(
        ..., ge=1, le=MAX_CYCLE, description="信号周期 C（秒），1..86400"
    )
    offset: int = Field(..., ge=0, description="相位偏移 o（秒），需满足 0 <= o < C")
    green_start: int = Field(
        ..., ge=0, description="绿灯起点（本地相位秒），需满足 0 <= g_start < C"
    )
    green_end: int = Field(
        ..., ge=0, description="绿灯终点（本地相位秒，不含），需满足 0 <= g_end < C"
    )
    discharge_per_second: int = Field(
        ..., ge=1, description="每个绿灯秒最多放行的车辆数（正整数）"
    )
    initial_queue: int = Field(
        ..., ge=0, description="预测范围起点时已在排队等待的车辆数（非负整数）"
    )
    arrivals: list[ArrivalBatch] = Field(
        ..., max_length=MAX_ARRIVAL_BATCHES,
        description="到达批次列表，0..1000 条；同一秒可多批，按输入顺序入队",
    )

    def validate_ranges(self) -> None:
        """跨字段校验：范围长度、相位上界与到达时刻；不合法时抛出 HTTP 422。"""
        errors: list[str] = []
        length = self.forecast_to - self.forecast_from
        if length <= 0:
            errors.append("forecast_to 必须大于 forecast_from（半开预测范围）")
        elif length > MAX_QUEUE_FORECAST_SECONDS:
            errors.append("预测范围长度不得超过 86400 秒")
        if not 0 <= self.offset < self.cycle:
            errors.append("offset 必须满足 0 <= offset < cycle")
        if not 0 <= self.green_start < self.cycle:
            errors.append("green_start 必须满足 0 <= green_start < cycle")
        if not 0 <= self.green_end < self.cycle:
            errors.append("green_end 必须满足 0 <= green_end < cycle")
        for index, batch in enumerate(self.arrivals):
            if not self.forecast_from <= batch.time < self.forecast_to:
                errors.append(
                    f"arrivals[{index}].time = {batch.time} 必须落在预测范围 "
                    f"[{self.forecast_from}, {self.forecast_to}) 内"
                )
        if errors:
            raise HTTPException(status_code=422, detail=errors)


class QueueForecastResponse(BaseModel):
    """单路口排队预测结果：各批最后通过秒、期末待行车辆数与最大排队数。"""

    batch_pass_times: list[int | None] = Field(
        ...,
        description=(
            "各到达批次最后一辆车的通过秒（整数秒，与 arrivals 一一对应）；"
            "该批车辆在预测范围内未全部通过时为 null"
        ),
    )
    final_queue: int = Field(
        ..., ge=0, description="预测范围终点时仍在排队等待的车辆数（期末待行车辆数）"
    )
    max_queue: int = Field(
        ..., ge=0,
        description="预测范围内的最大排队车辆数（每秒到达批次入队后、放行前统计）",
    )

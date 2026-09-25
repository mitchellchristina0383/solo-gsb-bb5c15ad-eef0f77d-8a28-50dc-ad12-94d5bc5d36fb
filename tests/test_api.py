import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.main import (
    green_wave_convoy_starts,
    green_wave_earliest_route,
    green_wave_max_coverage,
    green_wave_offset_diagnostics,
    green_wave_queue_forecast,
    green_wave_slot_offsets,
    green_wave_timetable_reschedule,
    green_wave_windows,
)
from app.schemas import (
    ConvoyStartsRequest,
    EarliestRouteRequest,
    GreenWaveRequest,
    Intersection,
    OffsetDiagnosticsRequest,
    QueueForecastRequest,
    SlotOffsetsRequest,
    TimetableRescheduleRequest,
)


def make_request(payload):
    return GreenWaveRequest.model_validate(payload)


def test_api_returns_windows_payload():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 300,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 30, "travel": 0},
                {"cycle": 60, "offset": 30, "green_start": 0, "green_end": 30, "travel": 30},
            ],
        }
    )
    windows = green_wave_windows(req)
    assert [[w.start, w.end] for w in windows] == [
        [0, 30], [60, 90], [120, 150], [180, 210], [240, 270],
    ]


def test_api_empty_array_on_no_solution():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 10, "travel": 0},
                {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 30, "travel": 0},
            ],
        }
    )
    assert green_wave_windows(req) == []


def test_reject_invalid_cycle():
    with pytest.raises(ValidationError):
        Intersection(cycle=0, offset=0, green_start=0, green_end=10, travel=0)


def test_reject_negative_travel():
    with pytest.raises(ValidationError):
        Intersection(cycle=60, offset=0, green_start=0, green_end=10, travel=-1)


def test_reject_offset_outside_cycle():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "intersections": [
                {"cycle": 60, "offset": 60, "green_start": 0, "green_end": 10, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        req.validate_ranges()
    assert exc.value.status_code == 422


def test_reject_green_endpoint_outside_cycle():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 60, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        req.validate_ranges()
    assert exc.value.status_code == 422


def test_reject_range_over_one_hour():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 3601,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 10, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        req.validate_ranges()
    assert exc.value.status_code == 422


def test_reject_too_many_intersections():
    with pytest.raises(ValidationError):
        make_request(
            {
                "depart_from": 0,
                "depart_to": 60,
                "intersections": [
                    {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 10}
                    for _ in range(9)
                ],
            }
        )


def test_reject_empty_intersections():
    with pytest.raises(ValidationError):
        make_request({"depart_from": 0, "depart_to": 60, "intersections": []})


# ---------- travel_max 波动行驶时间 ----------

def test_travel_max_shrinks_windows():
    # 绿灯 [20,40)，行驶时间 [0,10]：窗口由 20 秒收缩为 10 秒
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 120,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 20,
                 "green_end": 40, "travel": 0, "travel_max": 10}
            ],
        }
    )
    windows = green_wave_windows(req)
    assert [[w.start, w.end] for w in windows] == [[20, 30], [80, 90]]


def test_travel_max_defaults_to_travel():
    base = {
        "cycle": 60, "offset": 0, "green_start": 20, "green_end": 40,
        "travel": 5,
    }
    req = make_request(
        {"depart_from": 0, "depart_to": 120, "intersections": [base]}
    )
    req2 = make_request(
        {"depart_from": 0, "depart_to": 120,
         "intersections": [{**base, "travel_max": 5}]}
    )
    assert green_wave_windows(req) == green_wave_windows(req2)


def test_reject_travel_max_less_than_travel():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 30, "travel": 20, "travel_max": 19}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        req.validate_ranges()
    assert exc.value.status_code == 422


def test_reject_travel_max_over_86400():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 30, "travel": 0, "travel_max": 86401}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        req.validate_ranges()
    assert exc.value.status_code == 422


def test_travel_max_86400_boundary_accepted():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "intersections": [
                # 整周期常绿：波动再大也不受影响
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 0, "travel": 0, "travel_max": 86400}
            ],
        }
    )
    req.validate_ranges()
    windows = green_wave_windows(req)
    assert [[w.start, w.end] for w in windows] == [[0, 60]]


# ---------- POST /api/green-wave/max-coverage ----------

def test_max_coverage_payload_overlap():
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 120,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 40, "travel": 0},
                {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 50, "travel": 0},
            ],
        }
    )
    resp = green_wave_max_coverage(req)
    assert resp.max_coverage == 2
    assert [[w.start, w.end] for w in resp.optimal_intervals] == [
        [20, 40], [80, 100],
    ]


def test_max_coverage_zero_returns_complete_range():
    req = make_request(
        {
            "depart_from": 10,
            "depart_to": 70,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 40,
                 "travel": 0, "travel_max": 30}
            ],
        }
    )
    resp = green_wave_max_coverage(req)
    assert resp.max_coverage == 0
    assert [[w.start, w.end] for w in resp.optimal_intervals] == [[10, 70]]


def test_max_coverage_reuses_request_validation():
    # 与 /windows 相同的跨字段校验：发车范围超过 3600 秒仍返回 422。
    req = make_request(
        {
            "depart_from": 0,
            "depart_to": 3601,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 10, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_max_coverage(req)
    assert exc.value.status_code == 422


def test_max_coverage_route_is_in_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/green-wave/max-coverage" in paths
    assert "post" in paths["/api/green-wave/max-coverage"]


# ---------- POST /api/green-wave/offset-diagnostics ----------

def make_diag_request(payload):
    return OffsetDiagnosticsRequest.model_validate(payload)


def test_offset_diagnostics_payload_plain_green():
    req = make_diag_request(
        {
            "cycle": 60,
            "green_start": 20,
            "green_end": 40,
            "observations": [
                {"arrival_time": 0, "observed_green": True},
                {"arrival_time": 5, "observed_green": True},
            ],
        }
    )
    resp = green_wave_offset_diagnostics(req)
    # arrival=0 观测绿 ⇔ offset∈[20,40)；arrival=5 观测绿 ⇔ offset∈[15,35)
    # 零错配集合为两者之交 [20,35)
    assert resp.min_mismatches == 0
    assert [[w.start, w.end] for w in resp.optimal_intervals] == [[20, 35]]


def test_offset_diagnostics_payload_wrapping_optimal_set():
    req = make_diag_request(
        {
            "cycle": 60,
            "green_start": 50,
            "green_end": 10,
            "observations": [{"arrival_time": 0, "observed_green": True}],
        }
    )
    resp = green_wave_offset_diagnostics(req)
    assert resp.min_mismatches == 0
    assert [[w.start, w.end] for w in resp.optimal_intervals] == [
        [0, 10], [50, 60]
    ]


def test_offset_diagnostics_min_mismatches_positive():
    # 常绿路口但观测到红灯：任何 offset 都错 1 条
    req = make_diag_request(
        {
            "cycle": 60,
            "green_start": 30,
            "green_end": 30,
            "observations": [{"arrival_time": 9, "observed_green": False}],
        }
    )
    resp = green_wave_offset_diagnostics(req)
    assert resp.min_mismatches == 1
    assert [[w.start, w.end] for w in resp.optimal_intervals] == [[0, 60]]


def test_offset_diagnostics_accepts_negative_arrival_time():
    req = make_diag_request(
        {
            "cycle": 60,
            "green_start": 20,
            "green_end": 40,
            "observations": [{"arrival_time": -1, "observed_green": True}],
        }
    )
    resp = green_wave_offset_diagnostics(req)
    assert resp.min_mismatches == 0
    assert [[w.start, w.end] for w in resp.optimal_intervals] == [[21, 41]]


def test_offset_diagnostics_rejects_zero_cycle():
    with pytest.raises(ValidationError):
        make_diag_request(
            {
                "cycle": 0,
                "green_start": 0,
                "green_end": 10,
                "observations": [{"arrival_time": 0, "observed_green": True}],
            }
        )


def test_offset_diagnostics_rejects_cycle_over_86400():
    with pytest.raises(ValidationError):
        make_diag_request(
            {
                "cycle": 86401,
                "green_start": 0,
                "green_end": 10,
                "observations": [{"arrival_time": 0, "observed_green": True}],
            }
        )


def test_offset_diagnostics_rejects_green_start_outside_cycle():
    req = make_diag_request(
        {
            "cycle": 60,
            "green_start": 60,
            "green_end": 10,
            "observations": [{"arrival_time": 0, "observed_green": True}],
        }
    )
    with pytest.raises(HTTPException) as exc:
        req.validate_ranges()
    assert exc.value.status_code == 422


def test_offset_diagnostics_rejects_negative_green_end():
    with pytest.raises(ValidationError):
        make_diag_request(
            {
                "cycle": 60,
                "green_start": 0,
                "green_end": -1,
                "observations": [{"arrival_time": 0, "observed_green": True}],
            }
        )


def test_offset_diagnostics_rejects_empty_observations():
    with pytest.raises(ValidationError):
        make_diag_request(
            {"cycle": 60, "green_start": 0, "green_end": 10, "observations": []}
        )


def test_offset_diagnostics_rejects_too_many_observations():
    with pytest.raises(ValidationError):
        make_diag_request(
            {
                "cycle": 60,
                "green_start": 0,
                "green_end": 10,
                "observations": [
                    {"arrival_time": i, "observed_green": True}
                    for i in range(2001)
                ],
            }
        )


def test_offset_diagnostics_accepts_2000_observations_boundary():
    req = make_diag_request(
        {
            "cycle": 60,
            "green_start": 0,
            "green_end": 0,  # 常绿
            "observations": [
                {"arrival_time": i, "observed_green": True}
                for i in range(2000)
            ],
        }
    )
    req.validate_ranges()
    resp = green_wave_offset_diagnostics(req)
    assert resp.min_mismatches == 0
    assert [[w.start, w.end] for w in resp.optimal_intervals] == [[0, 60]]


def test_offset_diagnostics_route_is_in_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/green-wave/offset-diagnostics" in paths
    assert "post" in paths["/api/green-wave/offset-diagnostics"]


# ---------- POST /api/green-wave/slot-offsets ----------

def make_slot_request(payload):
    return SlotOffsetsRequest.model_validate(payload)


def test_slot_offsets_plain_payload():
    req = make_slot_request(
        {
            "depart_from": 0,
            "depart_to": 10,
            "adjustable_index": 0,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 30, "travel": 0}
            ],
        }
    )
    resp = green_wave_slot_offsets(req)
    assert resp.adjustable_index == 0
    assert [[w.start, w.end] for w in resp.feasible_intervals] == [[0, 21]]
    assert resp.recommended_offset == 0


def test_slot_offsets_wrapping_payload_and_recommendation():
    req = make_slot_request(
        {
            "depart_from": 0,
            "depart_to": 5,
            "adjustable_index": 0,
            "intersections": [
                {"cycle": 60, "offset": 30, "green_start": 50,
                 "green_end": 10, "travel": 0}
            ],
        }
    )
    resp = green_wave_slot_offsets(req)
    assert [[w.start, w.end] for w in resp.feasible_intervals] == [
        [0, 6], [50, 60]
    ]
    assert resp.recommended_offset == 50


def test_slot_offsets_empty_when_fixed_intersection_cannot_cover_range():
    req = make_slot_request(
        {
            "depart_from": 0,
            "depart_to": 30,
            "adjustable_index": 0,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 0, "travel": 0},
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 10, "travel": 0},
            ],
        }
    )
    resp = green_wave_slot_offsets(req)
    assert resp.feasible_intervals == []
    assert resp.recommended_offset is None


def test_slot_offsets_slack_is_honored():
    # 绿灯 [20,50)、slack=10 收缩为 [20,40)：范围 15 秒只剩 6 个可行 offset
    req = make_slot_request(
        {
            "depart_from": 0,
            "depart_to": 15,
            "adjustable_index": 0,
            "intersections": [
                {"cycle": 60, "offset": 23, "green_start": 20,
                 "green_end": 50, "travel": 0, "travel_max": 10}
            ],
        }
    )
    resp = green_wave_slot_offsets(req)
    assert [[w.start, w.end] for w in resp.feasible_intervals] == [[20, 26]]
    assert resp.recommended_offset == 23


def test_slot_offsets_rejects_index_out_of_range():
    req = make_slot_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "adjustable_index": 1,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 30, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_slot_offsets(req)
    assert exc.value.status_code == 422


def test_slot_offsets_rejects_negative_index():
    with pytest.raises(ValidationError):
        make_slot_request(
            {
                "depart_from": 0,
                "depart_to": 60,
                "adjustable_index": -1,
                "intersections": [
                    {"cycle": 60, "offset": 0, "green_start": 0,
                     "green_end": 30, "travel": 0}
                ],
            }
        )


def test_slot_offsets_reuses_green_wave_validation():
    # 与 /windows 相同的跨字段校验：路口 offset 越界与范围过长均 422。
    req = make_slot_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "adjustable_index": 0,
            "intersections": [
                {"cycle": 60, "offset": 60, "green_start": 0,
                 "green_end": 10, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_slot_offsets(req)
    assert exc.value.status_code == 422

    req2 = make_slot_request(
        {
            "depart_from": 0,
            "depart_to": 3601,
            "adjustable_index": 0,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 10, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_slot_offsets(req2)
    assert exc.value.status_code == 422


def test_slot_offsets_route_is_in_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/green-wave/slot-offsets" in paths
    assert "post" in paths["/api/green-wave/slot-offsets"]


# ---------- POST /api/green-wave/convoy-starts ----------

def make_convoy_request(payload):
    return ConvoyStartsRequest.model_validate(payload)


def test_convoy_starts_payload():
    # 两路口绿波带，2 辆车间隔 10 秒：首车窗口由 30 秒收缩为 20 秒
    req = make_convoy_request(
        {
            "depart_from": 0,
            "depart_to": 300,
            "vehicle_count": 2,
            "headway": 10,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 30, "travel": 0},
                {"cycle": 60, "offset": 30, "green_start": 0, "green_end": 30, "travel": 30},
            ],
        }
    )
    starts = green_wave_convoy_starts(req)
    assert [[w.start, w.end] for w in starts] == [
        [0, 20], [60, 80], [120, 140], [180, 200], [240, 260],
    ]


def test_convoy_starts_empty_array_on_no_solution():
    # 3 辆车间隔 40 秒：首末车检查会误判可行，中间车必卡红灯，返回空数组
    req = make_convoy_request(
        {
            "depart_from": 0,
            "depart_to": 120,
            "vehicle_count": 3,
            "headway": 40,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 30, "travel": 0}
            ],
        }
    )
    assert green_wave_convoy_starts(req) == []


def test_convoy_rejects_vehicle_count_out_of_range():
    for count in (1, 51):
        with pytest.raises(ValidationError):
            make_convoy_request(
                {
                    "depart_from": 0,
                    "depart_to": 300,
                    "vehicle_count": count,
                    "headway": 5,
                    "intersections": [
                        {"cycle": 60, "offset": 0, "green_start": 0,
                         "green_end": 30, "travel": 0}
                    ],
                }
            )


def test_convoy_rejects_non_positive_headway():
    with pytest.raises(ValidationError):
        make_convoy_request(
            {
                "depart_from": 0,
                "depart_to": 300,
                "vehicle_count": 2,
                "headway": 0,
                "intersections": [
                    {"cycle": 60, "offset": 0, "green_start": 0,
                     "green_end": 30, "travel": 0}
                ],
            }
        )


def test_convoy_rejects_span_not_less_than_range():
    # (3-1)×10 = 20 不小于范围长度 20：首车不存在可行时刻，422
    req = make_convoy_request(
        {
            "depart_from": 0,
            "depart_to": 20,
            "vehicle_count": 3,
            "headway": 10,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 30, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_convoy_starts(req)
    assert exc.value.status_code == 422


def test_convoy_span_one_less_than_range_accepted():
    # (3-1)×9 = 18 < 20：常绿路口下首车范围为 [0, 2)
    req = make_convoy_request(
        {
            "depart_from": 0,
            "depart_to": 20,
            "vehicle_count": 3,
            "headway": 9,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0, "travel": 0}
            ],
        }
    )
    starts = green_wave_convoy_starts(req)
    assert [[w.start, w.end] for w in starts] == [[0, 2]]


def test_convoy_reuses_green_wave_validation():
    # 与 /windows 相同的跨字段校验：发车范围超过 3600 秒仍返回 422。
    req = make_convoy_request(
        {
            "depart_from": 0,
            "depart_to": 3601,
            "vehicle_count": 2,
            "headway": 5,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 10, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_convoy_starts(req)
    assert exc.value.status_code == 422


def test_convoy_route_is_in_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/api/green-wave/convoy-starts" in paths
    assert "post" in paths["/api/green-wave/convoy-starts"]


# ---------- POST /api/green-wave/timetable-reschedule ----------

def make_reschedule_request(payload):
    return TimetableRescheduleRequest.model_validate(payload)


def test_reschedule_payload_greedy_trap():
    # 贪心第一班留在 25 会让第二班无点可选；DP 整体优化为 [24,29]
    req = make_reschedule_request(
        {
            "depart_from": 0,
            "depart_to": 120,
            "original_departures": [25, 30],
            "tolerance": 5,
            "headway": 5,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 30, "travel": 0}
            ],
        }
    )
    resp = green_wave_timetable_reschedule(req)
    assert resp is not None
    assert resp.departures == [24, 29]
    assert resp.shifts == [-1, -1]
    assert resp.total_absolute_shift == 2


def test_reschedule_keeps_original_when_feasible():
    req = make_reschedule_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "original_departures": [0, 10, 20],
            "tolerance": 0,
            "headway": 5,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 30, "travel": 0}
            ],
        }
    )
    resp = green_wave_timetable_reschedule(req)
    assert resp is not None
    assert resp.departures == [0, 10, 20]
    assert resp.shifts == [0, 0, 0]
    assert resp.total_absolute_shift == 0


def test_reschedule_returns_null_when_infeasible():
    req = make_reschedule_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "original_departures": [0, 3],
            "tolerance": 0,
            "headway": 10,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 0, "travel": 0}
            ],
        }
    )
    assert green_wave_timetable_reschedule(req) is None


def test_reschedule_rejects_non_strictly_increasing_trips():
    req = make_reschedule_request(
        {
            "depart_from": 0,
            "depart_to": 60,
            "original_departures": [10, 10],
            "tolerance": 5,
            "headway": 5,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 30, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_timetable_reschedule(req)
    assert exc.value.status_code == 422


def test_reschedule_rejects_trip_outside_range():
    req = make_reschedule_request(
        {
            "depart_from": 10,
            "depart_to": 60,
            "original_departures": [5],
            "tolerance": 5,
            "headway": 5,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 30, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_timetable_reschedule(req)
    assert exc.value.status_code == 422


def test_reschedule_rejects_trip_count_out_of_range():
    base = {
        "depart_from": 0,
        "depart_to": 3000,
        "tolerance": 5,
        "headway": 5,
        "intersections": [
            {"cycle": 60, "offset": 0, "green_start": 0,
             "green_end": 0, "travel": 0}
        ],
    }
    with pytest.raises(ValidationError):
        make_reschedule_request({**base, "original_departures": []})
    with pytest.raises(ValidationError):
        make_reschedule_request(
            {**base, "original_departures": list(range(0, 255, 5))}
        )


def test_reschedule_rejects_tolerance_and_headway_ranges():
    base = {
        "depart_from": 0,
        "depart_to": 60,
        "original_departures": [10],
        "headway": 5,
        "intersections": [
            {"cycle": 60, "offset": 0, "green_start": 0,
             "green_end": 0, "travel": 0}
        ],
    }
    with pytest.raises(ValidationError):
        make_reschedule_request({**base, "tolerance": -1})
    with pytest.raises(ValidationError):
        make_reschedule_request({**base, "tolerance": 3601})
    with pytest.raises(ValidationError):
        make_reschedule_request(
            {**base, "tolerance": 5, "headway": 0}
        )
    with pytest.raises(ValidationError):
        make_reschedule_request(
            {**base, "tolerance": 5, "headway": 3601}
        )


def test_reschedule_reuses_green_wave_validation():
    # 与 /windows 相同的跨字段校验：发车范围超过 3600 秒仍返回 422。
    req = make_reschedule_request(
        {
            "depart_from": 0,
            "depart_to": 3601,
            "original_departures": [10],
            "tolerance": 5,
            "headway": 5,
            "intersections": [
                {"cycle": 60, "offset": 0, "green_start": 0,
                 "green_end": 10, "travel": 0}
            ],
        }
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_timetable_reschedule(req)
    assert exc.value.status_code == 422


def test_reschedule_route_is_in_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    path = "/api/green-wave/timetable-reschedule"
    assert path in paths
    assert "post" in paths[path]
    # 无解时响应体为 null（response_model 允许 None）
    schema = app.openapi()
    response = schema["paths"][path]["post"]["responses"]["200"]
    ref = response["content"]["application/json"]["schema"]
    assert {"type": "null"} in ref["anyOf"]
    assert any("$ref" in item for item in ref["anyOf"])


# ---------- POST /api/green-wave/earliest-route ----------

def make_route_request(payload):
    return EarliestRouteRequest.model_validate(payload)


def route_payload(**kw):
    base = {
        "depart_at": 0,
        "start": 0,
        "end": 2,
        "intersections": [
            {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 30},
            {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 50},
            {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0},
        ],
        "roads": [
            {"from": 0, "to": 1, "travel": 10},
            {"from": 1, "to": 2, "travel": 10},
            {"from": 0, "to": 2, "travel": 35},
        ],
    }
    base.update(kw)
    return base


def test_earliest_route_payload_wait_beats_direct():
    # 0→1→2 在路口 1 等 10 秒红灯仍比直达（35 秒）更快：30 秒到达
    resp = green_wave_earliest_route(make_route_request(route_payload()))
    assert resp is not None
    assert resp.arrival == 30
    assert resp.path == [0, 1, 2]


def test_earliest_route_tie_prefers_fewer_roads():
    # 直达改为 30 秒：与 0→1→2 同时到达，道路数更少者胜
    payload = route_payload(
        roads=[
            {"from": 0, "to": 1, "travel": 10},
            {"from": 1, "to": 2, "travel": 10},
            {"from": 0, "to": 2, "travel": 30},
        ]
    )
    resp = green_wave_earliest_route(make_route_request(payload))
    assert resp is not None
    assert resp.arrival == 30
    assert resp.path == [0, 2]


def test_earliest_route_unreachable_returns_null():
    payload = route_payload(roads=[{"from": 0, "to": 1, "travel": 10}])
    assert green_wave_earliest_route(make_route_request(payload)) is None


def test_earliest_route_start_equals_end():
    payload = route_payload(start=1, end=1, depart_at=7)
    resp = green_wave_earliest_route(make_route_request(payload))
    assert resp is not None
    assert resp.arrival == 7
    assert resp.path == [1]


def test_earliest_route_rejects_intersection_count_out_of_range():
    with pytest.raises(ValidationError):
        make_route_request(
            route_payload(
                intersections=[
                    {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0}
                ],
                roads=[],
                start=0,
                end=0,
            )
        )
    with pytest.raises(ValidationError):
        make_route_request(
            route_payload(
                intersections=[
                    {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0}
                    for _ in range(31)
                ]
            )
        )


def test_earliest_route_rejects_too_many_roads():
    with pytest.raises(ValidationError):
        make_route_request(
            route_payload(
                roads=[
                    {"from": 0, "to": 1, "travel": 1} for _ in range(121)
                ]
            )
        )


def test_earliest_route_rejects_bad_road_fields():
    # travel 必须为正整数
    with pytest.raises(ValidationError):
        make_route_request(
            route_payload(roads=[{"from": 0, "to": 1, "travel": 0}])
        )
    # 下标不得为负
    with pytest.raises(ValidationError):
        make_route_request(
            route_payload(roads=[{"from": -1, "to": 1, "travel": 5}])
        )
    # 出发秒不得为负
    with pytest.raises(ValidationError):
        make_route_request(route_payload(depart_at=-1))


def test_earliest_route_rejects_out_of_range_indices():
    # start / end 越界（跨字段 422）
    req = make_route_request(route_payload(start=3))
    with pytest.raises(HTTPException) as exc:
        green_wave_earliest_route(req)
    assert exc.value.status_code == 422
    req = make_route_request(route_payload(end=3))
    with pytest.raises(HTTPException) as exc:
        green_wave_earliest_route(req)
    assert exc.value.status_code == 422
    # 道路端点越界（跨字段 422）
    req = make_route_request(
        route_payload(roads=[{"from": 0, "to": 3, "travel": 5}])
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_earliest_route(req)
    assert exc.value.status_code == 422


def test_earliest_route_rejects_phase_out_of_range():
    req = make_route_request(
        route_payload(
            intersections=[
                {"cycle": 60, "offset": 60, "green_start": 0, "green_end": 30},
                {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0},
            ]
        )
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_earliest_route(req)
    assert exc.value.status_code == 422


def test_earliest_route_route_is_in_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    path = "/api/green-wave/earliest-route"
    assert path in paths
    assert "post" in paths[path]
    # 不可达时响应体为 null（response_model 允许 None）
    schema = app.openapi()
    response = schema["paths"][path]["post"]["responses"]["200"]
    ref = response["content"]["application/json"]["schema"]
    assert {"type": "null"} in ref["anyOf"]
    assert any("$ref" in item for item in ref["anyOf"])


# ---------- POST /api/green-wave/queue-forecast ----------


def make_queue_request(payload):
    return QueueForecastRequest.model_validate(payload)


def queue_payload(**kw):
    base = {
        "cycle": 10,
        "offset": 0,
        "green_start": 0,
        "green_end": 5,
        "forecast_from": 0,
        "forecast_to": 10,
        "discharge_per_second": 2,
        "initial_queue": 0,
        "arrivals": [],
    }
    base.update(kw)
    return base


def test_queue_forecast_basic_payload():
    req = make_queue_request(
        queue_payload(initial_queue=3, arrivals=[{"arrival_time": 2, "count": 2},
                                                {"arrival_time": 8, "count": 1}])
    )
    resp = green_wave_queue_forecast(req)
    # 期初 3 辆 t0/t1 放完；t2 队列已空，新到 2 辆当秒全部放行 → 2；
    # t8 到达时为红灯（绿灯 [0,5)），t9 仍红 → None，剩 1 辆。
    assert resp.pass_times == [2, None]
    assert resp.remaining_queue == 1
    assert resp.max_queue == 3


def test_queue_forecast_same_second_batches_in_input_order():
    req = make_queue_request(
        queue_payload(
            cycle=5, green_start=0, green_end=0, forecast_to=6,
            discharge_per_second=1,
            arrivals=[{"arrival_time": 0, "count": 2},
                     {"arrival_time": 0, "count": 3}],
        )
    )
    resp = green_wave_queue_forecast(req)
    assert resp.pass_times == [1, 4]
    assert resp.remaining_queue == 0
    assert resp.max_queue == 5


def test_queue_forecast_wrapping_green():
    # 本地绿灯 [8,10) ∪ [0,2)；offset=5，范围 [0,15)
    req = make_queue_request(
        queue_payload(
            cycle=10, offset=5, green_start=8, green_end=2, forecast_to=15,
            discharge_per_second=100,
            arrivals=[{"arrival_time": 9, "count": 1},
                     {"arrival_time": 11, "count": 1}],
        )
    )
    resp = green_wave_queue_forecast(req)
    assert resp.pass_times == [13, 13]
    assert resp.remaining_queue == 0
    assert resp.max_queue == 2


def test_queue_forecast_default_initial_queue_and_arrivals():
    # 常绿、范围内无车：全零结果
    req = make_queue_request(
        queue_payload(cycle=10, green_start=0, green_end=0)
    )
    resp = green_wave_queue_forecast(req)
    assert resp.pass_times == []
    assert resp.remaining_queue == 0
    assert resp.max_queue == 0


def test_queue_forecast_range_not_starting_at_zero():
    req = make_queue_request(
        queue_payload(
            forecast_from=100, forecast_to=104, green_start=0, green_end=2,
            discharge_per_second=100,
            arrivals=[{"arrival_time": 100, "count": 1},
                     {"arrival_time": 101, "count": 1},
                     {"arrival_time": 102, "count": 1},
                     {"arrival_time": 103, "count": 1}],
        )
    )
    resp = green_wave_queue_forecast(req)
    assert resp.pass_times == [100, 101, None, None]
    assert resp.remaining_queue == 2


def test_queue_forecast_rejects_arrival_before_forecast_from():
    req = make_queue_request(
        queue_payload(arrivals=[{"arrival_time": -1, "count": 1}])
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_queue_forecast(req)
    assert exc.value.status_code == 422


def test_queue_forecast_rejects_arrival_at_or_after_forecast_to():
    for bad_time in (10, 11):
        req = make_queue_request(
            queue_payload(arrivals=[{"arrival_time": bad_time, "count": 1}])
        )
        with pytest.raises(HTTPException) as exc:
            green_wave_queue_forecast(req)
        assert exc.value.status_code == 422


def test_queue_forecast_rejects_range_over_86400():
    # 长度 86401（两端均在字段级范围内）：跨字段 422
    req = make_queue_request(
        queue_payload(forecast_from=100, forecast_to=86501)
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_queue_forecast(req)
    assert exc.value.status_code == 422
    # forecast_to 超过字段上界 2×86400：字段级 422
    with pytest.raises(ValidationError):
        make_queue_request(queue_payload(forecast_to=2 * 86400 + 1))


def test_queue_forecast_accepts_86400_length_boundary():
    req = make_queue_request(
        queue_payload(
            cycle=86400, green_start=0, green_end=86400 // 2,
            forecast_from=0, forecast_to=86400,
            discharge_per_second=1,
            arrivals=[{"arrival_time": 86399, "count": 1}],
        )
    )
    resp = green_wave_queue_forecast(req)
    # t=86399 本地相位 86399 为红，未通过
    assert resp.pass_times == [None]
    assert resp.remaining_queue == 1


def test_queue_forecast_rejects_empty_or_reversed_range():
    req = make_queue_request(
        queue_payload(forecast_from=5, forecast_to=5)
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_queue_forecast(req)
    assert exc.value.status_code == 422

    req = make_queue_request(
        queue_payload(forecast_from=6, forecast_to=5)
    )
    with pytest.raises(HTTPException) as exc:
        green_wave_queue_forecast(req)
    assert exc.value.status_code == 422


def test_queue_forecast_rejects_invalid_signal_params():
    # offset 越界
    req = make_queue_request(queue_payload(offset=10))
    with pytest.raises(HTTPException) as exc:
        green_wave_queue_forecast(req)
    assert exc.value.status_code == 422
    # green_start 越界
    req = make_queue_request(queue_payload(green_start=10))
    with pytest.raises(HTTPException) as exc:
        green_wave_queue_forecast(req)
    assert exc.value.status_code == 422
    # green_end 越界
    req = make_queue_request(queue_payload(green_end=10))
    with pytest.raises(HTTPException) as exc:
        green_wave_queue_forecast(req)
    assert exc.value.status_code == 422


def test_queue_forecast_field_level_validation():
    # cycle 必须 >= 1
    with pytest.raises(ValidationError):
        make_queue_request(queue_payload(cycle=0))
    # cycle 不得超过 86400
    with pytest.raises(ValidationError):
        make_queue_request(queue_payload(cycle=86401))
    # discharge_per_second 必须为正整数
    with pytest.raises(ValidationError):
        make_queue_request(queue_payload(discharge_per_second=0))
    # initial_queue 不得为负
    with pytest.raises(ValidationError):
        make_queue_request(queue_payload(initial_queue=-1))
    # 每批车辆数必须为正整数
    with pytest.raises(ValidationError):
        make_queue_request(
            queue_payload(arrivals=[{"arrival_time": 0, "count": 0}])
        )
    # forecast_from 不得为负
    with pytest.raises(ValidationError):
        make_queue_request(queue_payload(forecast_from=-1))
    # 批次数不得超过 1000
    with pytest.raises(ValidationError):
        make_queue_request(
            queue_payload(
                arrivals=[{"arrival_time": 0, "count": 1} for _ in range(1001)]
            )
        )


def test_queue_forecast_accepts_1000_batches_boundary():
    req = make_queue_request(
        queue_payload(
            cycle=10, green_start=0, green_end=0, forecast_to=1,
            discharge_per_second=1000,
            arrivals=[{"arrival_time": 0, "count": 1} for _ in range(1000)],
        )
    )
    resp = green_wave_queue_forecast(req)
    assert resp.pass_times == [0] * 1000
    assert resp.remaining_queue == 0
    assert resp.max_queue == 1000


def test_queue_forecast_route_is_in_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    path = "/api/green-wave/queue-forecast"
    assert path in paths
    assert "post" in paths[path]

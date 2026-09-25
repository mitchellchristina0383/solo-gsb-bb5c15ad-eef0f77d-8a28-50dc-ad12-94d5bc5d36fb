# 干线绿波发车窗口 API

基于 **Python 3.11 + FastAPI** 的干线（arterial）绿波发车窗口计算服务。

提供九个接口：

1. **绿波发车窗口** `POST /api/green-wave/windows`：给定干线上至多 8 个路口各自的
   信号周期、相位偏移、周期内绿灯半开区间（允许跨周期零点）以及从起点到该路口的
   行驶秒数（可选上限 `travel_max`，表示实际行驶时间可取闭区间
   `[travel, travel_max]` 内任意实数秒），并给定一个不超过 3600 秒（一小时）的整数秒
   **半开**发车范围，服务返回在该范围内出发、**对任意可能的行驶时间**抵达**每个**路口时
   都恰好遇到绿灯的**全部极大半开发车区间**，按起点升序排列；不存在任何可行窗口时返回空数组 `[]`。
2. **最大绿波覆盖** `POST /api/green-wave/max-coverage`：请求参数与上一个接口完全相同。
   对发车范围内的每个整数出发时刻，统计**行驶时间取区间内任意实数**抵达时都能遇到绿灯的
   路口数（覆盖数），返回全局**最大路口数** `max_coverage` 以及取到该值的**全部极大半开
   发车区间**（相邻最优段已合并，按起点升序）；当最大值为 0 时仍返回**完整发车范围**
   `[depart_from, depart_to)` 作为唯一区间。
3. **单路口 offset 诊断** `POST /api/green-wave/offset-diagnostics`：给定单个路口的
   `cycle`、`green_start`、`green_end` 及 1～2000 条 `{arrival_time, observed_green}`
   观测（时间均为整数秒），对每个整数 `offset ∈ [0, cycle)` 按
   `(arrival_time + offset) mod cycle` 预测灯色，返回**最少错配条数**以及取到该值的
   **全部极大半开 offset 区间**（按起点排序；跨零点的最优集合在 `[0, cycle)` 内分段表示）。
4. **整段时隙可调 offset** `POST /api/green-wave/slot-offsets`：复用绿波窗口接口的全部
   路口参数与发车范围，另传 `adjustable_index`（从 0 起）指定**唯一**允许调整 offset 的
   路口。要求 `[depart_from, depart_to)` 内**每个整数秒**都必须能发车（其余路口保持原
   offset，各路口仍须对 `travel` 到 `travel_max` 的**任意实际行驶时间**遇绿），返回该
   可调路口的**全部可行整数** `offset ∈ [0, cycle)`（按极大半开区间输出，跨零点在
   `[0, cycle)` 内分段）以及**距原 offset 环形距离最小**的建议值（正反向等距时取较小
   offset；无可行值时为 `null`）。
5. **车队首车发车窗口** `POST /api/green-wave/convoy-starts`：复用绿波窗口接口的全部
   路口参数与发车范围，另传 `vehicle_count`（车队车辆数 `2..50`）与 `headway`
   （相邻车辆发车间隔，正整数秒），并要求 `(vehicle_count-1)×headway` **小于**发车范围
   长度。车队按固定间隔依次发车：首车时刻为 `t` 时第 `k` 辆在 `t + k×headway` 出发，
   要求**每辆车**都落在发车范围内，且每辆车在**每个**路口对 `travel` 到 `travel_max`
   的**任意实际行驶时间**均遇绿。服务基于单车可行窗口**平移、求交并合并相邻区间**
   （中间车辆同样检查，不只验首末车），返回**全部极大半开首车发车区间**，按起点升序；
   无解时返回空数组 `[]`。
6. **计划切换发车窗口** `POST /api/green-wave/plan-switch-windows`：复用绿波窗口接口的
   发车范围、路口**旧计划**信号参数与 `travel` / `travel_max` 行驶时间参数，另传全局
   整数秒切换时刻 `switch_at`，并为**每个路口**传 `next_plan`（新计划的 `cycle`、
   `offset`、`green_start`、`green_end`；行驶时间上下限沿用旧值）。车辆到达时刻
   **严格小于** `switch_at` 时按旧计划判灯，**等于或大于**时按新计划判灯；绿灯的半开
   区间、跨周期零点与常绿语义与其余接口完全一致。服务返回范围内全部极大半开发车窗口，
   其中每个整数秒出发、对各路口 `[travel, travel_max]` 内**任意实数**行驶时间，按
   实际到达时刻适用的计划均遇绿；无解返回空数组 `[]`。
7. **班次重排** `POST /api/green-wave/timetable-reschedule`：复用绿波窗口接口的路口信号、
   行驶时间波动与发车范围，另传 **1～50 个**按原时刻**严格递增**的班次
   `original_departures`、每班最大平移秒数 `tolerance`（`0..3600`）与最小发车间隔
   `headway`（`1..3600`）。为每班选择范围内的**整数出发秒**：必须处于**全路口遇绿
   窗口**（对 `travel` 到 `travel_max` 的任意实际行驶时间遇绿）、相对该班原时刻平移不
   超过 `tolerance`，且相邻班次至少间隔 `headway`。服务在所有可行时刻表中最小化
   **总绝对平移秒数**，总平移相同时取按班次顺序**字典序最早**的结果；基于遇绿窗口与
   **动态规划**求解（**不逐班贪心选最近时刻**），无可行时刻表时响应体为 `null`。
8. **最早到达路径** `POST /api/green-wave/earliest-route`：给定 **2～30 个**按下标编号的
   路口信号（`cycle`、`offset`、`green_start`、`green_end`，相位与绿灯语义与其余接口
   完全一致）、至多 **120 条**有向道路（`from`、`to`、`travel` 正整数秒）、起终点下标
   与非负出发秒 `depart_at`。车辆到达路口后可等待，**只能在该路口绿灯时驶入下一条路**；
   到达终点即完成，**不检查终点灯色**。服务返回**最早到达秒数**与**路口下标路径**；
   到达时刻相同时先取**道路数更少**者，再取**路径字典序更小**者；不可达时响应体为
   `null`。求解分 （到达时刻， 道路数） **Pareto Dijkstra**、**倒推最晚可行到达**与
   **字典序贪心重建**三个阶段，不枚举路径。
9. **单路口排队预测** `POST /api/green-wave/queue-forecast`：沿用现有周期、`offset` 与
   绿灯半开区间（跨零点、整周期常绿）语义，在长度不超过 **86400 秒**的**半开**预测范围
   `[forecast_from, forecast_to)` 内逐秒模拟单个路口的排队消散。给定每个绿灯秒的放行车数
   `discharge_per_second`（红灯秒不放行）、期初队列 `initial_queue` 与至多 **1000 条**
   到达批次（`arrival_time` 到达秒、`count` 正整数车辆数，**同一秒可给多批**、按输入顺序
   先到先走）。每秒**先**按输入顺序把到达批次入队，**再**判灯并按 FIFO 放行（放行可跨
   批次部分截断）；**最大排队数在当秒到达后、放行前统计**。队列以**批次计数**推进，
   **不逐辆展开**。返回各批**最后一辆的通过秒**（范围内未全部通过为 `null`）、**期末
   待行车辆数**与**最大排队数**；范围外到达及无效信号参数返回 422。

## 目录结构

```
.
├── app/
│   ├── __init__.py
│   ├── greenwave.py      # 纯算法：周期展开 + 区间求交，无逐秒试探
│   ├── schemas.py        # Pydantic 请求/响应模型与输入校验
│   └── main.py           # FastAPI 入口与路由
├── tests/                # pytest 测试（含随机用例的逐秒/逐 offset 对照）
├── conftest.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## 一条命令启动（Docker Compose，推荐）

需要本机已安装 Docker 与 Docker Compose 插件（Docker Desktop 自带）。在仓库根目录执行：

```bash
docker compose up --build -d
```

仅此一条命令即可完成镜像构建、依赖安装并在后台启动服务。启动后服务监听宿主机
**8000 端口**，直接访问 <http://localhost:8000/docs> 即可看到交互式文档。

查看日志：

```bash
docker compose logs -f
```

停止：

```bash
docker compose down
```

> 旧版独立命令 `docker-compose up --build -d` 同样可用。

### 无 Docker 时的本地启动

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

同样通过 <http://localhost:8000/> 访问。

## API 地址与端口

| 用途 | 地址 |
| --- | --- |
| 健康检查 | `GET http://localhost:8000/health` |
| 绿波窗口计算 | `POST http://localhost:8000/api/green-wave/windows` |
| 最大绿波覆盖 | `POST http://localhost:8000/api/green-wave/max-coverage` |
| 单路口 offset 诊断 | `POST http://localhost:8000/api/green-wave/offset-diagnostics` |
| 整段时隙可调 offset | `POST http://localhost:8000/api/green-wave/slot-offsets` |
| 车队首车发车窗口 | `POST http://localhost:8000/api/green-wave/convoy-starts` |
| 计划切换发车窗口 | `POST http://localhost:8000/api/green-wave/plan-switch-windows` |
| 班次重排 | `POST http://localhost:8000/api/green-wave/timetable-reschedule` |
| 最早到达路径 | `POST http://localhost:8000/api/green-wave/earliest-route` |
| 单路口排队预测 | `POST http://localhost:8000/api/green-wave/queue-forecast` |
| 交互式文档（Swagger UI） | `http://localhost:8000/docs` |
| OpenAPI 描述 | `http://localhost:8000/openapi.json` |

## 必要配置

所有配置均有默认值，不改任何文件即可启动：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `APP_PORT` | `8000` | **宿主机**暴露端口（容器内固定监听 8000）。8000 被占用时：`cp .env.example .env` 后改成如 `APP_PORT=8080`，再重新 `docker compose up -d` |
| `LOG_LEVEL` | `info` | uvicorn 日志级别（`critical`/`error`/`warning`/`info`/`debug`） |

## 时间与相位语义（重要约定）

所有时间量均为**整数秒**。对路口 *i*：

- `cycle`：信号周期 `C`（秒），`1 <= C <= 86400`；
- `offset`：相位偏移 `o`，`0 <= o < C`。绝对时刻 `t` 在该路口的本地相位为
  `(t + o) mod C`；
- `green_start` / `green_end`：周期内绿灯**半开区间**端点，均满足 `0 <= g < C`：
  - `green_start < green_end`：绿灯为 `[green_start, green_end)`；
  - `green_start > green_end`：绿灯**跨周期零点**，展开为
    `[green_start, C) ∪ [0, green_end)`；
  - `green_start == green_end`：整周期常绿 `[0, C)`；
- `travel`：从起点到该路口的行驶秒数**下限** `T >= 0`；
- `travel_max`（可选）：行驶秒数**上限** `T_max`，缺省等于 `travel`。实际行驶时间
  可取**闭区间** `[T, T_max]` 内的**任意实数秒**（如路况波动），窗口必须对其中每一种
  取值都保证遇绿；约束为 `0 <= T <= T_max <= 86400`。
- 发车范围为半开区间 `[depart_from, depart_to)`，长度 `1 .. 3600` 秒。

因此出发时刻 `t` 对该路口可行，当且仅当：**所有**实际行驶时间 `x ∈ [T, T_max]`
下，`(t + x + o) mod C` 都落在绿灯相位集合中。即抵达时刻覆盖闭区间
`[t+T+o, t+T_max+o]`，该闭区间必须整体落入展开（不绕零点）时间轴上的某个绿灯
**半开**区间：左端可压在绿灯起点（含），右端必须严格早于绿灯终点。令波动量
`slack = T_max - T`，等价于把每个连续绿灯段从右端收缩 `slack` 秒
（`[a,b)` → `[a, b-slack)`，slack 达到段长时该路口无解）。**跨周期零点的绿灯先视为
一条连续时段 `[green_start, C + green_end)` 再收缩**；`green_start == green_end`
的整周期常绿不受任何波动影响。

输出窗口同为半开区间 `[start, end)`：`start` 时刻可行、`end` 时刻不可行。

## 请求与响应

请求体：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `depart_from` | int | `>= 0`，发车范围起点（含） |
| `depart_to` | int | `> depart_from`，且 `depart_to - depart_from <= 3600` |
| `intersections` | array | 1..8 个路口 |
| `intersections[].name` | string? | 可选名称，仅用于辨识 |
| `intersections[].cycle` | int | `1..86400` |
| `intersections[].offset` | int | `0 <= offset < cycle` |
| `intersections[].green_start` | int | `0 <= green_start < cycle` |
| `intersections[].green_end` | int | `0 <= green_end < cycle` |
| `intersections[].travel` | int | `0 <= travel <= 86400`，行驶秒数下限 |
| `intersections[].travel_max` | int? | 可选，`travel <= travel_max <= 86400`，缺省等于 `travel`；实际行驶时间可取 `[travel, travel_max]` 内任意实数秒 |

成功响应为窗口数组（可能为空）：

```json
[ { "start": 0, "end": 30 }, { "start": 60, "end": 90 } ]
```

### 示例 1：两路口绿波带

两个周期 60 秒的路口，绿灯均为本地相位 `[0,30)`；路口 1 在起点（行驶 0 秒），
路口 2 行驶 30 秒，且下游相位偏移 `offset=30` 恰好补偿行程时间（即下游信号
比上游晚 30 秒启绿）。发车范围 `[0,300)`：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/windows \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 300,
    "intersections": [
      {"cycle": 60, "offset": 0,  "green_start": 0,  "green_end": 30, "travel": 0},
      {"cycle": 60, "offset": 30, "green_start": 0,  "green_end": 30, "travel": 30}
    ]
  }'
```

响应（每周期内前 30 秒出发可全程遇绿）：

```json
[{"start": 0, "end": 30}, {"start": 60, "end": 90},
 {"start": 120, "end": 150}, {"start": 180, "end": 210},
 {"start": 240, "end": 270}]
```

### 示例 2：绿灯跨零点

绿灯相位为 `[50,60) ∪ [0,10)`，行驶 5 秒，发车范围 `[0,125)`：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/windows \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 125,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 50, "green_end": 10, "travel": 5}
    ]
  }'
```

响应（跨零点的本地绿灯被展开后与发车范围求交）：

```json
[{"start": 0, "end": 5}, {"start": 45, "end": 65}, {"start": 105, "end": 125}]
```

### 示例 3：无解

两个路口的可行时段互不相交时返回空数组：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/windows \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 60,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0,  "green_end": 10, "travel": 0},
      {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 30, "travel": 0}
    ]
  }'
# []
```

### 示例 4：行驶时间波动（travel_max）

实际行驶时间可能在 `[travel, travel_max]` 内浮动时，窗口必须保证**最坏情况下**也遇绿。
绿灯 `[20,40)`、行驶时间可能取 `[0,10]` 任意实数秒：早到可压在第 20 秒（含），
最晚到达（t+10）必须严格早于第 40 秒，因此窗口由 20 秒收缩为 10 秒：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/windows \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 120,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 40,
       "travel": 0, "travel_max": 10}
    ]
  }'
```

响应（与固定行驶 0 秒时的 `[20,40) [80,100)` 相比，每段右端收缩 10 秒）：

```json
[{"start": 20, "end": 30}, {"start": 80, "end": 90}]
```

跨零点的绿灯先当作连续时段再收缩。绿灯为 `[50,60) ∪ [0,10)`（连续长度 20 秒）、
行驶时间 `[0,10]` 时，只有在 `[50,60)` 内出发才能保证任意行驶时长下全程遇绿
（若拆成两段分别收缩，则绕零点后的 10 秒会被错误丢弃）：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/windows \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 130,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 50, "green_end": 10,
       "travel": 0, "travel_max": 10}
    ]
  }'
# [{"start": 50, "end": 60}, {"start": 110, "end": 120}]
```

若波动量达到或超过（连续）绿灯长度（如绿灯 20 秒而 `travel_max - travel = 20`），
任何出发时刻都无法保证遇绿，该路口（进而整个请求）返回 `[]`；整周期常绿
（`green_start == green_end`）不受波动影响。省略 `travel_max` 时语义与旧版完全一致。

## 最大绿波覆盖

`POST /api/green-wave/max-coverage` 的**请求体与 `/api/green-wave/windows` 完全相同**
（同样的发车范围、路口参数与 422 校验规则），但不再要求所有路口同时可行，而是回答：
在给定发车范围内，最好的出发时刻能"稳过"几个路口？

- `max_coverage`：范围内任意整数出发时刻，**行驶时间取 `[T, T_max]` 内任意实数**
  抵达都遇绿的路口数的**全局最大值**；
- `optimal_intervals`：覆盖数恰好等于最大值的**全部极大半开**发车区间
  `[start, end)`，按起点升序。两个端点相接的最优段会被合并（如路口 A 的窗口
  `[0,30)` 与路口 B 的窗口 `[30,40)` 覆盖数同为最大值 1，则合并为 `[0,40)`）；
  中间隔着覆盖数更低的时段则分段表示。
- 当最大值为 **0**（例如唯一的路口因波动量过大而永不可行）时，仍返回**完整发车范围**
  `[{"start": depart_from, "end": depart_to}]`：范围内每个时刻的覆盖数都为 0，
  整个范围本身就是唯一的极大区间。

成功响应：

```json
{
  "max_coverage": 2,
  "optimal_intervals": [{"start": 20, "end": 40}, {"start": 80, "end": 100}]
}
```

### 示例 1：两路口部分重叠，最大值 2

两个周期 60 秒的路口绿灯分别为 `[0,40)` 与 `[20,50)`，均在起点：重叠段
`[20,40)` 内出发可同时稳过两个路口，其余时刻最多过一个。发车范围 `[0,120)`：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/max-coverage \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 120,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0,  "green_end": 40, "travel": 0},
      {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 50, "travel": 0}
    ]
  }'
```

响应（只返回覆盖数达到最大值 2 的区间，按周期重复）：

```json
{"max_coverage":2,"optimal_intervals":[{"start":20,"end":40},{"start":80,"end":100}]}
```

### 示例 2：相邻最优段合并

路口 1 可行窗口为 `[0,30)` 周期 60，路口 2 为 `[30,40)` 周期 60：覆盖数恒为 1
（同一时刻至多过一个路口），端点相接的最优段合并为 `[0,40)`；`[40,60)` 内两个
路口都不可行、覆盖数为 0，故最优区间在周期边界处断开：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/max-coverage \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 120,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0,  "green_end": 30, "travel": 0},
      {"cycle": 60, "offset": 0, "green_start": 30, "green_end": 40, "travel": 0}
    ]
  }'
# {"max_coverage":1,"optimal_intervals":[{"start":0,"end":40},{"start":60,"end":100}]}
```

### 示例 3：最大值为 0 时返回完整发车范围

唯一路口绿灯 20 秒，而行驶时间波动 `travel_max - travel = 30` 已超过绿灯长度，
任何出发时刻都无法保证任意行驶时长下遇绿。最大值为 0，仍返回完整发车范围：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/max-coverage \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 10,
    "depart_to": 130,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 40,
       "travel": 0, "travel_max": 30}
    ]
  }'
# {"max_coverage":0,"optimal_intervals":[{"start":10,"end":130}]}
```

### 最大覆盖的算法说明（复用单路口窗口 + 端点事件扫描）

1. **复用单路口可行窗口**：对每个路口直接调用与 `/windows` 相同的单路口计算
   （含跨周期绿灯先展开再收缩、常绿不收缩、半开边界裁剪），得到它在发车范围内
   的全部可行半开区间；
2. **端点差分事件扫描**：每个可行窗口 `[a,b)` 在 `a` 处记 +1、`b` 处记 -1，
   事件按位置排序后从 `depart_from` 扫到 `depart_to`，逐段维护当前覆盖路口数。
   覆盖数只可能在窗口端点处变化，故**不逐秒统计**；
3. 取各段覆盖数的全局最大值，把相邻（端点相接）且同为最大值的段合并，即得全部
   极大半开发车区间；没有任何事件时覆盖数恒为 0，直接返回完整发车范围。

## 单路口 offset 诊断

`POST /api/green-wave/offset-diagnostics` 用于根据实际车辆到达观测反推路口最合适的
信号相位偏移。给定一个路口的周期与绿灯相位，以及 1～2000 条
`{arrival_time, observed_green}` 观测（时间均为**整数秒**，`arrival_time` 可为任意
整数——含负数——按周期取模），服务对每个整数 `offset ∈ [0, cycle)` 按

```
本地相位 = (arrival_time + offset) mod cycle
```

预测该观测到达时的灯色（绿灯半开区间、跨零点、端点相等为常绿的语义与上文完全一致），
统计预测灯色与 `observed_green` 不符的观测条数，返回：

- `min_mismatches`：所有整数 offset 中**最少**的错配条数；
- `optimal_intervals`：取到最少错配数的**全部极大半开 offset 区间**
  `[start, end)`（整数 offset 满足 `start <= offset < end`），按 `start` 升序；
  跨零点的最优集合在 `[0, cycle)` 内**分段**表示（例如
  `[{"start":0,"end":10},{"start":50,"end":60}]`），不会出现跨周期的单一区间。

请求体：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `cycle` | int | `1..86400`，信号周期 C（秒） |
| `green_start` | int | `0 <= green_start < cycle`，绿灯起点（本地相位秒） |
| `green_end` | int | `0 <= green_end < cycle`，绿灯终点（本地相位秒，不含）；与 `green_start` 相等表示整周期常绿 |
| `observations` | array | **1..2000** 条观测 |
| `observations[].arrival_time` | int | 到达时刻（整数秒，任意整数，按周期取模） |
| `observations[].observed_green` | bool | 到达时实际灯色：`true`=绿，`false`=红 |

成功响应：

```json
{
  "min_mismatches": 0,
  "optimal_intervals": [{"start": 0, "end": 10}, {"start": 50, "end": 60}]
}
```

### 示例 1：跨零点最优集合分段

绿灯为 `[50,60) ∪ [0,10)`：一条 `arrival_time=0` 观测为绿灯时，offset 取
`[0,10)` 或 `[50,60)` 都零错配（最优集合在 `[0,60)` 内分两段）；另一条
`arrival_time=100`（本地相位 40）观测为红灯，在这两段内相位分别为 40..50 与
30..40（端点 40 不含），仍均预测为红、零错配：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/offset-diagnostics \
  -H "Content-Type: application/json" \
  -d '{
    "cycle": 60,
    "green_start": 50,
    "green_end": 10,
    "observations": [
      {"arrival_time": 0,   "observed_green": true},
      {"arrival_time": 100, "observed_green": false}
    ]
  }'
```

响应：

```json
{"min_mismatches":0,"optimal_intervals":[{"start":0,"end":10},{"start":50,"end":60}]}
```

### 示例 2：不可完全拟合时给出最少错配

整周期常绿（`green_start == green_end`）下任何 offset 都预测为绿；若有一条观测
实际为红灯，则每个 offset 都恰好错配 1 条，最优区间为整个周期：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/offset-diagnostics \
  -H "Content-Type: application/json" \
  -d '{
    "cycle": 60,
    "green_start": 30,
    "green_end": 30,
    "observations": [{"arrival_time": 9, "observed_green": false}]
  }'
# {"min_mismatches":1,"optimal_intervals":[{"start":0,"end":60}]}
```

### offset 诊断的算法说明（周期区间事件扫描）

错配条数是定义在周期圆 `[0, C)` 上的分段常值函数：单条观测的"预测≠观测"offset
集合至多是两条半开整数区间（观测为红时取"预测绿"集合，观测为绿时取其补集）。
算法**不逐一计算 offset × 观测**，而是：

1. 对每条观测，把绿灯集合在周期圆上平移 `-arrival_time`（绕零点断成两段），
   按观测灯色决定取正集还是补集，得到该观测的错配半开区间；
2. 在每个错配区间 `[a,b)` 的端点放置差分事件（`a` 处 +1，`b` 处 -1），共至多
   4n 个事件，按位置排序；
3. 沿 `[0, C)` 扫描事件，维护当前错配条数，逐段记录 `(段起点, 段终点, 错配数)`；
4. 取最小错配数，合并相邻且同值的段，即得全部极大半开最优区间（按起点升序）。

复杂度为 `O(n log n)`（n 为观测条数，≤ 2000），与周期 `cycle` 的大小无关；
2000 条观测、86400 秒周期的请求在毫秒级完成。

## 整段时隙可调 offset

`POST /api/green-wave/slot-offsets` 用于干线配时调整：在**其余路口相位不动**的前提下，
调整唯一一个路口的信号 offset，使给定发车范围 `[depart_from, depart_to)` 内
**每个整数秒**出发的车辆，在**每个**路口面对 `[travel, travel_max]` 内**任意实际
行驶时间**时都遇绿。请求体与 `/windows` 完全相同（同样的发车范围、1..8 个路口参数
与 422 校验规则），仅额外增加：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `adjustable_index` | int | `>= 0`，唯一允许调整 offset 的路口下标，从 0 起，须满足 `adjustable_index < 路口数` |

响应：

- `adjustable_index`：回显请求中的可调路口下标；
- `feasible_intervals`：可调路口的**全部可行整数 offset** 压缩成的极大半开区间
  `[start, end)`（`0 <= start < end <= cycle`，整数 offset 满足
  `start <= offset < end`），按起点升序；跨零点的可行集合在 `[0, cycle)` 内**分段**
  表示；无任何可行值时为 `[]`；
- `recommended_offset`：距该路口**原 offset 环形距离最小**的可行整数 offset
  （环形距离 `min(|o-o'|, C-|o-o'|)`）；正向与反向等距时取**较小**的 offset；
  无可行值时为 `null`。

成功响应示例：

```json
{
  "adjustable_index": 0,
  "feasible_intervals": [{"start": 0, "end": 6}, {"start": 50, "end": 60}],
  "recommended_offset": 50
}
```

### 示例 1：普通绿灯，可行 offset 为一段

路口周期 60 秒、绿灯本地相位 `[0,30)`、无行驶时间波动，要求 `[0,10)` 内全部 10 个
整数秒都可发车：连续 10 个本地相位点都必须落在 `[0,30)` 内，可行 offset 为
`[0, 30-10+1) = [0,21)`（offset=21 时第 9 秒出发抵达相位 30，恰为绿灯终点不含）：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/slot-offsets \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 10,
    "adjustable_index": 0,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 30, "travel": 0}
    ]
  }'
# {"adjustable_index":0,"feasible_intervals":[{"start":0,"end":21}],
#  "recommended_offset":0}
```

### 示例 2：跨零点绿灯与环形最近建议值

绿灯为 `[50,60) ∪ [0,10)`（先视为连续段，长 20 秒），范围 `[0,5)` 共 5 秒，可行
offset 弧长 `20-5+1 = 16`，自 50 起跨零点表示为 `[50,60) ∪ [0,6)`。原 offset 为
30 时，正向最近可行值 50（环距 20）比反向最近值 5（环距 25）更近，建议 50：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/slot-offsets \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 5,
    "adjustable_index": 0,
    "intersections": [
      {"cycle": 60, "offset": 30, "green_start": 50, "green_end": 10, "travel": 0}
    ]
  }'
# {"adjustable_index":0,
#  "feasible_intervals":[{"start":0,"end":6},{"start":50,"end":60}],
#  "recommended_offset":50}
```

### 示例 3：行驶时间波动先收缩绿灯弧

绿灯 `[20,50)` 长 30 秒，实际行驶时间可能取 `[0,10]` 任意实数秒：跨零点语义与
`/windows` 一致——绿灯先按连续段右端收缩 10 秒为 `[20,40)`（长 20），范围 15 秒时
可行 offset 弧长仅 `20-15+1 = 6`：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/slot-offsets \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 15,
    "adjustable_index": 0,
    "intersections": [
      {"cycle": 60, "offset": 23, "green_start": 20, "green_end": 50,
       "travel": 0, "travel_max": 10}
    ]
  }'
# {"adjustable_index":0,"feasible_intervals":[{"start":20,"end":26}],
#  "recommended_offset":23}
```

### 示例 4：其他路口无法覆盖整段 ⇒ 可行集为空

可调路口虽为整周期常绿，但固定路口绿灯仅 `[0,10)`，不可能覆盖整个 `[0,30)` 发车
范围；无论怎样调整路口 0 都无济于事，返回空集与 `null`：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/slot-offsets \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 30,
    "adjustable_index": 0,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0, "travel": 0},
      {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 10, "travel": 0}
    ]
  }'
# {"adjustable_index":0,"feasible_intervals":[],"recommended_offset":null}
```

同理，当发车范围秒数 `n >= cycle` 而可调路口并非整周期常绿（连续一整圈相位必有
红灯），或波动收缩后的连续绿灯长度 `L < n` 时，可行集也为空；整周期常绿
（`green_start == green_end`）不受波动与范围长度影响，任何 offset 均可行。

### 整段时隙的算法说明（连续弧旋转，不逐 offset 试探）

1. **固定路口整段校验**：对每个保持原 offset 的路口直接复用单路口可行窗口计算
   （与 `/windows` 相同的周期展开、跨零点连续化、波动收缩与裁剪）。各区间之间
   任何正长度间隙都会漏掉至少一个整数秒，故覆盖范围内**每个整数秒**当且仅当
   合并结果恰为 `[depart_from, depart_to)`；任一固定路口不满足即返回空集。
2. **可调路口收缩绿灯弧**：令 `slack = travel_max - travel`，复用
   :func:`eroded_green_components`——跨零点绿灯先视为连续段
   `[green_start, C + green_end)` 再右端收缩，常绿直接占满整圆。设收缩后的连续
   绿灯弧为 `[e0, e0+L)`（半开长度 L，常绿时 `L = C`）。
3. **整段时隙收缩**：令 `shift = (travel + offset) mod C`，范围内 n 个整数出发
   时刻的本地相位恰为圆上 n 个连续点 `[lo+shift, hi+shift) mod C`
   （`hi - lo = n`）。它们整体落入弧 E 当且仅当 `L >= n`，且可行 shift 是长
   `M = L - n + 1` 的连续闭整数弧（半开表示 `[r0, r0+M) mod C`，
   `r0 = (e0 - lo) mod C`）；再整体旋转 `-travel` 即得可行 offset 弧，跨零点在
   `[0, C)` 内分两段。`L >= C`（常绿）时每个 offset 都可行；`L < n`（含
   `n >= C` 而非常绿）时为空。
4. **建议值**：原 offset 自身可行时直接返回；否则只比较环形正向最近点与环形反向
   最近点，等距取较小者。

全程仅做常数次区间运算（固定路口的窗口数同 `/windows`），与周期大小、范围长度无关；
测试含 3000 组随机参数下与逐 offset × 逐秒暴力实现的逐项对照（可行区间与建议值）。

## 车队首车发车窗口

`POST /api/green-wave/convoy-starts` 用于编队（convoy）出行：一个车队的全部车辆以
**固定间隔**依次发车，求首车可以在哪些时刻出发，才能让**每辆车**都在发车范围内、
且在**每个**路口对 `[travel, travel_max]` 内**任意实际行驶时间**都遇绿。请求体与
`/windows` 完全相同（同样的发车范围、1..8 个路口参数与 422 校验规则），仅额外增加：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `vehicle_count` | int | `2..50`，车队车辆数 n |
| `headway` | int | `>= 1`，相邻车辆发车间隔 h（秒，正整数） |
| （跨字段） | | `(vehicle_count-1)×headway` 必须**小于**发车范围长度，否则 422 |

首车时刻为 `t` 时，第 `k` 辆车（`k = 0..n-1`）在 `t + k×headway` 出发。首车时刻
可行，当且仅当：**每辆车的出发时刻都在 `[depart_from, depart_to)` 内**（等价于
`t ∈ [depart_from, depart_to - (n-1)×headway)`），且每辆车在每个路口都满足与
`/windows` 完全一致的单车可行条件（跨周期绿灯先连续化再收缩、常绿不收缩、半开
边界等语义全部沿用）。

响应为**全部极大半开首车发车区间** `[start, end)`（按起点升序），与 `/windows`
同为窗口数组；无解时返回空数组 `[]`：

```json
[{"start": 0, "end": 20}, {"start": 60, "end": 80}]
```

### 示例 1：两路口绿波带上的 2 辆编队

沿用 `/windows` 示例 1 的两个路口（周期 60 秒、绿灯 `[0,30)`、下游 offset 恰好
补偿 30 秒行程），2 辆车间隔 10 秒发车：首车 `t` 与第二辆车 `t+10` 必须同落某个
`[60q, 60q+30)`，故每周期 30 秒的单车窗口收缩为 20 秒：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/convoy-starts \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 300,
    "vehicle_count": 2,
    "headway": 10,
    "intersections": [
      {"cycle": 60, "offset": 0,  "green_start": 0, "green_end": 30, "travel": 0},
      {"cycle": 60, "offset": 30, "green_start": 0, "green_end": 30, "travel": 30}
    ]
  }'
```

响应：

```json
[{"start":0,"end":20},{"start":60,"end":80},{"start":120,"end":140},
 {"start":180,"end":200},{"start":240,"end":260}]
```

### 示例 2：中间车辆被红灯卡住（不能只检查首末车）

绿灯 `[0,30)`、3 辆车间隔 40 秒：首车 `t ∈ [0,10)` 时首车（`t`）与末车
（`t+80`，相位 20..30 内）都遇绿，但第 2 辆车在 `t+40 ∈ [40,50)` 必遇红灯——
只验首末车会误判可行，正确结果是无解：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/convoy-starts \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 120,
    "vehicle_count": 3,
    "headway": 40,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 30, "travel": 0}
    ]
  }'
# []
```

### 车队窗口的算法说明（单车窗口平移求交，不逐秒试探）

1. **复用单车可行窗口**：对每个路口先计算与 `/windows` 完全相同的单车可行窗口
   （跨周期绿灯先连续化再收缩、常绿不收缩、半开边界裁剪）；
2. **按车间隔平移求交**：第 `k` 辆车在 `t + k×h` 出发，等价于首车时刻 `t` 落在
   单车窗口整体**左移 `k×h`** 后的集合中。逐路口把 `k = 0..n-1` 的 n 份平移窗口
   **全部**求交——中间车辆同样检查，只验首末车会漏掉恰好卡住中间车辆的绿灯间隙
   （见示例 2）——再跨路口求交；
3. **裁剪首车范围并合并**：把结果裁剪进首车范围
   `[depart_from, depart_to - (n-1)×headway)`，合并相邻（端点相接）区间，即得全部
   极大半开首车发车区间。全程只做区间平移与求交，不逐秒试探。

## 计划切换发车窗口

`POST /api/green-wave/plan-switch-windows` 用于信号配时在某一时刻整体切换的场景：
每个路口除**旧计划**（请求中原有的 `cycle` / `offset` / `green_start` / `green_end`）
外，另携带一份**新计划** `next_plan`；另由顶层字段 `switch_at` 给出全局整数秒切换
时刻 `S`。车辆到达时刻**严格小于 `S`** 时按旧计划判灯，**等于或大于 `S`** 时按新
计划判灯。行驶时间参数（`travel` / `travel_max`）、半开绿灯区间、跨周期零点
（先视为连续段再收缩）、整周期常绿等语义与 `/windows` **完全一致**。

请求体在 `/windows` 基础上增加：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `switch_at` | int | 全局计划切换时刻 S（整数秒，**可为负或落在发车范围外**）：到达 `< S` 用旧计划，`>= S` 用新计划 |
| `intersections[].next_plan` | object | **必填**，路口切换后的新信号计划 |
| `intersections[].next_plan.cycle` | int | 新计划周期 `C'`，`1..86400`（可与旧周期不同） |
| `intersections[].next_plan.offset` | int | 新计划相位偏移，`0 <= offset < cycle` |
| `intersections[].next_plan.green_start` | int | 新计划绿灯起点，`0 <= green_start < cycle` |
| `intersections[].next_plan.green_end` | int | 新计划绿灯终点（不含），`0 <= green_end < cycle`；与 `green_start` 相等表示整周期常绿 |

`next_plan` **不含**行驶时间：`travel` 与 `travel_max` 描述车辆行为，新旧计划共用。
响应与 `/windows` 相同，为窗口数组（可能为空）：

```json
[{"start": 39, "end": 59}, {"start": 99, "end": 110}]
```

### 切换点落在抵达波动区间内（关键语义）

整数出发时刻 `t` 的实际到达覆盖闭区间 `[t+T, t+T_max]`（行驶时间为 `[T,T_max]`
内任意**实数**）。该区间与切换时刻 `S` 有三种位置关系：

1. **整段在切换前**（`t + T_max < S`）：直接按旧计划判灯，等价于旧计划的收缩窗口；
2. **整段在切换后**（`t + T >= S`）：直接按新计划判灯，等价于新计划的收缩窗口；
3. **切换点落在波动区间内**（`t + T < S <= t + T_max`）：到达被切成两段，
   **两侧必须分别检查，不能只按最早抵达或最晚抵达选择一侧的计划**：
   - 旧计划侧为半开抵达段 `[t+T, S)`（`S` 不含，实际到达可任意逼近 `S`，故该段右端
     允许压在旧绿灯分量的终点上）；
   - 新计划侧为闭抵达段 `[S, t+T_max]`（两端都真实可达，右端必须**严格早于**新绿灯
     分量终点）；
   - 两段必须各自**整体**落入相应计划展开时间轴上的**同一条**连续绿灯分量。

### 示例 1：波动区间跨过切换点，两侧都绿才可行

周期 60 秒、绿灯 `[0,30)`，行驶时间 `[0,10]`，`switch_at=100`。旧计划 `offset=21`
（S 的旧本地相位为 1，S 前紧邻时刻在旧绿灯内），新计划 `offset=30`（S 的新本地相位
为 10，在新绿灯内）。发车范围 `[0,200)`：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/plan-switch-windows \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 200,
    "switch_at": 100,
    "intersections": [
      {"cycle": 60, "offset": 21, "green_start": 0, "green_end": 30,
       "travel": 0, "travel_max": 10,
       "next_plan": {"cycle": 60, "offset": 30, "green_start": 0, "green_end": 30}}
    ]
  }'
```

响应：

```json
[{"start":39,"end":59},{"start":99,"end":110},{"start":150,"end":170}]
```

其中 `[99,110)` 由三部分端点相接合并：`t=99` 属混合段（旧侧半开段、新侧闭段均绿），
`t=100..109` 整段抵达都在切换后；`t=90..98` 虽最早到达（`t`）在旧绿灯内，但最晚
到达跨到 S 之后而 S 紧邻前方的旧计划侧不满足，故不可行——只按最早抵达选旧计划会
误判。

### 示例 2：只改一侧计划不够，混合段被掐掉

将旧计划改为 `offset=20`，则 S 的旧本地相位恰为 `0`（绿灯**起点**，其紧邻前方是
红灯）：混合段内任何出发都无法让半开段 `[t+T, S)` 整体落入旧绿灯；尽管新计划在 S
为绿，`t∈[90,100)` 仍全部不可行：

```json
[{"start":40,"end":60},{"start":100,"end":110},{"start":160,"end":170}]
```

### 示例 3：切换点落在发车范围外

`switch_at` 远早于（或为负）所有可能到达时刻时，结果等价于仅用 `next_plan` 调用
`/windows`；远晚于所有可能到达时刻时，等价于仅用旧计划。新旧计划周期可以不同
（如新计划把周期从 60 秒改成 90 秒），两侧各自按自身周期与 offset 判定。

### 计划切换的算法说明（三段区间运算，不逐秒试探）

1. **整段旧 / 整段新**：分别对旧、新计划复用
   :func:`departure_windows_for_intersection`（跨零点绿灯先连续化、波动右端收缩、
   常绿不收缩），再按 `t <= S - T_max - 1` 与 `t >= S - T` 裁剪；
2. **混合段的两侧分量判定**：令 rho 为 S 沿绿灯方向距该计划（跨零点先连续化后的）
   绿灯分量起点的秒数、L 为该分量长度：
   - 旧侧半开段可行当且仅当常绿或 `1 <= rho <= L`（`rho=0` 时 S 恰为绿灯起点、紧邻
     前方为红灯；`rho=L` 时 S 恰为分量右端不含，半开段仍可整体落入），给出整数出发
     下界 `t >= S - T - rho`；
   - 新侧闭段可行当且仅当常绿或 `0 <= rho < L`（`rho=L` 时 S 恰为绿灯终点不含），
     给出整数出发上界 `t <= S + L - rho - 1 - T_max`；
   - 与混合整数段 `[S - T_max, S - T)` 取交至多形成一条半开区间；
3. 三段结果裁剪进发车范围、合并相邻区间后，跨路口两两求交，即得全部极大半开发车
   窗口。全程只做区间运算，不逐秒试探；无任何可行整数秒时返回空数组。

## 班次重排

`POST /api/green-wave/timetable-reschedule` 用于已有班次时刻表的小幅调整：在不改变
路口信号配时的前提下，把 1～50 个班次各自**平移**到一个整数出发秒，使每一班都能全程
遇绿，同时尽量贴近原计划时刻。路口信号、`travel` / `travel_max` 行驶时间波动与发车
范围参数与 `/windows` 完全相同（同样的跨零点连续化、波动右端收缩、常绿不收缩、半开
边界语义），另增加：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `original_departures` | int[] | **1..50** 个整数秒，按原时刻**严格递增**，且每个都须落在半开发车范围 `[depart_from, depart_to)` 内 |
| `tolerance` | int | 每班最大平移秒数，`0..3600`；新时刻 `x` 须满足 `|x - 原时刻| <= tolerance` |
| `headway` | int | 相邻班次最小发车间隔，`1..3600`；重排后相邻出发时刻之差须 `>= headway` |

为第 `j` 班选择整数出发秒 `x_j` 时必须同时满足：

1. `depart_from <= x_j < depart_to`，且 `x_j` 处于**全路口遇绿窗口**（对
   `[travel, travel_max]` 内**任意实数**行驶时间抵达每个路口都遇绿）；
2. `|x_j - original_departures[j]| <= tolerance`；
3. `x_j - x_{j-1} >= headway`（因输入严格递增且 `headway >= 1`，结果必然严格递增）。

在全部可行时刻表中最小化总绝对平移

```
cost = Σ_j |x_j - original_departures[j]|
```

总平移相同时取**按班次顺序字典序最早**的时刻表（第一班最早；第一班相同再比第二班，
依此类推）。无任何可行时刻表时响应体为 JSON `null`；成功时返回：

```json
{
  "departures": [24, 29],
  "shifts": [-1, -1],
  "total_absolute_shift": 2
}
```

- `departures`：各班重排后的整数出发时刻，与 `original_departures` 一一对应；
- `shifts`：逐班平移秒数 `departures[j] - original_departures[j]`（正数延后、负数
  提前、`0` 保持原时刻）；
- `total_absolute_shift`：总绝对平移秒数 `Σ|shift|`，即所有可行时刻表中的最小值。

### 示例 1：逐班贪心会失败，整体 DP 才能求解

绿灯 `[0,30)` 周期 60、无行驶波动，发车范围 `[0,120)`；两班原时刻 25、30，每班容限
5 秒、最小间隔 5 秒。**逐班贪心**（第一班选离 25 最近的可行点，即留在 25）会让第二
班在 `[30,35]` 内没有任何遇绿点（30 是绿灯终点不含，下一窗口要到 60），从而误判无
解；动态规划整体权衡后把两班各提前 1 秒，得到 `[24,29]`，总平移 2 秒：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/timetable-reschedule \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 120,
    "original_departures": [25, 30],
    "tolerance": 5,
    "headway": 5,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 30, "travel": 0}
    ]
  }'
```

响应：

```json
{"departures":[24,29],"shifts":[-1,-1],"total_absolute_shift":2}
```

### 示例 2：全部保持原时刻

原时刻本身都在遇绿窗口内、相邻间隔也达标时，最优成本为 0，各班保持不变：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/timetable-reschedule \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 300,
    "original_departures": [0, 60, 120],
    "tolerance": 30,
    "headway": 30,
    "intersections": [
      {"cycle": 60, "offset": 0,  "green_start": 0, "green_end": 30, "travel": 0},
      {"cycle": 60, "offset": 30, "green_start": 0, "green_end": 30, "travel": 30}
    ]
  }'
# {"departures":[0,60,120],"shifts":[0,0,0],"total_absolute_shift":0}
```

### 示例 3：字典序 tie-break

常绿路口（`green_start == green_end`）、发车范围 `[0,60)`，原时刻 10、12，容限 10、
最小间隔 10。可行最优成本为 8：`[2,12]`（平移 8+0）与 `[10,20]`（0+8）等总成本，
按班次顺序字典序最早取 `[2,12]`：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/timetable-reschedule \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 60,
    "original_departures": [10, 12],
    "tolerance": 10,
    "headway": 10,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0, "travel": 0}
    ]
  }'
# {"departures":[2,12],"shifts":[-8,0],"total_absolute_shift":8}
```

### 示例 4：无可行时刻表返回 null

容限为 0 而原时刻相邻间隔小于 `headway` 时没有任何调整空间，响应体即 JSON `null`
（HTTP 状态码仍为 200）：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/timetable-reschedule \
  -H "Content-Type: application/json" \
  -d '{
    "depart_from": 0,
    "depart_to": 60,
    "original_departures": [0, 3],
    "tolerance": 0,
    "headway": 10,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0, "green_end": 0, "travel": 0}
    ]
  }'
# null
```

### 班次重排的算法说明（遇绿窗口 + 动态规划，不逐班贪心）

1. **逐秒可行性展开**：对全部路口复用第 1、2 步的单车可行窗口（跨零点先连续化、波动
   右端收缩、常绿不收缩），把合并后的极大半开窗口 `[a,b)` 展开成发车范围上的逐秒
   布尔标记——整数秒 `t` 可行当且仅当落在某条窗口内；
2. **逐班候选秒**：第 `j` 班的候选集合为遇绿秒 ∩ 容限窗
   `[o_j-tolerance, o_j+tolerance]` ∩ 发车范围，按升序排列，至多 3600 个；任一班无
   候选即无解；
3. **正向动态规划**：令 `f_j(t)` 为第 `j` 班在 `t` 出发时前 `j+1` 班的最小总平移，

   ```
   f_j(t) = |t - o_j| + min{ f_{j-1}(s) : s <= t - headway }
   ```

   候选秒升序扫描，用单调游标维护允许集合内 `f_{j-1}` 的最小值，每次转移 O(1)。
   最后一班的最小 `f` 即最优总成本 `C*`；不存在有限值则返回 `null`；
4. **字典序最早解的重建**：对称地做后缀 DP
   `b_j(t) = |t-o_j| + min{ b_{j+1}(s) : s >= t+headway }`（候选降序扫描，同样 O(1)
   转移）。随后自第一班起逐班在满足间隔与遇绿/容限的候选中取**最小**的 `t`，使
   "已确定前缀成本 + `b_j(t)`"恰好等于 `C*`。这在最优解集合内逐位取最小，得到的就是
   字典序最早的全局最优时刻表。

复杂度约为 `O(班次数 × 每班候选数)`，50 班、3600 秒范围、容限 3600 的最坏规模下候选
上限约 18 万次 O(1) 转移，亚秒级完成；**不逐班贪心选最近时刻**（贪心会把后续班次挤出
遇绿窗口或顶破 headway，见示例 1），也不枚举时刻表组合。

## 最早到达路径（路网等灯）

`POST /api/green-wave/earliest-route` 把问题从单条干线推广到**路网**：车辆从起点路口
出发，沿有向道路行驶，途中经过的每个路口都要**等绿灯才能驶入下一条路**，求到达终点
路口的最早时刻与路径。路口信号的相位约定（`(t+offset) mod cycle`、绿灯半开区间、
跨周期零点、`green_start == green_end` 为整周期常绿）与其余接口**完全一致**；行驶
时间由道路携带（固定正整数秒，无波动）。

请求体：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `depart_at` | int | `>= 0`，在起点路口的出发时刻（整数秒） |
| `start` | int | `0 <= start < 路口数`，起点路口下标 |
| `end` | int | `0 <= end < 路口数`，终点路口下标（可与 `start` 相同） |
| `intersections` | array | **2..30** 个路口，按下标编号（0 起） |
| `intersections[].name` | string? | 可选名称，仅用于辨识 |
| `intersections[].cycle` | int | `1..86400` |
| `intersections[].offset` | int | `0 <= offset < cycle` |
| `intersections[].green_start` | int | `0 <= green_start < cycle` |
| `intersections[].green_end` | int | `0 <= green_end < cycle`；与 `green_start` 相等表示整周期常绿 |
| `roads` | array | **0..120** 条有向道路 |
| `roads[].from` | int | `0 <= from < 路口数`，起点路口下标 |
| `roads[].to` | int | `0 <= to < 路口数`，终点路口下标 |
| `roads[].travel` | int | `1..86400`，行驶秒数（正整数） |

语义要点：

- 车辆在 `depart_at` 时刻位于起点路口，**须等起点路口绿灯**才能驶入第一条道路；
  每到达一个中间路口，同样可等待、仅绿灯时驶入下一条路；**到达终点即完成，不检查
  终点灯色**（`start == end` 时直接以 `depart_at` 完成，路径为 `[start]`）。
- 同一 `(from, to)` 的并行道路只相当于最小 `travel` 那条（更慢者不可能更优）；
  自环只增加时间与道路数，不会出现在最优路径中。
- 目标为字典序最小的三元组 **(到达时刻, 道路数, 路口下标路径)**：先比最早到达，
  再比道路数更少，最后比路径字典序更小。

成功响应（不可达时响应体为 JSON `null`，HTTP 状态码仍为 200）：

```json
{ "arrival": 30, "path": [0, 1, 2] }
```

### 示例 1：等一次红灯反而比直达更快

三个路口：路口 0 绿灯 `[0,30)`、路口 1 绿灯 `[20,50)`（周期均 60 秒）、路口 2 常绿。
道路 `0→1`、`1→2` 各行驶 10 秒，直达 `0→2` 行驶 35 秒。0 秒出发：在路口 0 立即遇绿，
10 秒到路口 1 遇红灯等到 20 秒，30 秒到终点——比直达的 35 秒更快：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/earliest-route \
  -H "Content-Type: application/json" \
  -d '{
    "depart_at": 0,
    "start": 0,
    "end": 2,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0,  "green_end": 30},
      {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 50},
      {"cycle": 60, "offset": 0, "green_start": 0,  "green_end": 0}
    ],
    "roads": [
      {"from": 0, "to": 1, "travel": 10},
      {"from": 1, "to": 2, "travel": 10},
      {"from": 0, "to": 2, "travel": 35}
    ]
  }'
```

响应：

```json
{"arrival":30,"path":[0,1,2]}
```

### 示例 2：同时到达时道路数更少者胜

把直达道路改为 30 秒：直达 `0→2`（1 条道路）与 `0→1→2`（2 条道路）都在 30 秒到达，
道路数更少者胜：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/earliest-route \
  -H "Content-Type: application/json" \
  -d '{
    "depart_at": 0,
    "start": 0,
    "end": 2,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0,  "green_end": 30},
      {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 50},
      {"cycle": 60, "offset": 0, "green_start": 0,  "green_end": 0}
    ],
    "roads": [
      {"from": 0, "to": 1, "travel": 10},
      {"from": 1, "to": 2, "travel": 10},
      {"from": 0, "to": 2, "travel": 30}
    ]
  }'
# {"arrival":30,"path":[0,2]}
```

### 示例 3：不可达返回 null

没有任何道路通向终点时，响应体为 JSON `null`（HTTP 状态码仍为 200）：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/earliest-route \
  -H "Content-Type: application/json" \
  -d '{
    "depart_at": 0,
    "start": 0,
    "end": 2,
    "intersections": [
      {"cycle": 60, "offset": 0, "green_start": 0,  "green_end": 30},
      {"cycle": 60, "offset": 0, "green_start": 20, "green_end": 50},
      {"cycle": 60, "offset": 0, "green_start": 0,  "green_end": 0}
    ],
    "roads": [{"from": 0, "to": 1, "travel": 10}]
  }'
# null
```

### 最早到达路径的算法说明（三阶段，不枚举路径）

1. **(到达时刻, 道路数) Pareto Dijkstra**：等待免费且行驶时间为正整数，标号沿道路
   严格增大，按 `(t, e)` 字典序弹出即定型。每个路口只保留**不被支配**的标号
   （t 递增则 e 严格递减，至多"路口数"个）：标号 `(t,e)` 被 `(t',e')` 支配
   （`t'<=t` 且 `e'<=e`）时，前者的任何延续都被后者不劣地复现（等灯时刻函数单调
   不减）。终点第一次弹出即最优 `(T*, E*)`。只保留单一路径标号不正确：较晚到达但
   道路数更少的标号，可能在下一路口的红灯等待中**追平**较早标号，再以更少的道路数
   胜出；
2. **倒推最晚可行到达 `H(u, k)`**：`H(终点, 0) = T*`；`H(u, k)` 为"经恰好 k 条道路、
   恰在 `T*` 到达终点"时到达 `u` 的最晚时刻。沿道路 `(u,v,w)` 倒推：到达 `v` 不晚于
   `H(v,k-1)` 要求驶离 `u` 不晚于 `H(v,k-1)-w`，即到达 `u` 不晚于
   `latest_green_departure(u, H(v,k-1)-w)`（跨零点绿灯由取模正确回退）；按 k 递增
   递推，每条道路每个阶段只算一次；
3. **字典序最小路径贪心重建**：自 `(start, depart_at)` 起，每步在"到达下一路口不晚于
   其 H 值"的道路中取**下标最小**者。不变式 `t <= H(u, k)` 保证每步必有可行道路、
   不会走入死路；`E*` 步后恰在 `T*` 到达终点，所得即 `(T*, E*)` 路径中字典序最小者。

复杂度约为 `O(路口数² × 道路数)`（每路口至多"路口数"个 Pareto 标号，倒推 DP 每个
阶段全部道路各扫描一次、阶段数不超过路口数），30 路口、120 条道路的最坏规模也
在毫秒级完成；测试含 3000 组随机参数下与枚举全部简单路径的暴力参考实现的逐项对照。

## 单路口排队预测

`POST /api/green-wave/queue-forecast` 在给定信号计划下预测单个路口在一段时间内的排队
消散过程，信号语义与其余接口**完全一致**：本地相位 `(t + offset) mod cycle`、绿灯为
半开区间（`green_start < green_end` 一段、`green_start > green_end` 跨零点两段、
`green_start == green_end` 整周期常绿，绿灯起点含、终点不含）。

预测范围为半开整数秒区间 `[forecast_from, forecast_to)`，长度 **1..86400 秒**（一日）。
每个模拟秒严格按以下顺序推进：

1. **到达入队**：先按请求中 `arrivals` 的**输入顺序**把该秒的全部到达批次追加到队尾
   （同一秒可给多个批次，同秒批次保留先后次序；不同秒之间按时间先后，天然 FIFO）；
2. **统计最大排队**：在当秒到达**之后、放行之前**统计队列总车数，更新 `max_queue`
   （期初队列在首秒放行前即计入，故 `initial_queue > 0` 时 `max_queue` 至少为它）；
3. **判灯放行**：该秒为绿灯时按队列**先到先走**（FIFO）放行至多
   `discharge_per_second` 辆（正整数，每个绿灯秒相同）；**红灯秒一辆不放行**。放行可在
   批次中间截断（一批 10 辆、每秒放 3 辆时，前 3 辆与接下来 3 辆分别在两个绿灯秒通过，
   该批结果只记录**最后一辆**的通过秒）。

期初队列 `initial_queue`（非负整数，缺省 0）先于任何到达批次接受放行，但它不对应请求
中的任何批次，故不出现在逐批结果里；`arrivals` 可为空数组（或缺省），至多 **1000 条**。

请求体：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `cycle` | int | `1..86400`，信号周期 C（秒） |
| `offset` | int | `0 <= offset < cycle`，相位偏移 |
| `green_start` | int | `0 <= green_start < cycle`，绿灯起点（本地相位秒） |
| `green_end` | int | `0 <= green_end < cycle`，绿灯终点（本地相位秒，不含）；与 `green_start` 相等表示整周期常绿 |
| `forecast_from` | int | `>= 0`，半开预测范围起点（秒，含） |
| `forecast_to` | int | `> forecast_from`，且 `forecast_to - forecast_from <= 86400`（半开终点，不含） |
| `discharge_per_second` | int | `>= 1`，每个绿灯秒放行的车辆数；红灯秒不放行 |
| `initial_queue` | int | `>= 0`，缺省 `0`：期初已在排队的车辆数 |
| `arrivals` | array | **0..1000** 条到达批次，可缺省为空 |
| `arrivals[].arrival_time` | int | 到达秒，必须满足 `forecast_from <= arrival_time < forecast_to`，否则 422 |
| `arrivals[].count` | int | `>= 1`，该批车辆数（正整数）；同一秒可给多条批次 |

响应：

- `pass_times`：与请求 `arrivals` **一一对应**、等长的数组，元素为各批**最后一辆**
  通过停止线的整数秒；该批在预测范围结束前未全部放行（包括恰好在 `forecast_to` 秒才
  放完的情形——该秒不在半开范围内）时为 `null`；
- `remaining_queue`：**期末待行车辆数**，即最后一个模拟秒（`forecast_to - 1`）放行
  结束后队列中的车辆总数（含只放行了一部分的批次）；
- `max_queue`：范围内**最大排队车辆数**，在每秒"到达后、放行前"统计。

```json
{
  "pass_times": [2, null],
  "remaining_queue": 1,
  "max_queue": 3
}
```

### 示例 1：红灯积压、跨批次部分放行

周期 10 秒、绿灯为本地相位 `[0,5)`、每个绿灯秒放 2 辆，预测范围 `[0,10)`，期初已有
3 辆车排队，另在第 2 秒到达一批 2 辆、第 8 秒到达一批 1 辆：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/queue-forecast \
  -H "Content-Type: application/json" \
  -d '{
    "cycle": 10,
    "offset": 0,
    "green_start": 0,
    "green_end": 5,
    "forecast_from": 0,
    "forecast_to": 10,
    "discharge_per_second": 2,
    "initial_queue": 3,
    "arrivals": [
      {"arrival_time": 2, "count": 2},
      {"arrival_time": 8, "count": 1}
    ]
  }'
```

期初 3 辆在第 0、1 秒放完（t0 放 2、t1 放 1）；第 2 秒队列已空，新到的 2 辆当秒全部
放行，故第 0 批最后一辆通过秒为 **2**；第 8 秒本地相位为 8（红灯），第 9 秒仍红，
第 1 批一辆未放，通过秒为 `null`、期末剩 1 辆。最大排队出现在首秒放行前期初的 3 辆：

```json
{"pass_times":[2,null],"remaining_queue":1,"max_queue":3}
```

### 示例 2：同秒多批按输入顺序先到先走

整周期常绿（`green_start == green_end`）、每秒放 1 辆，第 0 秒同秒内先后到达两批
（2 辆、3 辆）：严格按输入顺序放行，第 0 批最后一辆在第 1 秒通过、第 1 批最后一辆
在第 4 秒通过，最大排队为到达后、放行前的 5 辆：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/queue-forecast \
  -H "Content-Type: application/json" \
  -d '{
    "cycle": 5,
    "offset": 0,
    "green_start": 0,
    "green_end": 0,
    "forecast_from": 0,
    "forecast_to": 6,
    "discharge_per_second": 1,
    "arrivals": [
      {"arrival_time": 0, "count": 2},
      {"arrival_time": 0, "count": 3}
    ]
  }'
# {"pass_times":[1,4],"remaining_queue":0,"max_queue":5}
```

### 示例 3：跨零点绿灯，积压到下一段绿灯一次清空

绿灯本地相位为 `[8,10) ∪ [0,2)`、`offset=5`（故绝对绿灯秒为 `t mod 10 ∈ {3,4,5,6}`），
每秒可放 100 辆。两批车分别在第 9、11 秒到达时都遇红灯，共积压 2 辆（峰值 2）；
下一段绿灯始于第 13 秒，两批在同一秒按 FIFO 一次清空，最后一辆通过秒均为 13：

```bash
curl -s -X POST http://localhost:8000/api/green-wave/queue-forecast \
  -H "Content-Type: application/json" \
  -d '{
    "cycle": 10,
    "offset": 5,
    "green_start": 8,
    "green_end": 2,
    "forecast_from": 0,
    "forecast_to": 15,
    "discharge_per_second": 100,
    "arrivals": [
      {"arrival_time": 9, "count": 1},
      {"arrival_time": 11, "count": 1}
    ]
  }'
# {"pass_times":[13,13],"remaining_queue":0,"max_queue":2}
```

### 排队预测的算法说明（批次计数，不逐辆展开）

队列以**批次为节点**的双端队列推进：每个节点记录该批的**剩余车数**与其批次下标
（期初队列用一个特殊节点表示，不产生输出）。每秒先把该秒到达的批次整体追加到队尾，
随后绿灯秒从队首节点按车数扣减 `discharge_per_second`：

- 放行能力不小于队首批剩余车数时整批弹出，记录该批最后一辆在**当秒**通过，剩余能力
  继续消费下一批（一个绿灯秒可清空多批）；
- 否则只扣减队首批的剩余车数，该批尚未完成、不写通过秒。

队列总车数用一个随入队 / 放行增减的计数器维护，最大排队 O(1) 更新。全程入队与放行
都按**批次计数**，单批 10⁹ 辆与 1 辆的运算量相同；主循环至多 86400 个模拟秒、队列
节点至多 `1001` 个（1000 批 + 期初节点），最坏规模亚秒级完成。测试含 600 组随机
参数（普通绿灯、跨零点、常绿、随机 offset、随机期初队列与同秒多批）下与**逐秒逐辆**
FIFO 暴力模拟的逐项对照（逐批通过秒、期末待行数与最大排队数），并覆盖红灯不放行、
跨批次部分放行、到达后放行前统计峰值、半开范围末端边界、范围不始于 0、周期 1 秒、
86400 秒范围 + 1000 批性能等场景。

## 输入校验与错误

无效周期、相位偏移、绿灯端点、行驶时间（含 `travel_max < travel` 或
`travel_max > 86400`），或路口数、发车范围长度越界时返回
`422 Unprocessable Entity`，响应体含中文原因，例如：

```json
{ "detail": ["travel_max 不得小于 travel（路口 中山路）"] }
```

字段类型错误、缺失字段也由 Pydantic 统一返回 422。

`/api/green-wave/offset-diagnostics` 同样在以下情况返回 422：

- `cycle` 不在 `1..86400`；
- `green_start` / `green_end` 不满足 `0 <= g < cycle`（端点相等表示常绿，合法）；
- `observations` 数量不在 `1..2000`；
- 字段缺失或类型错误（如 `observed_green` 不是布尔值）。

`/api/green-wave/slot-offsets` 沿用绿波窗口接口的**全部** 422 校验（路口参数、
发车范围长度等），并额外要求 `adjustable_index >= 0` 且
`adjustable_index < 路口数`，否则返回 422：

```json
{ "detail": ["adjustable_index 必须满足 0 <= adjustable_index < 路口数"] }
```

例如绿灯终点越界：

```json
{ "detail": ["green_end 必须满足 0 <= green_end < cycle"] }
```

`/api/green-wave/convoy-starts` 同样沿用绿波窗口接口的**全部** 422 校验，并额外
要求 `vehicle_count ∈ [2, 50]`、`headway >= 1`（字段级 422），以及
`(vehicle_count-1)×headway` **小于**发车范围长度（否则首车不存在任何可行时刻）：

```json
{ "detail": ["(vehicle_count - 1) × headway 必须小于发车范围长度"] }
```

`/api/green-wave/plan-switch-windows` 沿用绿波窗口接口的**全部** 422 校验（旧计划
路口参数、`travel_max` 上下界、发车范围长度、路口数等），并对每个路口的 `next_plan`
做同规则校验：`cycle ∈ [1, 86400]`（字段级 422），且
`0 <= offset / green_start / green_end < cycle`（跨字段 422，错误信息带路口名称）；
`next_plan` 缺失也由 Pydantic 返回 422。`switch_at` 为任意整数（可为负或落在发车
范围外，不构成错误）：

```json
{ "detail": ["next_plan.offset 必须满足 0 <= offset < cycle（路口 cycle=60）"] }
```

`/api/green-wave/timetable-reschedule` 沿用绿波窗口接口的**全部** 422 校验（路口
参数、`travel_max` 上下界、发车范围长度、路口数等），并额外要求：

- `original_departures` 数量在 **1..50**（字段级 422）；
- 每个原时刻都落在半开发车范围 `[depart_from, depart_to)` 内（跨字段 422，错误信息带
  下标与时刻）；
- 原时刻必须**严格递增**（跨字段 422，错误信息带下标）；
- `tolerance ∈ [0, 3600]`、`headway ∈ [1, 3600]`（字段级 422）。

注意：`headway` 或 `tolerance` 导致**不存在可行时刻表**属于业务结果而非请求错误，
HTTP 状态码为 200、响应体为 `null`（不会返回 422）。例如：

```json
{ "detail": ["original_departures 必须按原时刻严格递增（第 0 班 10 之后第 1 班 10 未严格增大）"] }
```

```json
{ "detail": ["original_departures[0] = 5 必须落在发车范围 [10, 60) 内"] }
```

`/api/green-wave/earliest-route` 的 422 校验：

- `intersections` 数量在 **2..30**、`roads` 数量不超过 **120**（字段级 422）；
- 每个路口的 `cycle ∈ [1, 86400]`（字段级 422），且
  `0 <= offset / green_start / green_end < cycle`（跨字段 422，错误信息带路口下标）；
- `depart_at >= 0`、`start >= 0`、`end >= 0`、`roads[].from >= 0`、`roads[].to >= 0`
  （字段级 422）；
- `start`、`end` 与每条道路的 `from` / `to` 必须**小于路口数**（跨字段 422）；
- `roads[].travel ∈ [1, 86400]`（正整数秒，字段级 422）。

注意：终点**不可达**属于业务结果而非请求错误，HTTP 状态码为 200、响应体为 `null`
（不会返回 422）。例如：

```json
{ "detail": ["roads[0].to 必须满足 0 <= to < 路口数（当前 3 个）"] }
```

`/api/green-wave/queue-forecast` 的 422 校验：

- `cycle ∈ [1, 86400]`、`discharge_per_second >= 1`、`initial_queue >= 0`、
  `forecast_from >= 0`、每批 `count >= 1`（字段级 422）；
- `0 <= offset / green_start / green_end < cycle`（跨字段 422；端点相等表示常绿，
  合法）；
- 预测范围必须满足 `forecast_to > forecast_from` 且长度
  `forecast_to - forecast_from <= 86400`（跨字段 422）；
- 每条 `arrivals[].arrival_time` 都必须落在半开预测范围
  `[forecast_from, forecast_to)` **之内**，早于 `forecast_from`（含负数）或等于 /
  晚于 `forecast_to` 均返回 422（错误信息带批次下标与时刻）；
- `arrivals` 数量不超过 **1000**（字段级 422），允许为空数组或省略。

```json
{ "detail": ["arrivals[0].arrival_time = 10 必须落在预测范围 [0, 10) 内"] }
```

```json
{ "detail": ["offset 必须满足 0 <= offset < cycle"] }
```

注意：批次在范围内**未全部放行**（排队溢出到 `forecast_to` 之后）属于业务结果而非
请求错误，HTTP 状态码为 200，对应 `pass_times` 元素为 `null`、车辆计入
`remaining_queue`（不会返回 422）。

## 算法说明（区间运算，不逐秒试探）

1. **周期内展开与波动收缩**：每个路口的绿灯半开区间先展开为连续分量
   （`g_start > g_end` 跨零点时视为**一条**连续段 `[g_start, C + g_end)`，
   不拆两段；`g_start == g_end` 时为整周期常绿）。当行驶时间可能取
   `[T, T_max]` 时，令 `slack = T_max - T`，每条连续绿灯段右端收缩为
   `[a, b-slack)`（抵达闭区间须整体落在绿灯半开区间内）；常绿不收缩。
2. **映射到出发时间轴**：行驶时间下限与相位偏移合并为 `shift = (T + o) mod C`，
   收缩后的本地绿灯 `[a,b)` 对应出发时间轴上周期重复的
   `[kC + a - shift, kC + b - shift)`。只枚举与发车范围有非空交的周期 `k`
   （由整除直接算出 `k_min / k_max`），裁剪进 `[depart_from, depart_to)`，
   并合并重叠或端点相接（`[a,b)` 与 `[b,c)`）的区间。
3. **多路口求交**：各路口的有序区间列表用双指针两两求交，得到交集的全部连通段；
   交集为空立即返回。最终结果天然是全部**极大**区间，按起点升序输出。

复杂度约为 `O(路口数 × (范围长度 / 最小周期))` 次区间运算；对一小时范围、
周期最小 1 秒的极端情形，每路口也仅约 3600 个区间。

`/api/green-wave/max-coverage` 复用第 1、2 步得到的各路口可行窗口，再在窗口端点
放置差分事件做一次扫描（至多 `8 × 2 × 3600` 个事件），复杂度与窗口接口同阶。

`/api/green-wave/convoy-starts` 同样复用第 1、2 步的单车可行窗口：第 `k` 辆车
（`k = 0..n-1`）在首车之后 `k×headway` 秒出发，等价于把单车窗口整体左移 `k×headway`
后求交；逐路口完成 n 份平移窗口的求交后再跨路口求交，最后裁剪进首车范围并合并
相邻区间，复杂度约为 `O(路口数 × 车辆数 × 每路口窗口数)` 次区间运算。

`/api/green-wave/plan-switch-windows` 的整段旧 / 整段新两部分直接复用第 1、2 步
（各按旧、新计划自身的周期与 offset）；切换点落在波动区间内的混合整数段至多一条，
按切换时刻 S 在各自计划绿灯分量上的位置 rho 直接算出两侧的整数出发上下界（旧侧
下界、新侧上界，半开 / 闭端端点语义不同），三段合并后跨路口求交，复杂度与窗口
接口同阶。

`/api/green-wave/timetable-reschedule` 先复用第 1、2 步把全路口遇绿窗口展开成逐秒
标记，再对各班候选秒做动态规划：正向 `f_j(t) = |t-o_j| + min f_{j-1}(s)`
（`s <= t-headway`，游标维护前缀最小值，O(1) 转移）求最优总成本；对称的后缀 DP
配合自前向后逐位取最小候选秒重建字典序最早的最优时刻表。复杂度
`O(班次数 × 每班候选数)`（上限 50 × 3600 次 O(1) 转移），不逐班贪心、不枚举时刻表
组合。

`/api/green-wave/queue-forecast` 与上述区间接口不同，模拟本身以整数秒为最小粒度
（范围至多 86400 秒），但队列只以**批次为节点**（节点记录剩余车数与批次下标），
入队整批追加、绿灯秒从队首按车数扣减（整批弹出或部分扣减），队列总车数与峰值
O(1) 维护——**不逐辆展开**，单批 10⁹ 辆与 1 辆运算量相同。复杂度
`O(范围秒数 + 批次数)`，86400 秒、1000 批的最坏规模亚秒级完成。

## 运行测试

```bash
pip install pytest
pytest -q
```

测试包含边界场景（跨零点、偏移、范围边界、半开端点不含、无解、行驶时间波动
`travel_max`）以及 400 组随机参数下与逐秒判定参考实现的逐项对照；最大覆盖另有
400 组随机参数下与逐秒统计覆盖数参考实现的对照（含相邻最优段合并与最大值为 0
时返回完整范围）；offset 诊断
另有 2000+ 组随机参数下与逐 offset 暴力实现的对照、跨零点分段、常绿灯、
负到达时刻、周期 1 秒及 2000 条观测的性能用例；整段时隙可调 offset
另有 3000 组随机参数下与逐 offset × 逐秒暴力实现的对照（可行区间与环形最近
建议值），并覆盖跨零点分段、常绿、波动收缩后弧长不足、范围不短于周期、
固定路口无法覆盖整段及等距建议取较小 offset 等边界；车队首车发车窗口
另有 3000 组随机参数下与逐首车时刻 × 逐车暴力参考实现的逐项对照，并覆盖
中间车辆被绿灯间隙卡住（不能只验首末车）、跨零点绿灯、行驶时间波动、
首车范围裁剪与半开边界、常绿及无解等场景；计划切换发车窗口
另有多组随机种子共 18000 组随机参数（新旧计划周期、offset、绿灯相位各自
独立随机）下与逐整数出发秒 × 逐侧抵达段暴力参考实现的逐项对照，并专门
覆盖切换点落在抵达波动区间内时两侧必须同时满足（不能只按最早或最晚抵达
选择计划）、切换点恰为绿灯起点 / 终点的半开端点语义、`slack=0` 单点到达、
新旧计划周期不同、`switch_at` 为负或落在发车范围外及 `next_plan` 的 422
校验等场景；班次重排
另有 3000 组随机参数下与逐班枚举候选秒的动态规划暴力参考实现（直接最小化
`(总成本, 时刻表元组)`）的逐项对照，并覆盖逐班贪心选最近点导致误判无解的
陷阱用例、同成本字典序 tie-break（单班与多班联动）、容限 0、headway 顶破
原时刻、半开绿灯 / 范围右端边界、跨零点绿灯、行驶时间波动收缩候选、50 班
上界性能、无解返回 `null` 及 422 校验等场景；单路口排队预测
另有 600 组随机参数（普通 / 跨零点 / 常绿绿灯、随机 offset、期初队列与同秒多批）
下与逐秒逐辆 FIFO 暴力模拟的逐项对照（逐批通过秒、期末待行数、最大排队数），
并覆盖红灯不放行、跨批次部分放行、峰值在到达后放行前统计、半开范围末端、
范围不始于 0、周期 1 秒、86400 秒 + 1000 批性能及范围外到达 / 无效信号参数的
422 校验等场景。

# 包装板材折叠打孔模板展开 API

基于 Python + FastAPI 的 HTTP 服务：客户端提交整数网格矩形板材、依次执行的上下/左右对折方向，以及最终折叠面上的打孔点；服务端**逆序展开**折叠序列，通过**镜像传播**孔位，自动**拒绝当前折叠轴长度为奇数**的折叠步骤，并将展开后**重合的坐标合并**（各自传播路径完整保留）。

返回内容：展开后的唯一孔位、每个孔位的覆盖层数，以及每个孔位的来源路径（来自哪个打孔点、命中最终折叠栈的哪一层、每一步折叠走了哪一侧）。

打孔点支持可选 **`depth` 限深**：取值 `1..2^折叠次数`，表示只打穿最终折叠栈（自上而下编号）最上面的 `depth` 层；省略时保持原有行为，贯穿全部层。

另提供**反向打孔规划**接口：提交期望在展开板材上出现的目标孔位，服务端沿折叠过程将目标归并到最终折叠面的等价位置，复算校验镜像轨道完整后，返回最小且唯一的打孔点列表。

## 快速开始

只需一条命令（依赖随容器构建自动安装）：

```bash
docker compose up --build
```

启动后访问：

- API 交互文档（Swagger UI）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health
- 业务接口：`POST http://localhost:8000/api/v1/unfold`（正向展开）、`POST http://localhost:8000/api/v1/punch-plan`（反向打孔规划）

停止服务：`docker compose down`。

## 配置

通过环境变量配置（可在 `compose.yaml` 的 `environment` 中修改）：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MAX_FOLDS` | `20` | 单次请求允许的最大折叠步数 |
| `MAX_PUNCHES` | `200` | 单次请求允许的最大打孔点数（对 `/punch-plan` 而言指归并后的打孔点数） |
| `MAX_TOTAL_HOLES` | `200000` | 展开后孔位总数（打孔点数 × 2^折叠步数）上限 |

端口映射在 `compose.yaml` 中为 `"8000:8000"`，如需修改对外端口，调整冒号左侧即可。

## API 说明

### `POST /api/v1/unfold`

**请求体**

```json
{
  "board": { "width": 8, "height": 4 },
  "folds": ["left", "down"],
  "punches": [{ "x": 1, "y": 0 }]
}
```

| 字段 | 说明 |
| --- | --- |
| `board` | 原始板材的整数网格尺寸，`width`/`height` 为正整数 |
| `folds` | 按执行顺序给出的对折方向：`up` / `down` / `left` / `right`，可为空数组 |
| `punches` | 最终折叠面上的打孔点，使用折叠面**局部坐标**（左上角为 `(0,0)`），至少 1 个 |
| `punches[].depth` | 可选，限深打孔：只打穿最终折叠栈自上而下最上面的 `depth` 层，合法取值 `1..2^折叠次数`（无折叠时仅为 `1`）；省略表示贯穿全部层 |

**层序与限深语义**

- 每一步折叠先把**被移动半区翻面**（其内部层序整体反转），再叠到**固定半区之上**。
- 最终折叠栈自上而下编号 `1..2^折叠次数`；每个孔位路径中的 `layer` 即该分支命中的最终层号。
- 带 `depth` 时，孔位只传播到前 `depth` 层对应的原板坐标；省略 `depth`（或取满 `2^折叠次数`）时传播到全部层。
- 多个打孔点（含重复点或不同 `depth`）命中同一原板坐标时，该坐标的 `layers` 累计、`paths` 保留全部来源路径。

**坐标与折叠语义约定**

- 板材为整数网格，单元格坐标 `(x, y)`，`x` 向右、`y` 向下，左上角 `(0, 0)`。
- 折叠方向表示"被移动的一半朝该方向折"：`left` = 右半向左折；`right` = 左半向右折；`up` = 下半向上折；`down` = 上半向下折。
- 每次对折要求当前对应边长为**偶数**（左右折看当前宽度，上下折看当前高度），否则该步骤被拒绝并返回 400。
- 响应中的孔位坐标为**原始板材坐标系**。

**响应示例**（上面请求的返回，节选）

```json
{
  "final_face": { "x": 0, "y": 2, "width": 4, "height": 2 },
  "stack_layers": 4,
  "total_holes": 4,
  "unique_holes": 4,
  "holes": [
    {
      "x": 1,
      "y": 1,
      "layers": 1,
      "paths": [
        {
          "punch": 0,
          "punch_point": { "x": 1, "y": 0 },
          "layer": 1,
          "steps": [
            { "fold": 0, "direction": "left", "branch": "stay" },
            { "fold": 1, "direction": "down", "branch": "mirror" }
          ]
        }
      ]
    }
  ]
}
```

| 响应字段 | 说明 |
| --- | --- |
| `final_face` | 最终折叠面在原始板材坐标系中的位置与尺寸 |
| `stack_layers` | 折叠后每处的纸层数 = 2^折叠步数 |
| `total_holes` / `unique_holes` | 展开孔位总数（按路径计）/ 去重后的唯一孔位数 |
| `holes[].layers` | 覆盖该坐标的传播路径数（重合次数，含限深累计） |
| `holes[].paths[]` | 来源路径：`punch` 为请求中打孔点下标；`layer` 为该分支命中的最终层号（自上而下从 1 开始）；`steps` 按折叠原始顺序记录每一步的分支，`stay` = 未移动的一层，`mirror` = 被折过来的一层；请求中显式给出的 `depth` 会在 `punch_point` 中原样回显，省略时不输出 |

**限深打孔示例**

请求把同一个打孔点的深度限制为 2（`8x4` 板材，`left` 后 `down`），最终只展开最上面两层：

```json
{
  "board": { "width": 8, "height": 4 },
  "folds": ["left", "down"],
  "punches": [{ "x": 1, "y": 0, "depth": 2 }]
}
```

响应（节选）：层 1 落在原板 `(1, 1)`（`left` 折时留在固定半区、`down` 折时随被移动半区翻面到最上），层 2 落在 `(6, 1)`，其余两层不再展开。

```json
{
  "stack_layers": 4,
  "total_holes": 2,
  "unique_holes": 2,
  "holes": [
    {
      "x": 1, "y": 1, "layers": 1,
      "paths": [{ "punch": 0, "punch_point": { "x": 1, "y": 0, "depth": 2 }, "layer": 1,
        "steps": [{ "fold": 0, "direction": "left", "branch": "stay" },
                  { "fold": 1, "direction": "down", "branch": "mirror" }] }]
    },
    {
      "x": 6, "y": 1, "layers": 1,
      "paths": [{ "punch": 0, "punch_point": { "x": 1, "y": 0, "depth": 2 }, "layer": 2,
        "steps": [{ "fold": 0, "direction": "left", "branch": "mirror" },
                  { "fold": 1, "direction": "down", "branch": "mirror" }] }]
    }
  ]
}
```

同一点分别以 `depth: 1` 和不带 `depth` 各打一次时，层 1 坐标的 `layers` 为 2、`paths` 保留两条来源（层号均为 1），其余坐标各保留贯穿打孔产生的一条路径。

**curl 示例**

```bash
curl -X POST http://localhost:8000/api/v1/unfold \
  -H "Content-Type: application/json" \
  -d '{
    "board": {"width": 8, "height": 4},
    "folds": ["left", "down"],
    "punches": [{"x": 1, "y": 0}]
  }'
```

**错误响应**

- `400 odd_fold_axis`：某一步折叠时当前轴长为奇数，`detail` 中带 `step` / `direction` / `axis` / `axis_length`。
- `400 punch_out_of_bounds`：打孔点超出最终折叠面范围。
- `400 limit_exceeded`：超出 `MAX_FOLDS` / `MAX_PUNCHES` / `MAX_TOTAL_HOLES` 限制。
- `422`：请求体不符合 schema（如非法方向、负坐标、空打孔列表，或 `depth` 不是 1..2^折叠次数之间的整数）。

```json
{
  "detail": {
    "error": "odd_fold_axis",
    "message": "第 0 步折叠（'left'）要求当前宽度为偶数，实际为 3。",
    "step": 0,
    "direction": "left",
    "axis": "width",
    "axis_length": 3
  }
}
```

### `POST /api/v1/punch-plan`

反向打孔规划：提交期望在**展开板材**上出现的目标孔位，服务端沿折叠过程把每个目标孔位归并到最终折叠面的等价位置（相同位置构成一个等价组），再用现有展开逻辑复算校验，返回**最小且唯一**的打孔点列表（可直接作为 `/api/v1/unfold` 的 `punches` 使用）。

- 目标孔位自动**去重**，响应中 `punches` 按 `(x, y)` 稳定排序。
- 仅当每个等价组都形成**完整镜像轨道**（复算结果与目标集合完全一致）时才返回 200。
- 目标缺少对称孔或含越界坐标时返回 400，并列出首个不完整等价组的缺失/多余坐标，**不会默默补孔**。

**请求体**

```json
{
  "board": { "width": 8, "height": 4 },
  "folds": ["left", "down"],
  "targets": [
    { "x": 1, "y": 1 },
    { "x": 1, "y": 2 },
    { "x": 6, "y": 1 },
    { "x": 6, "y": 2 }
  ]
}
```

| 字段 | 说明 |
| --- | --- |
| `board` / `folds` | 同 `/api/v1/unfold` |
| `targets` | 期望在展开板材上出现的目标孔位，使用**原始板材坐标**，至少 1 个，自动去重 |

**响应示例**（上面请求的返回）

```json
{
  "board": { "width": 8, "height": 4 },
  "folds": ["left", "down"],
  "final_face": { "x": 0, "y": 2, "width": 4, "height": 2 },
  "stack_layers": 4,
  "target_count": 4,
  "punch_count": 1,
  "punches": [{ "x": 1, "y": 0 }]
}
```

| 响应字段 | 说明 |
| --- | --- |
| `final_face` / `stack_layers` | 同 `/api/v1/unfold` |
| `target_count` | 去重后的目标孔位数 |
| `punch_count` | 最小打孔点数（等价组数） |
| `punches` | 最终折叠面上的打孔点（局部坐标），按 `(x, y)` 稳定排序 |

**curl 示例**

```bash
curl -X POST http://localhost:8000/api/v1/punch-plan \
  -H "Content-Type: application/json" \
  -d '{
    "board": {"width": 8, "height": 4},
    "folds": ["left", "down"],
    "targets": [{"x": 1, "y": 1}, {"x": 1, "y": 2}, {"x": 6, "y": 1}, {"x": 6, "y": 2}]
  }'
```

**错误响应**

- `400 target_out_of_bounds`：目标含越界坐标，`detail.out_of_bounds` 按 `(x, y)` 排序列出全部越界点。
- `400 incomplete_equivalence_group`：目标缺少对称孔，`detail.group` 为首个不完整等价组（折叠面局部坐标，按 `(x, y)` 顺序取第一个），`detail.missing` / `detail.extra` 分别为该组缺失 / 多余的坐标（原始板材坐标）。
- `400 odd_fold_axis` / `400 limit_exceeded`：同 `/api/v1/unfold`。
- `422`：请求体不符合 schema（如空目标列表、负坐标）。

```json
{
  "detail": {
    "error": "incomplete_equivalence_group",
    "message": "等价组 (1, 0) 的镜像轨道不完整：缺失 3 个、多余 0 个坐标；请补全或移除后重试，服务端不会自动补孔。",
    "group": { "x": 1, "y": 0 },
    "missing": [{ "x": 1, "y": 2 }, { "x": 6, "y": 1 }, { "x": 6, "y": 2 }],
    "extra": []
  }
}
```

## 本地开发（不用 Docker）

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest                                   # 运行测试
uvicorn app.main:app --reload --port 8000
```

## 项目结构

```
app/
  main.py       # FastAPI 入口与路由
  models.py     # Pydantic 请求/响应模型
  folding.py    # 核心折叠/展开与反向打孔规划逻辑（纯 Python，可独立测试）
tests/
  test_api.py      # HTTP 接口测试
  test_folding.py  # 核心逻辑测试
Dockerfile
compose.yaml
requirements.txt        # 运行时依赖
requirements-dev.txt    # 开发/测试依赖
```

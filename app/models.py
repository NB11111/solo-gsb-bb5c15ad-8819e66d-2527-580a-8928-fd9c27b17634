"""请求 / 响应的 Pydantic 模型。"""
from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class FoldDirection(str, Enum):
    up = "up"
    down = "down"
    left = "left"
    right = "right"


class Board(BaseModel):
    """原始矩形板材的整数网格尺寸。"""

    width: int = Field(..., gt=0, le=1_000_000, examples=[8])
    height: int = Field(..., gt=0, le=1_000_000, examples=[4])


class PunchPoint(BaseModel):
    """最终折叠面上的打孔点，(0, 0) 为折叠面左上角。"""

    x: int = Field(..., ge=0, examples=[1])
    y: int = Field(..., ge=0, examples=[0])
    depth: Optional[int] = Field(
        default=None,
        ge=1,
        description=(
            "限深打孔：只打穿最终层序（自上而下编号）中最上面的 depth 层，"
            "合法取值 1..2^折叠次数；省略表示贯穿全部层。"
        ),
    )


class UnfoldRequest(BaseModel):
    board: Board
    folds: List[FoldDirection] = Field(
        default_factory=list,
        max_length=64,
        description="按执行顺序给出的折叠方向序列",
    )
    punches: List[PunchPoint] = Field(
        ...,
        min_length=1,
        max_length=1024,
        description="最终折叠面上的打孔点（局部坐标），可选 depth 限深",
    )

    @model_validator(mode="after")
    def _validate_punch_depths(self) -> "UnfoldRequest":
        max_depth = 1 << len(self.folds)
        for idx, punch in enumerate(self.punches):
            if punch.depth is not None and punch.depth > max_depth:
                raise ValueError(
                    f"punches[{idx}].depth={punch.depth} 超过 2^折叠次数={max_depth}，"
                    f"合法取值为 1..{max_depth}，省略表示贯穿全部层。"
                )
        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "board": {"width": 8, "height": 4},
                    "folds": ["left", "down"],
                    "punches": [{"x": 1, "y": 0}],
                }
            ]
        }
    }


class PathStep(BaseModel):
    """一次折叠中该孔位所在层的分支选择（按折叠原始顺序排列）。"""

    fold: int = Field(..., description="对应请求中 folds 的下标")
    direction: FoldDirection
    branch: Literal["stay", "mirror"] = Field(
        ..., description="stay=未移动的一层；mirror=被折过来的一层"
    )


class HolePath(BaseModel):
    """一个展开孔位的一条来源传播路径。"""

    punch: int = Field(..., description="对应请求中 punches 的下标")
    punch_point: PunchPoint
    layer: int = Field(
        ...,
        ge=1,
        description=(
            "该分支命中的最终层号（折叠栈自上而下、从 1 开始编号）；"
            "省略 depth 时覆盖全部层，带 depth 时仅覆盖前 depth 层"
        ),
    )
    steps: List[PathStep]


class Hole(BaseModel):
    """展开后板材上的唯一孔位。"""

    x: int
    y: int
    layers: int = Field(..., description="覆盖该坐标的传播路径数（重合次数）")
    paths: List[HolePath]


class FaceRegion(BaseModel):
    """最终折叠面在原始板材坐标系中的位置与尺寸。"""

    x: int
    y: int
    width: int
    height: int


class UnfoldResponse(BaseModel):
    board: Board
    folds: List[FoldDirection]
    final_face: FaceRegion
    stack_layers: int = Field(..., description="折叠后每处的纸层数 = 2^len(folds)")
    total_holes: int = Field(..., description="展开孔位总数（含重合，按路径计）")
    unique_holes: int = Field(..., description="去重后的唯一孔位数")
    holes: List[Hole]


class TargetHole(BaseModel):
    """期望在展开板材上出现的目标孔位，使用原始板材坐标。"""

    x: int = Field(..., ge=0, examples=[1])
    y: int = Field(..., ge=0, examples=[1])


class PunchPlanRequest(BaseModel):
    board: Board
    folds: List[FoldDirection] = Field(
        default_factory=list,
        max_length=64,
        description="按执行顺序给出的折叠方向序列",
    )
    targets: List[TargetHole] = Field(
        ...,
        min_length=1,
        max_length=4096,
        description="期望在展开板材上出现的目标孔位（原始板材坐标），服务端自动去重",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "board": {"width": 8, "height": 4},
                    "folds": ["left", "down"],
                    "targets": [
                        {"x": 1, "y": 1},
                        {"x": 1, "y": 2},
                        {"x": 6, "y": 1},
                        {"x": 6, "y": 2},
                    ],
                }
            ]
        }
    }


class PunchPlanResponse(BaseModel):
    board: Board
    folds: List[FoldDirection]
    final_face: FaceRegion
    stack_layers: int = Field(..., description="折叠后每处的纸层数 = 2^len(folds)")
    target_count: int = Field(..., description="去重后的目标孔位数")
    punch_count: int = Field(..., description="最小打孔点数（等价组数）")
    punches: List[PunchPoint] = Field(
        ..., description="最终折叠面上的打孔点（局部坐标），按 (x, y) 稳定排序"
    )


class ErrorDetail(BaseModel):
    error: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail

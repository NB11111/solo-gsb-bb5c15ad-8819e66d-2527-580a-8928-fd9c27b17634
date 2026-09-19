"""核心展开逻辑测试。"""
import pytest

from app.folding import FoldError, fold_point, fold_regions, plan_punches, unfold_board


def test_unfold_left_down_known_coordinates():
    # 8x4 板材：右半向左折 -> 上半向下折；折叠面为 x∈[0,4), y∈[2,4)
    res = unfold_board(8, 4, ["left", "down"], [(1, 0)])
    assert res["final_face"] == {"x": 0, "y": 2, "width": 4, "height": 2}
    assert res["stack_layers"] == 4
    assert res["total_holes"] == 4
    assert res["unique_holes"] == 4
    coords = {(h["x"], h["y"]) for h in res["holes"]}
    assert coords == {(1, 1), (1, 2), (6, 1), (6, 2)}
    for hole in res["holes"]:
        assert hole["layers"] == 1
        assert len(hole["paths"]) == 1
        path = hole["paths"][0]
        assert path["punch"] == 0
        assert path["punch_point"] == {"x": 1, "y": 0}
        # 步骤按折叠原始顺序排列
        assert [s["fold"] for s in path["steps"]] == [0, 1]


def test_path_branches_recorded():
    res = unfold_board(8, 4, ["left", "down"], [(1, 0)])
    by_coord = {(h["x"], h["y"]): h for h in res["holes"]}
    # (6, 1) 是两次都取镜像分支的孔位
    steps = by_coord[(6, 1)]["paths"][0]["steps"]
    assert [s["branch"] for s in steps] == ["mirror", "mirror"]
    assert [s["direction"] for s in steps] == ["left", "down"]
    # (1, 2) 是两次都留在原层的孔位
    steps = by_coord[(1, 2)]["paths"][0]["steps"]
    assert [s["branch"] for s in steps] == ["stay", "stay"]


def test_fold_right_semantics():
    # 4x1：左半向右折，折叠面为 x∈[2,4)
    res = unfold_board(4, 1, ["right"], [(0, 0)])
    assert res["final_face"] == {"x": 2, "y": 0, "width": 2, "height": 1}
    coords = {(h["x"], h["y"]) for h in res["holes"]}
    assert coords == {(1, 0), (2, 0)}


def test_fold_up_semantics():
    # 1x4：下半向上折，折叠面为 y∈[0,2)
    res = unfold_board(1, 4, ["up"], [(0, 1)])
    assert res["final_face"] == {"x": 0, "y": 0, "width": 1, "height": 2}
    coords = {(h["x"], h["y"]) for h in res["holes"]}
    assert coords == {(0, 1), (0, 2)}


def test_no_folds_passthrough():
    res = unfold_board(3, 3, [], [(2, 1)])
    assert res["stack_layers"] == 1
    assert res["unique_holes"] == 1
    hole = res["holes"][0]
    assert (hole["x"], hole["y"], hole["layers"]) == (2, 1, 1)
    assert hole["paths"][0]["steps"] == []


def test_odd_axis_rejected_at_first_step():
    with pytest.raises(FoldError) as exc_info:
        unfold_board(8, 5, ["up"], [(0, 0)])
    err = exc_info.value
    assert err.code == "odd_fold_axis"
    assert err.context["step"] == 0
    assert err.context["axis"] == "height"
    assert err.context["axis_length"] == 5


def test_odd_axis_rejected_at_later_step():
    # 6 -> 3 之后宽度为奇数，第二步应被拒绝
    with pytest.raises(FoldError) as exc_info:
        unfold_board(6, 2, ["left", "left"], [(0, 0)])
    err = exc_info.value
    assert err.code == "odd_fold_axis"
    assert err.context["step"] == 1
    assert err.context["axis_length"] == 3


def test_punch_out_of_bounds():
    with pytest.raises(FoldError) as exc_info:
        unfold_board(4, 4, ["left"], [(2, 0)])  # 折叠面宽 2，x=2 越界
    assert exc_info.value.code == "punch_out_of_bounds"
    assert exc_info.value.context["punch"] == 0


def test_duplicate_punches_merge_but_keep_paths():
    res = unfold_board(4, 2, ["left"], [(1, 0), (1, 0)])
    assert res["total_holes"] == 4
    assert res["unique_holes"] == 2
    for hole in res["holes"]:
        assert hole["layers"] == 2
        assert len(hole["paths"]) == 2
        assert {p["punch"] for p in hole["paths"]} == {0, 1}


def test_multiple_distinct_punches():
    res = unfold_board(4, 4, ["left", "down"], [(0, 0), (1, 1)])
    assert res["stack_layers"] == 4
    assert res["total_holes"] == 8
    assert res["unique_holes"] == 8


def test_fold_regions_sequence():
    regions = fold_regions(8, 4, ["left", "down"])
    assert [(r.x, r.y, r.width, r.height) for r in regions] == [
        (0, 0, 8, 4),
        (0, 0, 4, 4),
        (0, 2, 4, 2),
    ]


def test_fold_point_matches_unfold_paths():
    # 展开结果中的每个孔位，正向折叠后必须回到原打孔点
    regions = fold_regions(8, 4, ["left", "down"])
    res = unfold_board(8, 4, ["left", "down"], [(1, 0)])
    for hole in res["holes"]:
        assert fold_point(regions, ["left", "down"], hole["x"], hole["y"]) == (1, 2)


def test_plan_punches_round_trip_single_orbit():
    # 与 test_unfold_left_down_known_coordinates 互逆
    res = plan_punches(8, 4, ["left", "down"], [(1, 1), (1, 2), (6, 1), (6, 2)])
    assert res["final_face"] == {"x": 0, "y": 2, "width": 4, "height": 2}
    assert res["stack_layers"] == 4
    assert res["target_count"] == 4
    assert res["punch_count"] == 1
    assert res["punches"] == [{"x": 1, "y": 0}]


def test_plan_punches_multiple_orbits_sorted():
    targets = [
        (1, 0), (1, 3), (2, 0), (2, 3),  # 等价组 (1, 1)
        (0, 1), (0, 2), (3, 1), (3, 2),  # 等价组 (0, 0)
    ]
    res = plan_punches(4, 4, ["left", "down"], targets)
    assert res["target_count"] == 8
    assert res["punch_count"] == 2
    assert res["punches"] == [{"x": 0, "y": 0}, {"x": 1, "y": 1}]


def test_plan_punches_no_folds_dedup_and_sort():
    res = plan_punches(3, 3, [], [(2, 1), (0, 0), (2, 1)])
    assert res["stack_layers"] == 1
    assert res["target_count"] == 2
    assert res["punches"] == [{"x": 0, "y": 0}, {"x": 2, "y": 1}]


def test_plan_punches_result_feeds_unfold_board():
    targets = [(1, 1), (1, 2), (6, 1), (6, 2)]
    res = plan_punches(8, 4, ["left", "down"], targets)
    punches = [(p["x"], p["y"]) for p in res["punches"]]
    unfolded = unfold_board(8, 4, ["left", "down"], punches)
    assert {(h["x"], h["y"]) for h in unfolded["holes"]} == set(targets)


def test_plan_punches_target_out_of_bounds():
    with pytest.raises(FoldError) as exc_info:
        plan_punches(4, 4, ["left"], [(1, 1), (9, 0), (0, 4)])
    err = exc_info.value
    assert err.code == "target_out_of_bounds"
    # 越界坐标去重后按 (x, y) 排序全部列出
    assert err.context["out_of_bounds"] == [{"x": 0, "y": 4}, {"x": 9, "y": 0}]
    assert err.context["board_width"] == 4
    assert err.context["board_height"] == 4


def test_plan_punches_incomplete_group_reports_missing():
    with pytest.raises(FoldError) as exc_info:
        plan_punches(8, 4, ["left", "down"], [(1, 1)])
    err = exc_info.value
    assert err.code == "incomplete_equivalence_group"
    assert err.context["group"] == {"x": 1, "y": 0}
    assert err.context["missing"] == [
        {"x": 1, "y": 2},
        {"x": 6, "y": 1},
        {"x": 6, "y": 2},
    ]
    assert err.context["extra"] == []


def test_plan_punches_reports_first_incomplete_group_sorted():
    # (6, 1) 归并到组 (1, 0)，(0, 3) 归并到组 (0, 1)；两组都不完整时报告 (x, y) 最小者
    with pytest.raises(FoldError) as exc_info:
        plan_punches(8, 4, ["left", "down"], [(6, 1), (0, 3)])
    err = exc_info.value
    assert err.code == "incomplete_equivalence_group"
    assert err.context["group"] == {"x": 0, "y": 1}
    assert err.context["missing"] == [
        {"x": 0, "y": 0},
        {"x": 7, "y": 0},
        {"x": 7, "y": 3},
    ]


def test_plan_punches_odd_axis_propagates():
    with pytest.raises(FoldError) as exc_info:
        plan_punches(3, 2, ["left"], [(0, 0)])
    assert exc_info.value.code == "odd_fold_axis"


def test_plan_punches_limit_exceeded():
    with pytest.raises(FoldError) as exc_info:
        plan_punches(4, 4, [], [(0, 0), (1, 1)], max_punches=1)
    assert exc_info.value.code == "limit_exceeded"

    with pytest.raises(FoldError) as exc_info:
        plan_punches(4, 4, ["left"], [(0, 0), (1, 0)], max_total_holes=3)
    assert exc_info.value.code == "limit_exceeded"


# ---------------------------------------------------------------------------
# 限深打孔
# ---------------------------------------------------------------------------


def _stack_order(width, height, folds, local_x=0, local_y=0):
    """按真实折叠构造参考层序：返回打孔点处自上而下的 [(原板坐标, 分支序列)]。

    为折叠面上的每个物理格子维护一个自上而下的层栈；每步折叠时，
    移动半区的来源栈反转并追加 mirror，叠到固定半区来源栈（追加 stay）之上。
    """
    from app.folding import fold_regions

    regions = fold_regions(width, height, folds)
    stacks: dict[tuple[int, int], list[tuple[tuple[int, int], tuple]]] = {
        (x, y): [((x, y), ())] for x in range(width) for y in range(height)
    }
    for i, direction in enumerate(folds):
        before = regions[i]
        after = regions[i + 1]
        nxt: dict[tuple[int, int], list[tuple[tuple[int, int], tuple]]] = {}
        for ax in range(after.x, after.x + after.width):
            for ay in range(after.y, after.y + after.height):
                if direction in ("left", "right"):
                    mx, my = 2 * before.x + before.width - 1 - ax, ay
                else:
                    mx, my = ax, 2 * before.y + before.height - 1 - ay
                moved = [
                    (coord, seq + ("mirror",)) for coord, seq in reversed(stacks[(mx, my)])
                ]
                fixed = [
                    (coord, seq + ("stay",)) for coord, seq in stacks[(ax, ay)]
                ]
                nxt[(ax, ay)] = moved + fixed
        stacks = nxt
    final = regions[-1]
    return stacks[(final.x + local_x, final.y + local_y)]


def test_paths_carry_final_layer_number():
    res = unfold_board(8, 4, ["left", "down"], [(1, 0)])
    reference = {coord: idx + 1 for idx, (coord, _seq) in enumerate(_stack_order(8, 4, ["left", "down"], 1, 0))}
    seen_layers = set()
    for hole in res["holes"]:
        for path in hole["paths"]:
            assert path["layer"] == reference[(hole["x"], hole["y"])]
            seen_layers.add(path["layer"])
    assert seen_layers == {1, 2, 3, 4}


def test_depth_one_keeps_top_layer_only():
    res = unfold_board(8, 4, ["left", "down"], [(1, 0, 1)])
    assert res["total_holes"] == 1
    assert res["unique_holes"] == 1
    hole = res["holes"][0]
    # 顶层层号 1：left 折时留在固定半区，down 折时被翻面叠到最上
    assert (hole["x"], hole["y"]) == (1, 1)
    assert hole["layers"] == 1
    path = hole["paths"][0]
    assert path["layer"] == 1
    assert [s["branch"] for s in path["steps"]] == ["stay", "mirror"]


def test_depth_two_keeps_top_two_layers():
    res = unfold_board(8, 4, ["left", "down"], [(1, 0, 2)])
    assert res["total_holes"] == 2
    by_coord = {(h["x"], h["y"]): h for h in res["holes"]}
    assert set(by_coord) == {(1, 1), (6, 1)}
    assert by_coord[(1, 1)]["paths"][0]["layer"] == 1
    assert by_coord[(6, 1)]["paths"][0]["layer"] == 2


def test_depth_three_asymmetric_split():
    res = unfold_board(8, 4, ["left", "down"], [(1, 0, 3)])
    assert res["total_holes"] == 3
    by_coord = {(h["x"], h["y"]): h for h in res["holes"]}
    assert set(by_coord) == {(1, 1), (6, 1), (6, 2)}
    assert by_coord[(6, 2)]["paths"][0]["layer"] == 3


def test_depth_full_equals_omitted():
    full = unfold_board(8, 4, ["left", "down"], [(1, 0, 4)])
    omitted = unfold_board(8, 4, ["left", "down"], [(1, 0)])
    expected = {(1, 1, 1), (6, 1, 2), (6, 2, 3), (1, 2, 4)}
    for res in (full, omitted):
        assert res["total_holes"] == 4
        assert {
            (h["x"], h["y"], p["layer"])
            for h in res["holes"]
            for p in h["paths"]
        } == expected
    # 孔位/层号/路径完全一致，唯一区别是显式 depth 在 punch_point 中回显
    def normalize(res):
        return [
            {
                "x": h["x"],
                "y": h["y"],
                "layers": h["layers"],
                "paths": [
                    {k: v for k, v in p.items() if k != "punch_point"}
                    for p in h["paths"]
                ],
            }
            for h in res["holes"]
        ]

    assert normalize(full) == normalize(omitted)


def test_depth_semantics_other_directions():
    # 4x1 右折：左半被翻面叠到右半之上，punch 位于面 x=2（局部 0），
    # 顶层来自被翻面的左半 -> 原 x=1，底层为固定半区 x=2
    res = unfold_board(4, 1, ["right"], [(0, 0, 1)])
    assert [(h["x"], h["y"]) for h in res["holes"]] == [(1, 0)]
    assert res["holes"][0]["paths"][0]["layer"] == 1
    res2 = unfold_board(4, 1, ["right"], [(0, 0, 2)])
    assert {(h["x"], h["y"]) for h in res2["holes"]} == {(1, 0), (2, 0)}

    # 1x4 上折：下半被翻面叠到上半之上，面 y∈[0,2)，punch 局部 (0,1)：
    # 顶层来自被翻面的下半 -> 原 y=2，底层为固定半区 y=1
    res3 = unfold_board(1, 4, ["up"], [(0, 1, 1)])
    assert [(h["x"], h["y"]) for h in res3["holes"]] == [(0, 2)]
    res4 = unfold_board(1, 4, ["up"], [(0, 1, 2)])
    assert {(h["x"], h["y"]) for h in res4["holes"]} == {(0, 1), (0, 2)}


def test_depth_no_folds():
    res = unfold_board(3, 3, [], [(2, 1, 1)])
    hole = res["holes"][0]
    assert (hole["x"], hole["y"], hole["layers"]) == (2, 1, 1)
    assert hole["paths"][0]["layer"] == 1


def test_same_punch_different_depth_accumulates_layers():
    # 同一点 depth=1 与贯穿同时打孔：层1 坐标重合，layers 累计为 2，保留两条来源
    res = unfold_board(8, 4, ["left", "down"], [(1, 0, 1), (1, 0)])
    assert res["total_holes"] == 5
    by_coord = {(h["x"], h["y"]): h for h in res["holes"]}
    top = by_coord[(1, 1)]
    assert top["layers"] == 2
    assert len(top["paths"]) == 2
    assert {p["punch"] for p in top["paths"]} == {0, 1}
    assert {p["layer"] for p in top["paths"]} == {1}
    # 其余三个坐标只由贯穿打孔（punch #1）产生
    for coord in ((6, 1), (6, 2), (1, 2)):
        hole = by_coord[coord]
        assert hole["layers"] == 1
        assert hole["paths"][0]["punch"] == 1


def test_depth_keeps_only_top_depth_against_reference():
    # 与独立的显式层序构造交叉校验：depth 恰好保留前 depth 层对应原板坐标
    folds = ["right", "up", "left"]
    width, height = 8, 4
    px, py = 0, 0
    layers = _stack_order(width, height, folds, px, py)
    for depth in range(1, 9):
        res = unfold_board(width, height, folds, [(px, py, depth)])
        expected_coords = {coord for coord, _seq in layers[:depth]}
        actual = {(h["x"], h["y"]) for h in res["holes"]}
        assert actual == expected_coords
        assert res["total_holes"] == depth
        layer_by_coord = {
            (h["x"], h["y"]): h["paths"][0]["layer"] for h in res["holes"]
        }
        for layer_no, (coord, _seq) in enumerate(layers[:depth], start=1):
            assert layer_by_coord[coord] == layer_no


def test_invalid_depth_zero_and_negative():
    with pytest.raises(FoldError) as exc_info:
        unfold_board(8, 4, ["left", "down"], [(1, 0, 0)])
    err = exc_info.value
    assert err.code == "invalid_punch_depth"
    assert err.context["punch"] == 0
    assert err.context["max_depth"] == 4

    with pytest.raises(FoldError):
        unfold_board(4, 1, ["left"], [(0, 0, -1)])


def test_invalid_depth_above_stack_layers():
    with pytest.raises(FoldError) as exc_info:
        unfold_board(4, 1, ["left"], [(0, 0, 3)])  # 仅 2 层
    err = exc_info.value
    assert err.code == "invalid_punch_depth"
    assert err.context["depth"] == 3
    assert err.context["max_depth"] == 2


def test_invalid_depth_no_folds():
    with pytest.raises(FoldError):
        unfold_board(3, 3, [], [(0, 0, 2)])

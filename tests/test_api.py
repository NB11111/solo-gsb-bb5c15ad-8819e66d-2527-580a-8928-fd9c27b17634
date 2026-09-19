"""HTTP API 测试。"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_unfold_ok():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 8, "height": 4},
            "folds": ["left", "down"],
            "punches": [{"x": 1, "y": 0}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_face"] == {"x": 0, "y": 2, "width": 4, "height": 2}
    assert body["stack_layers"] == 4
    assert body["total_holes"] == 4
    assert body["unique_holes"] == 4
    coords = {(h["x"], h["y"]) for h in body["holes"]}
    assert coords == {(1, 1), (1, 2), (6, 1), (6, 2)}
    sample = body["holes"][0]
    assert sample["layers"] == 1
    assert sample["paths"][0]["punch"] == 0
    assert len(sample["paths"][0]["steps"]) == 2


def test_unfold_odd_axis_returns_400():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 3, "height": 2},
            "folds": ["left"],
            "punches": [{"x": 0, "y": 0}],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error"] == "odd_fold_axis"
    assert detail["axis"] == "width"
    assert detail["axis_length"] == 3
    assert detail["step"] == 0


def test_unfold_punch_out_of_bounds_returns_400():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 4, "height": 4},
            "folds": ["left"],
            "punches": [{"x": 2, "y": 0}],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "punch_out_of_bounds"


def test_invalid_direction_returns_422():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 4, "height": 4},
            "folds": ["sideways"],
            "punches": [{"x": 0, "y": 0}],
        },
    )
    assert resp.status_code == 422


def test_empty_punches_returns_422():
    resp = client.post(
        "/api/v1/unfold",
        json={"board": {"width": 4, "height": 4}, "folds": [], "punches": []},
    )
    assert resp.status_code == 422


def test_negative_coordinate_returns_422():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 4, "height": 4},
            "folds": [],
            "punches": [{"x": -1, "y": 0}],
        },
    )
    assert resp.status_code == 422


def test_duplicate_punches_merged_with_paths():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 4, "height": 2},
            "folds": ["left"],
            "punches": [{"x": 1, "y": 0}, {"x": 1, "y": 0}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["unique_holes"] == 2
    for hole in body["holes"]:
        assert hole["layers"] == 2
        assert {p["punch"] for p in hole["paths"]} == {0, 1}


def test_punch_plan_ok():
    resp = client.post(
        "/api/v1/punch-plan",
        json={
            "board": {"width": 8, "height": 4},
            "folds": ["left", "down"],
            "targets": [
                {"x": 1, "y": 1},
                {"x": 1, "y": 2},
                {"x": 6, "y": 1},
                {"x": 6, "y": 2},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["final_face"] == {"x": 0, "y": 2, "width": 4, "height": 2}
    assert body["stack_layers"] == 4
    assert body["target_count"] == 4
    assert body["punch_count"] == 1
    assert body["punches"] == [{"x": 1, "y": 0}]


def test_punch_plan_dedupes_and_sorts_targets():
    resp = client.post(
        "/api/v1/punch-plan",
        json={
            "board": {"width": 4, "height": 4},
            "folds": [],
            "targets": [{"x": 2, "y": 1}, {"x": 0, "y": 0}, {"x": 2, "y": 1}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_count"] == 2
    assert body["punch_count"] == 2
    assert body["punches"] == [{"x": 0, "y": 0}, {"x": 2, "y": 1}]


def test_punch_plan_result_compatible_with_unfold():
    plan = client.post(
        "/api/v1/punch-plan",
        json={
            "board": {"width": 8, "height": 4},
            "folds": ["left", "down"],
            "targets": [
                {"x": 1, "y": 1},
                {"x": 1, "y": 2},
                {"x": 6, "y": 1},
                {"x": 6, "y": 2},
            ],
        },
    ).json()
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 8, "height": 4},
            "folds": ["left", "down"],
            "punches": plan["punches"],
        },
    )
    assert resp.status_code == 200
    coords = {(h["x"], h["y"]) for h in resp.json()["holes"]}
    assert coords == {(1, 1), (1, 2), (6, 1), (6, 2)}


def test_punch_plan_target_out_of_bounds_returns_400():
    resp = client.post(
        "/api/v1/punch-plan",
        json={
            "board": {"width": 4, "height": 4},
            "folds": [],
            "targets": [{"x": 1, "y": 1}, {"x": 4, "y": 0}],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error"] == "target_out_of_bounds"
    assert detail["out_of_bounds"] == [{"x": 4, "y": 0}]


def test_punch_plan_incomplete_group_returns_400():
    resp = client.post(
        "/api/v1/punch-plan",
        json={
            "board": {"width": 8, "height": 4},
            "folds": ["left", "down"],
            "targets": [{"x": 1, "y": 1}],
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error"] == "incomplete_equivalence_group"
    assert detail["group"] == {"x": 1, "y": 0}
    assert detail["missing"] == [
        {"x": 1, "y": 2},
        {"x": 6, "y": 1},
        {"x": 6, "y": 2},
    ]
    assert detail["extra"] == []


def test_punch_plan_odd_axis_returns_400():
    resp = client.post(
        "/api/v1/punch-plan",
        json={
            "board": {"width": 3, "height": 2},
            "folds": ["left"],
            "targets": [{"x": 0, "y": 0}],
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "odd_fold_axis"


def test_punch_plan_empty_targets_returns_422():
    resp = client.post(
        "/api/v1/punch-plan",
        json={"board": {"width": 4, "height": 4}, "folds": [], "targets": []},
    )
    assert resp.status_code == 422


def test_punch_plan_negative_coordinate_returns_422():
    resp = client.post(
        "/api/v1/punch-plan",
        json={
            "board": {"width": 4, "height": 4},
            "folds": [],
            "targets": [{"x": -1, "y": 0}],
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 限深打孔
# ---------------------------------------------------------------------------


def test_unfold_depth_one():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 8, "height": 4},
            "folds": ["left", "down"],
            "punches": [{"x": 1, "y": 0, "depth": 1}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_holes"] == 1
    assert body["unique_holes"] == 1
    hole = body["holes"][0]
    assert (hole["x"], hole["y"]) == (1, 1)
    path = hole["paths"][0]
    assert path["layer"] == 1
    assert path["punch_point"] == {"x": 1, "y": 0, "depth": 1}


def test_unfold_depth_two():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 8, "height": 4},
            "folds": ["left", "down"],
            "punches": [{"x": 1, "y": 0, "depth": 2}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_holes"] == 2
    coords = {
        (h["x"], h["y"]): h["paths"][0]["layer"] for h in body["holes"]
    }
    assert coords == {(1, 1): 1, (6, 1): 2}


def test_unfold_depth_full_same_as_omitted():
    common = {"board": {"width": 8, "height": 4}, "folds": ["left", "down"]}
    omitted = client.post(
        "/api/v1/unfold", json={**common, "punches": [{"x": 1, "y": 0}]}
    ).json()
    full = client.post(
        "/api/v1/unfold",
        json={**common, "punches": [{"x": 1, "y": 0, "depth": 4}]},
    ).json()
    assert full["total_holes"] == omitted["total_holes"] == 4
    assert {(h["x"], h["y"]) for h in full["holes"]} == {
        (h["x"], h["y"]) for h in omitted["holes"]
    }
    # 省略 depth 的请求/响应均不携带 depth 字段
    assert omitted["holes"][0]["paths"][0]["punch_point"] == {"x": 1, "y": 0}
    assert full["holes"][0]["paths"][0]["punch_point"] == {"x": 1, "y": 0, "depth": 4}
    for h in omitted["holes"]:
        assert "layer" in h["paths"][0]


def test_unfold_duplicate_punches_different_depth_accumulate():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 8, "height": 4},
            "folds": ["left", "down"],
            "punches": [
                {"x": 1, "y": 0, "depth": 1},
                {"x": 1, "y": 0},
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_holes"] == 5
    top = next(h for h in body["holes"] if (h["x"], h["y"]) == (1, 1))
    assert top["layers"] == 2
    assert len(top["paths"]) == 2
    assert {p["punch"] for p in top["paths"]} == {0, 1}
    assert all(p["layer"] == 1 for p in top["paths"])


def test_unfold_depth_too_large_returns_422():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 4, "height": 1},
            "folds": ["left"],
            "punches": [{"x": 0, "y": 0, "depth": 3}],
        },
    )
    assert resp.status_code == 422


def test_unfold_depth_zero_returns_422():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 4, "height": 1},
            "folds": ["left"],
            "punches": [{"x": 0, "y": 0, "depth": 0}],
        },
    )
    assert resp.status_code == 422


def test_unfold_depth_negative_returns_422():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 4, "height": 4},
            "folds": [],
            "punches": [{"x": 0, "y": 0, "depth": -1}],
        },
    )
    assert resp.status_code == 422


def test_unfold_depth_one_without_folds_ok():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 4, "height": 4},
            "folds": [],
            "punches": [{"x": 0, "y": 0, "depth": 1}],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["holes"][0]["paths"][0]["layer"] == 1


def test_unfold_depth_exceeds_stack_no_folds_returns_422():
    resp = client.post(
        "/api/v1/unfold",
        json={
            "board": {"width": 4, "height": 4},
            "folds": [],
            "punches": [{"x": 0, "y": 0, "depth": 2}],
        },
    )
    assert resp.status_code == 422

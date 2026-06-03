import pytest

from deck_builder.layout_constraints import LayoutConstraintError
from deck_builder.layout_solver import solve_layout


def test_solves_deterministic_balanced_grid_by_priority_then_id():
    solution = solve_layout(
        [
            {"element_id": "summary", "priority": 3},
            {"element_id": "chart", "kind": "chart", "priority": 1},
            {"element_id": "table", "kind": "table", "priority": 1},
            {"element_id": "quote", "priority": 0},
        ],
        width=800,
        height=600,
        margin=40,
        gutter=20,
        max_columns=3,
    )

    assert solution.columns == 2
    assert solution.rows == 2
    assert [frame.element_id for frame in solution.frames] == [
        "summary",
        "chart",
        "table",
        "quote",
    ]
    assert solution.by_id()["summary"].x == 40
    assert solution.by_id()["chart"].x > solution.by_id()["summary"].x


def test_respects_aspect_ratio_inside_cell():
    solution = solve_layout(
        [{"element_id": "hero_chart", "aspect_ratio": 2.0, "min_width": 200, "min_height": 100}],
        width=600,
        height=400,
        margin=40,
    )

    frame = solution.by_id()["hero_chart"]
    assert round(frame.width / frame.height, 1) == 2.0
    assert frame.x >= 40
    assert frame.bottom <= 360


def test_fails_closed_when_minimum_sizes_cannot_fit():
    with pytest.raises(LayoutConstraintError, match="unsatisfiable"):
        solve_layout(
            [
                {"element_id": "a", "min_width": 500, "min_height": 320},
                {"element_id": "b", "min_width": 500, "min_height": 320},
                {"element_id": "c", "min_width": 500, "min_height": 320},
            ],
            width=640,
            height=360,
            margin=40,
            gutter=24,
            max_columns=3,
        )

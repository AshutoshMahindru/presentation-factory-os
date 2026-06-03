import pytest

from deck_builder.layout_constraints import (
    LayoutConstraintError,
    LayoutElement,
    LayoutFrame,
    LayoutSpec,
    assert_frames_fit,
    normalize_elements,
    validate_layout_spec,
)


def test_normalizes_dict_elements_into_layout_elements():
    elements = normalize_elements(
        [
            {
                "element_id": "chart",
                "kind": "chart",
                "min_width": 240,
                "min_height": 160,
                "priority": 2,
                "aspect_ratio": 1.6,
            }
        ]
    )

    assert elements == (
        LayoutElement(
            element_id="chart",
            kind="chart",
            min_width=240,
            min_height=160,
            priority=2,
            aspect_ratio=1.6,
        ),
    )


def test_rejects_duplicate_element_ids():
    spec = LayoutSpec(
        elements=(
            LayoutElement("same"),
            LayoutElement("same"),
        )
    )

    with pytest.raises(LayoutConstraintError, match="duplicate"):
        validate_layout_spec(spec)


def test_assert_frames_fit_rejects_overlap():
    spec = LayoutSpec(elements=(LayoutElement("a"), LayoutElement("b")))
    frames = (
        LayoutFrame("a", 48, 48, 220, 120),
        LayoutFrame("b", 120, 80, 220, 120),
    )

    with pytest.raises(LayoutConstraintError, match="overlap"):
        assert_frames_fit(spec, frames)

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


class LayoutConstraintError(ValueError):
    """Raised when a layout request violates deterministic solver constraints."""


@dataclass(frozen=True)
class SlideBounds:
    width: int = 1280
    height: int = 720
    margin: int = 48

    @property
    def inner_width(self) -> int:
        return self.width - (self.margin * 2)

    @property
    def inner_height(self) -> int:
        return self.height - (self.margin * 2)


@dataclass(frozen=True)
class LayoutElement:
    element_id: str
    kind: str = "content"
    min_width: int = 160
    min_height: int = 96
    priority: int = 0
    aspect_ratio: float | None = None


@dataclass(frozen=True)
class LayoutFrame:
    element_id: str
    x: int
    y: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass(frozen=True)
class LayoutSpec:
    elements: tuple[LayoutElement, ...]
    bounds: SlideBounds = SlideBounds()
    gutter: int = 24
    max_columns: int = 3


def normalize_elements(elements: Iterable[LayoutElement | dict]) -> tuple[LayoutElement, ...]:
    normalized: list[LayoutElement] = []
    for item in elements:
        if isinstance(item, LayoutElement):
            normalized.append(item)
            continue
        normalized.append(
            LayoutElement(
                element_id=str(item["element_id"]),
                kind=str(item.get("kind", "content")),
                min_width=int(item.get("min_width", 160)),
                min_height=int(item.get("min_height", 96)),
                priority=int(item.get("priority", 0)),
                aspect_ratio=(
                    float(item["aspect_ratio"])
                    if item.get("aspect_ratio") is not None
                    else None
                ),
            )
        )
    return tuple(normalized)


def validate_layout_spec(spec: LayoutSpec) -> None:
    if spec.bounds.width <= 0 or spec.bounds.height <= 0:
        raise LayoutConstraintError("slide bounds must be positive")
    if spec.bounds.margin < 0:
        raise LayoutConstraintError("slide margin must be non-negative")
    if spec.bounds.inner_width <= 0 or spec.bounds.inner_height <= 0:
        raise LayoutConstraintError("slide margin leaves no drawable area")
    if spec.gutter < 0:
        raise LayoutConstraintError("layout gutter must be non-negative")
    if spec.max_columns <= 0:
        raise LayoutConstraintError("max_columns must be positive")
    if not spec.elements:
        raise LayoutConstraintError("at least one layout element is required")

    seen: set[str] = set()
    for element in spec.elements:
        if not element.element_id:
            raise LayoutConstraintError("layout element id is required")
        if element.element_id in seen:
            raise LayoutConstraintError(f"duplicate layout element id: {element.element_id}")
        seen.add(element.element_id)
        if element.min_width <= 0 or element.min_height <= 0:
            raise LayoutConstraintError(
                f"element {element.element_id} minimum size must be positive"
            )
        if element.aspect_ratio is not None and element.aspect_ratio <= 0:
            raise LayoutConstraintError(
                f"element {element.element_id} aspect_ratio must be positive"
            )


def assert_frames_fit(spec: LayoutSpec, frames: Iterable[LayoutFrame]) -> None:
    frame_tuple = tuple(frames)
    expected = {element.element_id for element in spec.elements}
    actual = {frame.element_id for frame in frame_tuple}
    if expected != actual:
        raise LayoutConstraintError("layout frames do not match requested elements")

    for frame in frame_tuple:
        if frame.x < spec.bounds.margin or frame.y < spec.bounds.margin:
            raise LayoutConstraintError(f"frame {frame.element_id} starts outside bounds")
        if frame.right > spec.bounds.width - spec.bounds.margin:
            raise LayoutConstraintError(f"frame {frame.element_id} exceeds right bound")
        if frame.bottom > spec.bounds.height - spec.bounds.margin:
            raise LayoutConstraintError(f"frame {frame.element_id} exceeds bottom bound")

    for index, left in enumerate(frame_tuple):
        for right in frame_tuple[index + 1 :]:
            if _overlaps(left, right):
                raise LayoutConstraintError(
                    f"frames overlap: {left.element_id}, {right.element_id}"
                )


def _overlaps(left: LayoutFrame, right: LayoutFrame) -> bool:
    return not (
        left.right <= right.x
        or right.right <= left.x
        or left.bottom <= right.y
        or right.bottom <= left.y
    )

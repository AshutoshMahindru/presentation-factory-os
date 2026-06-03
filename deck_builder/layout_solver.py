from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Iterable

from deck_builder.layout_constraints import (
    LayoutConstraintError,
    LayoutElement,
    LayoutFrame,
    LayoutSpec,
    SlideBounds,
    assert_frames_fit,
    normalize_elements,
    validate_layout_spec,
)


@dataclass(frozen=True)
class LayoutSolution:
    frames: tuple[LayoutFrame, ...]
    columns: int
    rows: int
    solver: str = "deterministic-grid-v1"

    def by_id(self) -> dict[str, LayoutFrame]:
        return {frame.element_id: frame for frame in self.frames}


class DeterministicLayoutSolver:
    def solve(self, spec: LayoutSpec) -> LayoutSolution:
        validate_layout_spec(spec)

        ordered = tuple(
            sorted(
                spec.elements,
                key=lambda element: (-element.priority, element.element_id),
            )
        )
        columns, rows = self._choose_grid(spec, ordered)
        frames = self._build_frames(spec, ordered, columns, rows)
        assert_frames_fit(spec, frames)
        return LayoutSolution(frames=frames, columns=columns, rows=rows)

    def _choose_grid(
        self,
        spec: LayoutSpec,
        elements: tuple[LayoutElement, ...],
    ) -> tuple[int, int]:
        count = len(elements)
        candidates: list[tuple[int, int, int, int]] = []
        max_columns = min(spec.max_columns, count)
        for columns in range(1, max_columns + 1):
            rows = ceil(count / columns)
            cell_width = _cell_size(spec.bounds.inner_width, spec.gutter, columns)
            cell_height = _cell_size(spec.bounds.inner_height, spec.gutter, rows)
            if not self._all_elements_fit(elements, cell_width, cell_height):
                continue
            candidates.append((abs(columns - rows), rows, -columns, columns))

        if not candidates:
            largest_min_width = max(element.min_width for element in elements)
            largest_min_height = max(element.min_height for element in elements)
            raise LayoutConstraintError(
                "layout is unsatisfiable: "
                f"minimum element size {largest_min_width}x{largest_min_height} "
                f"does not fit {count} element(s) inside "
                f"{spec.bounds.inner_width}x{spec.bounds.inner_height}"
            )

        _, rows, _, columns = min(candidates)
        return columns, rows

    @staticmethod
    def _all_elements_fit(
        elements: tuple[LayoutElement, ...],
        cell_width: int,
        cell_height: int,
    ) -> bool:
        for element in elements:
            if cell_width < element.min_width or cell_height < element.min_height:
                return False
            if element.aspect_ratio is None:
                continue
            fitted_width = min(cell_width, round(cell_height * element.aspect_ratio))
            fitted_height = min(cell_height, round(fitted_width / element.aspect_ratio))
            if fitted_width < element.min_width or fitted_height < element.min_height:
                return False
        return True

    @staticmethod
    def _build_frames(
        spec: LayoutSpec,
        elements: tuple[LayoutElement, ...],
        columns: int,
        rows: int,
    ) -> tuple[LayoutFrame, ...]:
        cell_width = _cell_size(spec.bounds.inner_width, spec.gutter, columns)
        cell_height = _cell_size(spec.bounds.inner_height, spec.gutter, rows)
        frames: list[LayoutFrame] = []
        for index, element in enumerate(elements):
            row = index // columns
            column = index % columns
            width = cell_width
            height = cell_height
            x = spec.bounds.margin + column * (cell_width + spec.gutter)
            y = spec.bounds.margin + row * (cell_height + spec.gutter)

            if element.aspect_ratio is not None:
                width, height = _fit_aspect_ratio(cell_width, cell_height, element.aspect_ratio)
                x += (cell_width - width) // 2
                y += (cell_height - height) // 2

            frames.append(
                LayoutFrame(
                    element_id=element.element_id,
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                )
            )
        return tuple(frames)


def solve_layout(
    elements: Iterable[LayoutElement | dict],
    *,
    width: int = 1280,
    height: int = 720,
    margin: int = 48,
    gutter: int = 24,
    max_columns: int = 3,
) -> LayoutSolution:
    spec = LayoutSpec(
        elements=normalize_elements(elements),
        bounds=SlideBounds(width=width, height=height, margin=margin),
        gutter=gutter,
        max_columns=max_columns,
    )
    return DeterministicLayoutSolver().solve(spec)


def _cell_size(inner_size: int, gutter: int, count: int) -> int:
    return (inner_size - gutter * (count - 1)) // count


def _fit_aspect_ratio(width: int, height: int, aspect_ratio: float) -> tuple[int, int]:
    fitted_width = min(width, round(height * aspect_ratio))
    fitted_height = round(fitted_width / aspect_ratio)
    if fitted_height > height:
        fitted_height = height
        fitted_width = round(fitted_height * aspect_ratio)
    return fitted_width, fitted_height

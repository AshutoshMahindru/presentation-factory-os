from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ChartDatum:
    label: str
    value: float


def normalize_chart_data(rows: Iterable[ChartDatum | dict | tuple[str, float]]) -> tuple[ChartDatum, ...]:
    normalized: list[ChartDatum] = []
    for row in rows:
        if isinstance(row, ChartDatum):
            datum = row
        elif isinstance(row, dict):
            datum = ChartDatum(label=str(row["label"]), value=float(row["value"]))
        else:
            label, value = row
            datum = ChartDatum(label=str(label), value=float(value))
        if datum.value < 0:
            raise ValueError("chart values must be non-negative")
        normalized.append(datum)
    if not normalized:
        raise ValueError("chart data is required")
    return tuple(sorted(normalized, key=lambda item: item.label))

from __future__ import annotations

from typing import Iterable

from tool_server.charts.chart_base import ChartDatum
from tool_server.charts.chart_vega_lite import render_bar_chart_svg
from tool_server.vector_renderer import VectorArtifact


def render_echarts_bar_svg(
    data: Iterable[ChartDatum | dict | tuple[str, float]],
    *,
    title: str = "Bar chart",
    width: int = 640,
    height: int = 360,
) -> VectorArtifact:
    artifact = render_bar_chart_svg(data, title=title, width=width, height=height)
    metadata = dict(artifact.metadata or {})
    metadata["adapter"] = "echarts-compatible"
    return VectorArtifact(
        kind=artifact.kind,
        body=artifact.body,
        width=artifact.width,
        height=artifact.height,
        metadata=metadata,
    )

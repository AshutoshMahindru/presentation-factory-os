from __future__ import annotations

from typing import Iterable

from tool_server.charts.chart_base import ChartDatum, normalize_chart_data
from tool_server.vector_renderer import VectorArtifact, palette, stable_json, svg_document, xml_attr, xml_text


def render_bar_chart_svg(
    data: Iterable[ChartDatum | dict | tuple[str, float]],
    *,
    title: str = "Bar chart",
    width: int = 640,
    height: int = 360,
) -> VectorArtifact:
    rows = normalize_chart_data(data)
    if width < 240 or height < 180:
        raise ValueError("chart canvas is too small")

    margin_left = 72
    margin_right = 24
    margin_top = 48
    margin_bottom = 56
    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom
    max_value = max(datum.value for datum in rows) or 1
    slot = plot_width / len(rows)
    bar_width = max(12, int(slot * 0.56))

    children = [
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{margin_left}" y="28" font-size="18" font-family="Arial" '
        f'font-weight="700" fill="#1b1f24">{xml_text(title)}</text>',
        f'<line x1="{margin_left}" y1="{margin_top + plot_height}" '
        f'x2="{margin_left + plot_width}" y2="{margin_top + plot_height}" '
        'stroke="#4b5563" stroke-width="1"/>',
    ]
    for index, datum in enumerate(rows):
        bar_height = int((datum.value / max_value) * plot_height)
        x = int(margin_left + index * slot + (slot - bar_width) / 2)
        y = margin_top + plot_height - bar_height
        children.extend(
            [
                f'<rect data-label="{xml_attr(datum.label)}" x="{x}" y="{y}" '
                f'width="{bar_width}" height="{bar_height}" fill="{palette(index)}"/>',
                f'<text x="{x + bar_width // 2}" y="{margin_top + plot_height + 20}" '
                'font-size="12" font-family="Arial" fill="#374151" '
                f'text-anchor="middle">{xml_text(datum.label)}</text>',
                f'<text x="{x + bar_width // 2}" y="{max(42, y - 6)}" '
                'font-size="12" font-family="Arial" fill="#111827" '
                f'text-anchor="middle">{datum.value:g}</text>',
            ]
        )

    svg = svg_document(
        width=width,
        height=height,
        title=title,
        description="Deterministic local SVG bar chart",
        children=children,
    )
    return VectorArtifact(
        kind="chart.bar",
        body=svg,
        width=width,
        height=height,
        metadata={
            "data_hash_input": stable_json([datum.__dict__ for datum in rows]),
            "mark": "bar",
            "row_count": len(rows),
        },
    )

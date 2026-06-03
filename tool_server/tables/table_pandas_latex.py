from __future__ import annotations

from typing import Any, Iterable

from tool_server.tables.table_duckdb_html import render_table_svg
from tool_server.vector_renderer import VectorArtifact


def render_latex_compatible_table_svg(
    rows: Iterable[dict[str, Any]],
    *,
    columns: Iterable[str] | None = None,
    title: str = "Table",
    width: int = 720,
    row_height: int = 34,
) -> VectorArtifact:
    artifact = render_table_svg(
        rows,
        columns=columns,
        title=title,
        width=width,
        row_height=row_height,
    )
    metadata = dict(artifact.metadata or {})
    metadata["adapter"] = "latex-compatible"
    return VectorArtifact(
        kind=artifact.kind,
        body=artifact.body,
        width=artifact.width,
        height=artifact.height,
        metadata=metadata,
    )

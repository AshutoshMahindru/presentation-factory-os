from __future__ import annotations

from typing import Any, Iterable

from tool_server.vector_renderer import VectorArtifact, stable_json, svg_document, xml_text


def render_table_svg(
    rows: Iterable[dict[str, Any]],
    *,
    columns: Iterable[str] | None = None,
    title: str = "Table",
    width: int = 720,
    row_height: int = 34,
) -> VectorArtifact:
    normalized_rows = tuple(dict(row) for row in rows)
    if not normalized_rows:
        raise ValueError("table rows are required")

    column_tuple = tuple(columns) if columns is not None else _derive_columns(normalized_rows)
    if not column_tuple:
        raise ValueError("table columns are required")
    if width < 320:
        raise ValueError("table canvas is too small")

    header_height = 42
    title_height = 42
    height = title_height + header_height + row_height * len(normalized_rows) + 24
    col_width = width // len(column_tuple)
    children = [
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="24" y="28" font-size="18" font-family="Arial" '
        f'font-weight="700" fill="#111827">{xml_text(title)}</text>',
        f'<rect x="0" y="{title_height}" width="{width}" height="{header_height}" fill="#e8eef3"/>',
    ]

    for index, column in enumerate(column_tuple):
        x = index * col_width
        children.extend(
            [
                f'<line x1="{x}" y1="{title_height}" x2="{x}" y2="{height - 24}" '
                'stroke="#c7d0d9" stroke-width="1"/>',
                f'<text x="{x + 10}" y="{title_height + 27}" font-size="12" '
                f'font-family="Arial" font-weight="700" fill="#111827">{xml_text(column)}</text>',
            ]
        )
    children.append(
        f'<line x1="{width - 1}" y1="{title_height}" x2="{width - 1}" y2="{height - 24}" '
        'stroke="#c7d0d9" stroke-width="1"/>'
    )

    for row_index, row in enumerate(normalized_rows):
        y = title_height + header_height + row_index * row_height
        fill = "#ffffff" if row_index % 2 == 0 else "#f7f9fb"
        children.append(f'<rect x="0" y="{y}" width="{width}" height="{row_height}" fill="{fill}"/>')
        children.append(
            f'<line x1="0" y1="{y}" x2="{width}" y2="{y}" stroke="#d7dee5" stroke-width="1"/>'
        )
        for col_index, column in enumerate(column_tuple):
            value = row.get(column, "")
            children.append(
                f'<text x="{col_index * col_width + 10}" y="{y + 22}" font-size="12" '
                f'font-family="Arial" fill="#1f2937">{xml_text(value)}</text>'
            )
    children.append(
        f'<line x1="0" y1="{height - 24}" x2="{width}" y2="{height - 24}" '
        'stroke="#c7d0d9" stroke-width="1"/>'
    )

    svg = svg_document(
        width=width,
        height=height,
        title=title,
        description="Deterministic local SVG table",
        children=children,
    )
    return VectorArtifact(
        kind="table.svg",
        body=svg,
        width=width,
        height=height,
        metadata={
            "columns": list(column_tuple),
            "row_count": len(normalized_rows),
            "table_hash_input": stable_json(
                {"columns": column_tuple, "rows": normalized_rows}
            ),
        },
    )


def _derive_columns(rows: tuple[dict[str, Any], ...]) -> tuple[str, ...]:
    columns: set[str] = set()
    for row in rows:
        columns.update(str(column) for column in row)
    return tuple(sorted(columns))

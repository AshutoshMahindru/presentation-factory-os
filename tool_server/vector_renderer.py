from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from html import escape
from typing import Any, Iterable


SVG_NS = "http://www.w3.org/2000/svg"


@dataclass(frozen=True)
class VectorArtifact:
    kind: str
    body: str
    width: int
    height: int
    mime_type: str = "image/svg+xml"
    renderer: str = "pfos-local-svg-v1"
    metadata: dict[str, Any] | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()

    def as_payload(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "mime_type": self.mime_type,
            "renderer": self.renderer,
            "width": self.width,
            "height": self.height,
            "content_hash": self.content_hash,
            "body": self.body,
            "metadata": self.metadata or {},
        }


def svg_document(
    *,
    width: int,
    height: int,
    children: Iterable[str],
    title: str,
    description: str | None = None,
) -> str:
    if width <= 0 or height <= 0:
        raise ValueError("svg dimensions must be positive")
    title_node = f"<title>{xml_text(title)}</title>"
    description_node = (
        f"<desc>{xml_text(description)}</desc>" if description is not None else ""
    )
    child_text = "".join(children)
    return (
        f'<svg xmlns="{SVG_NS}" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img">'
        f"{title_node}{description_node}{child_text}</svg>"
    )


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def xml_text(value: Any) -> str:
    return escape(str(value), quote=False)


def xml_attr(value: Any) -> str:
    return escape(str(value), quote=True)


def palette(index: int) -> str:
    colors = (
        "#255f85",
        "#2e7d59",
        "#8a5a10",
        "#7a4f87",
        "#b2473e",
        "#3f6c2f",
    )
    return colors[index % len(colors)]

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from html import escape
from typing import Any


@dataclass(frozen=True)
class WebDeckRender:
    html: str
    content_hash: str
    slide_count: int
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RasterizedArtifact:
    renderer: str
    mime_type: str
    width: int
    height: int
    content_hash: str
    payload: bytes


def render_web_deck(deck: dict[str, Any]) -> WebDeckRender:
    """
    Render a deterministic, self-contained HTML deck.

    This is the local-safe contract used before a browser-backed renderer is
    available. It deliberately avoids remote assets and script execution.
    """

    slides = list(deck.get("slides", []) or [])
    warnings: list[str] = []
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>PFOS Deck</title>",
        "<style>",
        "body{margin:0;font-family:Inter,Arial,sans-serif;background:#f7f7f4;color:#1d1f23}",
        ".slide{width:1280px;min-height:720px;box-sizing:border-box;padding:64px;border-bottom:1px solid #d8d8d2}",
        ".eyebrow{font-size:18px;text-transform:uppercase;color:#5d6675}",
        "h1{font-size:54px;line-height:1.05;margin:18px 0 24px}",
        "p{font-size:28px;line-height:1.35;max-width:980px}",
        "</style>",
        "</head>",
        "<body>",
    ]

    for index, slide in enumerate(slides, start=1):
        slide_id = escape(str(slide.get("slide_id") or f"slide_{index:03d}"))
        content = slide.get("content", {}) or {}
        headline = escape(str(content.get("headline") or slide.get("headline") or "Untitled slide"))
        body = escape(str(content.get("body") or slide.get("body") or ""))
        materiality = escape(str(slide.get("materiality") or "unknown"))
        visual_quality = escape(str(slide.get("visual_quality") or "unknown"))
        if not body:
            warnings.append(f"{slide_id}: missing body text")
        parts.extend(
            [
                f'<section class="slide" data-slide-id="{slide_id}" data-materiality="{materiality}" data-visual-quality="{visual_quality}">',
                f'<div class="eyebrow">{index:02d} / {materiality}</div>',
                f"<h1>{headline}</h1>",
                f"<p>{body}</p>",
                "</section>",
            ]
        )

    parts.extend(["</body>", "</html>"])
    html = "\n".join(parts)
    return WebDeckRender(
        html=html,
        content_hash=sha256(html.encode("utf-8")).hexdigest(),
        slide_count=len(slides),
        warnings=tuple(warnings),
    )


class HeadlessRasterizer:
    """
    Deterministic stand-in for a browser rasterizer.

    The payload is a compact SVG preview encoded as bytes. Browser-backed PNG
    rendering can be plugged in later without changing the output contract.
    """

    def rasterize(self, html: str, *, width: int = 1280, height: int = 720) -> RasterizedArtifact:
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        digest = sha256(html.encode("utf-8")).hexdigest()
        preview = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">'
            '<rect width="100%" height="100%" fill="#f7f7f4"/>'
            f'<text x="48" y="80" fill="#1d1f23" font-size="28">PFOS render {digest[:12]}</text>'
            "</svg>"
        )
        return RasterizedArtifact(
            renderer="deterministic-svg-rasterizer",
            mime_type="image/svg+xml",
            width=width,
            height=height,
            content_hash=digest,
            payload=preview.encode("utf-8"),
        )

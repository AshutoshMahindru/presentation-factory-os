from deck_builder.render_web_deck import HeadlessRasterizer, render_web_deck


def deck():
    return {
        "slides": [
            {
                "slide_id": "slide_001",
                "materiality": "high",
                "visual_quality": "code_generated",
                "content": {
                    "headline": "Growth thesis",
                    "body": "Evidence-backed expansion plan.",
                    "evidence_refs": ["src_001"],
                },
            }
        ]
    }


def test_web_deck_render_is_deterministic_and_escapes_content():
    payload = deck()
    payload["slides"][0]["content"]["headline"] = "Growth < thesis"

    first = render_web_deck(payload)
    second = render_web_deck(payload)

    assert first.content_hash == second.content_hash
    assert first.slide_count == 1
    assert "Growth &lt; thesis" in first.html


def test_headless_rasterizer_returns_stable_svg_contract():
    rendered = render_web_deck(deck())
    artifact = HeadlessRasterizer().rasterize(rendered.html, width=640, height=360)

    assert artifact.renderer == "deterministic-svg-rasterizer"
    assert artifact.mime_type == "image/svg+xml"
    assert artifact.width == 640
    assert artifact.height == 360
    assert artifact.content_hash == rendered.content_hash
    assert artifact.payload.startswith(b"<svg")

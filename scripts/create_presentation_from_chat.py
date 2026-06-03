from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from deck_builder.chat_presentation import create_presentation_from_chat


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a deterministic PFOS presentation preview from a chat prompt."
    )
    parser.add_argument("message", help="Chat prompt describing the presentation to create.")
    parser.add_argument(
        "--context-json",
        default="{}",
        help="Inline JSON object with project_context, source_refs, financial_cells, or decision_required.",
    )
    parser.add_argument(
        "--context-file",
        help="Path to a JSON file containing project_context.",
    )
    parser.add_argument(
        "--out",
        default="tool_server/outputs/chat_presentation.html",
        help="HTML preview output path.",
    )
    parser.add_argument(
        "--metadata-out",
        default="",
        help="Optional JSON output path for the full presentation run payload.",
    )
    args = parser.parse_args()

    context = _load_context(args.context_json, args.context_file)
    run = create_presentation_from_chat(args.message, context)
    payload = run.to_payload()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload["web_preview"]["html"], encoding="utf-8")

    if args.metadata_out:
        metadata_out = Path(args.metadata_out)
        metadata_out.parent.mkdir(parents=True, exist_ok=True)
        metadata_out.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(_summary_payload(payload, out), indent=2, sort_keys=True))
    return 0


def _load_context(context_json: str, context_file: str | None) -> dict[str, Any]:
    if context_file:
        raw = Path(context_file).read_text(encoding="utf-8")
    else:
        raw = context_json
    context = json.loads(raw)
    if not isinstance(context, dict):
        raise ValueError("context must be a JSON object")
    return context


def _summary_payload(payload: dict[str, Any], out: Path) -> dict[str, Any]:
    return {
        "run_id": payload["run_id"],
        "html": str(out),
        "slide_count": payload["web_preview"]["slide_count"],
        "content_hash": payload["web_preview"]["content_hash"],
        "export_allowed": payload["export_gate"]["export_allowed"],
        "blocking_reasons": payload["export_gate"]["blocking_reasons"],
        "evidence_gaps": payload["evidence_gaps"],
        "recommended_next_action": payload["recommended_next_action"],
        "formats": payload["export_metadata"]["formats"],
    }


if __name__ == "__main__":
    raise SystemExit(main())

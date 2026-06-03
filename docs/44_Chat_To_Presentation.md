# Chat To Presentation

PFOS now has a deterministic local path from a chat prompt to a validated deck preview. It does not require remote LLM API keys.

## Local CLI

```bash
python3 scripts/create_presentation_from_chat.py \
  "Create a 5 slide board deck for PFOS automation reliability." \
  --context-json '{"source_refs":["source_reliability"],"decision_required":"Approve the reliability roadmap."}' \
  --out tool_server/outputs/first_chat_presentation.html \
  --metadata-out tool_server/outputs/first_chat_presentation.json
```

Open the generated HTML preview:

```bash
open tool_server/outputs/first_chat_presentation.html
```

## API

Standalone:

```http
POST /presentations/from-chat
```

Project-scoped:

```http
POST /projects/{project_id}/presentations/from-chat
```

Payload:

```json
{
  "content": "Create a CFO presentation for PFOS unit economics.",
  "project_context": {
    "source_refs": ["source_finance"],
    "decision_required": "Approve economics review."
  }
}
```

Response includes:

- `brief`
- `pillars`
- `slides`
- `export_gate`
- `web_preview`
- `export_metadata`
- `evidence_gaps`
- `recommended_next_action`

If no external sources are supplied, the preview still renders with provisional operator-brief evidence and explicit evidence gaps. This keeps the chat flow moving without pretending unsupported claims are fully evidence-backed.

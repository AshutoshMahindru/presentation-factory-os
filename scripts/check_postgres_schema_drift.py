from __future__ import annotations

import argparse
import difflib
from pathlib import Path
from typing import Sequence


DEFAULT_DOCS_SCHEMA = Path("docs/04_Database_Schemas.sql")
DEFAULT_INIT_SCHEMA = Path("infra/postgres/init/001_schema.sql")


def normalize_sql(content: str) -> str:
    """Normalize formatting differences that do not change SQL content."""
    lines = [line.rstrip() for line in content.splitlines()]

    while lines and lines[-1] == "":
        lines.pop()

    return "\n".join(lines)


def schemas_match(docs_schema: Path, init_schema: Path) -> bool:
    return normalize_sql(docs_schema.read_text()) == normalize_sql(init_schema.read_text())


def unified_diff(docs_schema: Path, init_schema: Path) -> str:
    docs_normalized = normalize_sql(docs_schema.read_text()).splitlines()
    init_normalized = normalize_sql(init_schema.read_text()).splitlines()

    return "\n".join(
        difflib.unified_diff(
            docs_normalized,
            init_normalized,
            fromfile=str(docs_schema),
            tofile=str(init_schema),
            lineterm="",
        )
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check docs and Postgres init schemas for substantive drift."
    )
    parser.add_argument(
        "--docs-schema",
        type=Path,
        default=DEFAULT_DOCS_SCHEMA,
        help=f"Canonical documented schema path. Defaults to {DEFAULT_DOCS_SCHEMA}.",
    )
    parser.add_argument(
        "--init-schema",
        type=Path,
        default=DEFAULT_INIT_SCHEMA,
        help=f"Postgres init schema path. Defaults to {DEFAULT_INIT_SCHEMA}.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)

    if schemas_match(args.docs_schema, args.init_schema):
        print(
            "PASS Postgres schema drift: "
            f"{args.docs_schema} matches {args.init_schema}"
        )
        return 0

    print(
        "FAIL Postgres schema drift: "
        f"{args.docs_schema} differs from {args.init_schema}"
    )
    print(unified_diff(args.docs_schema, args.init_schema))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

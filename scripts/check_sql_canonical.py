#!/usr/bin/env python3
"""
SQL Canonicalization Drift Check (Step 124).

Ensures infra/postgres/init/001_schema.sql is a byte-for-byte copy of
docs/04_Database_Schemas.sql, which is the single canonical source of truth.

Fails with exit code 1 and prints diff if they diverge.
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path

CANONICAL = Path("docs/04_Database_Schemas.sql")
DEPLOYABLE = Path("infra/postgres/init/001_schema.sql")


def main() -> int:
    if not CANONICAL.exists():
        print(f"FAIL: Canonical schema missing: {CANONICAL}", file=sys.stderr)
        return 1
    if not DEPLOYABLE.exists():
        print(f"FAIL: Deployable schema missing: {DEPLOYABLE}", file=sys.stderr)
        return 1

    canonical_text = CANONICAL.read_text(encoding="utf-8")
    deployable_text = DEPLOYABLE.read_text(encoding="utf-8")

    if canonical_text == deployable_text:
        print("OK: Deployable schema is byte-for-byte canonical.")
        return 0

    print("FAIL: Deployable schema drifted from canonical source.", file=sys.stderr)
    diff = difflib.unified_diff(
        canonical_text.splitlines(keepends=True),
        deployable_text.splitlines(keepends=True),
        fromfile=str(CANONICAL),
        tofile=str(DEPLOYABLE),
    )
    sys.stderr.writelines(diff)
    return 1


if __name__ == "__main__":
    sys.exit(main())

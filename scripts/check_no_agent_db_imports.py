from pathlib import Path

BANNED = [
    "neo4j",
    "psycopg2",
    "asyncpg",
    "sqlalchemy",
    "qdrant_client",
    "pymongo",
    "redis",
]

def main() -> None:
    failed = []

    for path in Path("agents").glob("**/*.py"):
        text = path.read_text()
        for item in BANNED:
            if f"import {item}" in text or f"from {item}" in text:
                failed.append((str(path), item))

    if failed:
        raise SystemExit(f"Raw DB imports found in agents: {failed}")

    print("PASS: agents contain no raw DB imports")

if __name__ == "__main__":
    main()

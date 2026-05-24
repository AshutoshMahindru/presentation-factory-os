from pathlib import Path

BANNED = ["neo4j", "psycopg2", "asyncpg", "sqlalchemy", "qdrant_client", "pymongo", "redis"]

def test_agents_do_not_import_raw_db_clients():
    for path in Path("agents").glob("**/*.py"):
        text = path.read_text()
        for banned in BANNED:
            assert f"import {banned}" not in text
            assert f"from {banned}" not in text

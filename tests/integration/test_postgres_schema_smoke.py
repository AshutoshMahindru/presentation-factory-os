import subprocess


COMPOSE = ["docker", "compose", "-f", "docker-compose.apps.yaml"]


def psql(sql: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "postgres",
            "psql",
            "-U",
            "pfos",
            "-d",
            "pfos",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_projects_accepts_valid_project():
    sql = """
    INSERT INTO projects (name, audience, audience_profile)
    VALUES (
      'Smoke Test Project',
      'Investment committee',
      '{"decision_maker_type":"ic_partner"}'::jsonb
    )
    RETURNING id;
    """
    result = psql(sql)
    assert result.returncode == 0, result.stderr


def test_projects_blocked_requires_blocked_reason():
    sql = """
    INSERT INTO projects (name, audience, blocked)
    VALUES ('Invalid Blocked Project', 'Investment committee', TRUE);
    """
    result = psql(sql)
    assert result.returncode != 0
    assert "projects_check" in result.stderr or "violates check constraint" in result.stderr


def test_financial_cells_excel_requires_parser_provenance():
    setup = """
    INSERT INTO projects (name, audience, audience_profile)
    VALUES ('Finance Smoke Project', 'Investment committee', '{}'::jsonb)
    RETURNING id;
    """
    project_result = psql(setup)
    assert project_result.returncode == 0, project_result.stderr

    project_id = project_result.stdout.splitlines()[2].strip()

    sql = f"""
    INSERT INTO financial_cells (
      project_id, scenario, cell_ref, label, value, formula, ingestion_source_type
    )
    VALUES (
      '{project_id}', 'base', 'FM!REV_M01_BASE', 'Revenue M01', 100, '=A1+B1', 'excel_xlsx'
    );
    """
    result = psql(sql)
    assert result.returncode != 0
    assert "parser_provenance" in result.stderr or "violates check constraint" in result.stderr

import subprocess
from uuid import uuid4


COMPOSE = ["docker", "compose", "-f", "docker-compose.apps.yaml"]


def cypher(query: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            *COMPOSE,
            "exec",
            "-T",
            "neo4j",
            "cypher-shell",
            "-u",
            "neo4j",
            "-p",
            "pfos_neo4j_password",
            query,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_can_create_project_source_claim_with_supported_edge():
    project_id = f"project_{uuid4()}"
    source_id = f"source_{uuid4()}"
    claim_id = f"claim_{uuid4()}"

    query = f"""
    CREATE (p:Project {{id: '{project_id}', name: 'Smoke Project', status: 'active', current_phase: 'research'}})
    CREATE (s:Source {{id: '{source_id}', project_id: '{project_id}', status: 'active', title: 'Smoke Source'}})
    CREATE (c:Claim {{id: '{claim_id}', project_id: '{project_id}', text: 'Evidence-backed claim', materiality: 'high', audience_relevance: 'core', status: 'supported'}})
    CREATE (c)-[:SUPPORTED_BY {{source_id: '{source_id}', confidence: 0.9}}]->(s)
    CREATE (p)-[:HAS_CLAIM]->(c)
    RETURN c.id AS claim_id;
    """

    result = cypher(query)
    assert result.returncode == 0, result.stderr
    assert claim_id in result.stdout


def test_retraction_marks_single_supported_claim_unsupported():
    project_id = f"project_{uuid4()}"
    source_id = f"source_{uuid4()}"
    claim_id = f"claim_{uuid4()}"

    setup = f"""
    CREATE (p:Project {{id: '{project_id}', name: 'Retraction Project', status: 'active', current_phase: 'research'}})
    CREATE (s:Source {{id: '{source_id}', project_id: '{project_id}', status: 'active', title: 'Retractable Source'}})
    CREATE (c:Claim {{id: '{claim_id}', project_id: '{project_id}', text: 'Claim to retract', materiality: 'high', audience_relevance: 'core', status: 'supported'}})
    CREATE (c)-[:SUPPORTED_BY {{source_id: '{source_id}', confidence: 0.9}}]->(s)
    RETURN c.id;
    """
    setup_result = cypher(setup)
    assert setup_result.returncode == 0, setup_result.stderr

    retract = f"""
    MATCH (s:Source {{id: '{source_id}'}})
    SET s.status = 'retracted'
    WITH s
    MATCH (c:Claim)-[r:SUPPORTED_BY]->(s)
    SET r.status = 'retracted'
    WITH c
    OPTIONAL MATCH (c)-[:SUPPORTED_BY]->(active:Source {{status: 'active'}})
    WITH c, count(active) AS active_support_count
    WHERE active_support_count < 2
    SET c.status = 'unsupported'
    RETURN c.id AS claim_id, c.status AS status;
    """
    retract_result = cypher(retract)
    assert retract_result.returncode == 0, retract_result.stderr
    assert "unsupported" in retract_result.stdout

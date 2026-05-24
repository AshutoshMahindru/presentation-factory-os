import subprocess


COMPOSE = ["docker", "compose", "-f", "docker-compose.apps.yaml"]


def run_from_agent(command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*COMPOSE, "exec", "-T", "agent-service", "sh", "-lc", command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_agent_can_reach_allowed_http_services():
    allowed_targets = [
        ("workflow-service", 8000),
        ("retrieval-engine", 8002),
        ("tool-server", 8003),
    ]

    for host, port in allowed_targets:
        result = run_from_agent(f"nc -zvw2 {host} {port}")
        assert result.returncode == 0, (
            f"agent-service should reach {host}:{port}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )


def test_agent_cannot_reach_data_stores():
    blocked_targets = [
        ("postgres", 5432),
        ("neo4j", 7687),
        ("qdrant", 6333),
    ]

    for host, port in blocked_targets:
        result = run_from_agent(f"nc -zvw2 {host} {port}")
        assert result.returncode != 0, (
            f"agent-service must not reach {host}:{port}\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )

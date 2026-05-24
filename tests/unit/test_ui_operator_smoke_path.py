from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_repo_file(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_operator_smoke_path_runbook_documents_the_required_path() -> None:
    runbook = read_repo_file("docs/35_UI_Operator_Smoke_Path.md")

    required_phrases = [
        "Open the project dashboard",
        "Review project health",
        "Inspect hard-gate results and queue status",
        "Inspect approval and quorum status",
        "Inspect export readiness",
    ]

    for phrase in required_phrases:
        assert phrase in runbook


def test_ui_api_client_exposes_operator_status_helpers() -> None:
    api_client = read_repo_file("ui/lib/api.ts")

    required_contracts = [
        "getProjectControlPlaneHealth",
        "getProjectOutboxStatus",
        "getProjectSourceRetractionStatus",
        "getProjectHardGateStatus",
        "getApprovalStatus",
        "requestPhaseTransition",
        "OutboxQueueRow",
        "SourceLifecycleEventStatus",
        "/health/projects/${encodedProjectId}/outbox",
        "/health/projects/${encodedProjectId}/source-retractions",
        "/health/projects/${encodedProjectId}/hard-gates",
        "/projects/${encodePathSegment(projectId)}/approvals/status/${encodePathSegment(phase)}",
    ]

    for contract in required_contracts:
        assert contract in api_client


def test_operator_smoke_path_ui_files_are_present() -> None:
    required_paths = [
        "ui/app/approvals/page.tsx",
        "ui/components/ApprovalLedger.tsx",
        "ui/components/ExportReadinessPanel.tsx",
        "ui/components/HardGateStatusPanel.tsx",
        "ui/components/ProjectHealth.tsx",
        "ui/components/QueueStatusPanel.tsx",
    ]

    for path in required_paths:
        assert (ROOT / path).is_file()


def test_project_health_component_surfaces_dashboard_status() -> None:
    project_health = read_repo_file("ui/components/ProjectHealth.tsx")

    required_render_labels = [
        "Project dashboard",
        "Control-plane status",
        "Approval status",
        "No phase approval snapshot selected.",
        "Request transition",
        "QueueStatusPanel",
        "HardGateStatusPanel",
    ]

    for label in required_render_labels:
        assert label in project_health

    assert "export function ProjectHealth" in project_health
    assert "export default ProjectHealth" in project_health


def test_queue_and_hard_gate_panels_surface_operator_blockers() -> None:
    queue_status = read_repo_file("ui/components/QueueStatusPanel.tsx")
    hard_gate_status = read_repo_file("ui/components/HardGateStatusPanel.tsx")

    for label in [
        "Queue status",
        "Pending outbox rows",
        "Failed outbox rows",
        "Pending source retraction cascades",
        "Failed source lifecycle events",
    ]:
        assert label in queue_status

    for label in [
        "Hard-gate status",
        "Checks evaluated",
        "Failed checks",
        "Gate result",
        "No hard-gate checks returned.",
    ]:
        assert label in hard_gate_status


def test_approval_page_and_ledger_surface_quorum_status() -> None:
    approvals_page = read_repo_file("ui/app/approvals/page.tsx")
    approval_ledger = read_repo_file("ui/components/ApprovalLedger.tsx")

    for label in [
        "Operator approvals",
        "Approval ledger",
        "Project ID",
        "Load status",
        "createPfosApiClient",
        "getApprovalStatus",
    ]:
        assert label in approvals_page

    for label in [
        "Approval quorum",
        "Current ledger snapshot",
        "Quorum met",
        "Quorum open",
        "Ledger entries",
        "Missing roles",
        "Escalation status",
    ]:
        assert label in approval_ledger


def test_export_readiness_panel_surfaces_delivery_blockers() -> None:
    export_readiness = read_repo_file("ui/components/ExportReadinessPanel.tsx")

    for label in [
        "Export readiness",
        "Read-only gate summary",
        "Export blockers",
        "Visual readiness",
        "Source appendix readiness",
        "Financial reference readiness",
        "Stale artifact readiness",
        "No blocking export condition is surfaced.",
    ]:
        assert label in export_readiness

    assert "export function ExportReadinessPanel" in export_readiness
    assert "export default ExportReadinessPanel" in export_readiness


def test_static_ui_smoke_does_not_assume_unconfigured_frontend_tooling() -> None:
    package_json = read_repo_file("package.json")

    assert package_json == ""


def test_operator_ui_components_do_not_introduce_fake_data_paths() -> None:
    forbidden_markers = [
        "fake",
        "fixture",
        "mock",
        "placeholderData",
        "dummy",
    ]

    component_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "ui/components").glob("*.tsx"))
    )
    lowered_component_text = component_text.lower()

    for marker in forbidden_markers:
        assert marker.lower() not in lowered_component_text

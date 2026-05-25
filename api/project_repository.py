from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from system.approval_ledger_repository import ApprovalLedgerRepository
from system.db import execute_psql


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    name: str
    audience: str
    audience_profile: dict[str, Any]
    current_phase: str


approval_ledger_repository = ApprovalLedgerRepository()


class ProjectRepository:
    """
    Baby-step Postgres-backed project repository.

    Uses the shared system DB helper so connection behavior is centralized while
    preserving the repository method contract.
    """

    def create_project(
        self,
        name: str,
        audience: str,
        audience_profile: dict[str, Any],
        client_name: str | None = None,
        decision_required: str | None = None,
        objection_preemption_map: dict[str, Any] | None = None,
    ) -> ProjectRecord:
        audience_profile_json = self._json(audience_profile)
        objection_map_json = self._json(objection_preemption_map or {})

        sql = f"""
        INSERT INTO projects (
          name,
          client_name,
          audience,
          audience_profile,
          decision_required,
          objection_preemption_map,
          current_phase
        )
        VALUES (
          '{self._sql(name)}',
          {self._nullable(client_name)},
          '{self._sql(audience)}',
          '{audience_profile_json}'::jsonb,
          {self._nullable(decision_required)},
          '{objection_map_json}'::jsonb,
          'created'
        )
        RETURNING id, name, audience, audience_profile::text, current_phase;
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        return self._parse_project_record(result.stdout)

    def get_project(self, project_id: str) -> ProjectRecord | None:
        sql = f"""
        SELECT id, name, audience, audience_profile::text, current_phase
        FROM projects
        WHERE id = '{self._sql(project_id)}';
        """
        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        if not result.stdout.strip():
            return None

        return self._parse_project_record(result.stdout)



    def record_approval(
        self,
        project_id: str,
        phase: str,
        actor_email: str,
        role: str,
        decision: str,
        rubric_score_snapshot: dict[str, Any],
        notes: str | None = None,
    ) -> None:
        approval_ledger_repository.record_approval(
            project_id=project_id,
            phase=phase,
            actor_email=actor_email,
            role=role,
            decision=decision,
            rubric_score_snapshot=rubric_score_snapshot,
            notes=notes,
        )

    def list_approvals_for_phase(self, project_id: str, phase: str) -> list[dict[str, Any]]:
        return approval_ledger_repository.list_approval_dicts_for_phase(project_id, phase)

    def get_observability_metrics_snapshot(self) -> dict[str, Any]:
        sql = """
        SELECT jsonb_build_object(
          'project_count', (SELECT count(*) FROM projects),
          'phase_transition_count', (SELECT count(*) FROM phase_transitions),
          'approval_count', (SELECT count(*) FROM approval_ledger),
          'open_outbox_count', (SELECT count(*) FROM outbox WHERE processed = FALSE),
          'failed_outbox_count', (SELECT count(*) FROM outbox WHERE processed = FALSE AND error_count > 0),
          'open_source_retraction_count', (
            SELECT count(*)
            FROM source_lifecycle_events
            WHERE event_type = 'retracted'
              AND processing_status IN ('pending', 'processing', 'failed', 'blocked')
          ),
          'retrieval_routing_log_count', (SELECT count(*) FROM retrieval_routing_log),
          'rubric_score_count', (SELECT count(*) FROM rubric_scores)
        )::text;
        """
        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        return self._parse_json_result(result.stdout)

    def list_phase_traces(self, project_id: str) -> list[dict[str, Any]]:
        sql = f"""
        SELECT COALESCE(
          jsonb_agg(
            jsonb_build_object(
              'trace_id', trace_id::text,
              'phase', phase::text,
              'span_name', span_name,
              'service_name', service_name,
              'started_at', to_char(started_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
              'ended_at', CASE
                WHEN ended_at IS NULL THEN NULL
                ELSE to_char(ended_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
              END,
              'duration_ms', duration_ms,
              'status', status,
              'metadata', metadata
            )
            ORDER BY started_at DESC, id DESC
          ),
          '[]'::jsonb
        )::text
        FROM phase_traces
        WHERE project_id = '{self._sql(project_id)}';
        """
        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        return list(self._parse_json_result(result.stdout))

    def list_retrieval_routing_logs(self, project_id: str) -> list[dict[str, Any]]:
        sql = f"""
        SELECT COALESCE(
          jsonb_agg(
            jsonb_build_object(
              'request_id', request_id::text,
              'query', query,
              'query_classification', query_classification,
              'mode', mode::text,
              'forced_hybrid', forced_hybrid,
              'escalation_reason', escalation_reason,
              'confidence', confidence::float,
              'item_count', item_count,
              'gaps', gaps,
              'created_at', to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
            )
            ORDER BY created_at DESC, id DESC
          ),
          '[]'::jsonb
        )::text
        FROM retrieval_routing_log
        WHERE project_id = '{self._sql(project_id)}';
        """
        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        return list(self._parse_json_result(result.stdout))

    def list_rubric_scores(self, project_id: str, phase: str) -> list[dict[str, Any]]:
        sql = f"""
        SELECT COALESCE(
          jsonb_agg(
            jsonb_build_object(
              'dimension', dimension,
              'score_version', score_version,
              'score', score::float,
              'weight', weight::float,
              'evaluator_type', evaluator_type,
              'evaluator_model', evaluator_model,
              'blocking', blocking,
              'threshold', threshold::float,
              'trace_id', trace_id::text,
              'created_at', to_char(created_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
            )
            ORDER BY created_at DESC, dimension ASC
          ),
          '[]'::jsonb
        )::text
        FROM rubric_scores
        WHERE project_id = '{self._sql(project_id)}'
          AND phase = '{self._sql(phase)}';
        """
        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)
        return list(self._parse_json_result(result.stdout))


    def record_phase_transition(
        self,
        project_id: str,
        from_phase: str,
        to_phase: str,
        transition_kind: str,
        guard_results: list[dict[str, Any]],
        hard_gate_results: dict[str, Any],
        state_machine_version: str,
        reason: str | None,
        actor_email: str,
    ) -> None:
        guard_results_json = self._json_array(guard_results)
        hard_gate_results_json = self._json(hard_gate_results)

        sql = f"""
        INSERT INTO phase_transitions (
          project_id,
          from_phase,
          to_phase,
          transition_kind,
          guard_results,
          hard_gate_results,
          state_machine_version,
          reason,
          actor_email
        )
        VALUES (
          '{self._sql(project_id)}',
          '{self._sql(from_phase)}',
          '{self._sql(to_phase)}',
          '{self._sql(transition_kind)}',
          '{guard_results_json}'::jsonb,
          '{hard_gate_results_json}'::jsonb,
          '{self._sql(state_machine_version)}',
          {self._nullable(reason)},
          '{self._sql(actor_email)}'
        );
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)


    def update_phase(self, project_id: str, to_phase: str) -> None:
        sql = f"""
        UPDATE projects
        SET current_phase = '{self._sql(to_phase)}',
            updated_at = now()
        WHERE id = '{self._sql(project_id)}';
        """
        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

    def _parse_project_record(self, stdout: str) -> ProjectRecord:
        for line in stdout.splitlines():
            if "|" not in line:
                continue

            parts = [part.strip() for part in line.split("|", maxsplit=4)]
            if len(parts) != 5:
                continue

            project_id, name, audience, audience_profile_text, current_phase = parts

            if project_id == "id":
                continue

            return ProjectRecord(
                project_id=project_id,
                name=name,
                audience=audience,
                audience_profile=json.loads(audience_profile_text),
                current_phase=current_phase,
            )

        raise RuntimeError(f"Could not parse project record from psql output: {stdout}")

    def _parse_json_result(self, stdout: str) -> Any:
        for line in stdout.splitlines():
            candidate = line.strip()
            if not candidate:
                continue
            if candidate[0] in "[{":
                return json.loads(candidate)
        raise RuntimeError(f"Could not parse JSON from psql output: {stdout}")

    def _psql(self, sql: str):
        return execute_psql(sql)


    def _json_array(self, value: list[dict[str, Any]]) -> str:
        return self._sql(json.dumps(value, separators=(",", ":")))

    def _json(self, value: dict[str, Any]) -> str:
        return self._sql(json.dumps(value, separators=(",", ":")))

    def _sql(self, value: str) -> str:
        return str(value).replace("'", "''")

    def _nullable(self, value: str | None) -> str:
        if value is None:
            return "NULL"
        return f"'{self._sql(value)}'"


project_repository = ProjectRepository()

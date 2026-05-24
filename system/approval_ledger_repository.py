from __future__ import annotations

import json
import subprocess
from typing import Any

from system.approval_quorum import ApprovalEntry


COMPOSE_FILE = "docker-compose.apps.yaml"


class ApprovalLedgerRepository:
    """
    Postgres-backed approval ledger repository.

    This repository is intentionally deterministic and snapshot-window aware.
    Approval rows count toward quorum only if they were created after the
    latest successful entry into the evaluated phase.
    """

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
        snapshot_json = self._json(rubric_score_snapshot)

        sql = f"""
        INSERT INTO approval_ledger (
          project_id,
          phase,
          actor_email,
          role,
          decision,
          rubric_score_snapshot,
          notes
        )
        VALUES (
          '{self._sql(project_id)}',
          '{self._sql(phase)}',
          '{self._sql(actor_email)}',
          '{self._sql(role)}',
          '{self._sql(decision)}',
          '{snapshot_json}'::jsonb,
          {self._nullable(notes)}
        );
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

    def list_approval_dicts_for_phase(self, project_id: str, phase: str) -> list[dict[str, Any]]:
        return [
            {
                "actor_email": entry.actor_email,
                "role": entry.role,
                "decision": entry.decision,
            }
            for entry in self.list_approvals_for_phase(project_id, phase)
        ]

    def list_approvals_for_phase(self, project_id: str, phase: str) -> list[ApprovalEntry]:
        sql = f"""
        WITH latest_phase_entry AS (
          SELECT max(created_at) AS entered_at
          FROM phase_transitions
          WHERE project_id = '{self._sql(project_id)}'
            AND to_phase = '{self._sql(phase)}'
            AND transition_kind IN ('forward', 'initial')
        )
        SELECT
          approval_ledger.actor_email,
          approval_ledger.role,
          approval_ledger.decision
        FROM approval_ledger
        CROSS JOIN latest_phase_entry
        WHERE approval_ledger.project_id = '{self._sql(project_id)}'
          AND approval_ledger.phase = '{self._sql(phase)}'
          AND (
            latest_phase_entry.entered_at IS NULL
            OR approval_ledger.created_at > latest_phase_entry.entered_at
          )
        ORDER BY approval_ledger.created_at ASC;
        """

        result = self._psql(sql)
        if result.returncode != 0:
            raise RuntimeError(result.stderr)

        entries: list[ApprovalEntry] = []
        for line in result.stdout.splitlines():
            if "|" not in line:
                continue

            actor_email, role, decision = [part.strip() for part in line.split("|")]
            entries.append(
                ApprovalEntry(
                    actor_email=actor_email,
                    role=role,
                    decision=decision,
                )
            )

        return entries

    def _psql(self, sql: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                COMPOSE_FILE,
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
                "-A",
                "-t",
                "-F",
                "|",
                "-c",
                sql,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _json(self, value: dict[str, Any]) -> str:
        return self._sql(json.dumps(value))

    def _nullable(self, value: str | None) -> str:
        if value is None:
            return "NULL"
        return f"'{self._sql(value)}'"

    def _sql(self, value: str) -> str:
        return str(value).replace("'", "''")

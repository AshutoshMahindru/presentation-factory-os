import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.check_sql_canonical import CANONICAL, DEPLOYABLE, main


class TestCheckSqlCanonical:
    def test_identical_files_returns_zero(self, tmp_path: Path) -> None:
        content = "-- identical\n"
        with patch("scripts.check_sql_canonical.CANONICAL", tmp_path / "canonical.sql"), \
             patch("scripts.check_sql_canonical.DEPLOYABLE", tmp_path / "deployable.sql"):
            (tmp_path / "canonical.sql").write_text(content, encoding="utf-8")
            (tmp_path / "deployable.sql").write_text(content, encoding="utf-8")
            assert main() == 0

    def test_different_files_returns_one(self, tmp_path: Path) -> None:
        with patch("scripts.check_sql_canonical.CANONICAL", tmp_path / "canonical.sql"), \
             patch("scripts.check_sql_canonical.DEPLOYABLE", tmp_path / "deployable.sql"):
            (tmp_path / "canonical.sql").write_text("-- a\n", encoding="utf-8")
            (tmp_path / "deployable.sql").write_text("-- b\n", encoding="utf-8")
            assert main() == 1

    def test_missing_canonical_returns_one(self, tmp_path: Path) -> None:
        with patch("scripts.check_sql_canonical.CANONICAL", tmp_path / "missing.sql"), \
             patch("scripts.check_sql_canonical.DEPLOYABLE", tmp_path / "deployable.sql"):
            (tmp_path / "deployable.sql").write_text("-- x\n", encoding="utf-8")
            assert main() == 1

    def test_missing_deployable_returns_one(self, tmp_path: Path) -> None:
        with patch("scripts.check_sql_canonical.CANONICAL", tmp_path / "canonical.sql"), \
             patch("scripts.check_sql_canonical.DEPLOYABLE", tmp_path / "missing.sql"):
            (tmp_path / "canonical.sql").write_text("-- x\n", encoding="utf-8")
            assert main() == 1

    def test_real_files_are_canonical(self) -> None:
        """End-to-end: the actual committed files must match."""
        assert main() == 0


class TestCliInvocation:
    def test_runs_as_script(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "scripts.check_sql_canonical"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

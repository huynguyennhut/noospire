"""Lab launcher isolation, without starting processes or reading customer data."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("assessment_lab", ROOT / "scripts/assessment_lab.py")
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


def test_lab_mirrors_data_settings_and_reuses_private_generated_identity(tmp_path):
    directory = tmp_path / "lab"
    first = lab.environment(directory, create=True)
    second = lab.environment(directory, create=True)
    assert first["DATABASE_URL"] == first["SENTINEL_DATABASE_URL"]
    assert str(directory) in first["DATABASE_URL"]
    assert first["STORAGE_DIR"] == first["SENTINEL_STORAGE_DIR"] == str(directory / "storage")
    assert first["SECRET_KEY"] == second["SECRET_KEY"] and len(first["SECRET_KEY"]) >= 32
    assert first["SOLE_OWNER_EMAIL"] == "owner@pilot-test.invalid"
    assert (directory / "lab.json").stat().st_mode & 0o777 == 0o600
    assert not (directory / "checks.db").exists()  # environment creation does not initialize/seed data
    assert json.loads((directory / "lab.json").read_text())["kind"] == "noosforge-isolated-ui-lab/1"


def test_lab_refuses_nonempty_unmarked_data(tmp_path):
    (tmp_path / "retained-evidence.txt").write_text("synthetic preserved evidence")
    with pytest.raises(ValueError, match="Refusing a non-empty"):
        lab.environment(tmp_path, create=True)
    assert (tmp_path / "retained-evidence.txt").read_text() == "synthetic preserved evidence"

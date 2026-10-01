"""Settings: what serving needs, and where .env is read from."""

import subprocess
import sys
from pathlib import Path

import pytest

from owcsmuse import config
from owcsmuse.config import Settings, load_settings

ROOT = Path(config.__file__).resolve().parent.parent


@pytest.fixture
def clean_env(monkeypatch):
    for name in ("FACEIT_API_KEY", "OWCS_FACEIT_API_KEY", "DATABASE_URL", "OWCS_DATABASE_URL", "LIQUIPEDIA_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_serve_settings_load_with_only_database_url(clean_env, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@host:5432/db")
    settings = Settings(_env_file=None)
    assert settings.faceit_api_key is None
    assert settings.database_url == "postgresql://u:p@host:5432/db"
    assert load_settings(_env_file=None).database_url == settings.database_url


def test_database_url_has_no_fallback(clean_env):
    with pytest.raises(Exception) as err:
        Settings(_env_file=None)
    assert "DATABASE_URL" in str(err.value)


def test_ingest_demands_the_faceit_key_at_the_point_of_use(clean_env):
    settings = Settings(_env_file=None, database_url="postgresql://unused")
    with pytest.raises(RuntimeError, match="FACEIT_API_KEY"):
        settings.require_faceit_key()
    assert Settings(_env_file=None, database_url="x", faceit_api_key="k").require_faceit_key() == "k"


def test_env_file_is_the_project_roots_not_the_working_directory():
    assert Settings.model_config["env_file"] == ROOT / ".env"
    assert Path(Settings.model_config["env_file"]).is_absolute()


def test_env_file_is_found_from_another_working_directory(tmp_path):
    env = tmp_path / "root.env"
    env.write_text("DATABASE_URL=postgresql://from-dotenv/db\n")
    other = tmp_path / "elsewhere"
    other.mkdir()
    code = (
        "import os; from pathlib import Path; from owcsmuse import config; "
        "[os.environ.pop(k, None) for k in ('DATABASE_URL','OWCS_DATABASE_URL','FACEIT_API_KEY')]; "
        f"config.Settings.model_config['env_file'] = Path({str(env)!r}); "
        "print(config.load_settings().database_url)"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=other, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "postgresql://from-dotenv/db"


def test_no_module_shadows_the_standard_library():
    stdlib = set(sys.stdlib_module_names)
    clash = [p.stem for p in (ROOT / "owcsmuse").glob("*.py") if p.stem in stdlib]
    assert clash == []

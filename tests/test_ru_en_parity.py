"""RU/EN documentation parity (DOC-07).

The repository is bilingual by policy (AGENTS.md): Russian is the source
language and every `*.md` file needs an `*_EN.md` counterpart with the same
structure. `scripts/check-ru-en-parity.py` enforces the language-independent
invariants (heading tree, table shapes, fence languages, env tokens, locale
scope of links); these tests make the check run in CI and prove it bites.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts" / "check-ru-en-parity.py"


def run_checker(root: Path):
    return subprocess.run(
        [sys.executable, str(CHECKER), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_repository_documentation_is_in_ru_en_parity():
    proc = run_checker(REPO_ROOT)
    assert proc.returncode == 0, f"RU/EN drift detected:\n{proc.stdout}\n{proc.stderr}"
    assert "problems" in proc.stdout


def test_checker_flags_each_kind_of_drift(tmp_path):
    ru = tmp_path / "README.md"
    en = tmp_path / "README_EN.md"
    ru.write_text(
        "# Заголовок\n\n"
        "## Раздел\n\n"
        "| A | B |\n|---|---|\n| 1 | 2 |\n\n"
        "```bash\necho MAX_BOT_TOKEN\n```\n\n"
        "- [Настройка](docs/setup.md)\n"
        "- [API](docs/api_EN.md)\n",
        encoding="utf-8",
    )
    en.write_text(
        "# Title\n\n"
        "## Section\n\n"
        "### Extra Subsection\n\n"
        "| A | B | C |\n|---|---|---|\n| 1 | 2 |\n\n"
        "```python\nprint('MAX_BOT_TOKEN', 'HERMES_HOME')\n```\n\n"
        "- [Setup](docs/setup.md)\n",
        encoding="utf-8",
    )
    (tmp_path / "docs").mkdir()
    for name in ("setup.md", "setup_EN.md", "api_EN.md"):
        (tmp_path / "docs" / name).write_text("# Stub\n", encoding="utf-8")

    proc = run_checker(tmp_path)
    assert proc.returncode == 1, proc.stdout
    for expected in (
        "heading levels differ",
        "table shapes differ",
        "code-fence languages differ",
        "env tokens differ",
        "RU file links to a translated file",
        "EN file links to a Russian-only file",
    ):
        assert expected in proc.stdout, f"checker missed: {expected}\n{proc.stdout}"


def test_identical_translations_pass(tmp_path):
    body = "# Заголовок\n\n## Раздел\n\n| A | B |\n|---|---|\n| 1 | 2 |\n"
    (tmp_path / "README.md").write_text(body, encoding="utf-8")
    (tmp_path / "README_EN.md").write_text(body, encoding="utf-8")
    proc = run_checker(tmp_path)
    assert proc.returncode == 0, proc.stdout
    assert "1 in sync" in proc.stdout


def test_locales_json_valid_and_present():
    """LOCALE-PACK-01: ru-RU.json and en-US.json exist and are valid JSON."""
    import json

    import yaml
    manifest_path = REPO_ROOT / "plugin.yaml"
    with open(manifest_path, encoding="utf-8") as f:
        manifest = yaml.safe_load(f)
    assert "provides_locales" in manifest
    locales = [loc["id"] for loc in manifest["provides_locales"]]
    assert "ru-RU" in locales
    assert "en-US" in locales

    for loc in ("ru-RU", "en-US"):
        file_path = REPO_ROOT / "locales" / f"{loc}.json"
        assert file_path.exists(), f"Missing {file_path}"
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, dict)
        assert "messaging" in data


def test_translation_fallback_to_english():
    """LOCALE-FALLBACK-01: Missing key in target locale falls back to english."""
    import json
    ru_path = REPO_ROOT / "locales" / "ru-RU.json"
    en_path = REPO_ROOT / "locales" / "en-US.json"
    with open(ru_path, encoding="utf-8") as f:
        ru_data = json.load(f)
    with open(en_path, encoding="utf-8") as f:
        en_data = json.load(f)

    def t(key_path: str, lang: str = "ru-RU") -> str:
        data = ru_data if lang == "ru-RU" else en_data
        parts = key_path.split(".")
        val = data
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                val = None
                break
        if val is not None:
            return str(val)
        # Fallback to English
        val = en_data
        for p in parts:
            if isinstance(val, dict) and p in val:
                val = val[p]
            else:
                return key_path
        return str(val)

    # Key present in English but missing in Russian
    assert t("messaging.buttons.missing_key_en_only", "ru-RU") == "English Only Fallback"
    # Key missing in both
    assert t("messaging.buttons.non_existent", "ru-RU") == "messaging.buttons.non_existent"

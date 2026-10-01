"""
Test suite for MAX plugin localization (Language Packs).

Validates:
1. provides_locales declaration in plugin.yaml
2. Existence of ru.desktop.yaml and en.desktop.yaml
3. Coverage of all MAX_* environment variables in both locale files
4. Presence of GitHub repository link in platformIntro
"""

import yaml
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def test_provides_locales_in_plugin_yaml():
    """plugin.yaml must declare provides_locales with ru and en."""
    manifest_path = PLUGIN_ROOT / "plugin.yaml"
    with open(manifest_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "provides_locales" in data, "plugin.yaml must declare provides_locales"
    locales = [loc if isinstance(loc, str) else loc.get("id") for loc in data["provides_locales"]]
    assert "ru" in locales, "ru must be in provides_locales"
    assert "en" in locales, "en must be in provides_locales"


def test_desktop_locale_files_exist_and_complete():
    """Both ru.desktop.yaml and en.desktop.yaml must exist and cover all MAX_* fields."""
    manifest_path = PLUGIN_ROOT / "plugin.yaml"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = yaml.safe_load(f)

    # Collect all environment variable names
    env_vars = [item["name"] for item in manifest.get("requires_env", [])]
    env_vars += [item["name"] for item in manifest.get("optional_env", [])]

    for lang in ["ru", "en"]:
        locale_path = PLUGIN_ROOT / "locales" / f"{lang}.desktop.yaml"
        assert locale_path.is_file(), f"Missing {locale_path}"
        
        with open(locale_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # Check platformIntro.max exists and contains GitHub link
        assert "messaging.platformIntro.max" in data, \
            f"Missing messaging.platformIntro.max in {lang}.desktop.yaml"
        assert "github.com/Realmagnum/hermes-max-integration" in data["messaging.platformIntro.max"], \
            f"platformIntro must reference GitHub repo in {lang}.desktop.yaml"

        # Check all env vars have label and help
        for var in env_vars:
            label_key = f"messaging.fieldCopy.{var}.label"
            help_key = f"messaging.fieldCopy.{var}.help"
            assert label_key in data, f"Missing {label_key} in {lang}.desktop.yaml"
            assert help_key in data, f"Missing {help_key} in {lang}.desktop.yaml"

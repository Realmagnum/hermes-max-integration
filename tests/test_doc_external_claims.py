"""DOC-10: pin the external/unconfirmed claims after reconciliation.

Every assertion here failed on the pre-DOC-10 tree (retracted absolutes still
present, no evidence register) and passes once the docs cite verified facts.
The verified facts and their sources/dates live in docs/external-claims.md.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(*parts: str) -> str:
    return ROOT.joinpath(*parts).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Claims retracted as false or unsupported absolutes
# --------------------------------------------------------------------------

RETRACTED = {
    ("README.md",): [
        "гарантирует доставку любых безопасных расширений",  # unsupported absolute
        "поддерживает markdown-таблицы «из коробки»",  # false for classic parse_mode
    ],
    ("README_EN.md",): [
        "guaranteeing delivery for any safe extension",
        "supports markdown tables natively",
    ],
}


def test_retracted_absolutes_are_gone():
    for (fname,), phrases in RETRACTED.items():
        text = _read(fname)
        for phrase in phrases:
            assert phrase not in text, f"{fname} still contains retracted claim: {phrase!r}"


def test_reasoning_workaround_no_longer_points_at_display_platforms():
    # The old README told users to set display.platforms.max.fresh_final_after_seconds,
    # a key path core never reads, on a platform the setting never applies to.
    broken_fragment = "display:\n  platforms:\n    max:\n      fresh_final_after_seconds"
    for fname in ("README.md", "README_EN.md"):
        text = _read(fname)
        assert broken_fragment not in text, f"{fname} still documents the broken config path"
        assert "streaming:\n  fresh_final_after_seconds" in text, (
            f"{fname} must document the real streaming.fresh_final_after_seconds key"
        )


# --------------------------------------------------------------------------
# Verified facts that must now be cited
# --------------------------------------------------------------------------


def test_telegram_tables_route_through_rich_messages():
    for fname in ("README.md", "README_EN.md"):
        text = _read(fname)
        assert "sendRichMessage" in text, f"{fname} must name the only table-capable API"
        assert "Bot API 10.1" in text, f"{fname} must cite the Telegram Bot API version"


def test_max_host_and_format_limits_are_documented():
    claims = _read("docs", "external-claims.md")
    for needle in (
        "platform-api2.max.ru",
        "2026-09-16",
        "443",
        "Bot API 10.1",
        "File extension is forbidden",
        "GET /chats",
    ):
        assert needle in claims, f"verification register is missing {needle!r}"


def test_webhook_production_claim_cites_official_source():
    for rel in (("docs", "setup.md"), ("docs", "setup_EN.md")):
        text = _read(*rel)
        assert "443" in text, f"{rel[-1]} must state the official webhook port"
        assert "dev.max.ru/docs-api" in text, f"{rel[-1]} must cite the MAX docs"


def test_evidence_register_exists_in_both_languages():
    ru = _read("docs", "external-claims.md")
    en = _read("docs", "external-claims_EN.md")
    assert "platform-api2.max.ru" in ru and "platform-api2.max.ru" in en
    assert "2026-09-16" in ru and "2026-09-16" in en
    # The register must keep the follow-up list honest about the patch script.
    assert "apply-core-fix.py" in ru and "apply-core-fix.py" in en

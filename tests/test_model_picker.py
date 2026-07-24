"""Tests for ModelPicker class."""

import pytest
from unittest.mock import MagicMock

from model_picker import ModelPicker, ModelPickerState


class TestModelPicker:
    """Test ModelPicker class."""

    def test_create_picker(self):
        """Test creating ModelPicker."""
        adapter = MagicMock()
        picker = ModelPicker(adapter=adapter)
        assert picker.adapter == adapter

    def test_build_provider_buttons(self):
        """Test building provider buttons."""
        picker = ModelPicker(adapter=MagicMock())
        picker.providers = [
            {"slug": "openrouter", "name": "OpenRouter", "models": ["gpt-4"], "is_current": True},
            {"slug": "deepseek", "name": "DeepSeek", "models": ["deepseek-v3"], "is_current": False},
        ]

        buttons = picker._build_provider_buttons(picker.providers)

        # Should have buttons
        assert len(buttons) > 0
        # Should contain provider slugs
        payloads = [b["payload"] for row in buttons for b in row]
        assert any("openrouter" in p for p in payloads)
        assert any("deepseek" in p for p in payloads)

    def test_state_defaults(self):
        """Test ModelPickerState defaults."""
        state = ModelPickerState()
        assert state.provider_msg_id == ""
        assert state.model_msg_id == ""
        assert state.providers == []

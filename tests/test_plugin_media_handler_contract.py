from unittest.mock import MagicMock

from adapter import register


def test_max_registers_send_message_handler():
    ctx = MagicMock()
    register(ctx)
    assert ctx.register_platform.called
    kwargs = ctx.register_platform.call_args[1]
    assert "send_message_handler" in kwargs
    assert callable(kwargs["send_message_handler"])
    assert kwargs.get("standalone_sender_fn") is not None

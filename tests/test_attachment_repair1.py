"""F3 schema null normalization and destination-aware notify policy."""
import importlib
import json

import pytest

import adapter

tool = importlib.import_module(f"{adapter.__package__}.attachment_tool")


@pytest.mark.asyncio
@pytest.mark.parametrize('target,kind,allowed', [('user:42', None, True), ('chat:-42', 'chat', True), ('chat:-42', 'channel', False), ('chat:-42', None, False)])
async def test_notify_uses_real_task_context_and_target_metadata(target, kind, allowed, monkeypatch, max_api):
    from gateway.session_context import reset_session_vars, set_session_vars
    set_session_vars(platform='max', chat_id=target, source='gateway', user_id='42')
    monkeypatch.setattr(tool, 'get_max_secret', lambda *a: 'fixture')
    monkeypatch.setattr(tool.httpx, 'AsyncClient', lambda **kw: max_api.client())
    max_api.route('GET', '/chats/-42', json_body={'chat_id': -42, 'type': kind})
    try:
        result = json.loads(await tool.send_attachments({'notify': False, 'attachments': [{'type': 'sticker', 'payload': {'code': 'fixture'}}]}))
        assert bool(result.get('success')) == allowed
        assert bool(max_api.calls('POST', '/messages')) == allowed
    finally:
        reset_session_vars()


@pytest.mark.parametrize('optional', ['text', 'format', 'link'])
def test_nullable_body_fields_normalize(optional):
    value = tool.validate({optional: None, 'attachments': [{'type': 'image', 'payload': {'token': 'fixture', 'url': None, 'photos': None}}]})
    assert optional not in value
    assert value['attachments'][0]['payload'] == {'token': 'fixture'}


def test_nullable_contact_name_and_selector():
    value = tool.validate({'attachments': [{'type': 'contact', 'payload': {'name': None, 'contact_id': 42, 'vcf_info': None}}]})
    assert value['attachments'][0]['payload'] == {'contact_id': 42}


def test_notify_false_is_valid_before_target_kind_check():
    assert tool.validate({'notify': False, 'attachments': [{'type': 'sticker', 'payload': {'code': 'fixture'}}]})['notify'] is False


def test_nonnullable_nulls_still_fail():
    with pytest.raises(ValueError):
        tool.validate({'notify': None, 'attachments': [{'type': 'sticker', 'payload': {'code': 'fixture'}}]})
    with pytest.raises(ValueError):
        tool.validate({'attachments': [{'type': 'image', 'payload': {'token': 'a', 'url': 'https://example.com'}}]})

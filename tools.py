"""Eager declaration of the existing current-MAX-only tool, never a destination tool."""


def register_tools(ctx):
    from .attachment_tool import SCHEMA, send_attachments

    ctx.register_tool(name="max_send_attachments", toolset="max", schema=SCHEMA, handler=send_attachments, is_async=True)

"""Hermes MAX plugin: keep eager tool discovery independent of adapter imports."""


def register(ctx):
    from .adapter import register as register_adapter

    return register_adapter(ctx)


__all__ = ["register"]

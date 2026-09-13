"""Finite trusted provider wire mapping; standalone from Session and execution logic."""
from .client import WireClient
from .jsoncodec import WireError

__all__ = ["WireClient", "WireError"]

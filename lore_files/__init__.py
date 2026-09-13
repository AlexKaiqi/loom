"""Linux ordinary-file version boundary. No model or execution authority is supplied here."""
from .errors import FileError
from .store import FileStore

__all__ = ["FileStore", "FileError"]

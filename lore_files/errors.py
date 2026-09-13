"""Explicit file-boundary failures; never use missing data as an empty result."""
class FileError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(f"{code}: {message}")


def require(condition, code, message):
    if not condition:
        raise FileError(code, message)

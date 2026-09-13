class ExecutionError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def require(value, code, message):
    if not value:
        raise ExecutionError(code, message)

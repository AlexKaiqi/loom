"""The existing trusted two-target routing guard; no execution grant or dispatch."""
from .snapshot_files import require


def require_tool_target(target, script):
    require(target in ('runtime', 'workspace'),
            'target outside the registered ordinary Shell routes', 'unauthorized_target')
    require(isinstance(script, str) and script,
            'ordinary authorized target requires an exact nonempty script', 'invalid_request')

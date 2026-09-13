"""Explicit construction of the existing trusted owners; no task or model loop."""
import copy
from pathlib import Path
from lore_control import ControlStore
from lore_control.values import fail
from .file_thread import RuntimeFiles
from lore_execution import ExecutionStore
from lore_session.snapshots import SnapshotStore
from lore_session.service import SessionService
from .host_files import HostFiles
from .startup_assets import StartupAssets
from .session_plans import SessionPlans
from .tool_plans import ToolPlans
from .file_publication import FilePublication
from .tool_service import ToolService
from .provider_owner import ProviderOwner
from .runtime import Runtime


class _References:
    def __init__(self, host):
        self.host, self.tools, self.publication, self.provider = host, None, None, None

    def authorization(self, ref, purpose, context):
        if purpose in ('import_archive', 'install') or (purpose == 'materialize' and
                context.get('request_id', '').startswith('tool-materialize-')):
            return self.tools is not None and self.tools.file_authorization(ref, purpose, context)
        return self.host.authorization(ref, purpose, context)

    def file_reference(self, ref, purpose, context):
        if purpose == 'source':
            return self.tools is not None and self.tools.file_reference(ref, purpose, context)
        if purpose in ('intent', 'stop'):
            return self.publication is not None and self.publication.file_reference(ref, purpose, context)
        return self.host.reference(ref, purpose, context)

    def stopped(self, ref, purpose, scope):
        return self.tools is not None and self.tools.validate_stopped(ref, purpose, scope)

    def control_reference(self, ref, purpose, expected=None):
        try:
            if type(ref) is not dict: return False
            if purpose == 'base':
                resource = self.host._resource(expected['resource_id'], 'read')
                return resource is not None and ref['resource_id'] == resource['id'] and ref['domain'] == resource['kind'] and self.host._version(ref)
            if purpose == 'receipt':
                if ref.get('delivery_owner') == 'provider':
                    return self.provider is not None and self.provider.control_reference(ref, purpose, expected)
                if ref.get('facility_ref', {}).get('kind') == 'ordinary_tool':
                    return self.tools is not None and self.tools.control_reference(ref, purpose, expected)
                return False
            if purpose in ('staged', 'stopped', 'installation', 'published'):
                return self.publication is not None and self.publication.control_reference(ref, purpose, expected)
            return self.host.control_reference(ref, purpose, expected)
        except Exception:
            return False


def assemble(config, *, credential_provider=None, checkpoint=None):
    """Returns the original Runtime with actual F initial refs; starts no invocation."""
    from .session_sources import SessionSources
    c = copy.deepcopy(config)
    required = {'runtime', 'startup_root', 'startup', 'provider', 'initial_session_ref'}
    if set(c) != required: fail('invalid', 'complete fixed owner configuration required')
    cfg = c['runtime']
    control = ControlStore(cfg['control_db'], cfg['authority'])
    execution = None
    try:
        startup_root = Path(c['startup_root'])
        if startup_root.is_dir() and any(startup_root.iterdir()):
            assets = StartupAssets.open_existing(startup_root, c['startup'], control=control)
        else:
            assets = StartupAssets(startup_root, c['startup'])
        host = assets.host
        if cfg['execution_dir'] != host['state_root'] or cfg['event_profile']['input_root'] != host['event_input_root']:
            fail('invalid', 'Runtime paths differ from original startup owners')
        authority = HostFiles(control, host)
        references = _References(authority)
        control.reference_checker = references.control_reference
        files = RuntimeFiles(cfg['files_dir'], references.authorization, references.file_reference, control=control)
        authority.files = files
        original = assets.build(files)
        snapshots = SnapshotStore(cfg['session_dir'], host['namespace'], assets.register)
        plans = SessionPlans(control, files, snapshots, host, authority.resolve, assets.register)
        provider = ProviderOwner(control, credential_provider=credential_provider, **c['provider'])
        if provider.principal != host['principal']: fail('invalid', 'provider principal differs from fixed host')
        references.provider = provider
        execution = ExecutionStore(cfg['execution_dir'], cfg['engine_endpoint'],
            trusted_config=assets.config_ref['path'], trusted_config_sha256=assets.config_ref['sha256'])
        publication = FilePublication(control, files, references.stopped)
        references.publication = publication
        tools = ToolService(control, files, execution, publication, ToolPlans(plans, snapshots), references.stopped)
        references.tools = tools
        service = SessionService(execution, snapshots, provider, plans, tools)
        runtime = Runtime(cfg, session_service=service, provider_bridge=provider, checkpoint=checkpoint)
        sources = SessionSources(control, snapshots, runtime.delivery, c['initial_session_ref'])
        authority.session_resolver = sources.resolve
        refs = original['initial_refs']
        runtime.initial_refs = dict(harness_ref=refs['harness_ref'], capability_ref=refs['capability_ref'],
            session_ref=copy.deepcopy(c['initial_session_ref']), source_result_ref=None,
            surface_ref=refs['surface_version_ref'], previous_session_ref=None,
            execution_targets=[dict(resource_id=refs[d+'_version_ref']['resource_id'], version_ref=refs[d+'_version_ref'])
                               for d in ('surface', 'workspace')])
        runtime.registrations_spec = original['registrations_spec']
        runtime.startup = assets
        runtime.file_authority = authority
        return runtime
    except BaseException:
        if execution is not None: execution.journal.close()
        control.close()
        raise

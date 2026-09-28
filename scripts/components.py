"""Assemble pinned capabilities; their submodules remain the source authority."""
import os
from pathlib import Path
import subprocess

ASSETS = ('runtime', 'deploy', 'components/model-resource-hub/model-invocation/pi',
          'components/worksurface', 'components/sandbox/linux_process_execution',
          'components/sandbox/linux_container_execution/loom-profile')

def copy_assets(source, target, copy_component):
    for name in ASSETS:
        if not (source/name).is_dir():
            raise ValueError('Missing pinned component; run git submodule update --init --recursive with access to the component repositories')
        copy_component(source/name, target/name)

def vendor_execution(runtime):
    # Credentials stay in the host Git helper. Docker receives source, not secrets.
    env=dict(os.environ)
    env['GOPRIVATE']=','.join(filter(None,[env.get('GOPRIVATE',''),'github.com/AlexKaiqi/ondemand-sandbox']))
    subprocess.run(['go','mod','vendor'],cwd=runtime,env=env,check=True)

"""Owned immutable files and atomic publication; no event queue or progress state."""
import os,stat,uuid
from pathlib import Path
from .values import fail

def sync_directory(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:os.fsync(fd)
    finally:os.close(fd)

def read_file(path):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):fail('reference_invalid','original is not a regular file')
        with os.fdopen(fd,'rb',closefd=False) as stream:return stream.read()
    finally:os.close(fd)

def save_once(path,raw):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    if path.parent.is_symlink():fail('reference_invalid','owned directory cannot be symlink')
    temporary=path.parent/('.pending-'+uuid.uuid4().hex)
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        try:os.link(temporary,path,follow_symlinks=False)
        except FileExistsError:
            if read_file(path)!=raw:fail('reference_invalid','immutable original bytes conflict')
        sync_directory(path.parent)
    finally:
        if temporary.exists():temporary.unlink();sync_directory(path.parent)
    return path

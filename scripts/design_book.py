"""Copy the complete HTML specification and record every delivered file."""
import hashlib
from pathlib import Path
import shutil


def copy_design_book(source: Path, target: Path):
    target.mkdir(parents=True)
    shutil.copyfile(source / 'loom-design-book.html', target / 'loom-design-book.html')
    shutil.copyfile(source / 'capability-migration.md', target / 'capability-migration.md')
    shutil.copytree(source / 'design-book', target / 'design-book')
    return {path.relative_to(target).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(target.rglob('*')) if path.is_file()}

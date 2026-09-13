"""Compile model modules from the exact captured bytes, including lazy helpers."""
import importlib
import importlib.abc
import importlib.util
from hashlib import sha256
import sys
from .observer import ProtocolError, verify_hashes

class FrozenModels(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self, root, sources):
        self.root = root
        self.captured = {"simulations."+path.stem: (path, path.read_bytes()) for path in sources}
        unexpected = set(self.captured).intersection(sys.modules)
        if unexpected:
            raise ProtocolError("unexpected preloaded model modules: "+str(sorted(unexpected)))
        self.hashes = {str(path.relative_to(root)): sha256(data).hexdigest() for path, data in self.captured.values()}
        verify_hashes(root, self.hashes)
        sys.meta_path.insert(0, self)

    def find_spec(self, fullname, path=None, target=None):
        if fullname in self.captured:
            return importlib.util.spec_from_loader(fullname, self)
        if fullname.startswith("simulations.") and fullname not in sys.modules:
            raise ImportError("model dependency not in captured source set: "+fullname)
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        path, source = self.captured[module.__name__]
        module.__file__ = str(path)
        exec(compile(source, str(path), "exec", dont_inherit=True), module.__dict__)

    def load(self, family, class_name):
        module = importlib.import_module("simulations."+family)
        verify_hashes(self.root, self.hashes)
        return getattr(module, class_name)

    def close(self):
        if self in sys.meta_path:
            sys.meta_path.remove(self)

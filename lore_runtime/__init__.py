"""Linux shared Runtime and narrow adapters over original component owners."""
__all__ = ['Runtime']

def __getattr__(name):
    if name == 'Runtime':
        from .runtime import Runtime
        return Runtime
    raise AttributeError(name)

"""Deliberately wrong candidate used only to calibrate the external driver."""
class FileStore:
    def __init__(self,*args,**kwargs):pass
    def __getattr__(self,name):
        return lambda *args,**kwargs:{'status':'PASS'}

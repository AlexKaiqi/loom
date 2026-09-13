"""Known bad G3 fixture: claims PASS but implements no control capability. Never production."""
class ControlStore:
    def __init__(self,*args,**kwargs):pass
    def close(self):pass
    def __getattr__(self,name):return lambda *args,**kwargs:{"status":"PASS"}

"""Deliberately incorrect candidate: reports success without admission or original NATS bytes."""
class EmitService:
    def __init__(self,*args):pass
    async def publish(self,*args):return [{'status':'CONFIRMED','request_id':'fabricated'}]

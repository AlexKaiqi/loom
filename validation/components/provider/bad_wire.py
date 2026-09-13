"""Deliberately wrong calibration component; NEVER the product or a passing substitute."""
import hashlib
import http.client
import json
from pathlib import Path


class WireClient:
    def __init__(self,endpoint,scope,evidence_dir,timeout=2):
        self.endpoint,self.scope,self.root,self.timeout=endpoint,scope,Path(evidence_dir),timeout

    def complete(self,intent):
        # Mechanism fault: ignore request validation and send even rejected inputs.
        request=b'{"bad":"REAL_HTTP_SENT"}'
        connection=http.client.HTTPConnection(self.endpoint["host"],self.endpoint["port"],timeout=self.timeout)
        connection.request("POST","/v1/chat/completions",body=request,headers={"Content-Type":"application/json"})
        response=connection.getresponse()
        try: raw=response.read()
        except http.client.IncompleteRead as error: raw=error.partial
        transport=dict(http_status=response.status,content_length=int(response.getheader("Content-Length")),received_size=len(raw),complete=True)
        connection.close()
        self.root.mkdir()
        records={"request.body":request,"response.body":raw,"transport.json":json.dumps(transport).encode(),
                 "association.json":json.dumps(dict(binding=self.scope,scope=self.scope,request_sha256=hashlib.sha256(request).hexdigest(),response_sha256=hashlib.sha256(raw).hexdigest())).encode()}
        for name,data in records.items():(self.root/name).write_bytes(data)
        return dict(accepted=True,normalized={},request=dict(sha256=hashlib.sha256(request).hexdigest(),size=len(request),method="POST",path="/v1/chat/completions"),transport=transport,
                    artifacts={key:str(self.root/name) for key,name in (("request_path","request.body"),("response_path","response.body"),("transport_path","transport.json"),("association_path","association.json"))})

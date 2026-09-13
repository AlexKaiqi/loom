"""Thin one-intent wire client. It has no Session, tool dispatch or business state."""
import copy
import hashlib
from pathlib import Path
from .jsoncodec import WireError, require
from .persistence import save, save_json
from .request import encode_request
from .response import normalize
from .transport import exchange


class WireClient:
    def __init__(self, endpoint, scope, evidence_dir, timeout=2.0, credential_provider=None):
        require(type(timeout) in (int, float) and 0 < timeout <= 60, "invalid_endpoint")
        require(credential_provider is None or callable(credential_provider), "invalid_credential")
        self.credential_provider = credential_provider
        self.endpoint, self.scope = copy.deepcopy(endpoint), copy.deepcopy(scope)
        self.root, self.timeout = Path(evidence_dir).absolute(), timeout

    def complete(self, intent):
        try:
            request = encode_request(intent, self.scope)
        except WireError:
            return dict(accepted=False,reason="invalid_request",request=None,transport=None,artifacts=None)
        # Read only after every untrusted intent field has passed validation.
        authorization = None
        if self.credential_provider is not None:
            try:
                credential = self.credential_provider()
                require(isinstance(credential, str) and 0 < len(credential) <= 4096 and
                        credential.isascii() and "\r" not in credential and "\n" not in credential,
                        "invalid_credential")
                authorization = "Bearer " + credential
            except Exception:
                # A credential callback's exception text can contain the secret.
                raise WireError("invalid_credential") from None
        # A trusted fresh receipt directory is not a model-selected content path.
        self.root.mkdir(mode=0o700, parents=False, exist_ok=False)
        request_path, response_path = self.root/"request.body", self.root/"response.body"
        transport_path, association_path = self.root/"transport.json", self.root/"association.json"
        save(request_path, request)
        raw, transport, headers = exchange(self.endpoint, request, self.timeout, authorization=authorization)
        save(response_path, raw)
        save_json(transport_path, transport)
        save_json(self.root/"response.headers.json", headers)
        save_json(association_path, dict(binding=copy.deepcopy(intent["binding"]),scope=self.scope,
                  request_sha256=hashlib.sha256(request).hexdigest(),response_sha256=hashlib.sha256(raw).hexdigest()))
        result = dict(request=dict(method="POST",path="/v1/chat/completions",size=len(request),
                                   sha256=hashlib.sha256(request).hexdigest()),transport=transport,
                      artifacts=dict(request_path=str(request_path),response_path=str(response_path),
                                     transport_path=str(transport_path),association_path=str(association_path)))
        # This transformation only runs after original bytes and association were saved.
        try:
            result.update(accepted=True,normalized=normalize(raw,transport))
        except WireError as error:
            result.update(accepted=False,reason=error.reason)
        return result

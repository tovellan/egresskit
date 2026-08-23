# HTTPX integration

Install the optional adapter dependency:

```console
python -m pip install "egresskit[httpx] @ git+https://github.com/tovellan/egresskit.git@v0.5.3"
```

The adapter accepts a caller-owned HTTPX client. Configure authentication, TLS, proxies,
timeouts, and connection limits on that client, then pass the adapter to a bound guarded
transport:

```python
import httpx

from egresskit import BoundGuardedTransport, DestinationBindings, PolicyEvaluator
from egresskit.httpx_transport import HTTPXDestinationTransport

with httpx.Client(headers={"authorization": "Bearer application-managed"}) as client:
    guarded = BoundGuardedTransport(
        evaluator=PolicyEvaluator(policy),
        bindings=DestinationBindings({"processor_a": "https://processor.example.test/v1/submit"}),
        transport=HTTPXDestinationTransport(client),
    )
```

`HTTPXDestinationTransport` supports `POST`, `PUT`, and `PATCH`, with `POST` as the
default. It sends the serializer output as raw `content` bytes. The async equivalent is
`HTTPXAsyncDestinationTransport` and accepts an `httpx.AsyncClient`.

Every request sets `follow_redirects=False`, even if the client default enables
redirects. A redirect response is returned to the application and is not followed. The
adapter does not own or close the client, does not raise for HTTP status codes, and does
not log request bodies.

Destination validation and policy authorization still happen in
`BoundGuardedTransport` before serialization. HTTPX handles DNS and TLS after that
boundary, so the DNS and destination identity limitations in
[Destination binding](destinations.md) still apply.

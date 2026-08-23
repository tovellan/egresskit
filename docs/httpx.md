# HTTPX integration

Install the optional adapter dependency:

```console
python -m pip install "egresskit[httpx] @ git+https://github.com/tovellan/egresskit.git@v0.5.4"
```

The adapter accepts a caller-owned HTTPX client. Configure authentication with a
protected default header, and configure TLS, proxies, timeouts, and connection limits on
that client before passing it to a bound guarded transport:

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
`HTTPXAsyncDestinationTransport` and accepts an `httpx.AsyncClient`. Each adapter rejects
the opposite client kind during construction, before it can build or send a request.

Every request sets `follow_redirects=False`, even if the client default enables
redirects. A redirect response is returned to the application and is not followed. The
adapter does not own or close the client, does not raise for HTTP status codes, and does
not log request bodies.

Default query parameters, an explicit `Host` header, an HTTPX `auth` handler, and request
event hooks are rejected because each can change the validated request after binding.
Use a protected default `Authorization` header instead of `auth`. The adapter rechecks
the client before every send, builds the request, and compares its URL and authority with
the validated destination. Do not mutate a client while a request is in progress.

Destination validation and policy authorization still happen in
`BoundGuardedTransport` before serialization. HTTPX handles DNS and TLS after that
boundary, so the DNS and destination identity limitations in
[Destination binding](destinations.md) still apply. Custom transports, proxies, and the
Python process remain trusted application components; the adapter cannot verify their
last-mile network behavior.

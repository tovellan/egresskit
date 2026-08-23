# Destination binding

`DestinationBindings` maps each policy provider identifier to one canonical HTTPS
destination. The mapping is immutable after construction. `BoundGuardedTransport` and
`BoundGuardedAsyncTransport` resolve the mapping after an allow decision and before the
payload serializer runs.

```python
bindings = DestinationBindings({"processor_a": "https://processor.example.test/v1/submit"})
```

Matching is exact across the canonical host, port, and path. Destinations cannot contain
credentials, a query, a fragment, percent encoding, repeated path separators, or dot
segments. Empty query, fragment, and port delimiters are also rejected instead of being
canonicalized away. Bracketed authorities must contain an IPv6 address. An unbound
provider produces a structured error with a fixed reason and no caller-supplied lookup
value. A mismatched destination includes only the validated, configured provider and a
fixed reason. Public `resolve()` and `require()` calls require an exact built-in provider
string, then reject invalid identifiers or overlength input with a fixed error that does
not reflect the rejected value. URL strings, direct host and path strings, integer ports,
and passed `Destination` objects must also be exact built-in or EgressKit types.
Subclasses with active behavior are rejected before storage or comparison.

## Adapter contract

The destination transport receives a validated `Destination` object and serialized
bytes. EgressKit deliberately has no HTTP dependency. An adapter must:

1. Build its outbound request only from the supplied destination.
2. Put credentials in a protected header or client configuration, never in the URL.
3. Disable redirects, or call `bindings.require(provider, redirect_url)` before following
   every redirect.
4. Preserve HTTPS certificate and hostname verification.
5. Avoid logging the serialized body.

The binding controls the URL presented to the adapter. It does not pin DNS answers,
network routes, IP addresses, or TLS certificates. DNS rebinding and compromised name
resolution remain outside the library boundary. Use outbound firewall rules, trusted
DNS, and destination-aware monitoring when those threats are in scope.

`DestinationBindings.require()` is useful when an SDK or callback supplies a destination
at runtime. It must be called before serialization, and the adapter must send to the
returned `Destination`, not the unchecked input.

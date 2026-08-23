# Support and compatibility

Use GitHub Discussions for usage questions and GitHub Issues for reproducible defects.
Use private vulnerability reporting for security concerns.

Version 0.3.0 supports CPython 3.10 through 3.14. Continuous integration tests the lower
and upper supported versions plus an intermediate version. Other Python implementations
are not currently tested.

Patch releases preserve the public Python API and policy schema semantics where
practical. Before version 1.0, a minor release may change the Python API. A serialized
policy incompatibility requires a new `schema_version` and explicit migration notes.

Only the latest patch release receives fixes. No response-time commitment is provided.

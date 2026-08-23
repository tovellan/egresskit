# Security policy

## Supported versions

The latest 0.4.x release receives security fixes. Older release lines are unsupported.

## Reporting

Use GitHub private vulnerability reporting for suspected vulnerabilities. Do not open a
public issue. Include affected versions, impact, and a minimal synthetic reproduction.
Do not include real payloads, credentials, or personal data.

Maintainers will acknowledge reports when available, investigate, and coordinate a fix
and disclosure. This project does not promise a specific response time.

## Boundary

EgressKit is a library-level enforcement point. It does not prevent application code
from using another network client, validate destination identity, or discover sensitive
content. Review [the threat model](docs/threat-model.md) before deployment.

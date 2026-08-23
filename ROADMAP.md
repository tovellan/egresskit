# Roadmap

The 0.1.x line will focus on correctness, integration guidance, and compatibility.

- Add optional adapters for widely used HTTP clients without making them core
  dependencies.
- Define a receipt signing extension without changing the payload-free core receipt.
- Add policy test-case files that can be run by the CLI.
- Evaluate destination-binding helpers for transport adapters.
- Document composition with network firewalls and general policy engines.

These are design directions, not delivery commitments. EgressKit will not become a
payload classifier, content scanner, consent ledger, or compliance certification tool.

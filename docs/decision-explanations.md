# Decision explanations

Normal decisions contain a receipt UUID and evaluation timestamp because receipts are
runtime evidence. Those fields make otherwise identical decisions differ between runs.
Policy review, snapshot tests, and CI often need a stable explanation instead.

```console
egresskit explain POLICY \
  --classification internal \
  --purpose summarize \
  --provider processor_a \
  --environment test \
  --mode synthetic
```

The command evaluates the same metadata and uses the same exit codes as `decide`: `0`
for allow, `3` for deny, and `2` for invalid input. Its version 1 JSON output retains:

- policy identifier and digest;
- status and reason codes;
- matched rule identifiers;
- provider, classification, purpose, environment, execution mode, and dry-run state.

It omits the receipt UUID, evaluation timestamp, and every payload field. Repeated
explanations for the same policy and intent are byte-stable when emitted by the CLI.

Applications can call `explain_decision(decision)` directly. Use
`decision_explanation_json_schema()` or `egresskit schema --kind explanation` to obtain
the output schema.

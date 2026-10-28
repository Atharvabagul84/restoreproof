# Independent acknowledged-write ledger

The ledger checks whether explicitly recorded, acknowledged writes survived a
restore. It catches an interior missing write even when the latest recovered
timestamp is current. It does not calculate a production RPO duration or prove
that every real application acknowledgement was captured.

## Evidence boundary

Record expected writes outside the database being backed up, from the writer's
acknowledgement path. Seal the completed experiment ledger and put its SHA-256 in
the recovery contract. Never construct the expected ledger by querying the
restored database or by extracting records from the backup under test. That would
make both sides share the same missing data.

The recorder should append only after the relevant transaction's successful
commit acknowledgement. A timed-out commit has an unknown outcome until resolved;
it must not silently become an acknowledged or a failed write. The small synthetic
demo can control this sequence explicitly. Its timestamps describe the experiment,
not independently audited production commit times.

SHA-256 verifies that the supplied bytes match the contract's reference. It is not
a digital signature, an immutable storage policy, or evidence that the recorder
was complete. Protect the original contract and ledger together; changing both can
change the expected result. The file is held in memory after successful bounded
loading, so later comparison uses that verified payload.

## Format and limits

```json
{
  "version": 1,
  "writes": [
    {
      "write_id": "write-001",
      "sequence": 1,
      "payload_sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
      "acknowledged_at": "2026-10-06T12:00:01Z"
    }
  ]
}
```

The example digest represents UTF-8 bytes `abc`. The schema allows exactly these
fields and rejects duplicate JSON object keys, malformed dates, naive timestamps,
unknown fields, and coercible types such as `true` or `1.0` for a sequence.

- Maximum file: **2 MiB**, read with an additional one-byte overflow check.
- Expected writes: **1–5,000**; recovered writes: **0–5,000**.
- `write_id`: an exact, case-sensitive token matching
  `[A-Za-z0-9][A-Za-z0-9._:-]{0,63}`. UUID strings fit this format.
- `sequence`: a strict integer from **1** through **9,223,372,036,854,775,807**.
- `payload_sha256`: exactly 64 hexadecimal characters; hex case is normalized.
- `acknowledged_at`: an explicit timezone-aware ISO timestamp, at most 64
  characters and representable in UTC. Equivalent timezone offsets compare equal.
- Expected write IDs and sequences must each be unique.

Sequences identify the writer's declared logical order; they are not inferred
commit order, database LSNs, or proof of contiguous coverage. An expected ledger
with sequences `2, 7, 40` can pass when precisely those writes recover. The tool
does not invent 37 missing writes. Expected and recovered array order is irrelevant.

## Python integration

```python
from pathlib import Path
from restoreproof.ledger import load_ledger, compare_ledger

# The engine resolves a relative ledger path against the contract's directory.
ledger_path = (Path(contract_path).resolve().parent / spec.path).resolve()
expected = load_ledger(ledger_path, spec.sha256)
check = compare_ledger(expected, recovered_json_array,
                       incident_at=contract.freshness.incident_at)
```

`load_ledger(path, expected_sha256)` returns a validated dictionary or raises
`LedgerError` with a safe message. Load it during preflight before allocating a
restore environment. The comparison accepts the validated dictionary and a JSON
array of recovered records with the same four fields. SQL returning `null` is
unknown evidence; an actual empty result must be represented as `[]`.

The SQL must select the same experiment or application scope as the ledger and
recompute each digest from recovered payload bytes. Selecting a previously stored
digest alone cannot detect payload corruption that leaves the digest column
unchanged. For an application that preserves canonical UTF-8 payload text,
PostgreSQL 17 supports this expression without an extension:

```sql
encode(sha256(convert_to(payload_text, 'UTF8')), 'hex')
```

The writer must hash exactly the same bytes; two different JSON serializations of
equivalent objects can hash differently. These are PostgreSQL's documented
[binary string functions](https://www.postgresql.org/docs/17/functions-binarystring.html).
Keep SQL read-only and bound its result size and execution time through the
existing database adapter. The pure ledger comparison does not execute SQL.

## Results and interpretation

The check is named `committed-write-ledger`.

| Status | Meaning |
| --- | --- |
| `PASS` | Every known expected write has one recovered identity with matching sequence, digest, and acknowledgement timestamp; no extra identities or duplicate sequences were returned. |
| `FAIL` | Structurally valid evidence demonstrates missing IDs, unexpected IDs, duplicate recovered IDs/sequences, or changed metadata/payload digests. |
| `INCOMPLETE` | Expected or recovered evidence is invalid, the incident timestamp is invalid, or an acknowledgement is later than the supplied incident cutoff. Comparison counts remain `null`. |

An unexpected recovered write fails the **closed experiment scope**. It is not a
claim that the database performed an unauthorized write: it could be a committed
write whose acknowledgement the client never received, an incomplete recorder, or
an incorrectly scoped query. Investigate that uncertainty and correct the scope
or evidence; do not silently discard the unexpected row to produce a pass.

Reports include `expected_count`, total `recovered_count`, and `matched_count`.
The latter counts expected identities with one recovered row whose compared
fields all match; duplicate identities never increase it. Duplicate category
counts count distinct duplicated IDs or sequences, not the number of excess rows.
Each difference category includes its exact count and up to **25** sorted IDs
(numeric sequences for `duplicate_sequences`). `ids_truncated` indicates that a
list was shortened; the count remains exact. Reports omit payload bytes, expected
digests, timestamps, and raw malformed input.

Always pass the experiment's incident timestamp from the contract. Acknowledgements
after it produce `INCOMPLETE`; omission is disclosed as
`timestamp_bound_checked: false`. This cutoff uses the provided experiment clock,
not the machine's current wall clock. No newest-row timestamp, sequence maximum,
or missing-write count is converted into an RPO duration.

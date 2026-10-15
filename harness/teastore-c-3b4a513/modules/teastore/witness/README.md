# TeaStore independent application witness v1

This package closes only the positive application-side path-witness seam for
the frozen TeaStore candidate-pilot design. It is not deployed evidence and it
does not prove native-trace correlation.

The patch is bound to TeaStore commit
`34b37f7e7be433ce72d5f9455e66922a13116749`. It accepts only the workload's
40-character `journey-<32 lowercase hex>` token from the exact
`X-Observability-Journey-Id` header. The token is propagated explicitly along
the login call from webui to auth to persistence. Auth and persistence emit
fixed-schema rows containing only timestamp, token, service, and event. Invalid
tokens are neither forwarded nor logged. Credentials, session IDs, cookies,
bodies, arbitrary headers, and exception messages never enter witness rows.

The extractor reads independently captured auth and persistence container
logs, the immutable opportunity plan, its complete hash-chained JSONL journey
ledger, and the run receipt. It first reuses the workload's full ledger
validator and then considers only `journey-terminal` records. A missing final
reconciliation, truncated line, broken chain, plan mismatch, or non-terminal
row blocks extraction. It also rejects
malformed or extra fields, secret-bearing fields, unknown or invalid tokens,
out-of-window observations, duplicates, reversed timestamps, and incomplete
scored pairs. It requires one pair for every no-fault opportunity and every
before/post-readiness effect opportunity. During-exposure and recovery
opportunities may have no pair; partial optional observations are counted but
do not become guessed negative rows. Successful output
is one exact `teastore.app-witness` row per positively witnessed path plus a
terminal extraction receipt binding all input and output bytes by SHA-256.

Apply validation from the repository root:

```sh
test "$(git -C upstream/teastore rev-parse HEAD)" = 34b37f7e7be433ce72d5f9455e66922a13116749
git -C upstream/teastore apply --check ../../modules/teastore/witness/teastore-app-witness-v1.patch
```

The current repository has three runtime integration blockers before this can
produce candidate evidence:

1. The compose layer pulls published TeaStore images. It does not build and
   digest-pin patched webui, auth, and persistence images. The patched
   registry-client code must be embedded in all three images and their exact
   digests recorded before a run.
2. The runtime harness does not yet capture bounded, timestamped auth and
   persistence logs or invoke this extractor before sealing `receipt.json`.
   The extraction receipt must be retained and the final `app-witness.jsonl`
   SHA-256 copied into the immutable run receipt.
3. Absence of auth/persistence log rows does not prove non-execution. A future
   negative witness requires an independently captured webui attempt event and
   a terminal, hash-reconciled service-log capture receipt. Until then the
   extractor blocks missing scored pairs and never fabricates a negative row.

The local host used to construct this package has no Maven executable, so a
TeaStore Java build has not been claimed. The patch-apply check and Python
falsification suite are the local gates; image build and runtime capture remain
explicit deployment gates.

# Redactions

Every file in this bundle is byte-identical to its committed blob (see `README.md`) except the files below, and the five launch/fetch scripts,
which are working-tree copies (`harness/PROVENANCE.md`). SHA-256: *original* is the bytes exported from git (the script's source for the file), *new* is the file in this bundle. Paths are relative to the bundle root.

| File | Original sha256 | New sha256 | Replacements | What changed |
|---|---|---|---:|---|
| `harness/teastore-c-3b4a513/modules/teastore/execution/candidate_release_installer.py` | `83ba4ebe2b376282da88cfd2e0074636c900ff297eb74a60e6aee8ac7832db86` | `85c32e65212fc8c2520e32bddcb73b8cb87aa4c22c103d60d504b1086aa02a98` | 1 | FQDN: lab-host domain part replaced by <redacted-domain> |
| `harness/teastore-c-3b4a513/modules/teastore/execution/candidate_runtime_adapter.py` | `9803dd1b9014e6115e459f816cce3d37aac83ea596d7067633d7c0517764a172` | `0f4e7f105aa0a8428a5a2d36cf44a4091ec12147ae1c40ec683473ef7b3fa555` | 1 | FQDN: lab-host domain part replaced by <redacted-domain> |
| `harness/teastore-offpath-f74b29b/modules/teastore/execution/candidate_release_installer.py` | `83ba4ebe2b376282da88cfd2e0074636c900ff297eb74a60e6aee8ac7832db86` | `85c32e65212fc8c2520e32bddcb73b8cb87aa4c22c103d60d504b1086aa02a98` | 1 | FQDN: lab-host domain part replaced by <redacted-domain> |
| `harness/teastore-offpath-f74b29b/modules/teastore/execution/candidate_runtime_adapter.py` | `9803dd1b9014e6115e459f816cce3d37aac83ea596d7067633d7c0517764a172` | `0f4e7f105aa0a8428a5a2d36cf44a4091ec12147ae1c40ec683473ef7b3fa555` | 1 | FQDN: lab-host domain part replaced by <redacted-domain> |
| `harness/teastore-offpath-placement-04254228/modules/teastore/execution/candidate_release_installer.py` | `83ba4ebe2b376282da88cfd2e0074636c900ff297eb74a60e6aee8ac7832db86` | `85c32e65212fc8c2520e32bddcb73b8cb87aa4c22c103d60d504b1086aa02a98` | 1 | FQDN: lab-host domain part replaced by <redacted-domain> |
| `harness/teastore-offpath-placement-04254228/modules/teastore/execution/candidate_runtime_adapter.py` | `9803dd1b9014e6115e459f816cce3d37aac83ea596d7067633d7c0517764a172` | `0f4e7f105aa0a8428a5a2d36cf44a4091ec12147ae1c40ec683473ef7b3fa555` | 1 | FQDN: lab-host domain part replaced by <redacted-domain> |
| `research/PLAN_LANES_20261014.md` | `46c8cf8379a972512c90407fcd3e88c35709cef50790ff7e59c5197cfc395bb1` | `c5adfa4b72a20d4a6597116b265035768766d0dbb6a27bccae964919dd825889` | 1 | incident-review heading and bullets (original lines 20-25) replaced by a neutral heading and one sentence |

Total: 7 files changed, 7 replacements.

Rules (same as v1): the lab-host domain part of a fully qualified host name becomes `<redacted-domain>` (short host names `fb14srv4/5/6` stay); the design note drawn from a private incident review in `research/PLAN_LANES_20261014.md` is replaced by a neutral heading and one sentence; files that carry a cloud account identifier are not shipped (below). Any digest in the bundle that pins a changed file no longer matches the copy here.

`research/PLAN_LANES_20261014.md`: the v1 copy had new sha256 `c5adfa4b72a20d4a6597116b265035768766d0dbb6a27bccae964919dd825889` from original `46c8cf8379a972512c90407fcd3e88c35709cef50790ff7e59c5197cfc395bb1`; this build's original is `46c8cf8379a972512c90407fcd3e88c35709cef50790ff7e59c5197cfc395bb1` and new is `c5adfa4b72a20d4a6597116b265035768766d0dbb6a27bccae964919dd825889` (same as v1).

## Files not shipped because of the scan (not redactions: absent from the bundle)

| Path | Reason |
|---|---|
| `harness/hotel-offpath-9ad0b98/src/obsplacement/execution/aws_ec2.py` | hard scan hit: AWS-ACCOUNT-ID-CONSTANT |
| `harness/hotel-offpath-9ad0b98/src/obsplacement/execution/aws_remote.py` | imports excluded module aws_ec2.py |
| `harness/hotel-offpath-9ad0b98/tests/test_aws_ec2_executor.py` | hard scan hit: AWS-ACCOUNT-ID-IN-ARN |
| `harness/otel-ablation-4ab4433/src/obsplacement/execution/aws_ec2.py` | hard scan hit: AWS-ACCOUNT-ID-CONSTANT |
| `harness/otel-ablation-4ab4433/src/obsplacement/execution/aws_remote.py` | imports excluded module aws_ec2.py |
| `harness/otel-ablation-4ab4433/tests/test_aws_ec2_executor.py` | hard scan hit: AWS-ACCOUNT-ID-IN-ARN |
| `harness/otel-c-8018a19/src/obsplacement/execution/aws_ec2.py` | hard scan hit: AWS-ACCOUNT-ID-CONSTANT |
| `harness/otel-c-8018a19/src/obsplacement/execution/aws_remote.py` | imports excluded module aws_ec2.py |
| `harness/otel-c-8018a19/tests/test_aws_ec2_executor.py` | hard scan hit: AWS-ACCOUNT-ID-IN-ARN |
| `harness/otel-e-6a5c2a9/src/obsplacement/execution/aws_ec2.py` | hard scan hit: AWS-ACCOUNT-ID-CONSTANT |
| `harness/otel-e-6a5c2a9/src/obsplacement/execution/aws_remote.py` | imports excluded module aws_ec2.py |
| `harness/otel-e-6a5c2a9/tests/test_aws_ec2_executor.py` | hard scan hit: AWS-ACCOUNT-ID-IN-ARN |
| `harness/otel-f-715d57b/src/obsplacement/execution/aws_ec2.py` | hard scan hit: AWS-ACCOUNT-ID-CONSTANT |
| `harness/otel-f-715d57b/src/obsplacement/execution/aws_remote.py` | imports excluded module aws_ec2.py |
| `harness/otel-f-715d57b/tests/test_aws_ec2_executor.py` | hard scan hit: AWS-ACCOUNT-ID-IN-ARN |
| `harness/otel-seed2-f08ba1d/src/obsplacement/execution/aws_ec2.py` | hard scan hit: AWS-ACCOUNT-ID-CONSTANT |
| `harness/otel-seed2-f08ba1d/src/obsplacement/execution/aws_remote.py` | imports excluded module aws_ec2.py |
| `harness/otel-seed2-f08ba1d/tests/test_aws_ec2_executor.py` | hard scan hit: AWS-ACCOUNT-ID-IN-ARN |
| `harness/teastore-c-3b4a513/src/obsplacement/execution/aws_ec2.py` | hard scan hit: AWS-ACCOUNT-ID-CONSTANT |
| `harness/teastore-c-3b4a513/src/obsplacement/execution/aws_remote.py` | imports excluded module aws_ec2.py |
| `harness/teastore-c-3b4a513/tests/test_aws_ec2_executor.py` | hard scan hit: AWS-ACCOUNT-ID-IN-ARN |
| `harness/teastore-offpath-f74b29b/src/obsplacement/execution/aws_ec2.py` | hard scan hit: AWS-ACCOUNT-ID-CONSTANT |
| `harness/teastore-offpath-f74b29b/src/obsplacement/execution/aws_remote.py` | imports excluded module aws_ec2.py |
| `harness/teastore-offpath-f74b29b/tests/test_aws_ec2_executor.py` | hard scan hit: AWS-ACCOUNT-ID-IN-ARN |
| `harness/teastore-offpath-placement-04254228/src/obsplacement/execution/aws_ec2.py` | hard scan hit: AWS-ACCOUNT-ID-CONSTANT |
| `harness/teastore-offpath-placement-04254228/src/obsplacement/execution/aws_remote.py` | imports excluded module aws_ec2.py |
| `harness/teastore-offpath-placement-04254228/tests/test_aws_ec2_executor.py` | hard scan hit: AWS-ACCOUNT-ID-IN-ARN |
| `src/obsplacement/execution/aws_ec2.py` | hard scan hit: AWS-ACCOUNT-ID-CONSTANT |
| `src/obsplacement/execution/aws_remote.py` | imports excluded module aws_ec2.py |


| `research/protocol/make_bib_w1.py` | work email address in a User-Agent string replaced by `fhuebscher@users.noreply.github.com` (applied to the push snapshot after the v2 build) | `1eeacdf04c4aed96b2f1ecf5c2e9bbb005798372dac9d94e52423de57b5e6576` | `26de649e310075fd9c18bb6d8cca55123666fae39c2adf39e4d2b3514306821f` |

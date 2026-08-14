# Checkpoint 3 qualification harness revision V2

Status: prospective infrastructure correction, made before qualification execution and before
inspection of protected task source or outcomes.

The corpus lock, project split, complete within-project candidate order, upstream BugsInPy commit,
qualification criterion, and timeout remain frozen.

V1 cloned buggy and fixed commits directly. This omits an essential BugsInPy checkout operation:
the regression test from the fixed commit must be copied into the buggy checkout. Without that
operation, a buggy checkout may execute an older or absent test and produce a false
`buggy_unreproduced` infrastructure negative.

V2 therefore:

1. verifies the same frozen metadata hashes;
2. checks out and verifies the exact fixed and buggy commits;
3. reproduces the essential official BugsInPy checkout rule by copying the fixed regression test
   into the exact buggy checkout before execution;
4. provisions a disposable virtual environment with the bug's declared Python patch version;
5. executes every non-empty relevant-test command and records subprocess return codes;
6. requires all fixed relevant tests to pass and at least one buggy relevant test to fail;
7. retains all provisioning, timeout, network, checkout, and reproduction failures as
   infrastructure negatives.

Direct use of the upstream checkout script was rejected for this harness because its fixed-version
mode leaves `HEAD` at the buggy commit and overlays fixed files. V2 instead keeps exact commit
identity while applying only the benchmark's fixed regression test to the buggy checkout. The V1
artifact remains in the repository as negative harness provenance. No V1 qualification outcome is
used.

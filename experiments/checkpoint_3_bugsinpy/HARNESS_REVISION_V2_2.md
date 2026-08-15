# Checkpoint 3 qualification harness revision V2.2

Status: infrastructure-only correction. Recovery run `31853219181` successfully started the five
encoding-recovery shards. Its three Python 3.6 shards stopped before candidate execution because
the container rejected the host-owned pinned BugsInPy checkout. V2.2 adds that exact checkout to
Git's container-local safe-directory list and replays only the three Python 3.6 shards.

No corpus, ordering, metadata, verifier, timeout, or qualification rule changes.

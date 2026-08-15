# Checkpoint 3 qualification harness revision V2.1

Status: prospective infrastructure correction. The corpus, project split, candidate order,
metadata hashes, upstream commit, qualification criterion, and timeout remain frozen.

Preflight 002 is GitHub Actions run `31851256761`. It established two execution barriers without
changing any scientific verdict:

1. Five project requirement files are UTF-16 with a byte-order mark. V2 assumed UTF-8 and stopped
   before recording an attempt. V2.1 deterministically decodes BOM-marked UTF-16 and otherwise
   requires UTF-8 (optionally with a BOM). The locked file bytes and hashes are unchanged.
2. GitHub's Ubuntu 22.04 Python installer does not provide Python 3.6. The three frozen Python 3.6
   projects are therefore executed in a pinned `python:3.6.15-buster` container. The declared and
   executed versions remain recorded and major/minor mismatches remain rejected.

Only the eight infrastructure-blocked project shards are replayed. Completed V2 shards are not
rerun or replaced. Every V2 and V2.1 artifact remains separate and attributable.

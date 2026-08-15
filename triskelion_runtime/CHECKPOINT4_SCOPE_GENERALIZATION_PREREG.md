# Checkpoint 4 — scope-generalization pre-registration

Status: **PRE-REGISTERED BEFORE ANY FRESH PROTECTED CASE IS INSPECTED**.

Checkpoint 3 is immutable. Its repaired protected run (`31880097475`) is retained as a complete negative: 5/5 evaluable cases in all four arms, zero repairs, VERIFIED activation 0/5, ALWAYS_ON activation 5/5 with 100% false activation.

## Diagnostic motivating CP4

The sole admitted CP3 rule is route-unsatisfiable under the frozen literal-substring semantics: `re.sub` appears in both a positive signature set and `forbidden_any`. Because negatives are checked first, no context containing the required `re.sub` signal can activate the rule. CP3 therefore establishes a compiler/admission failure mode, not evidence that a satisfiable verified capability cannot transfer.

CP4 may not alter or reinterpret the CP3 rows. It is a new prospective experiment.

## Frozen questions

1. Can acquisition evidence compile into at least one **route-satisfiable, non-leaking, mechanism-level** rule?
2. On fresh disjoint protected cases, does VERIFIED routing improve repair success over COLD while avoiding the false activation of ALWAYS_ON?
3. Does disabling the admitted capability remove any observed advantage and re-enabling it restore that advantage?

## Freshness boundary

All CP3 acquisition and protected IDs are excluded from CP4. No CP3 protected production source, gold patch, model output, or per-case repair result may be used to choose CP4 cases, rules, thresholds, or prompts.

CP4 case selection is frozen from the remaining BugsInPy lock order. Qualification may use fixed commits only to establish `fixed passes / buggy fails`; **split and mechanism grouping use buggy-visible evidence only**.

## Mechanism-balanced split

Arbitrary cross-project splitting is replaced by a prospective buggy-visible grouping rule:

- construct a deterministic fingerprint from failing test command/name, exception/assertion class, and normalized failure-message tokens;
- remove project name, bug ID, absolute paths, commit hashes, numbers longer than 3 digits, and low-information stop tokens;
- compute token-set similarity deterministically;
- only admit a transfer family when it contains at least 2 qualified cases and the family assignment was made without fixed-source/gold-patch features;
- first frozen member is acquisition; later frozen members are protected;
- protected cases remain unopened to the compiler.

If no qualifying transfer family exists, CP4 terminates `NO_MATCHED_TRANSFER_FAMILY`; cases are not hand-selected.

## Capability contract V2

The rule schema remains declarative. Admission adds hard invariants before a rule can exist:

### 1. Route satisfiability

For literal substring routing, reject a rule if any `required_all` signature entails a forbidden signature (the forbidden string is a substring of the required signature). If `required_any` is nonempty, reject when every alternative entails at least one forbidden signature. Exact positive/negative overlap is therefore impossible.

### 2. Fixed-patch leakage in both directions

For every normalized signature/instruction span of length >=16 and every normalized added fixed-patch line of length >=16, reject if either is a substring of the other. This closes the CP3 loophole where an exact inner expression from a fixed line could pass because only `fixed_line in output` was tested.

### 3. Prospective activation sanity

Before protected evaluation, every admitted rule must activate on its own **buggy acquisition context** and must not require text that exists only in the fixed patch. This is an acquisition-only sanity check, not a performance filter.

### 4. No manual rescue

No manual rule editing, deletion, signature rewriting, threshold tuning, protected-case selection, or post-hoc scope widening is allowed. Invalid compiler outputs are recorded as negatives.

## Frozen arms

Exactly four arms on every fresh protected case:

- `cold`: no acquisition memory/capability;
- `raw_memory`: acquisition evidence, no compiled routing;
- `always_on`: every admitted rule exposed;
- `verified`: only route-matching admitted rules exposed.

Same base model, temperature, call count, token budget, repair parser, historical target verifier, and case ordering across arms.

## Primary success criterion

CP4 PASS requires all of:

- 100% evaluable protected coverage;
- at least one admitted route-satisfiable capability;
- VERIFIED has at least one protected repair success where COLD fails;
- the repaired case had VERIFIED activation;
- VERIFIED false-activation rate < ALWAYS_ON false-activation rate;
- no protected case/source/gold information entered capability construction;
- disable/re-enable reproduces loss/restoration for a selected successful protected demonstration case.

Otherwise CP4 is a valid negative or infrastructure negative according to the frozen failure taxonomy. No tuning against protected results is permitted.

# Triskelion × DeepSeek Harness

This integration mounts Triskelion's verifier-controlled capability lifecycle into DeepSeek Harness without moving developmental authority into the model or the harness.

DeepSeek Harness supplies the host/plugin boundary. Triskelion supplies content-addressed capability admission, enable/disable/uninstall lifecycle, and the same deterministic scope semantics used by Checkpoint 3.

## What is wired now

The Harness plugin exposes six model-facing tools:

- `triskelion_status`
- `triskelion_install`
- `triskelion_enable`
- `triskelion_disable`
- `triskelion_uninstall`
- `triskelion_route`

`triskelion_install` accepts a Checkpoint-3-style `CAPABILITY.json`. Before admission, the Python bridge:

1. validates every public rule with `checkpoint3_eval_core.rule_from_public`;
2. recomputes the canonical SHA-256 capability id and rejects tampering;
3. copies the admitted package into local Triskelion runtime state;
4. enables it.

`triskelion_route` applies the existing `verified` scope arm to only enabled installed capability rules. Disabling or uninstalling the capability therefore provides a direct causal ablation while the underlying model weights remain unchanged.

Local runtime state is stored under `.triskelion/deepseek-harness/` and is intentionally gitignored.

## Deliberate boundary

This first adapter wires the **scoped declarative capability channel** already frozen for BugsInPy Checkpoint 3. It does not pretend that a Checkpoint 3 repair rule is an executable artifact, and it does not silently train or modify model weights.

The earlier Triskelion runtime also has evidence for executable artifacts. A later Harness adapter can add an executable-artifact service behind the same lifecycle once its package contract is frozen. River remains the separate neural-learning/control arm for experiments that compile verified capability into weights.

## Setup

Requirements: Git, Node.js, pnpm, and Python 3.10+.

From the MathGraph/Triskelion checkout on `triskelion-runtime-cp1`:

```bash
bash integrations/deepseek-harness/setup.sh
```

The setup script clones DeepSeek Harness into `.external/deepseek-harness`, pins it to:

```text
47f943859bef60e4160492346772ded9b24f765a
```

and builds it using the upstream source instructions. It copies the local Triskelion plugin into the Harness checkout and generates a Cordis overlay with the absolute paths Harness requires for local plugins.

Then run the command printed by the script, currently:

```bash
cd .external/deepseek-harness
pnpm dsh web --patch scratch-plugin/triskelion/cordis.yml
```

Open `http://127.0.0.1:3080` and ask the agent to call `triskelion_status`.

## Immediate integration smoke test

`SMOKE_CAPABILITY.json` exists only to verify the Harness lifecycle. It is explicitly **not scientific evidence** and should never be reported as a learned capability result.

In Harness, call:

```text
triskelion_install({"capability_path":"integrations/deepseek-harness/SMOKE_CAPABILITY.json"})
```

Then:

```text
triskelion_route({"visible_context":"triskelion-smoke-trigger"})
```

The route should activate `smoke-rule-v1`. Disable the returned capability id and call the same route again; it must not activate. Re-enable and it must activate again. Uninstall and it must disappear from `triskelion_status`.

This proves only that native Harness → Triskelion lifecycle/routing plumbing works. The real demo substitutes a verifier-produced capability and an externally decided unseen task.

## Install a learned capability

After a capability build has produced a `CAPABILITY.json`, place or copy it somewhere inside this repository, for example:

```text
.triskelion/imports/cp3/CAPABILITY.json
```

Then the Harness agent can call:

```text
triskelion_install({"capability_path":".triskelion/imports/cp3/CAPABILITY.json"})
```

The returned `capability_id` is the content identity used for enable/disable/uninstall.

For a task/failure/source context, call:

```text
triskelion_route({"visible_context":"..."})
```

A matching enabled rule returns `activated: true`, its matched rule ids, and only the routed repair guidance. Nonmatching rules are not exposed.

## Causal demo sequence

The intended live experiment is:

```text
FROZEN AGENT + no capability
  -> task fails

verified CAPABILITY.json
  -> triskelion_install
  -> triskelion_route activates on the relevant unseen context
  -> agent retries
  -> verifier passes

triskelion_disable
  -> same frozen agent / same unseen task
  -> routed capability disappears
  -> failure returns

triskelion_enable
  -> pass is restored
```

That sequence isolates the installed capability state from model weights. It should only be presented as a competence result when the external task verifier actually supplies the PASS/FAIL decision.

## Tests

The bridge lifecycle test covers install, content-address verification, scope activation, disable ablation, restore, and uninstall:

```bash
pytest -q tests/test_deepseek_harness_bridge.py tests/test_checkpoint3_eval_core.py
```

The TypeScript plugin follows DeepSeek Harness's current native tool contract (`@deepseek-ai/cordis` + `@deepseek-ai/dsh-tools`) and is intentionally pinned to the upstream Harness revision above because Harness is still in developer preview.

A GitHub Actions workflow at `.github/workflows/deepseek-harness-integration.yml` checks the Python lifecycle and imports the plugin against the pinned upstream Harness packages.

## Architecture

```text
DeepSeek Harness agent
        |
        | native Harness tools
        v
triskelion-plugin.ts
        |
        | JSON over local subprocess boundary
        v
bridge.py
        |
        +--> content-addressed local registry
        |
        +--> Checkpoint 3 rule validation
        |
        +--> verified scope routing
        v
external task verifier decides PASS / FAIL
```

Harness is the host. Triskelion remains the capability authority.

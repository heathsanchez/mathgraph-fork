"""Opt-in source-exact Open MCT behavior test; requires pinned local checkout.

Use OPENMCT_PINNED_CHECKOUT=... for native-class/source replay in CI or local
research. No vendor files or generated output are bundled in MathGraph.
"""

import json
from hashlib import sha256
import os
from pathlib import Path
import subprocess

import pytest

from research.gap_conditional_cell.six_questions import evaluate_case


CHECKOUT = os.environ.get("OPENMCT_PINNED_CHECKOUT")


@pytest.mark.skipif(not CHECKOUT, reason="external pinned Open MCT checkout not supplied")
def test_original_openmct_api_coalesces_distinguishable_provider_filters():
    checkout = Path(CHECKOUT)
    result = subprocess.run(
        ["node", "--no-warnings", "--experimental-vm-modules",
         "research/gap_conditional_cell/openmct_replay.mjs", str(checkout)],
        capture_output=True, text=True, check=True,
    )
    output = json.loads(result.stdout)
    assert output["source_commit"] == "e09bfaf47856b2b7ae2ea74334800b26fd27a41e"
    assert output["telemetry_api_sha256"] == "95c39cfe100fb27724927976a1cc50a0576becb28e9f70e58c159803bc827802"
    assert output["options_json_distinct"] is True
    assert output["alias_numeric_values"] == [0, 1]
    assert output["shared_provider_subscriptions"] == 1
    assert output["shared_received"] == [[0], [0]]
    assert output["independent_control_received"] == [1]
    assert output["identical_options_reused"] is True

    # Route the fresh, original-class behavioral receipt through all six
    # obligations. This author-declared target is supported by the independent
    # state-1 control and upstream issue #7933, not inferred by the evaluator.
    case = {
        "id": "openmct-two-state-filters",
        "authority": "declared",
        "complete": False,
        "rows": [
            {"input": {"filter": "off"}, "old_image": output["shared_received"][0], "target": [0]},
            {"input": {"filter": "on"}, "old_image": output["shared_received"][1], "target": [1]},
        ],
    }
    source_bytes = (checkout / "src/api/telemetry/TelemetryAPI.js").read_bytes()
    report = evaluate_case(
        case, input_types={"filter": "string"}, old_type="array",
        source_bytes=source_bytes, source_sha256=sha256(source_bytes).hexdigest(),
        replay=lambda row: output["shared_received"][0 if row["filter"] == "off" else 1],
    )
    assert report["checks"]["meaning_gap"] == "CONSEQUENTIAL_COLLISION"
    assert report["verdict"] == "WARRANTED_BOUNDED_CONDITIONAL_RELATION"
    assert report["may_change"] is False

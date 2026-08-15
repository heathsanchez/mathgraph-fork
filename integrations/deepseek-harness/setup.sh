#!/usr/bin/env bash
set -euo pipefail

DEEPSEEK_HARNESS_COMMIT="47f943859bef60e4160492346772ded9b24f765a"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HARNESS_DIR="${1:-${REPO_ROOT}/.external/deepseek-harness}"
PLUGIN_DIR="${HARNESS_DIR}/scratch-plugin/triskelion"
PATCH_FILE="${PLUGIN_DIR}/cordis.yml"

command -v git >/dev/null || { echo "git is required" >&2; exit 2; }
command -v node >/dev/null || { echo "Node.js is required" >&2; exit 2; }
command -v pnpm >/dev/null || { echo "pnpm is required" >&2; exit 2; }
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }

if [[ ! -d "${HARNESS_DIR}/.git" ]]; then
  mkdir -p "$(dirname "${HARNESS_DIR}")"
  git clone https://github.com/deepseek-ai/deepseek-harness.git "${HARNESS_DIR}"
fi

git -C "${HARNESS_DIR}" fetch origin "${DEEPSEEK_HARNESS_COMMIT}"
git -C "${HARNESS_DIR}" checkout --detach "${DEEPSEEK_HARNESS_COMMIT}"

(
  cd "${HARNESS_DIR}"
  pnpm install
  pnpm run build
)

mkdir -p "${PLUGIN_DIR}"
cp "${REPO_ROOT}/integrations/deepseek-harness/triskelion-plugin.ts" \
   "${PLUGIN_DIR}/triskelion-plugin.ts"

PLUGIN_JSON="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "${PLUGIN_DIR}/triskelion-plugin.ts")"
ROOT_JSON="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "${REPO_ROOT}")"
cat > "${PATCH_FILE}" <<EOF
- insert:
    - id: triskelion-runtime
      name: ${PLUGIN_JSON}
      config:
        repoRoot: ${ROOT_JSON}
        pythonExecutable: 'python3'
EOF

cat <<EOF

Triskelion DeepSeek Harness integration is ready.
Pinned Harness commit: ${DEEPSEEK_HARNESS_COMMIT}
Patch: ${PATCH_FILE}

Start it with:
  cd ${HARNESS_DIR}
  pnpm dsh web --patch ${PATCH_FILE}

Then open http://127.0.0.1:3080 and ask the agent to call triskelion_status.
EOF

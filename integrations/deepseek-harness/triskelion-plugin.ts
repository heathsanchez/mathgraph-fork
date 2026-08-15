import { spawn } from 'node:child_process'
import { join } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import Schema from '@deepseek-ai/schemastery'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'triskelion-runtime'
export const inject = ['tools']

export interface Config {
  repoRoot: string
  pythonExecutable: string
}

export const Config: Schema<Config> = Schema.object({
  repoRoot: Schema.string().required(),
  pythonExecutable: Schema.string().default('python3'),
})

type BridgeRequest = Record<string, unknown>
type BridgeResponse = Record<string, unknown> & { ok?: boolean; message?: string }

function callBridge(config: Config, request: BridgeRequest, signal: AbortSignal): Promise<BridgeResponse> {
  const bridge = join(config.repoRoot, 'integrations', 'deepseek-harness', 'bridge.py')
  return new Promise((resolve, reject) => {
    const child = spawn(config.pythonExecutable, [bridge], {
      cwd: config.repoRoot,
      env: { ...process.env, TRISKELION_REPO_ROOT: config.repoRoot },
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    let stdout = ''
    let stderr = ''
    let settled = false

    const abort = () => {
      if (!settled) child.kill('SIGTERM')
    }
    signal.addEventListener('abort', abort, { once: true })

    child.stdout.setEncoding('utf8')
    child.stderr.setEncoding('utf8')
    child.stdout.on('data', chunk => {
      stdout += chunk
      if (stdout.length > 2_000_000) child.kill('SIGTERM')
    })
    child.stderr.on('data', chunk => {
      stderr += chunk
      if (stderr.length > 200_000) child.kill('SIGTERM')
    })
    child.on('error', error => {
      settled = true
      signal.removeEventListener('abort', abort)
      reject(error)
    })
    child.on('close', code => {
      if (settled) return
      settled = true
      signal.removeEventListener('abort', abort)
      if (signal.aborted) {
        reject(new Error('Triskelion bridge call aborted'))
        return
      }
      if (code !== 0) {
        reject(new Error(`Triskelion bridge exited ${code}: ${stderr.slice(-4000)}`))
        return
      }
      try {
        const response = JSON.parse(stdout.trim()) as BridgeResponse
        if (response.ok !== true) {
          reject(new Error(String(response.message ?? 'Triskelion bridge rejected request')))
          return
        }
        resolve(response)
      } catch (error) {
        reject(new Error(`Invalid Triskelion bridge response: ${String(error)}`))
      }
    })

    child.stdin.end(JSON.stringify(request))
  })
}

function renderJson(value: string) {
  return [{ type: 'text' as const, text: value }]
}

async function executeJson(config: Config, request: BridgeRequest, signal: AbortSignal): Promise<string> {
  const result = await callBridge(config, request, signal)
  return JSON.stringify(result)
}

export function apply(ctx: Context, config: Config) {
  ctx.tools.register(defineTool({
    name: 'triskelion_status',
    description: 'List verifier-controlled Triskelion capabilities installed for this agent and whether each is enabled.',
    parameters: {},
    output: { schema: { type: 'string' }, render: (_args, value) => renderJson(value) },
    async execute(_args, exec) {
      return executeJson(config, { action: 'status' }, exec.signal)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'triskelion_install',
    description: 'Install and enable a verified Triskelion CAPABILITY.json that already exists inside the Triskelion repository. The bridge verifies its content-addressed capability id before admission.',
    parameters: {
      capability_path: {
        type: 'string',
        required: true,
        description: 'Repository-relative path to a verified CAPABILITY.json',
      },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => renderJson(value) },
    async execute(args, exec) {
      return executeJson(config, { action: 'install', capability_path: args.capability_path }, exec.signal)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'triskelion_enable',
    description: 'Enable an installed Triskelion capability without changing the model weights.',
    parameters: {
      capability_id: { type: 'string', required: true, description: 'Installed capability sha256 id' },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => renderJson(value) },
    async execute(args, exec) {
      return executeJson(config, { action: 'enable', capability_id: args.capability_id }, exec.signal)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'triskelion_disable',
    description: 'Disable an installed Triskelion capability for a causal ablation without deleting its persisted package.',
    parameters: {
      capability_id: { type: 'string', required: true, description: 'Installed capability sha256 id' },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => renderJson(value) },
    async execute(args, exec) {
      return executeJson(config, { action: 'disable', capability_id: args.capability_id }, exec.signal)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'triskelion_uninstall',
    description: 'Uninstall a Triskelion capability and remove its persisted local package from the Harness registry.',
    parameters: {
      capability_id: { type: 'string', required: true, description: 'Installed capability sha256 id' },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => renderJson(value) },
    async execute(args, exec) {
      return executeJson(config, { action: 'uninstall', capability_id: args.capability_id }, exec.signal)
    },
  }))

  ctx.tools.register(defineTool({
    name: 'triskelion_route',
    description: 'Apply Triskelion verified scope routing to visible task or failure context. Returns only guidance from enabled capability rules whose frozen applicability conditions match.',
    parameters: {
      visible_context: {
        type: 'string',
        required: true,
        description: 'Visible task, source, verifier failure, or other context used for deterministic scope matching',
      },
    },
    output: { schema: { type: 'string' }, render: (_args, value) => renderJson(value) },
    async execute(args, exec) {
      return executeJson(config, { action: 'route', visible_context: args.visible_context }, exec.signal)
    },
  }))
}

export interface AppConfig {
  region: string
  userPoolId: string
  clientId: string
}

/** Runtime config written by the CDK deployment (public identifiers only). */
export async function loadConfig(): Promise<AppConfig> {
  const res = await fetch('/config.json', { cache: 'no-store' })
  const type = res.headers.get('content-type') ?? ''
  if (!res.ok || !type.includes('json')) throw new Error('config.json not found')
  const cfg = (await res.json()) as Partial<AppConfig>
  if (!cfg.region || !cfg.userPoolId || !cfg.clientId) throw new Error('config.json is incomplete')
  return cfg as AppConfig
}

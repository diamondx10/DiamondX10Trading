// Fetch wrapper for the dx10 backend (same origin, /api/*).
export interface DeskStatus { desk: string; equity: number | null; open_positions: number }
export interface Status { equity: number | null; capital: number; drawdown_pct: number | null; kill_switch_on: boolean; mt5_ok: boolean; telegram_ready: boolean; live_running: boolean; listener_running: boolean; desks: DeskStatus[] }
export interface Position { desk: string; symbol: string; direction: string; entry: number; sl: number | null; tp: number | null; volume: number; unrealised_pnl: number | null; opened: string }
export interface Signal { symbol: string; action: string; rsi: number | null; atr: number | null; patterns: string[]; regime: string | null }
export interface SynthesisItem { symbol: string; ta_action: string; fa_direction: string | null; fa_confidence: number | null; recommendation: string; size_factor: number | null; verdict_age_hours: number | null; rationale: string }
export interface PendingOrder { id: string; desk: string; manager: string; symbol: string; action: string; entry: number; sl: number | null; tp: number | null; volume: number; risk_usd: number | null; status: string; created_utc: string; expires_utc: string; ticket: number | null }
export interface DecisionRow { time: string; symbol: string; action: string; reason: string; desk: string; manager: string }
export interface Briefing { desk: string; file: string; name: string; created: string; path: string }
export interface Verdict { desk: string; analyst: string; direction: string; confidence: number | null; drivers: string[]; risks: string[]; note: string; created_utc: string; age_hours: number | null }
export interface Article { title: string; url: string; source: string; tier: number | string; published: string }
export interface Bar { time: string; open: number; high: number; low: number; close: number }
export interface MuseJob { status: 'sending' | 'sent' | 'verdict_stored' | 'timeout' | 'error'; verdict: Record<string, unknown> | null; reason: string }
export interface TeamNewsItem { title: string; source: string; tier: number | string; desk: string; analyst: string; time: string; briefing_url: string | null }
export interface TeamNewsVerdict { direction: string; confidence: number | null }
export interface TeamNewsBriefing { desk: string; file: string; time: string }
export interface TeamNews { items: TeamNewsItem[]; verdicts: Record<string, TeamNewsVerdict | null>; briefings: TeamNewsBriefing[] }

// Analysis feed (homepage): GET /api/posts, POST /api/posts, POST /api/publish.
// Every post carries a conclusion (action BUY/SELL/NEUTRAL). The backend
// sends a Telegram summary whenever the conclusion is BUY or SELL.
export interface Post {
  id: string
  created_utc: string
  desk: string
  analyst: string
  symbol: string
  action: 'BUY' | 'SELL' | 'NEUTRAL'
  confidence: number | null
  summary: string
  drivers: string[]
  risks: string[]
  entry: number | null
  sl: number | null
  tp: number | null
  source: string
  verdict_created_utc: string | null
}
export interface PostsResponse { posts: Post[] }
export interface PostCreate {
  desk: string
  symbol: string
  action: string
  summary: string
  confidence?: number | null
  entry?: number | null
  sl?: number | null
  tp?: number | null
  drivers?: string[]
  risks?: string[]
}

export async function fetchPosts(limit = 20, desk?: string): Promise<PostsResponse> {
  const q = new URLSearchParams({ limit: String(limit) })
  if (desk) q.set('desk', desk)
  return apiGet<PostsResponse>(`/api/posts?${q.toString()}`)
}

export async function createPost(body: PostCreate): Promise<{ post: Post }> {
  return apiPost<{ post: Post }>('/api/posts', body)
}

export async function publishPosts(desk?: string, symbol?: string): Promise<PostsResponse> {
  const body: Record<string, string> = {}
  if (desk) body.desk = desk
  if (symbol) body.symbol = symbol
  return apiPost<PostsResponse>('/api/publish', body)
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const j = await res.json(); detail = j.detail || j.reason || detail } catch { /* keep default */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

// ---- OTP auth + manager console + terminal logs ----
// Auth uses an httpOnly cookie ("dx10_session") set by the backend on a
// successful verify; the browser sends it automatically afterwards. The OTP
// itself is never present in any response and is never logged here.
export interface AuthStatus { authenticated: boolean }
export interface OtpRequestResult { sent: boolean; fallback?: string; reason?: string }
export interface LiveState { running: boolean; mode: string | null; started: string | null }
export interface ListenerState { running: boolean }
export interface ActionResult { ok: boolean; reason: string }
export type LogProcess = 'live' | 'listener' | 'diagnostics'
export interface LogResponse { process: string; running: boolean; started_utc: string | null; exit_code: number | null; lines: string[]; total: number }

export interface OtpFailure extends Error {
  code?: string
  retryAfter?: number
}

function otpError(message: string, code?: string, retryAfter?: number): OtpFailure {
  const e = new Error(message) as OtpFailure
  e.code = code
  e.retryAfter = retryAfter
  return e
}

export async function getAuthStatus(): Promise<AuthStatus> {
  return apiGet<AuthStatus>('/api/auth/status')
}

export async function requestOtp(): Promise<OtpRequestResult> {
  const res = await fetch('/api/auth/request-otp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>
  if (res.status === 429) {
    const retryAfter = typeof body.retry_after === 'number' ? body.retry_after : 60
    throw otpError(`HTTP 429`, 'cooldown', retryAfter)
  }
  if (!res.ok) {
    throw otpError(typeof body.reason === 'string' ? body.reason : `HTTP ${res.status}`, 'send_failed')
  }
  return body as unknown as OtpRequestResult
}

export async function verifyOtp(code: string): Promise<void> {
  const res = await fetch('/api/auth/verify-otp', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>
    const reason = typeof body.reason === 'string' ? body.reason : `HTTP ${res.status}`
    throw otpError(reason, reason)
  }
}

export async function signOut(): Promise<void> {
  await apiPost('/api/auth/sign-out')
}

export async function startLive(mode: 'recommend' | 'auto', desk = 'forex'): Promise<ActionResult> {
  return apiPost<ActionResult>('/api/live/start', { mode, desk })
}
export async function stopLive(): Promise<ActionResult> {
  return apiPost<ActionResult>('/api/live/stop')
}
export async function getLive(): Promise<LiveState> {
  return apiGet<LiveState>('/api/live')
}
export async function startListener(): Promise<ActionResult> {
  return apiPost<ActionResult>('/api/listener/start')
}
export interface StartAllResult { live: ActionResult; listener: ActionResult }
export async function startAll(): Promise<StartAllResult> {
  return apiPost<StartAllResult>('/api/start-all')
}
export async function stopListener(): Promise<ActionResult> {
  return apiPost<ActionResult>('/api/listener/stop')
}
export async function getListener(): Promise<ListenerState> {
  return apiGet<ListenerState>('/api/listener')
}
export async function runDiagnostics(): Promise<ActionResult> {
  return apiPost<ActionResult>('/api/diagnostics')
}
export async function telegramTest(): Promise<ActionResult> {
  return apiPost<ActionResult>('/api/telegram-test')
}
export async function toggleKillSwitch(on: boolean): Promise<unknown> {
  return apiPost('/api/kill-switch', { on })
}
export async function fetchLogs(process: LogProcess, after: number): Promise<LogResponse> {
  return apiGet<LogResponse>(`/api/logs?process=${process}&after=${after}`)
}

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path)
  return handle<T>(res)
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  return handle<T>(res)
}

export const DESKS = ['forex', 'xauusd', 'crypto', 'us_securities'] as const
export const DESK_LABELS: Record<string, string> = { forex: 'Forex', xauusd: 'Gold', crypto: 'Crypto', us_securities: 'Securities' }

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return '—'
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}
export function fmtUsd(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  const sign = v < 0 ? '-' : ''
  return `${sign}$${Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
export function fmtPct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v.toFixed(2)}%`
}

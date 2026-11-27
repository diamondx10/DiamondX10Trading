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

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try { const j = await res.json(); detail = j.detail || j.reason || detail } catch { /* keep default */ }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
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

export const DESKS = ['forex', 'gold', 'crypto', 'securities'] as const
export const DESK_LABELS: Record<string, string> = { forex: 'Forex', gold: 'Gold', crypto: 'Crypto', securities: 'Securities' }

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

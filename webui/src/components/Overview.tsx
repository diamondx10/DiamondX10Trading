import { useState } from 'react'
import { apiGet, apiPost, fmtPct, fmtUsd, type Status } from '../api'
import { Empty, Err, Loading, StatusDot, useFetch } from './shared'

export default function Overview() {
  const { data, loading, error, reload } = useFetch(() => apiGet<Status>('/api/status'))
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [live, setLive] = useState<{ running: boolean; mode: string | null; started: string | null } | null>(null)
  const [listener, setListener] = useState<{ running: boolean } | null>(null)

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(label); setMsg(null)
    try { await fn(); setMsg(`${label}: OK`); reload() } catch (e) { setMsg(`${label} that bai: ${e instanceof Error ? e.message : String(e)}`) } finally { setBusy('') }
  }

  if (loading) return <Loading />
  if (error || !data) return <Err message={error ?? 'Khong co du lieu'} onRetry={reload} />
  const s = data
  const openPositions = s.desks.reduce((a, d) => a + (d.open_positions || 0), 0)
  const dd = s.drawdown_pct ?? 0
  const ddClass = dd >= 8 ? 'bad' : dd >= 5 ? 'warn' : ''

  return (
    <div>
      {msg && <div className="notice">{msg}</div>}
      <div className="grid">
        <div className="card"><div className="stat-label">Equity</div><div className="stat-value">{fmtUsd(s.equity)}</div><div className="stat-sub">Von: {fmtUsd(s.capital)}</div></div>
        <div className="card">
          <div className="stat-label">Drawdown</div><div className="stat-value">{fmtPct(s.drawdown_pct)}</div>
          <div className="gauge"><div className={ddClass} style={{ width: `${Math.min(100, Math.max(0, dd * 10))}%` }} /></div>
          <div className="stat-sub">Gioi han: 10% — canh bao 5%</div>
        </div>
        <div className="card"><div className="stat-label">Vi the mo</div><div className="stat-value">{openPositions}</div><div className="stat-sub">Tong cac desk</div></div>
        <div className="card">
          <div className="stat-label">Trang thai</div>
          <div className="btn-row" style={{ marginTop: 8 }}>
            <StatusDot on={s.mt5_ok} label="MT5" />
            <StatusDot on={s.telegram_ready} label="Telegram" />
            <StatusDot on={s.live_running} label="Live" />
            <StatusDot on={s.listener_running} label="Listener" />
          </div>
        </div>
      </div>

      <div className="card">
        <h2>Kill switch</h2>
        <label className="toggle">
          <input type="checkbox" checked={s.kill_switch_on} disabled={busy !== ''}
            onChange={() => act(s.kill_switch_on ? 'Tat kill switch' : 'Bat kill switch', () => apiPost('/api/kill-switch', { on: !s.kill_switch_on }))} />
          <strong style={{ color: s.kill_switch_on ? 'var(--red)' : 'inherit' }}>{s.kill_switch_on ? 'DANG BAT — moi lenh deu bi chan' : 'Dang tat — giao dich binh thuong'}</strong>
        </label>
        <p className="muted small">Bat kill switch se chan moi lenh moi cho den khi tat lai.</p>
      </div>

      <div className="card">
        <h2>Live &amp; Listener</h2>
        <div className="btn-row">
          <button className="btn" disabled={busy !== ''} onClick={() => act('Start live (recommend)', async () => { const r = await apiPost<{ ok: boolean; reason: string }>('/api/live/start', { mode: 'recommend', desk: 'forex' }); if (!r.ok) throw new Error(r.reason) })}>Start live — Recommend</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={() => act('Start live (auto)', async () => { const r = await apiPost<{ ok: boolean; reason: string }>('/api/live/start', { mode: 'auto', desk: 'forex' }); if (!r.ok) throw new Error(r.reason) })}>Start live — Auto</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={() => act('Stop live', async () => { await apiPost('/api/live/stop') })}>Stop live</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={() => act('Start listener', async () => { await apiPost('/api/listener/start') })}>Start listener</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={() => act('Stop listener', async () => { await apiPost('/api/listener/stop') })}>Stop listener</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={async () => { try { setLive(await apiGet('/api/live')); setListener(await apiGet('/api/listener')) } catch (e) { setMsg(String(e)) } }}>Cap nhat trang thai</button>
        </div>
        {(live || listener) && (
          <p className="muted" style={{ marginTop: 12 }}>
            Live: {live ? (live.running ? `dang chay (${live.mode ?? ''})` : 'dung') : '—'} · Listener: {listener ? (listener.running ? 'dang chay' : 'dung') : '—'}
          </p>
        )}
      </div>

      <div className="card">
        <h2>Equity theo desk</h2>
        {s.desks.length === 0 ? <Empty /> : (
          <div className="table-wrap"><table><thead><tr><th>Desk</th><th>Equity</th><th>Vi the mo</th></tr></thead>
          <tbody>{s.desks.map((d) => <tr key={d.desk}><td>{d.desk}</td><td>{fmtUsd(d.equity)}</td><td>{d.open_positions}</td></tr>)}</tbody></table></div>
        )}
      </div>
    </div>
  )
}

import { useState } from 'react'
import { apiGet, apiPost, fmtPct, fmtUsd, type Status } from '../api'
import { useI18n } from '../i18n'
import { Empty, Err, Loading, StatusDot, useFetch } from './shared'
import AnalysisFeed from './Feed'

export default function Overview() {
  const { t } = useI18n()
  const { data, loading, error, reload } = useFetch(() => apiGet<Status>('/api/status'))
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [live, setLive] = useState<{ running: boolean; mode: string | null; started: string | null } | null>(null)
  const [listener, setListener] = useState<{ running: boolean } | null>(null)

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(label); setMsg(null)
    try { await fn(); setMsg(`${label}: ${t('common.ok')}`); reload() } catch (e) { setMsg(`${label} ${t('common.failed')}: ${e instanceof Error ? e.message : String(e)}`) } finally { setBusy('') }
  }

  if (loading) return <Loading />
  if (error || !data) return <Err message={error ?? t('common.empty')} onRetry={reload} />
  const s = data
  const openPositions = s.desks.reduce((a, d) => a + (d.open_positions || 0), 0)
  const dd = s.drawdown_pct ?? 0
  const ddClass = dd >= 8 ? 'bad' : dd >= 5 ? 'warn' : ''

  return (
    <div>
      {msg && <div className="notice">{msg}</div>}
      <div className="grid">
        <div className="card"><div className="stat-label">Equity</div><div className="stat-value">{fmtUsd(s.equity)}</div><div className="stat-sub">{t('ov.capital')}: {fmtUsd(s.capital)}</div></div>
        <div className="card">
          <div className="stat-label">{t('ov.drawdown')}</div><div className="stat-value">{fmtPct(s.drawdown_pct)}</div>
          <div className="gauge"><div className={ddClass} style={{ width: `${Math.min(100, Math.max(0, dd * 10))}%` }} /></div>
          <div className="stat-sub">{t('ov.ddLimit')}</div>
        </div>
        <div className="card"><div className="stat-label">{t('ov.openPositions')}</div><div className="stat-value">{openPositions}</div><div className="stat-sub">{t('ov.allDesks')}</div></div>
        <div className="card">
          <div className="stat-label">{t('ov.status')}</div>
          <div className="btn-row" style={{ marginTop: 8 }}>
            <StatusDot on={s.mt5_ok} label="MT5" />
            <StatusDot on={s.telegram_ready} label="Telegram" />
            <StatusDot on={s.live_running} label="Live" />
            <StatusDot on={s.listener_running} label="Listener" />
          </div>
        </div>
      </div>

      <AnalysisFeed />

      <div className="card">
        <h2>{t('ov.killSwitch')}</h2>
        <label className="toggle">
          <input type="checkbox" checked={s.kill_switch_on} disabled={busy !== ''}
            onChange={() => act(s.kill_switch_on ? t('ov.ksOffAction') : t('ov.ksOnAction'), () => apiPost('/api/kill-switch', { on: !s.kill_switch_on }))} />
          <strong style={{ color: s.kill_switch_on ? 'var(--red)' : 'inherit' }}>{s.kill_switch_on ? t('ov.ksOn') : t('ov.ksOff')}</strong>
        </label>
        <p className="muted small">{t('ov.ksNote')}</p>
      </div>

      <div className="card">
        <h2>{t('ov.liveListener')}</h2>
        <div className="btn-row">
          <button className="btn" disabled={busy !== ''} onClick={() => act(t('ov.startLiveRec'), async () => { const r = await apiPost<{ ok: boolean; reason: string }>('/api/live/start', { mode: 'recommend', desk: 'forex' }); if (!r.ok) throw new Error(r.reason) })}>{t('ov.startLiveRec')}</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={() => act(t('ov.startLiveAuto'), async () => { const r = await apiPost<{ ok: boolean; reason: string }>('/api/live/start', { mode: 'auto', desk: 'forex' }); if (!r.ok) throw new Error(r.reason) })}>{t('ov.startLiveAuto')}</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={() => act(t('ov.stopLive'), async () => { await apiPost('/api/live/stop') })}>{t('ov.stopLive')}</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={() => act(t('ov.startListener'), async () => { await apiPost('/api/listener/start') })}>{t('ov.startListener')}</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={() => act(t('ov.stopListener'), async () => { await apiPost('/api/listener/stop') })}>{t('ov.stopListener')}</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={async () => { try { setLive(await apiGet('/api/live')); setListener(await apiGet('/api/listener')) } catch (e) { setMsg(String(e)) } }}>{t('ov.refreshStatus')}</button>
        </div>
        {(live || listener) && (
          <p className="muted" style={{ marginTop: 12 }}>
            Live: {live ? (live.running ? `${t('ov.liveRunning')} (${live.mode ?? ''})` : t('ov.liveStopped')) : '—'} · Listener: {listener ? (listener.running ? t('ov.liveRunning') : t('ov.liveStopped')) : '—'}
          </p>
        )}
      </div>

      <div className="card">
        <h2>{t('ov.equityByDesk')}</h2>
        {s.desks.length === 0 ? <Empty /> : (
          <div className="table-wrap"><table><thead><tr><th>{t('ov.thDesk')}</th><th>{t('ov.thEquity')}</th><th>{t('ov.thOpen')}</th></tr></thead>
          <tbody>{s.desks.map((d) => <tr key={d.desk}><td>{d.desk}</td><td>{fmtUsd(d.equity)}</td><td>{d.open_positions}</td></tr>)}</tbody></table></div>
        )}
      </div>
    </div>
  )
}

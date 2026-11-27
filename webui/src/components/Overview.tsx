import { useState } from 'react'
import { apiGet, apiPost, fetchPortfolioRisk, fmtPct, fmtUsd, type Status } from '../api'
import { useI18n } from '../i18n'
import { Empty, Err, Loading, StatusDot, useFetch } from './shared'
import AnalysisFeed from './Feed'

function PortfolioRiskSection() {
  const { t } = useI18n()
  const { data, loading, error, reload } = useFetch(fetchPortfolioRisk)

  if (loading) return <div className="card"><h2>{t('portrisk.title')}</h2><Loading /></div>
  if (error || !data) return <div className="card"><h2>{t('portrisk.title')}</h2><Err message={error ?? t('common.empty')} onRetry={reload} /></div>
  const r = data
  if (!r.has_positions) {
    return (
      <div className="card">
        <h2>{t('portrisk.title')}</h2>
        <Empty text={t('portrisk.empty')} />
        <p className="muted small" style={{ textAlign: 'center' }}>{t('portrisk.emptyHint')}</p>
      </div>
    )
  }
  const worst = r.stress.length > 0 ? [...r.stress].sort((a, b) => a.pnl_usd - b.pnl_usd)[0] : null
  const totalCompVar = r.component_var.reduce((a, c) => a + (c.var_usd || 0), 0)

  return (
    <div className="card">
      <h2>{t('portrisk.title')}</h2>
      <div className="grid">
        <div><div className="stat-label">{t('portrisk.varParametric')}</div><div className="stat-value">{fmtUsd(r.var.parametric_95)}</div><div className="stat-sub">CVaR 95%: {fmtUsd(r.var.parametric_cvar_95)}</div></div>
        <div><div className="stat-label">{t('portrisk.varMc')}</div><div className="stat-value">{fmtUsd(r.var.mc_95)}</div><div className="stat-sub">CVaR 95%: {fmtUsd(r.var.mc_cvar_95)}</div></div>
        <div>
          <div className="stat-label">{t('portrisk.limit')}</div>
          <div className="stat-value">{fmtUsd(r.var.limit_usd)}</div>
          <div className="stat-sub" style={r.var.breached ? { color: 'var(--red)', fontWeight: 600 } : undefined}>
            {r.var.breached ? t('portrisk.breached') : t('portrisk.withinLimit')} ({fmtPct(r.var.limit_pct)})
          </div>
        </div>
        <div>
          <div className="stat-label">{t('portrisk.worstStress')}</div>
          {worst ? (
            <>
              <div className="stat-value" style={{ fontSize: 20 }}>{worst.name}</div>
              <div className={`stat-sub ${worst.pnl_usd < 0 ? 'neg' : ''}`}>{fmtUsd(worst.pnl_usd)} ({fmtPct(worst.pnl_pct)})</div>
            </>
          ) : <div className="stat-sub">—</div>}
        </div>
      </div>
      <p className="muted small">{t('portrisk.mcPaths', { paths: r.mc.paths, days: r.mc.horizon_days })}</p>
      {r.concentration.largest_symbol && (
        <p className="muted small">{t('portrisk.largest', { symbol: r.concentration.largest_symbol, pct: r.concentration.largest_share_pct.toFixed(1) })}</p>
      )}
      <h3 style={{ marginTop: 16 }}>{t('portrisk.componentVar')}</h3>
      {r.component_var.length === 0 ? <Empty /> : (
        <div>
          {r.component_var.map((c) => (
            <div key={c.symbol} style={{ marginBottom: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
                <span><strong>{c.symbol}</strong> <span className="muted small">{c.desk}</span></span>
                <span>{fmtUsd(c.var_usd)} · {fmtPct(c.share_pct)}</span>
              </div>
              <div className="gauge"><div style={{ width: `${Math.min(100, Math.max(0, totalCompVar > 0 ? (c.var_usd / totalCompVar) * 100 : c.share_pct))}%` }} /></div>
            </div>
          ))}
        </div>
      )}
      {r.warnings.length > 0 && (
        <p className="muted small" style={{ marginTop: 12 }}>{t('portrisk.warnings')}: {r.warnings.join('; ')}</p>
      )}
    </div>
  )
}

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

      <PortfolioRiskSection />

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

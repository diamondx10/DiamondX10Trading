// Manager tab — the landing view after sign-in. Status cards from
// GET /api/status plus controls for Live (recommend mode), the Telegram
// listener, system diagnostics, a Telegram test message and the kill
// switch. Each button reports the backend's result reason.
import { useState } from 'react'
import {
  apiGet, fmtUsd, getListener, getLive, runDiagnostics, startListener,
  startLive, stopListener, stopLive, telegramTest, toggleKillSwitch,
  type ActionResult, type LiveState, type ListenerState, type Status,
} from '../api'
import { useI18n } from '../i18n'
import LogViewer from './LogViewer'
import { Err, Loading, StatusDot, useFetch } from './shared'

export default function Manager() {
  const { t } = useI18n()
  const { data, loading, error, reload } = useFetch(() => apiGet<Status>('/api/status'))
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [live, setLive] = useState<LiveState | null>(null)
  const [listener, setListener] = useState<ListenerState | null>(null)

  async function act(label: string, fn: () => Promise<ActionResult | unknown>) {
    setBusy(label); setMsg(null)
    try {
      const r = await fn()
      const reason = (r as ActionResult | null)?.reason
      setMsg(reason ? `${label}: ${reason}` : `${label}: ${t('common.ok')}`)
      reload()
    } catch (e) {
      setMsg(`${label} ${t('common.failed')}: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setBusy('')
    }
  }

  async function refreshLive() {
    try {
      setLive(await getLive())
      setListener(await getListener())
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e))
    }
  }

  if (loading) return <Loading />
  if (error || !data) return <Err message={error ?? t('common.empty')} onRetry={reload} />
  const s = data

  return (
    <div>
      <div className="card">
        <h2>{t('mgr.title')}</h2>
        <p className="muted">{t('mgr.subtitle')}</p>
      </div>
      {msg && <div className="notice">{msg}</div>}
      <div className="grid">
        <div className="card">
          <div className="stat-label">{t('mgr.mt5')}</div>
          <StatusDot on={s.mt5_ok} label={s.mt5_ok ? t('mgr.connected') : t('mgr.notConnected')} />
        </div>
        <div className="card">
          <div className="stat-label">{t('mgr.live')}</div>
          <StatusDot on={s.live_running} label={s.live_running ? t('mgr.running') : t('mgr.stopped')} />
          {live?.mode && <div className="stat-sub">{live.mode}</div>}
        </div>
        <div className="card">
          <div className="stat-label">{t('mgr.listener')}</div>
          <StatusDot on={s.listener_running} label={s.listener_running ? t('mgr.running') : t('mgr.stopped')} />
        </div>
        <div className="card">
          <div className="stat-label">{t('mgr.telegram')}</div>
          <StatusDot on={s.telegram_ready} label={s.telegram_ready ? t('mgr.configured') : t('mgr.notConfigured')} />
        </div>
        <div className="card">
          <div className="stat-label">{t('mgr.killSwitch')}</div>
          <div className="stat-value" style={{ fontSize: 20, color: s.kill_switch_on ? 'var(--red)' : 'inherit' }}>
            {s.kill_switch_on ? t('mgr.on') : t('mgr.off')}
          </div>
        </div>
        <div className="card">
          <div className="stat-label">{t('mgr.equity')}</div>
          <div className="stat-value">{fmtUsd(s.equity)}</div>
        </div>
      </div>

      <div className="card">
        <h2>{t('mgr.controls')}</h2>
        <p className="muted small">{t('mgr.modeRecommend')}</p>
        <div className="btn-row">
          <button className="btn" disabled={busy !== '' || s.live_running} onClick={() => act(t('mgr.startLive'), async () => {
            const r = await startLive('recommend', 'forex')
            if (!r.ok) throw new Error(r.reason)
            return r
          })}>{t('mgr.startLive')}</button>
          <button className="btn secondary" disabled={busy !== '' || !s.live_running} onClick={() => act(t('mgr.stopLive'), stopLive)}>{t('mgr.stopLive')}</button>
          <button className="btn secondary" disabled={busy !== '' || s.listener_running} onClick={() => act(t('mgr.startListener'), async () => {
            const r = await startListener()
            if (!r.ok) throw new Error(r.reason)
            return r
          })}>{t('mgr.startListener')}</button>
          <button className="btn secondary" disabled={busy !== '' || !s.listener_running} onClick={() => act(t('mgr.stopListener'), stopListener)}>{t('mgr.stopListener')}</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={() => act(t('mgr.runDiagnostics'), async () => {
            const r = await runDiagnostics()
            if (!r.ok) throw new Error(r.reason)
            return r
          })}>{t('mgr.runDiagnostics')}</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={() => act(t('mgr.telegramTest'), telegramTest)}>{t('mgr.telegramTest')}</button>
          <button className="btn secondary" disabled={busy !== ''} onClick={async () => { await refreshLive(); reload() }}>{t('mgr.refresh')}</button>
        </div>
        {(live || listener) && (
          <p className="muted" style={{ marginTop: 12 }}>
            Live: {live ? (live.running ? `${t('mgr.running')} (${live.mode ?? ''})` : t('mgr.stopped')) : '—'}
            {' · '}Listener: {listener ? (listener.running ? t('mgr.running') : t('mgr.stopped')) : '—'}
          </p>
        )}
        <div style={{ marginTop: 16 }}>
          <label className="toggle">
            <input type="checkbox" checked={s.kill_switch_on} disabled={busy !== ''}
              onChange={() => act(s.kill_switch_on ? t('mgr.killSwitchOff') : t('mgr.killSwitchOn'), () => toggleKillSwitch(!s.kill_switch_on))} />
            <strong style={{ color: s.kill_switch_on ? 'var(--red)' : 'inherit' }}>
              {s.kill_switch_on ? t('mgr.killSwitchOn') : t('mgr.killSwitchOff')}
            </strong>
          </label>
        </div>
      </div>

      <LogViewer />
    </div>
  )
}

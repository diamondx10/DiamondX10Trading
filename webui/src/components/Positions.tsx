import { useState } from 'react'
import { apiGet, apiPost, fmtUsd, type PendingOrder, type Position } from '../api'
import { useI18n } from '../i18n'
import { Empty, Err, Loading, useFetch } from './shared'

export default function Positions() {
  const { t } = useI18n()
  const pos = useFetch(() => apiGet<{ positions: Position[] }>('/api/positions'))
  const pend = useFetch(() => apiGet<{ pending: PendingOrder[] }>('/api/pending'))
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState<string | null>(null)

  async function act(id: string, kind: 'place' | 'ignore') {
    setBusy(id + kind); setMsg(null)
    try {
      const r = await apiPost<{ ok: boolean; ticket?: number | null; reason?: string }>(`/api/pending/${encodeURIComponent(id)}/${kind}`)
      if (!r.ok) throw new Error(r.reason || t('pos.genericFail'))
      setMsg(kind === 'place' ? t('pos.placed', { ticket: r.ticket ?? '?' }) : t('pos.ignored'))
      pend.reload()
    } catch (e) { setMsg(`${kind === 'place' ? t('pos.placeFailed') : t('pos.ignoreFailed')} ${t('common.failed')}: ${e instanceof Error ? e.message : String(e)}`) }
    finally { setBusy('') }
  }

  return (
    <div>
      {msg && <div className="notice">{msg}</div>}
      <div className="card">
        <h2>{t('ov.openPositions')}</h2>
        {pos.loading ? <Loading /> : pos.error || !pos.data ? <Err message={pos.error ?? t('common.empty')} onRetry={pos.reload} />
          : pos.data.positions.length === 0 ? <Empty text={t('pos.empty')} /> : (
          <div className="table-wrap"><table><thead><tr><th>{t('common.desk')}</th><th>{t('common.symbol')}</th><th>{t('pos.thDirection')}</th><th>{t('pos.thEntry')}</th><th>{t('pos.thSl')}</th><th>{t('pos.thTp')}</th><th>{t('pos.thVolume')}</th><th>{t('pos.thPnl')}</th><th>{t('pos.thOpened')}</th></tr></thead>
          <tbody>{pos.data.positions.map((p, i) => (
            <tr key={i}><td>{p.desk}</td><td>{p.symbol}</td><td><span className={`badge ${p.direction.toLowerCase()}`}>{p.direction}</span></td>
            <td>{p.entry}</td><td>{p.sl ?? '—'}</td><td>{p.tp ?? '—'}</td><td>{p.volume}</td>
            <td className={p.unrealised_pnl === null ? '' : p.unrealised_pnl >= 0 ? 'pos' : 'neg'}>{fmtUsd(p.unrealised_pnl)}</td><td>{p.opened}</td></tr>
          ))}</tbody></table></div>)}
      </div>

      <div className="card">
        <h2>{t('pos.pendingTitle')}</h2>
        {pend.loading ? <Loading /> : pend.error || !pend.data ? <Err message={pend.error ?? t('common.empty')} onRetry={pend.reload} />
          : pend.data.pending.length === 0 ? <Empty text={t('pos.pendingEmpty')} /> : (
          <div className="table-wrap"><table><thead><tr><th>{t('common.desk')}</th><th>{t('common.symbol')}</th><th>{t('pos.thOrder')}</th><th>{t('pos.thEntry')}</th><th>{t('pos.thSl')}</th><th>{t('pos.thTp')}</th><th>{t('pos.thVolume')}</th><th>{t('pos.thRisk')}</th><th>{t('pos.thExpires')}</th><th>{t('pos.thStatus')}</th><th></th></tr></thead>
          <tbody>{pend.data.pending.map((p) => (
            <tr key={p.id}><td>{p.desk}<div className="small muted">{p.manager}</div></td><td>{p.symbol}</td>
            <td><span className={`badge ${p.action.toLowerCase()}`}>{p.action}</span></td>
            <td>{p.entry}</td><td>{p.sl ?? '—'}</td><td>{p.tp ?? '—'}</td><td>{p.volume}</td>
            <td>{fmtUsd(p.risk_usd)}</td><td className="small">{p.expires_utc}</td><td>{p.status}</td>
            <td><div className="btn-row">
              <button className="btn small" disabled={busy !== ''} onClick={() => act(p.id, 'place')}>{t('pos.approve')}</button>
              <button className="btn secondary small" disabled={busy !== ''} onClick={() => act(p.id, 'ignore')}>{t('pos.ignore')}</button>
            </div></td></tr>
          ))}</tbody></table></div>)}
      </div>
    </div>
  )
}

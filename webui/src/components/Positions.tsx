import { useState } from 'react'
import { apiGet, apiPost, fmtUsd, type PendingOrder, type Position } from '../api'
import { Empty, Err, Loading, useFetch } from './shared'

export default function Positions() {
  const pos = useFetch(() => apiGet<{ positions: Position[] }>('/api/positions'))
  const pend = useFetch(() => apiGet<{ pending: PendingOrder[] }>('/api/pending'))
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState<string | null>(null)

  async function act(id: string, kind: 'place' | 'ignore') {
    setBusy(id + kind); setMsg(null)
    try {
      const r = await apiPost<{ ok: boolean; ticket?: number | null; reason?: string }>(`/api/pending/${encodeURIComponent(id)}/${kind}`)
      if (!r.ok) throw new Error(r.reason || 'That bai')
      setMsg(kind === 'place' ? `Da dat lenh — ticket #${r.ticket ?? '?'}` : 'Da bo qua khuyen nghi')
      pend.reload()
    } catch (e) { setMsg(`${kind === 'place' ? 'Dat lenh' : 'Bo qua'} that bai: ${e instanceof Error ? e.message : String(e)}`) }
    finally { setBusy('') }
  }

  return (
    <div>
      {msg && <div className="notice">{msg}</div>}
      <div className="card">
        <h2>Vi the mo</h2>
        {pos.loading ? <Loading /> : pos.error || !pos.data ? <Err message={pos.error ?? 'Khong co du lieu'} onRetry={pos.reload} />
          : pos.data.positions.length === 0 ? <Empty text="Chua co vi the mo" /> : (
          <div className="table-wrap"><table><thead><tr><th>Desk</th><th>Symbol</th><th>Huong</th><th>Entry</th><th>SL</th><th>TP</th><th>Volume</th><th>P&amp;L chua thuc hien</th><th>Mo luc</th></tr></thead>
          <tbody>{pos.data.positions.map((p, i) => (
            <tr key={i}><td>{p.desk}</td><td>{p.symbol}</td><td><span className={`badge ${p.direction.toLowerCase()}`}>{p.direction}</span></td>
            <td>{p.entry}</td><td>{p.sl ?? '—'}</td><td>{p.tp ?? '—'}</td><td>{p.volume}</td>
            <td className={p.unrealised_pnl === null ? '' : p.unrealised_pnl >= 0 ? 'pos' : 'neg'}>{fmtUsd(p.unrealised_pnl)}</td><td>{p.opened}</td></tr>
          ))}</tbody></table></div>)}
      </div>

      <div className="card">
        <h2>Khuyen nghi cho duyet</h2>
        {pend.loading ? <Loading /> : pend.error || !pend.data ? <Err message={pend.error ?? 'Khong co du lieu'} onRetry={pend.reload} />
          : pend.data.pending.length === 0 ? <Empty text="Chua co khuyen nghi cho duyet" /> : (
          <div className="table-wrap"><table><thead><tr><th>Desk</th><th>Symbol</th><th>Lenh</th><th>Entry</th><th>SL</th><th>TP</th><th>Volume</th><th>Rui ro</th><th>Het han</th><th>Trang thai</th><th></th></tr></thead>
          <tbody>{pend.data.pending.map((p) => (
            <tr key={p.id}><td>{p.desk}<div className="small muted">{p.manager}</div></td><td>{p.symbol}</td>
            <td><span className={`badge ${p.action.toLowerCase()}`}>{p.action}</span></td>
            <td>{p.entry}</td><td>{p.sl ?? '—'}</td><td>{p.tp ?? '—'}</td><td>{p.volume}</td>
            <td>{fmtUsd(p.risk_usd)}</td><td className="small">{p.expires_utc}</td><td>{p.status}</td>
            <td><div className="btn-row">
              <button className="btn small" disabled={busy !== ''} onClick={() => act(p.id, 'place')}>Duyet — Dat lenh</button>
              <button className="btn secondary small" disabled={busy !== ''} onClick={() => act(p.id, 'ignore')}>Bo qua</button>
            </div></td></tr>
          ))}</tbody></table></div>)}
      </div>
    </div>
  )
}

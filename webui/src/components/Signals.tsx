import { useState } from 'react'
import { apiGet, DESK_LABELS, DESKS, fmtNum, type Signal, type SynthesisItem } from '../api'
import CandleChart from './CandleChart'
import { Empty, Err, Loading, useFetch } from './shared'

const SYMBOLS: Record<string, string[]> = {
  forex: ['EURUSD', 'GBPUSD', 'USDJPY'],
  gold: ['XAUUSD'],
  crypto: ['BTCUSD', 'ETHUSD', 'BNBUSDT'],
  securities: ['NVDA', 'AMD', 'INTC', 'SNPS', 'CDNS'],
}

export default function Signals() {
  const [desk, setDesk] = useState<string>('forex')
  const [symbol, setSymbol] = useState('EURUSD')
  const sig = useFetch(() => apiGet<{ desk: string; signals: Signal[] }>(`/api/signals?desk=${desk}`), [desk])
  const syn = useFetch(() => apiGet<{ desk: string; items: SynthesisItem[] }>(`/api/synthesis?desk=${desk}`), [desk])
  const symbols = SYMBOLS[desk] ?? []

  return (
    <div>
      <div className="card">
        <div className="btn-row">
          <label>Desk <select value={desk} onChange={(e) => { setDesk(e.target.value); setSymbol((SYMBOLS[e.target.value] ?? ['EURUSD'])[0]) }}>
            {DESKS.map((d) => <option key={d} value={d}>{DESK_LABELS[d]}</option>)}
          </select></label>
          <label>Symbol <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
            {symbols.map((s) => <option key={s} value={s}>{s}</option>)}
          </select></label>
          <button className="btn secondary small" onClick={() => { sig.reload(); syn.reload() }}>Lam moi</button>
        </div>
      </div>

      <div className="card">
        <h2>Bieu do nen — {symbol}</h2>
        <CandleChart symbol={symbol} />
      </div>

      <div className="card">
        <h2>Tin hieu ky thuat (TA)</h2>
        {sig.loading ? <Loading /> : sig.error || !sig.data ? <Err message={sig.error ?? 'Khong co du lieu'} onRetry={sig.reload} />
          : sig.data.signals.length === 0 ? <Empty text="Chua co tin hieu cho desk nay" /> : (
          <div className="grid">{sig.data.signals.map((s) => (
            <div key={s.symbol} className="card" style={{ marginBottom: 0, cursor: 'pointer' }} onClick={() => setSymbol(s.symbol)}>
              <h3>{s.symbol}</h3>
              <p><span className={`badge ${s.action.toLowerCase()}`}>{s.action}</span></p>
              <p>RSI: {fmtNum(s.rsi, 1)}</p>
              <p>ATR: {fmtNum(s.atr, 4)}</p>
              <p className="muted small">Regime: {s.regime ?? '—'}</p>
              <p className="small">{s.patterns.length ? s.patterns.join(', ') : 'Khong co pattern'}</p>
            </div>
          ))}</div>)}
      </div>

      <div className="card">
        <h2>Tong hop TA + FA (Yuling)</h2>
        {syn.loading ? <Loading /> : syn.error || !syn.data ? <Err message={syn.error ?? 'Khong co du lieu'} onRetry={syn.reload} />
          : syn.data.items.length === 0 ? <Empty text="Chua co tong hop cho desk nay" /> : (
          <div className="table-wrap"><table><thead><tr><th>Symbol</th><th>TA</th><th>FA</th><th>Do tin cay</th><th>Khuyen nghi</th><th>Size</th><th>Tuoi verdict</th><th>Ly do</th></tr></thead>
          <tbody>{syn.data.items.map((it, i) => (
            <tr key={i}><td>{it.symbol}</td><td>{it.ta_action}</td><td>{it.fa_direction ?? '—'}</td>
            <td>{it.fa_confidence === null ? '—' : `${(it.fa_confidence * 100).toFixed(0)}%`}</td>
            <td><span className={`badge ${it.recommendation.toLowerCase()}`}>{it.recommendation}</span></td>
            <td>{it.size_factor ?? '—'}</td><td>{it.verdict_age_hours === null ? '—' : `${it.verdict_age_hours.toFixed(1)}h`}</td><td>{it.rationale}</td></tr>
          ))}</tbody></table></div>)}
      </div>
    </div>
  )
}

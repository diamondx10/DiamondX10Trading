import { apiGet, type DecisionRow } from '../api'
import { Empty, Err, Loading, useFetch } from './shared'

export default function Activity() {
  const { data, loading, error, reload } = useFetch(() => apiGet<{ rows: DecisionRow[] }>('/api/decisions?lines=50'))
  return (
    <div className="card">
      <h2>Lich su quyet dinh (50 dong gan nhat)</h2>
      <div className="btn-row" style={{ marginBottom: 12 }}><button className="btn secondary small" onClick={reload}>Lam moi</button></div>
      {loading ? <Loading /> : error || !data ? <Err message={error ?? 'Khong co du lieu'} onRetry={reload} />
        : data.rows.length === 0 ? <Empty text="Chua co hoat dong nao" /> : (
        <div className="table-wrap"><table><thead><tr><th>Thoi gian</th><th>Symbol</th><th>Hanh dong</th><th>Ly do</th><th>Desk</th><th>Quan ly</th></tr></thead>
        <tbody>{data.rows.map((r, i) => (
          <tr key={i}><td>{r.time}</td><td>{r.symbol}</td><td><span className={`badge ${r.action.toLowerCase()}`}>{r.action}</span></td><td>{r.reason}</td><td>{r.desk}</td><td>{r.manager}</td></tr>
        ))}</tbody></table></div>)}
    </div>
  )
}

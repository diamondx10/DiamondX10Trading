import { apiGet, type Status } from '../api'
import { Err, Loading, StatusDot, useFetch } from './shared'

export default function Settings() {
  const { data, loading, error, reload } = useFetch(() => apiGet<Status>('/api/status'))
  if (loading) return <Loading />
  if (error || !data) return <Err message={error ?? 'Khong co du lieu'} onRetry={reload} />
  const s = data
  return (
    <div>
      <div className="card">
        <h2>Ket noi</h2>
        <dl className="kv">
          <dt>MT5</dt><dd><StatusDot on={s.mt5_ok} label={s.mt5_ok ? 'Dang ket noi' : 'Chua ket noi'} /></dd>
          <dt>Telegram</dt><dd><StatusDot on={s.telegram_ready} label={s.telegram_ready ? 'San sang' : 'Chua cau hinh'} /></dd>
          <dt>Live</dt><dd>{s.live_running ? 'Dang chay' : 'Dung'}</dd>
          <dt>Listener</dt><dd>{s.listener_running ? 'Dang chay' : 'Dung'}</dd>
        </dl>
        <p className="muted small">Duong dan MT5 terminal va token Telegram duoc cau hinh o backend (config.yaml / bien moi truong). Trang nay chi hien thi, khong chinh sua trong phien ban nay.</p>
      </div>
      <div className="card">
        <h2>Gioi han quy</h2>
        <dl className="kv">
          <dt>Von</dt><dd>${s.capital.toLocaleString('en-US')}</dd>
          <dt>Drawdown toi da</dt><dd>10% (canh bao 5%)</dd>
          <dt>Drawdown hien tai</dt><dd>{s.drawdown_pct === null ? '—' : `${s.drawdown_pct.toFixed(2)}%`}</dd>
          <dt>Kill switch</dt><dd>{s.kill_switch_on ? 'DANG BAT' : 'Tat'}</dd>
        </dl>
      </div>
      <div className="card">
        <h2>Tong hop TA + FA</h2>
        <dl className="kv">
          <dt>Verdict hieu luc</dt><dd>24 gio</dd>
          <dt>Yeu cau FA</dt><dd>Khong bat buoc (require_fa: false)</dd>
          <dt>Nguong tin cay</dt><dd>0.6</dd>
        </dl>
        <p className="muted small">Cac gia tri nay la mac dinh da chot theo rule 39. Chi hien thi, khong chinh sua trong phien ban nay.</p>
      </div>
    </div>
  )
}

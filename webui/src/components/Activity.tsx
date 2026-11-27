import { apiGet, type DecisionRow } from '../api'
import { useI18n } from '../i18n'
import { Empty, Err, Loading, useFetch } from './shared'

export default function Activity() {
  const { t } = useI18n()
  const { data, loading, error, reload } = useFetch(() => apiGet<{ rows: DecisionRow[] }>('/api/decisions?lines=50'))
  return (
    <div className="card">
      <h2>{t('act.title')}</h2>
      <div className="btn-row" style={{ marginBottom: 12 }}><button className="btn secondary small" onClick={reload}>{t('common.refresh')}</button></div>
      {loading ? <Loading /> : error || !data ? <Err message={error ?? t('common.empty')} onRetry={reload} />
        : data.rows.length === 0 ? <Empty text={t('act.empty')} /> : (
        <div className="table-wrap"><table><thead><tr><th>{t('act.thTime')}</th><th>{t('common.symbol')}</th><th>{t('act.thAction')}</th><th>{t('act.thReason')}</th><th>{t('common.desk')}</th><th>{t('act.thManager')}</th></tr></thead>
        <tbody>{data.rows.map((r, i) => (
          <tr key={i}><td>{r.time}</td><td>{r.symbol}</td><td><span className={`badge ${r.action.toLowerCase()}`}>{r.action}</span></td><td>{r.reason}</td><td>{r.desk}</td><td>{r.manager}</td></tr>
        ))}</tbody></table></div>)}
    </div>
  )
}

import type { ReactNode } from 'react'
import { apiGet } from '../api'
import { useI18n } from '../i18n'
import { Empty, Err, Loading, useFetch } from './shared'

function renderValue(v: unknown): ReactNode {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'object') {
    if (Array.isArray(v)) return v.length === 0 ? '—' : v.join(', ')
    return <pre className="json">{JSON.stringify(v, null, 2)}</pre>
  }
  return String(v)
}

export default function Backtest() {
  const { t } = useI18n()
  const { data, loading, error, reload } = useFetch(() => apiGet<{ backtest: Record<string, unknown> | null }>('/api/backtest'))
  if (loading) return <Loading />
  if (error || !data) return <Err message={error ?? t('common.empty')} onRetry={reload} />
  const b = data.backtest
  if (!b) return <div className="card"><Empty text={t('bt.empty')} /></div>
  const entries = Object.entries(b).filter(([k]) => k !== 'trades' && k !== 'equity_curve')
  return (
    <div className="card">
      <h2>{t('bt.latest')}</h2>
      <div className="btn-row" style={{ marginBottom: 12 }}><button className="btn secondary small" onClick={reload}>{t('common.refresh')}</button></div>
      <dl className="kv">
        {entries.map(([k, v]) => (
          <div key={k} style={{ display: 'contents' }}><dt>{k.replace(/_/g, ' ')}</dt><dd>{renderValue(v)}</dd></div>
        ))}
      </dl>
      {Array.isArray(b.trades) && b.trades.length > 0 && (
        <div style={{ marginTop: 16 }}><h3>{t('bt.trades')} ({(b.trades as unknown[]).length})</h3>
        <pre className="json">{JSON.stringify(b.trades.slice(0, 20), null, 2)}</pre></div>
      )}
    </div>
  )
}

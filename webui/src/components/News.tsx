import { useState } from 'react'
import { apiGet, DESK_LABELS, DESKS, type Article } from '../api'
import { useI18n } from '../i18n'
import { Empty, Err, Loading, useFetch } from './shared'

const TIER_KEYS: Record<string, 'news.tier1' | 'news.tier2' | 'news.tier3'> = { '1': 'news.tier1', '2': 'news.tier2', '3': 'news.tier3' }

export default function News() {
  const { t } = useI18n()
  const [desk, setDesk] = useState('forex')
  const { data, loading, error, reload } = useFetch(() => apiGet<{ desk: string; articles: Article[] }>(`/api/news?desk=${desk}`), [desk])
  if (loading) return <Loading />
  if (error || !data) return <Err message={error ?? t('common.empty')} onRetry={reload} />
  const groups = new Map<string, Article[]>()
  for (const a of data.articles) {
    const k = String(a.tier)
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(a)
  }
  const tiers = [...groups.keys()].sort()
  return (
    <div>
      <div className="card">
        <div className="btn-row">
          <label>{t('common.desk')} <select value={desk} onChange={(e) => setDesk(e.target.value)}>
            {DESKS.map((d) => <option key={d} value={d}>{DESK_LABELS[d]}</option>)}
          </select></label>
          <button className="btn secondary small" onClick={reload}>{t('common.refresh')}</button>
        </div>
      </div>
      {data.articles.length === 0 ? <div className="card"><Empty text={t('news.empty')} /></div> : (
        <div className="card">
          {tiers.map((tier) => (
            <div className="tier-group" key={tier}>
              <h3>{TIER_KEYS[tier] ? t(TIER_KEYS[tier]) : `Tier ${tier}`}</h3>
              <ul className="clean">{groups.get(tier)!.map((a, i) => (
                <li key={i}><a href={a.url} target="_blank" rel="noreferrer">{a.title}</a>
                  <div className="small muted">{a.source} · {a.published}</div></li>
              ))}</ul>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

import { useState } from 'react'
import { apiGet, DESK_LABELS, DESKS, type Article } from '../api'
import { Empty, Err, Loading, useFetch } from './shared'

const TIER_LABEL: Record<string, string> = { '1': 'Tier 1 — Nguon chinh thuc', '2': 'Tier 2 — Bao chi', '3': 'Tier 3 — Tin ro ri, chua xac minh' }

export default function News() {
  const [desk, setDesk] = useState('forex')
  const { data, loading, error, reload } = useFetch(() => apiGet<{ desk: string; articles: Article[] }>(`/api/news?desk=${desk}`), [desk])
  if (loading) return <Loading />
  if (error || !data) return <Err message={error ?? 'Khong co du lieu'} onRetry={reload} />
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
          <label>Desk <select value={desk} onChange={(e) => setDesk(e.target.value)}>
            {DESKS.map((d) => <option key={d} value={d}>{DESK_LABELS[d]}</option>)}
          </select></label>
          <button className="btn secondary small" onClick={reload}>Lam moi</button>
        </div>
      </div>
      {data.articles.length === 0 ? <div className="card"><Empty text="Chua co tin tuc cho desk nay" /></div> : (
        <div className="card">
          {tiers.map((t) => (
            <div className="tier-group" key={t}>
              <h3>{TIER_LABEL[t] ?? `Tier ${t}`}</h3>
              <ul className="clean">{groups.get(t)!.map((a, i) => (
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

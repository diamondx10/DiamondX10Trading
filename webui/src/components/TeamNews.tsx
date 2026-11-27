// Homepage section: latest news the team has analyzed, across desks.
// Data: GET /api/team-news -> { items, verdicts, briefings }.
// If the endpoint is not implemented yet (404), the section hides itself
// instead of erroring — the rest of the homepage keeps working.
// News titles/sources are data, never translated.
import { useEffect, useState } from 'react'
import { apiGet, DESK_LABELS, DESKS, type TeamNews } from '../api'
import { useI18n } from '../i18n'
import { Empty, Loading } from './shared'

export default function TeamNewsSection({ onOpenNews }: { onOpenNews: () => void }) {
  const { t } = useI18n()
  const { data, loading, error } = useFetchTeamNews()

  // Endpoint not implemented yet: hide the section silently.
  if (error) return null
  if (loading) return <div className="card"><h2>{t('teamNews.title')}</h2><Loading /></div>
  if (!data) return null

  const verdicts = data.verdicts ?? {}
  const briefings = data.briefings ?? []
  const items = data.items ?? []

  return (
    <div className="card">
      <div className="section-head">
        <h2 style={{ marginBottom: 0 }}>{t('teamNews.title')}</h2>
        <button className="btn secondary small" onClick={onOpenNews}>{t('teamNews.viewNews')}</button>
      </div>

      <h3 style={{ marginTop: 16 }}>{t('teamNews.verdicts')}</h3>
      <div className="verdict-strip">
        {DESKS.map((d) => {
          const v = verdicts[d]
          return (
            <div key={d} className="verdict-chip">
              <span className="muted small">{DESK_LABELS[d]}</span>
              {v ? (
                <span>
                  <span className={`badge ${v.direction.toLowerCase()}`}>{v.direction}</span>
                  {v.confidence !== null && v.confidence !== undefined && (
                    <span className="small muted"> · {(v.confidence * 100).toFixed(0)}%</span>
                  )}
                </span>
              ) : (
                <span className="small muted">{t('teamNews.noVerdict')}</span>
              )}
            </div>
          )
        })}
      </div>

      {items.length === 0 ? (
        <Empty text={t('teamNews.empty')} />
      ) : (
        <ul className="clean news-list">
          {items.map((a, i) => (
            <li key={i}>
              <button className="news-item" onClick={onOpenNews} title={t('teamNews.viewNews')}>
                <span className="news-title">{a.title}</span>
                <span className="small muted">
                  {a.source} · {a.time} · {DESK_LABELS[a.desk] ?? a.desk} · {a.analyst}
                </span>
              </button>
              <span className="news-meta">
                <span className="badge">Tier {a.tier}</span>
                {a.briefing_url && (
                  <a href={a.briefing_url} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()}>
                    {t('teamNews.viewBriefing')}
                  </a>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {briefings.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h3>{t('teamNews.latestBriefing')}</h3>
          <ul className="clean">
            {briefings.map((b, i) => (
              <li key={i}>
                <strong>{DESK_LABELS[b.desk] ?? b.desk}</strong>
                <span className="muted small"> · {b.file} · {b.time}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

// Local fetch hook (no error state surfaced to the user): a missing
// /api/team-news endpoint must not break the homepage.
function useFetchTeamNews() {
  const [data, setData] = useState<TeamNews | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    let cancelled = false
    apiGet<TeamNews>('/api/team-news')
      .then((d) => { if (!cancelled) setData(d) })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])
  return { data, loading, error }
}

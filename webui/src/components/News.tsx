// News tab: latest market news per desk (GET /api/news) plus a
// one-click "Load news now" (POST /api/news-fetch — same as the
// `news --all` CLI, posts new cards to the feed immediately) and the
// auto-fetch control (POST /api/news-auto-fetch, rule 60). When
// nothing has been loaded yet the empty state says so plainly and
// points at the Load button instead of showing a bare empty list.
import { useEffect, useState } from 'react'
import {
  apiGet, fetchNewsNow, getNewsAutoFetch, setNewsAutoFetch,
  DESK_LABELS, DESKS, type Article, type NewsAutoFetchState,
} from '../api'
import { useI18n } from '../i18n'
import { Empty, Err, Loading, useFetch } from './shared'
import { useRelativeTime } from './Feed'

const TIER_KEYS: Record<string, 'news.tier1' | 'news.tier2' | 'news.tier3'> = { '1': 'news.tier1', '2': 'news.tier2', '3': 'news.tier3' }

export default function News() {
  const { t } = useI18n()
  const relTime = useRelativeTime()
  const [desk, setDesk] = useState('forex')
  const { data, loading, error, reload } = useFetch(() => apiGet<{ desk: string; articles: Article[]; note?: string }>(`/api/news?desk=${desk}`), [desk])
  const [fetching, setFetching] = useState(false)
  const [fetchMsg, setFetchMsg] = useState<string | null>(null)
  const [auto, setAuto] = useState<NewsAutoFetchState | null>(null)
  const [autoBusy, setAutoBusy] = useState(false)
  const [autoMsg, setAutoMsg] = useState<string | null>(null)
  const [intervalInput, setIntervalInput] = useState('5')

  useEffect(() => {
    let cancelled = false
    getNewsAutoFetch()
      .then((r) => {
        if (cancelled) return
        setAuto(r)
        setIntervalInput(String(r.interval_min))
      })
      .catch(() => { if (!cancelled) setAuto(null) })
    return () => { cancelled = true }
  }, [])

  async function loadAuto() {
    try {
      const r = await getNewsAutoFetch()
      setAuto(r)
      setIntervalInput(String(r.interval_min))
    } catch { /* keep previous state */ }
  }

  async function loadNow() {
    setFetching(true); setFetchMsg(null)
    try {
      const r = await fetchNewsNow()
      let msg = t('newsFetch.done', { fetched: r.fetched, matched: r.matched, new: r.new, cards: r.cards_created })
      if (r.errors.length > 0) msg += ` ${t('newsFetch.errors', { msg: r.errors.join('; ') })}`
      setFetchMsg(msg)
      reload()
      loadAuto()
    } catch (e) {
      const detail = e instanceof Error ? e.message : String(e)
      setFetchMsg(detail.includes('Chua cau hinh nguon tin')
        ? t('newsFetch.notConfigured')
        : t('newsFetch.failed', { msg: detail }))
    } finally {
      setFetching(false)
    }
  }

  async function toggleAuto() {
    if (!auto || autoBusy) return
    setAutoBusy(true); setAutoMsg(null)
    try {
      const r = await setNewsAutoFetch(!auto.enabled, auto.interval_min)
      setAuto(r)
      setIntervalInput(String(r.interval_min))
      // Toggling ON fetches immediately once on the server; refresh
      // the state shortly after so last/next fetch times show up.
      if (r.enabled) setTimeout(() => { loadAuto() }, 3000)
    } catch (e) {
      setAutoMsg(`${t('newsAuto.label')} ${t('common.failed')}: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setAutoBusy(false)
    }
  }

  async function saveInterval() {
    if (!auto || autoBusy) return
    const minutes = parseInt(intervalInput, 10)
    if (!Number.isFinite(minutes)) {
      setAutoMsg(t('newsAuto.invalidInterval'))
      return
    }
    setAutoBusy(true); setAutoMsg(null)
    try {
      const r = await setNewsAutoFetch(auto.enabled, minutes)
      setAuto(r)
      setIntervalInput(String(r.interval_min))
    } catch (e) {
      setAutoMsg(`${t('newsAuto.label')} ${t('common.failed')}: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setAutoBusy(false)
    }
  }

  if (loading) return <Loading />
  if (error || !data) return <Err message={error ?? t('common.empty')} onRetry={reload} />
  const groups = new Map<string, Article[]>()
  for (const a of data.articles) {
    const k = String(a.tier)
    if (!groups.has(k)) groups.set(k, [])
    groups.get(k)!.push(a)
  }
  const tiers = [...groups.keys()].sort()
  const notConfigured = (data.note ?? '').includes('chua cau hinh')
  return (
    <div>
      <div className="card">
        <div className="btn-row">
          <label>{t('common.desk')} <select value={desk} onChange={(e) => setDesk(e.target.value)}>
            {DESKS.map((d) => <option key={d} value={d}>{DESK_LABELS[d]}</option>)}
          </select></label>
          <button className="btn small" disabled={fetching} onClick={loadNow}>
            {fetching ? t('newsFetch.loading') : t('newsFetch.loadNow')}
          </button>
          <button className="btn secondary small" disabled={fetching} onClick={reload}>{t('common.refresh')}</button>
        </div>
        {fetchMsg && <p className="muted" style={{ marginTop: 12, marginBottom: 0 }}>{fetchMsg}</p>}
        <div style={{ marginTop: 16 }}>
          <label className="toggle">
            <input type="checkbox" checked={auto?.enabled ?? false} disabled={autoBusy || auto === null} onChange={toggleAuto} />
            <strong>{t('newsAuto.label')}</strong>
          </label>
          <div className="btn-row" style={{ marginTop: 8 }}>
            <label>{t('newsAuto.interval')} <input type="number" min={1} max={60} step={1} style={{ width: 72 }} value={intervalInput} disabled={autoBusy || auto === null} onChange={(e) => setIntervalInput(e.target.value)} /></label>
            <button className="btn secondary small" disabled={autoBusy || auto === null} onClick={saveInterval}>{t('newsAuto.save')}</button>
            <span className="muted small">{auto ? (auto.enabled ? t('newsAuto.on') : t('newsAuto.off')) : ''}</span>
          </div>
          {auto && (
            <p className="muted small" style={{ marginTop: 8, marginBottom: 0 }}>
              {auto.last_fetch_utc
                ? `${t('newsAuto.lastFetch', { time: relTime(auto.last_fetch_utc) })}`
                : t('newsAuto.never')}
              {auto.next_fetch_utc && (
                <> · {t('newsAuto.nextFetch', { time: new Date(auto.next_fetch_utc).toLocaleString() })}</>
              )}
            </p>
          )}
          {autoMsg && <p className="muted small" style={{ marginTop: 8, marginBottom: 0 }}>{autoMsg}</p>}
        </div>
      </div>
      {data.articles.length === 0 ? (
        <div className="card">
          <Empty text={notConfigured ? t('newsFetch.notConfigured') : t('newsFetch.empty')} />
        </div>
      ) : (
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

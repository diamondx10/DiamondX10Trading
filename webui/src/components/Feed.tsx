// Analysis feed on the homepage (Overview tab), Facebook-style timeline.
// Layout patterns follow the Kinfolk reference (composer bar on top, centre
// column of post cards: avatar + name + time header, body, key numbers,
// collapsible details, footer) — built natively in dx10's Apple-style
// design tokens. No likes/comments/reactions/stories in v1.
// Data: GET /api/posts?limit=20&desk=..., POST /api/posts,
// POST /api/publish. If the endpoints are not implemented yet, the feed
// shows an empty state and the composer reports the error — the rest of
// the homepage keeps working.
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  createPost, fetchNewsCards, fetchPosts, fmtNum, publishPosts,
  DESK_LABELS, DESKS, type NewsCard, type Post,
} from '../api'
import { useI18n, type I18nKey } from '../i18n'
import { Empty, Loading } from './shared'

// Analyst per desk (fallback when a post carries no analyst name).
// Matches briefing.py DESK_ANALYSTS exactly (same desk keys).
const DESK_ANALYSTS: Record<string, string> = {
  forex: 'Yuling Pan',
  xauusd: 'Yumi',
  crypto: 'Rich',
  us_securities: 'Kathy',
}

// Desk colour for the avatar circle (dx10 palette, not Facebook blue).
const DESK_COLORS: Record<string, string> = {
  forex: '#0071e3',
  gold: '#b25e00',
  crypto: '#1d9e4b',
  securities: '#6e56cf',
}

const ACTIONS = ['BUY', 'SELL', 'NEUTRAL'] as const
type Action = (typeof ACTIONS)[number]

const ACTION_LABEL_KEY: Record<Action, I18nKey> = {
  BUY: 'feed.actionBuy',
  SELL: 'feed.actionSell',
  NEUTRAL: 'feed.actionNeutral',
}
// Existing badge classes: .badge.buy (green), .badge.sell (red); neutral
// gets the grey .badge.wait defined in styles.css.
const ACTION_BADGE_CLASS: Record<Action, string> = {
  BUY: 'buy',
  SELL: 'sell',
  NEUTRAL: 'wait',
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function splitLines(text: string): string[] {
  return text.split('\n').map((s) => s.trim()).filter(Boolean)
}

function parseNum(text: string): number | null {
  const v = parseFloat(text)
  return Number.isFinite(v) ? v : null
}

function sourceLabel(source: string, t: (k: I18nKey) => string): string {
  const s = (source || '').toLowerCase()
  if (s === 'synthesis' || s === 'ta_fa' || s === 'ta+fa' || s === 'ta-fa') return t('feed.sourceSynthesis')
  if (s === 'manual') return t('feed.sourceManual')
  return source || t('feed.sourceManual')
}

export function useRelativeTime() {
  const { t } = useI18n()
  return useCallback((iso: string): string => {
    const ts = Date.parse(iso)
    if (Number.isNaN(ts)) return iso
    const diffMs = Date.now() - ts
    if (diffMs < 60_000) return t('feed.timeNow')
    const mins = Math.floor(diffMs / 60_000)
    if (mins < 60) return t('feed.timeMinutes', { n: mins })
    const hours = Math.floor(mins / 60)
    if (hours < 24) return t('feed.timeHours', { n: hours })
    const days = Math.floor(hours / 24)
    return t('feed.timeDays', { n: days })
  }, [t])
}

function PostCard({ post }: { post: Post }) {
  const { t } = useI18n()
  const relTime = useRelativeTime()
  const [expanded, setExpanded] = useState(false)
  const analyst = post.analyst || DESK_ANALYSTS[post.desk] || post.desk
  const action: Action = post.action === 'BUY' || post.action === 'SELL' ? post.action : 'NEUTRAL'
  const drivers = post.drivers ?? []
  const risks = post.risks ?? []
  const hasDetails = drivers.length > 0 || risks.length > 0
  const color = DESK_COLORS[post.desk] ?? 'var(--accent)'

  return (
    <article className="card post-card">
      <div className="post-head">
        <span className="avatar" style={{ background: color }} aria-hidden="true">
          {initials(analyst)}
        </span>
        <div className="post-head-text">
          <div className="post-name">{analyst}</div>
          <div className="post-meta">
            {DESK_LABELS[post.desk] ?? post.desk} · {relTime(post.created_utc)}
          </div>
        </div>
        <span className={`badge ${ACTION_BADGE_CLASS[action]} post-badge`}>
          {t(ACTION_LABEL_KEY[action])}
        </span>
        {post.test_mode ? (
          <span className="badge post-badge" title={t('mgr.testModeHint')}>{t('feed.testBadge')}</span>
        ) : null}
      </div>

      <div className="post-symbol">{post.symbol}</div>
      <p className="post-summary">{post.summary}</p>

      {(post.entry !== null && post.entry !== undefined) ||
      (post.sl !== null && post.sl !== undefined) ||
      (post.tp !== null && post.tp !== undefined) ||
      (post.confidence !== null && post.confidence !== undefined) ? (
        <div className="key-numbers">
          {post.entry !== null && post.entry !== undefined && (
            <span className="key-num"><span className="k">{t('pos.thEntry')}</span>{fmtNum(post.entry)}</span>
          )}
          {post.sl !== null && post.sl !== undefined && (
            <span className="key-num"><span className="k">{t('pos.thSl')}</span>{fmtNum(post.sl)}</span>
          )}
          {post.tp !== null && post.tp !== undefined && (
            <span className="key-num"><span className="k">{t('pos.thTp')}</span>{fmtNum(post.tp)}</span>
          )}
          {post.confidence !== null && post.confidence !== undefined && (
            <span className="key-num"><span className="k">{t('sig.thConfidence')}</span>{(post.confidence * 100).toFixed(0)}%</span>
          )}
        </div>
      ) : null}

      {hasDetails && (
        <div className="post-details">
          <button className="link-btn" onClick={() => setExpanded(!expanded)} aria-expanded={expanded}>
            {expanded ? t('feed.showLess') : t('feed.showMore')}
          </button>
          {expanded && (
            <div className="post-details-body">
              {drivers.length > 0 && (
                <div>
                  <strong>{t('muse.thDrivers')}</strong>
                  <ul className="clean post-list">{drivers.map((d, i) => <li key={i}>{d}</li>)}</ul>
                </div>
              )}
              {risks.length > 0 && (
                <div>
                  <strong>{t('muse.thRisks')}</strong>
                  <ul className="clean post-list">{risks.map((r, i) => <li key={i}>{r}</li>)}</ul>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      <div className="post-footer">
        <span>{DESK_LABELS[post.desk] ?? post.desk}</span>
        <span>·</span>
        <span>{sourceLabel(post.source, t)}</span>
        {post.verdict_created_utc && (
          <>
            <span>·</span>
            <span>{t('feed.verdict')}: {relTime(post.verdict_created_utc)}</span>
          </>
        )}
      </div>
    </article>
  )
}

// Trust-tier labels (shared with the News tab).
const TIER_KEYS: Record<number, I18nKey> = {
  1: 'news.tier1',
  2: 'news.tier2',
  3: 'news.tier3',
}

// News card on the feed (rule 58): a followed news item rendered as a
// feed card, newest first alongside analysis posts. Title links to the
// source; the per-item Muse impact analysis reads like a comment
// underneath, or an "awaiting analysis" state while impact is null.
function NewsCardView({ card }: { card: NewsCard }) {
  const { t } = useI18n()
  const relTime = useRelativeTime()
  const analyst = card.analyst || DESK_ANALYSTS[card.desk] || card.desk
  const color = DESK_COLORS[card.desk] ?? 'var(--accent)'
  const impact = card.impact
  const dir = (impact?.direction || '').toUpperCase()
  const action: Action = dir === 'BUY' || dir === 'SELL' ? dir : 'NEUTRAL'
  const tierKey = TIER_KEYS[card.tier]
  const impactSummary = (impact?.summary || '').trim()

  return (
    <article className="card post-card">
      <div className="post-head">
        <span className="avatar" style={{ background: color }} aria-hidden="true">
          {initials(analyst)}
        </span>
        <div className="post-head-text">
          <div className="post-name">{analyst}</div>
          <div className="post-meta">
            {DESK_LABELS[card.desk] ?? card.desk} · {relTime(card.created_utc)}
          </div>
        </div>
        <span className="badge post-badge">{t('newsCard.label')}</span>
        {card.test_mode ? (
          <span className="badge post-badge" title={t('mgr.testModeHint')}>{t('feed.testBadge')}</span>
        ) : null}
      </div>

      <div className="post-symbol">
        <a className="news-title-link" href={card.link} target="_blank" rel="noreferrer">
          {card.title}
        </a>
      </div>
      {card.summary ? <p className="post-summary">{card.summary}</p> : null}

      <div className="news-impact">
        <strong>{t('newsCard.impactTitle')}</strong>
        {impact ? (
          <>
            <div>
              <span className={`badge ${ACTION_BADGE_CLASS[action]}`}>
                {t(ACTION_LABEL_KEY[action])}
              </span>
            </div>
            {(impact.affected_symbol || impact.confidence !== null && impact.confidence !== undefined) && (
              <div className="key-numbers">
                {impact.affected_symbol && (
                  <span className="key-num"><span className="k">{t('newsCard.affectedSymbol')}</span>{impact.affected_symbol}</span>
                )}
                {impact.confidence !== null && impact.confidence !== undefined && (
                  <span className="key-num"><span className="k">{t('sig.thConfidence')}</span>{(impact.confidence * 100).toFixed(0)}%</span>
                )}
              </div>
            )}
            {impactSummary && <p className="post-summary" style={{ marginTop: 0 }}>{impactSummary}</p>}
            {impact.verdict_created_utc && (
              <div className="post-meta">{t('feed.verdict')}: {relTime(impact.verdict_created_utc)}</div>
            )}
          </>
        ) : (
          <span className="muted small">{t('newsCard.awaitingAnalysis')}</span>
        )}
      </div>

      <div className="post-footer">
        <span>{card.source}</span>
        <span>·</span>
        <span className="badge">Tier {card.tier}</span>
        {tierKey && <span>{t(tierKey)}</span>}
      </div>
    </article>
  )
}

function Composer({ onPosted }: { onPosted: (post: Post) => void }) {
  const { t } = useI18n()
  const [open, setOpen] = useState(false)
  const [desk, setDesk] = useState<string>('forex')
  const [symbol, setSymbol] = useState('')
  const [action, setAction] = useState<Action>('NEUTRAL')
  const [summary, setSummary] = useState('')
  const [confidence, setConfidence] = useState('')
  const [entry, setEntry] = useState('')
  const [sl, setSl] = useState('')
  const [tp, setTp] = useState('')
  const [drivers, setDrivers] = useState('')
  const [risks, setRisks] = useState('')
  const [posting, setPosting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function reset() {
    setSymbol(''); setAction('NEUTRAL'); setSummary(''); setConfidence('')
    setEntry(''); setSl(''); setTp(''); setDrivers(''); setRisks(''); setError(null)
  }

  async function submit() {
    if (!symbol.trim() || !summary.trim()) {
      setError(t('feed.validation'))
      return
    }
    setPosting(true); setError(null)
    try {
      const conf = parseNum(confidence)
      const { post } = await createPost({
        desk,
        symbol: symbol.trim().toUpperCase(),
        action,
        summary: summary.trim(),
        confidence: conf === null ? null : Math.min(100, Math.max(0, conf)) / 100,
        entry: parseNum(entry),
        sl: parseNum(sl),
        tp: parseNum(tp),
        drivers: splitLines(drivers),
        risks: splitLines(risks),
      })
      onPosted(post)
      reset()
      setOpen(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setPosting(false)
    }
  }

  if (!open) {
    return (
      <div className="card composer-bar">
        <span className="avatar" style={{ background: 'var(--accent)' }} aria-hidden="true">DX</span>
        <button className="composer-trigger" onClick={() => setOpen(true)}>
          {t('feed.composerPlaceholder')}
        </button>
      </div>
    )
  }

  return (
    <div className="card composer-form-card">
      <h2>{t('feed.composerTitle')}</h2>
      <div className="form-grid">
        <label className="form-field">
          <span>{t('common.desk')}</span>
          <select value={desk} onChange={(e) => setDesk(e.target.value)}>
            {DESKS.map((d) => <option key={d} value={d}>{DESK_LABELS[d]}</option>)}
          </select>
        </label>
        <label className="form-field">
          <span>{t('common.symbol')}</span>
          <input value={symbol} onChange={(e) => setSymbol(e.target.value)} placeholder={t('feed.symbolPlaceholder')} />
        </label>
        <div className="form-field full">
          <span>{t('feed.action')}</span>
          <div className="btn-row" role="group" aria-label={t('feed.action')}>
            {ACTIONS.map((a) => (
              <button key={a} type="button"
                className={`btn secondary action-pick ${action === a ? `selected ${ACTION_BADGE_CLASS[a]}` : ''}`}
                onClick={() => setAction(a)}>
                {t(ACTION_LABEL_KEY[a])}
              </button>
            ))}
          </div>
        </div>
        <label className="form-field full">
          <span>{t('feed.summary')}</span>
          <textarea className="composer-text" value={summary} onChange={(e) => setSummary(e.target.value)} placeholder={t('feed.summaryPlaceholder')} />
        </label>
        <label className="form-field">
          <span>{t('feed.confidence')}</span>
          <input type="number" min="0" max="100" step="1" value={confidence} onChange={(e) => setConfidence(e.target.value)} />
        </label>
        <label className="form-field">
          <span>{t('pos.thEntry')}</span>
          <input type="number" step="any" value={entry} onChange={(e) => setEntry(e.target.value)} />
        </label>
        <label className="form-field">
          <span>{t('pos.thSl')}</span>
          <input type="number" step="any" value={sl} onChange={(e) => setSl(e.target.value)} />
        </label>
        <label className="form-field">
          <span>{t('pos.thTp')}</span>
          <input type="number" step="any" value={tp} onChange={(e) => setTp(e.target.value)} />
        </label>
        <label className="form-field full">
          <span>{t('feed.driversLabel')}</span>
          <textarea className="composer-text short" value={drivers} onChange={(e) => setDrivers(e.target.value)} />
        </label>
        <label className="form-field full">
          <span>{t('feed.risksLabel')}</span>
          <textarea className="composer-text short" value={risks} onChange={(e) => setRisks(e.target.value)} />
        </label>
      </div>
      {error && <div className="error" style={{ marginTop: 12, marginBottom: 0 }}>{error}</div>}
      <div className="btn-row" style={{ marginTop: 16 }}>
        <button className="btn" disabled={posting} onClick={submit}>{t('feed.post')}</button>
        <button className="btn secondary" disabled={posting} onClick={() => { reset(); setOpen(false) }}>{t('feed.cancel')}</button>
      </div>
    </div>
  )
}

export default function AnalysisFeed() {
  const { t } = useI18n()
  const [posts, setPosts] = useState<Post[]>([])
  const [cards, setCards] = useState<NewsCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<string>('all')
  const [notice, setNotice] = useState<string | null>(null)
  const [publishing, setPublishing] = useState(false)

  const load = useCallback(() => {
    setLoading(true); setError(null)
    const desk = filter === 'all' ? undefined : filter
    // News cards failing must not hide the analysis posts (and vice
    // versa): a failed /api/news-cards degrades to an empty card list.
    Promise.all([
      fetchPosts(20, desk),
      fetchNewsCards(50, desk).catch(() => ({ cards: [] as NewsCard[] })),
    ])
      .then(([pr, nr]) => { setPosts(pr.posts ?? []); setCards(nr.cards ?? []) })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [filter])

  useEffect(() => { load() }, [load])

  // One timeline, newest first: analysis posts and news cards
  // interleaved by created_utc (rule 58).
  type FeedItem =
    | { kind: 'post'; key: string; created: string; post: Post }
    | { kind: 'news'; key: string; created: string; card: NewsCard }
  const items: FeedItem[] = useMemo(() => {
    const merged: FeedItem[] = [
      ...posts.map((p): FeedItem => ({ kind: 'post', key: `post-${p.id}`, created: p.created_utc, post: p })),
      ...cards.map((c): FeedItem => ({ kind: 'news', key: `news-${c.id}`, created: c.created_utc, card: c })),
    ]
    merged.sort((a, b) => Date.parse(b.created) - Date.parse(a.created))
    return merged
  }, [posts, cards])

  async function publishFromSynthesis() {
    setPublishing(true); setNotice(null)
    try {
      const r = await publishPosts(filter === 'all' ? undefined : filter)
      const fresh = r.posts ?? []
      if (fresh.length > 0) setPosts((prev) => [...fresh, ...prev])
      setNotice(t('feed.publishDone', { n: fresh.length }))
    } catch (e) {
      setNotice(`${t('feed.publishFromSynthesis')} ${t('common.failed')}: ${e instanceof Error ? e.message : String(e)}`)
    } finally {
      setPublishing(false)
    }
  }

  return (
    <section className="feed-column" aria-label={t('feed.title')}>
      <Composer onPosted={(post) => { setPosts((prev) => [post, ...prev]); setNotice(t('feed.posted')) }} />

      <div className="feed-head">
        <h2>{t('feed.title')}</h2>
        <div className="btn-row">
          <button className="btn secondary small" disabled={publishing} onClick={publishFromSynthesis}>
            {t('feed.publishFromSynthesis')}
          </button>
          <button className="btn secondary small" disabled={loading} onClick={load}>
            {t('common.refresh')}
          </button>
        </div>
      </div>

      <div className="filter-chips" role="group" aria-label={t('common.desk')}>
        <button className={`chip${filter === 'all' ? ' active' : ''}`} onClick={() => setFilter('all')}>
          {t('feed.filterAll')}
        </button>
        {DESKS.map((d) => (
          <button key={d} className={`chip${filter === d ? ' active' : ''}`} onClick={() => setFilter(d)}>
            {DESK_LABELS[d]}
          </button>
        ))}
      </div>

      {notice && <div className="notice">{notice}</div>}

      {!loading && !error && cards.length === 0 && (
        <div className="notice">{t('feed.emptyNoNews')}</div>
      )}

      {loading ? (
        <Loading />
      ) : error ? (
        <div className="card">
          <Empty text={t('feed.empty')} />
          <p className="muted small" style={{ textAlign: 'center' }}>{t('common.loadError')}: {error}</p>
        </div>
      ) : items.length === 0 ? (
        <div className="card"><Empty text={t('feed.empty')} /></div>
      ) : (
        items.map((item) => item.kind === 'post'
          ? <PostCard key={item.key} post={item.post} />
          : <NewsCardView key={item.key} card={item.card} />)
      )}
    </section>
  )
}

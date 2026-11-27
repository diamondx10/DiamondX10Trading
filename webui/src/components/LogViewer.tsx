// Terminal log viewer: raw log lines are the source of truth in v1
// (no parsed progress bar). Polls GET /api/logs?process=...&after=<cursor>
// every ~2s, keeps the last ~200 lines, auto-scrolls unless paused.
import { useEffect, useRef, useState } from 'react'
import { fetchLogs, type LogProcess, type LogResponse } from '../api'
import { useI18n, type I18nKey } from '../i18n'

const MAX_LINES = 200
const POLL_MS = 2000

const PROCESSES: { id: LogProcess; label: I18nKey }[] = [
  { id: 'live', label: 'log.live' },
  { id: 'listener', label: 'log.listener' },
  { id: 'diagnostics', label: 'log.diagnostics' },
]

export default function LogViewer() {
  const { t } = useI18n()
  const [process, setProcess] = useState<LogProcess>('live')
  const [lines, setLines] = useState<string[]>([])
  const [meta, setMeta] = useState<Pick<LogResponse, 'running' | 'started_utc' | 'exit_code' | 'total'> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const cursorRef = useRef(0)
  const paneRef = useRef<HTMLDivElement>(null)

  // Reset on process switch, then poll.
  useEffect(() => {
    setLines([])
    setMeta(null)
    setError(null)
    cursorRef.current = 0
    let cancelled = false

    async function poll() {
      try {
        const r = await fetchLogs(process, cursorRef.current)
        if (cancelled) return
        setMeta({ running: r.running, started_utc: r.started_utc, exit_code: r.exit_code, total: r.total })
        setError(null)
        if (r.lines.length > 0) {
          cursorRef.current = r.total
          setLines((prev) => [...prev, ...r.lines].slice(-MAX_LINES))
        } else {
          // No new lines; keep the cursor in sync with the server total
          // (e.g. after a log rotation / process restart).
          cursorRef.current = r.total
        }
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : String(e))
      }
    }

    poll()
    const id = window.setInterval(poll, POLL_MS)
    return () => { cancelled = true; window.clearInterval(id) }
  }, [process])

  // Auto-scroll to the bottom on new lines, unless paused.
  useEffect(() => {
    if (autoScroll && paneRef.current) {
      paneRef.current.scrollTop = paneRef.current.scrollHeight
    }
  }, [lines, autoScroll])

  return (
    <div className="card">
      <h2>{t('log.title')}</h2>
      <div className="btn-row log-controls">
        <label className="form-field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <span>{t('log.process')}</span>
          <select value={process} onChange={(e) => setProcess(e.target.value as LogProcess)}>
            {PROCESSES.map((p) => (
              <option key={p.id} value={p.id}>{t(p.label)}</option>
            ))}
          </select>
        </label>
        <label className="toggle">
          <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} />
          {t('log.autoScroll')}
        </label>
      </div>
      {meta && (
        <p className="muted small log-status">
          {meta.running ? t('log.running') : t('log.stopped')}
          {' · '}{t('log.started')}: {meta.started_utc ?? t('log.notStarted')}
          {meta.exit_code !== null && meta.exit_code !== undefined && ` · ${t('log.exitCode')}: ${meta.exit_code}`}
          {` · ${meta.total} ${t('log.lines')}`}
        </p>
      )}
      {error && <div className="error">{t('log.loadError')}: {error}</div>}
      <div className="log-pane" ref={paneRef} role="log" aria-live="off">
        {lines.length === 0
          ? <span className="log-empty">{t('log.empty')}</span>
          : lines.map((line, i) => <div key={`${i}-${line.slice(0, 32)}`} className="log-line">{line}</div>)}
      </div>
    </div>
  )
}

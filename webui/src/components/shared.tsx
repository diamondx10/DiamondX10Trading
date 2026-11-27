import { useCallback, useEffect, useState } from 'react'
import { useI18n } from '../i18n'

export function useFetch<T>(fn: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    fn()
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  useEffect(() => { load() }, [load])
  return { data, loading, error, reload: load }
}

export function Loading() {
  const { t } = useI18n()
  return <div className="loading">{t('common.loading')}</div>
}
export function Empty({ text }: { text?: string }) {
  const { t } = useI18n()
  return <div className="empty">{text ?? t('common.empty')}</div>
}
export function Err({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const { t } = useI18n()
  return (
    <div className="error">
      {t('common.loadError')}: {message}
      {onRetry && <div style={{ marginTop: 8 }}><button className="btn secondary small" onClick={onRetry}>{t('common.retry')}</button></div>}
    </div>
  )
}
export function StatusDot({ on, label }: { on: boolean; label: string }) {
  return <span className="badge" style={{ color: on ? 'var(--green)' : 'var(--muted)' }}>{on ? '●' : '○'} {label}</span>
}

import { useCallback, useEffect, useState } from 'react'

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

export function Loading() { return <div className="loading">Dang tai...</div> }
export function Empty({ text = 'Chua co du lieu' }: { text?: string }) { return <div className="empty">{text}</div> }
export function Err({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error">
      Khong tai duoc du lieu: {message}
      {onRetry && <div style={{ marginTop: 8 }}><button className="btn secondary small" onClick={onRetry}>Thu lai</button></div>}
    </div>
  )
}
export function StatusDot({ on, label }: { on: boolean; label: string }) {
  return <span className="badge" style={{ color: on ? 'var(--green)' : 'var(--muted)' }}>{on ? '●' : '○'} {label}</span>
}

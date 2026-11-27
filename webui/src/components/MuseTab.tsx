import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPost, DESK_LABELS, DESKS, type Briefing, type MuseJob, type Verdict } from '../api'
import { Empty, Err, Loading, useFetch } from './shared'

type JobState = { job_id: string; file: string } & MuseJob

export default function MuseTab() {
  const brief = useFetch(() => apiGet<{ briefings: Briefing[] }>('/api/briefings'))
  const verd = useFetch(() => apiGet<{ verdicts: Verdict[] }>('/api/verdicts'))
  const [desk, setDesk] = useState('forex')
  const [days, setDays] = useState(3)
  const [paste, setPaste] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState('')
  const [jobs, setJobs] = useState<Record<string, JobState>>({})
  const timers = useRef<Record<string, number>>({})

  useEffect(() => () => { Object.values(timers.current).forEach(clearInterval) }, [])

  function poll(jobId: string) {
    timers.current[jobId] = window.setInterval(async () => {
      try {
        const j = await apiGet<MuseJob>(`/api/muse-send/${encodeURIComponent(jobId)}`)
        setJobs((prev) => ({ ...prev, [jobId]: { ...prev[jobId], ...j } }))
        if (j.status !== 'sending') {
          clearInterval(timers.current[jobId])
          if (j.status === 'verdict_stored') verd.reload()
        }
      } catch (e) {
        clearInterval(timers.current[jobId])
        setJobs((prev) => ({ ...prev, [jobId]: { ...prev[jobId], status: 'error', reason: e instanceof Error ? e.message : String(e) } }))
      }
    }, 5000)
  }

  async function sendToMuse(file: string) {
    setBusy(file); setErr(null); setMsg(null)
    try {
      const r = await apiPost<{ job_id: string; status: string }>(`/api/muse-send`, { file })
      const job: JobState = { job_id: r.job_id, file, status: 'sending', verdict: null, reason: '' }
      setJobs((prev) => ({ ...prev, [r.job_id]: job }))
      poll(r.job_id)
      setMsg(`Da gui ${file} — dang cho Muse phan hoi...`)
    } catch (e) {
      const m = e instanceof Error ? e.message : String(e)
      setErr(`Gui that bai: ${m}. Neu backend bao 503, module trinh duyet Muse chua co tren may nay.`)
    } finally { setBusy('') }
  }

  async function makeBriefing() {
    setBusy('briefing'); setErr(null)
    try {
      const r = await apiPost<{ ok: boolean; file: string | null; reason: string }>('/api/briefing', { desk, days })
      if (!r.ok) throw new Error(r.reason || 'That bai')
      setMsg(`Da tao briefing: ${r.file ?? ''}`)
      brief.reload()
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) } finally { setBusy('') }
  }

  async function submitVerdict() {
    setBusy('verdict'); setErr(null); setMsg(null)
    try {
      const parsed = JSON.parse(paste) as Record<string, unknown>
      const verdict = (parsed.verdict ?? parsed) as Record<string, unknown>
      const r = await apiPost<{ ok: boolean; reason: string }>('/api/verdicts', { verdict })
      if (!r.ok) throw new Error(r.reason || 'That bai')
      setMsg('Da luu verdict.')
      setPaste('')
      verd.reload()
    } catch (e) { setErr(e instanceof Error ? e.message : String(e)) } finally { setBusy('') }
  }

  const jobList = Object.values(jobs)

  return (
    <div>
      {msg && <div className="notice">{msg}</div>}
      {err && <div className="error">{err}</div>}

      <div className="card">
        <h2>Tao briefing moi</h2>
        <div className="btn-row">
          <label>Desk <select value={desk} onChange={(e) => setDesk(e.target.value)}>
            {DESKS.map((d) => <option key={d} value={d}>{DESK_LABELS[d]}</option>)}
          </select></label>
          <label>So ngay <input type="number" min={1} max={30} value={days} style={{ width: 80 }} onChange={(e) => setDays(Number(e.target.value))} /></label>
          <button className="btn" disabled={busy !== ''} onClick={makeBriefing}>Tao briefing</button>
        </div>
      </div>

      <div className="card">
        <h2>Briefings</h2>
        {brief.loading ? <Loading /> : brief.error || !brief.data ? <Err message={brief.error ?? 'Khong co du lieu'} onRetry={brief.reload} />
          : brief.data.briefings.length === 0 ? <Empty text="Chua co briefing nao" /> : (
          <ul className="clean">{brief.data.briefings.map((b) => (
            <li key={b.file}>
              <strong>{b.name || b.file}</strong> <span className="muted small">· {b.desk} · {b.created}</span>
              <div className="btn-row" style={{ marginTop: 6 }}>
                <button className="btn secondary small" disabled={busy !== ''} onClick={() => sendToMuse(b.file)}>Send to Muse</button>
                <span className="small muted">{b.path}</span>
              </div>
            </li>
          ))}</ul>)}
        {jobList.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <h3>Trang thai gui</h3>
            <ul className="clean">{jobList.map((j) => (
              <li key={j.job_id}><span className="badge">{j.status}</span> {j.file}
                {j.reason && <span className="muted small"> — {j.reason}</span>}
                {j.verdict && <pre className="json">{JSON.stringify(j.verdict, null, 2)}</pre>}
              </li>
            ))}</ul>
          </div>
        )}
      </div>

      <div className="card">
        <h2>Dan verdict (JSON)</h2>
        <p className="muted small">Dan JSON verdict Muse tra ve (ca object hoac chi phan verdict), roi bam Luu verdict. Loi validation se hien o day.</p>
        <textarea value={paste} onChange={(e) => setPaste(e.target.value)} placeholder='{"desk": "forex", "direction": "buy", "confidence": 0.7, ...}' />
        <div className="btn-row" style={{ marginTop: 10 }}>
          <button className="btn" disabled={busy !== '' || !paste.trim()} onClick={submitVerdict}>Luu verdict</button>
        </div>
      </div>

      <div className="card">
        <h2>Verdicts da luu</h2>
        {verd.loading ? <Loading /> : verd.error || !verd.data ? <Err message={verd.error ?? 'Khong co du lieu'} onRetry={verd.reload} />
          : verd.data.verdicts.length === 0 ? <Empty text="Chua co verdict nao" /> : (
          <div className="table-wrap"><table><thead><tr><th>Desk</th><th>Analyst</th><th>Huong</th><th>Do tin cay</th><th>Drivers</th><th>Risks</th><th>Tuoi</th></tr></thead>
          <tbody>{verd.data.verdicts.map((v, i) => (
            <tr key={i}><td>{v.desk}</td><td>{v.analyst}</td><td><span className={`badge ${v.direction.toLowerCase()}`}>{v.direction}</span></td>
            <td>{v.confidence === null ? '—' : `${(v.confidence * 100).toFixed(0)}%`}</td>
            <td className="small">{(v.drivers ?? []).join('; ')}</td><td className="small">{(v.risks ?? []).join('; ')}</td>
            <td>{v.age_hours === null ? '—' : `${v.age_hours.toFixed(1)}h`}</td></tr>
          ))}</tbody></table></div>)}
      </div>
    </div>
  )
}

import { apiGet, type Status } from '../api'
import { useI18n } from '../i18n'
import { Err, Loading, StatusDot, useFetch } from './shared'

export default function Settings() {
  const { t } = useI18n()
  const { data, loading, error, reload } = useFetch(() => apiGet<Status>('/api/status'))
  if (loading) return <Loading />
  if (error || !data) return <Err message={error ?? t('common.empty')} onRetry={reload} />
  const s = data
  return (
    <div>
      <div className="card">
        <h2>{t('set.connections')}</h2>
        <dl className="kv">
          <dt>MT5</dt><dd><StatusDot on={s.mt5_ok} label={s.mt5_ok ? t('set.mt5Connected') : t('set.mt5NotConnected')} /></dd>
          <dt>Telegram</dt><dd><StatusDot on={s.telegram_ready} label={s.telegram_ready ? t('set.tgReady') : t('set.tgNotReady')} /></dd>
          <dt>Live</dt><dd>{s.live_running ? t('set.liveRunning') : t('set.liveStopped')}</dd>
          <dt>Listener</dt><dd>{s.listener_running ? t('set.liveRunning') : t('set.liveStopped')}</dd>
        </dl>
        <p className="muted small">{t('set.note1')}</p>
      </div>
      <div className="card">
        <h2>{t('set.fundLimits')}</h2>
        <dl className="kv">
          <dt>{t('set.capital')}</dt><dd>${s.capital.toLocaleString('en-US')}</dd>
          <dt>{t('set.maxDd')}</dt><dd>{t('set.maxDdValue')}</dd>
          <dt>{t('set.currentDd')}</dt><dd>{s.drawdown_pct === null ? '—' : `${s.drawdown_pct.toFixed(2)}%`}</dd>
          <dt>{t('set.killSwitch')}</dt><dd>{s.kill_switch_on ? t('set.ksOn') : t('set.ksOff')}</dd>
        </dl>
      </div>
      <div className="card">
        <h2>{t('set.synthesis')}</h2>
        <dl className="kv">
          <dt>{t('set.verdictValidity')}</dt><dd>{t('set.verdictValidityValue')}</dd>
          <dt>{t('set.requireFa')}</dt><dd>{t('set.requireFaValue')}</dd>
          <dt>{t('set.confThreshold')}</dt><dd>0.6</dd>
        </dl>
        <p className="muted small">{t('set.note2')}</p>
      </div>
    </div>
  )
}

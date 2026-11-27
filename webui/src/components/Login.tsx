// OTP login screen. Shown when GET /api/auth/status says unauthenticated.
// Flow: "Send OTP via Telegram" -> 6-digit code input -> verify. The OTP
// itself is never displayed or logged by the frontend.
import { useEffect, useRef, useState } from 'react'
import { requestOtp, verifyOtp, type OtpFailure } from '../api'
import { useI18n } from '../i18n'

const OTP_TTL_SECONDS = 60

export default function Login({ onSignedIn }: { onSignedIn: () => void }) {
  const { t } = useI18n()
  const [code, setCode] = useState('')
  const [sent, setSent] = useState(false)
  const [fallbackTerminal, setFallbackTerminal] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const [cooldown, setCooldown] = useState(0)
  const [busy, setBusy] = useState<'send' | 'verify' | ''>('')
  const [error, setError] = useState<string | null>(null)
  const timerRef = useRef<number | null>(null)

  // 1-second ticker for both the OTP expiry countdown and the resend cooldown.
  useEffect(() => {
    timerRef.current = window.setInterval(() => {
      setCountdown((c) => (c > 0 ? c - 1 : 0))
      setCooldown((c) => (c > 0 ? c - 1 : 0))
    }, 1000)
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current)
    }
  }, [])

  async function sendOtp() {
    setBusy('send'); setError(null); setFallbackTerminal(false)
    try {
      const r = await requestOtp()
      if (r.sent) {
        setSent(true)
        setCountdown(OTP_TTL_SECONDS)
      } else if (r.fallback === 'terminal') {
        // Telegram delivery failed; the code is printed on the server
        // terminal instead. Still show the code box so it can be entered.
        setSent(true)
        setCountdown(OTP_TTL_SECONDS)
        setFallbackTerminal(true)
      } else {
        setError(t('auth.errorSendFailed', { msg: r.reason ?? '' }))
      }
    } catch (e) {
      const err = e as OtpFailure
      if (err.code === 'cooldown' && err.retryAfter !== undefined) {
        setCooldown(err.retryAfter)
        setError(t('auth.cooldown', { n: err.retryAfter }))
      } else {
        setError(t('auth.errorSendFailed', { msg: err.message }))
      }
    } finally {
      setBusy('')
    }
  }

  function verifyErrorMessage(err: OtpFailure): string {
    switch (err.code) {
      case 'invalid': return t('auth.errorInvalid')
      case 'expired': return t('auth.errorExpired')
      case 'too_many_attempts': return t('auth.errorTooMany')
      case 'no_otp': return t('auth.errorNoOtp')
      default: return t('auth.errorGeneric', { msg: err.message })
    }
  }

  async function verify() {
    if (code.length !== 6) return
    setBusy('verify'); setError(null)
    try {
      await verifyOtp(code)
      onSignedIn()
    } catch (e) {
      setError(verifyErrorMessage(e as OtpFailure))
    } finally {
      setBusy('')
    }
  }

  const codeValid = /^\d{6}$/.test(code)

  return (
    <div className="login-wrap">
      <div className="card login-card">
        <h2>{t('auth.title')}</h2>
        <p className="muted">{t('auth.subtitle')}</p>
        {error && <div className="error">{error}</div>}
        {fallbackTerminal && <div className="notice">{t('auth.fallbackTerminal')}</div>}
        {!sent ? (
          <button className="btn" disabled={busy === 'send' || cooldown > 0} onClick={sendOtp}>
            {busy === 'send' ? t('auth.sending') : t('auth.sendOtp')}
          </button>
        ) : (
          <div>
            <p className="muted small">{t('auth.sent')}</p>
            <div className="form-field">
              <span>{t('auth.codeLabel')}</span>
              <input
                className="otp-input"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                placeholder={t('auth.codePlaceholder')}
                value={code}
                disabled={busy === 'verify'}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                onKeyDown={(e) => { if (e.key === 'Enter') verify() }}
              />
            </div>
            <div className="btn-row" style={{ marginTop: 12 }}>
              <button className="btn" disabled={!codeValid || busy === 'verify'} onClick={verify}>
                {busy === 'verify' ? t('auth.verifying') : t('auth.signIn')}
              </button>
              <button className="btn secondary" disabled={busy === 'send' || cooldown > 0} onClick={sendOtp}>
                {busy === 'send' ? t('auth.sending') : t('auth.resend')}
              </button>
            </div>
            <p className="muted small" style={{ marginTop: 12 }}>
              {cooldown > 0
                ? t('auth.cooldown', { n: cooldown })
                : countdown > 0
                  ? t('auth.expiresIn', { n: countdown })
                  : t('auth.errorExpired')}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

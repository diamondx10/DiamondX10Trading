import { useEffect, useState } from 'react'
import Overview from './components/Overview'
import Positions from './components/Positions'
import Signals from './components/Signals'
import MuseTab from './components/MuseTab'
import News from './components/News'
import Backtest from './components/Backtest'
import Activity from './components/Activity'
import Settings from './components/Settings'
import Manager from './components/Manager'
import Login from './components/Login'
import { getAuthStatus, signOut } from './api'
import { I18nProvider, useI18n, type I18nKey, type Lang } from './i18n'

const TABS = [
  { id: 'manager', label: 'tab.manager' },
  { id: 'overview', label: 'tab.overview' },
  { id: 'positions', label: 'tab.positions' },
  { id: 'signals', label: 'tab.signals' },
  { id: 'muse', label: 'tab.muse' },
  { id: 'news', label: 'tab.news' },
  { id: 'backtest', label: 'tab.backtest' },
  { id: 'activity', label: 'tab.activity' },
  { id: 'settings', label: 'tab.settings' },
] as const

type TabId = (typeof TABS)[number]['id']
type AuthState = 'checking' | 'authed' | 'guest'

function LanguageToggle() {
  const { lang, setLang } = useI18n()
  const langs: Lang[] = ['vi', 'en']
  return (
    <div className="lang-toggle" role="group" aria-label="Language">
      {langs.map((l) => (
        <button key={l} className={lang === l ? 'active' : ''} onClick={() => setLang(l)}>
          {l === 'vi' ? 'VI' : 'EN'}
        </button>
      ))}
    </div>
  )
}

function Shell({ auth, onSignedIn, onSignedOut }: { auth: AuthState; onSignedIn: () => void; onSignedOut: () => void }) {
  const { t } = useI18n()
  // Manager is the landing view after sign-in.
  const [tab, setTab] = useState<TabId>('manager')
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem('dx10-theme') === 'dark' } catch { return false }
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    try { localStorage.setItem('dx10-theme', dark ? 'dark' : 'light') } catch { /* ignore */ }
  }, [dark])

  async function handleSignOut() {
    try { await signOut() } catch { /* session may already be gone — still show login */ }
    onSignedOut()
    setTab('manager')
  }

  return (
    <div className="app">
      <header className="header">
        <div className="brand"><h1>DiamondX10</h1><span>Trading — Demo</span></div>
        <div className="header-actions">
          <LanguageToggle />
          <button className="btn secondary" onClick={() => setDark(!dark)} aria-label={t('header.themeLabel')}>
            {dark ? t('header.themeLight') : t('header.themeDark')}
          </button>
          {auth === 'authed' && (
            <button className="btn secondary" onClick={handleSignOut}>{t('header.signOut')}</button>
          )}
        </div>
      </header>
      {auth === 'checking' && <div className="loading">{t('auth.checking')}</div>}
      {auth === 'guest' && <Login onSignedIn={onSignedIn} />}
      {auth === 'authed' && (
        <>
          <nav className="tabs">
            {TABS.map((tr) => (
              <button key={tr.id} className={`tab${tab === tr.id ? ' active' : ''}`} onClick={() => setTab(tr.id)}>{t(tr.label as I18nKey)}</button>
            ))}
          </nav>
          <main>
            {tab === 'manager' && <Manager />}
            {tab === 'overview' && <Overview onOpenNews={() => setTab('news')} />}
            {tab === 'positions' && <Positions />}
            {tab === 'signals' && <Signals />}
            {tab === 'muse' && <MuseTab />}
            {tab === 'news' && <News />}
            {tab === 'backtest' && <Backtest />}
            {tab === 'activity' && <Activity />}
            {tab === 'settings' && <Settings />}
          </main>
        </>
      )}
      <footer className="footer">{t('footer')}</footer>
    </div>
  )
}

export default function App() {
  // Auth gate: GET /api/auth/status is the FIRST and, while unauthenticated,
  // the ONLY /api/* call. No tab component mounts (and no other /api/*
  // request fires) until the session is confirmed. The language sync inside
  // I18nProvider is gated on the same state (syncLanguage).
  const [auth, setAuth] = useState<AuthState>('checking')

  useEffect(() => {
    let cancelled = false
    getAuthStatus()
      .then((r) => { if (!cancelled) setAuth(r.authenticated ? 'authed' : 'guest') })
      .catch(() => { if (!cancelled) setAuth('guest') })
    return () => { cancelled = true }
  }, [])

  return (
    <I18nProvider syncLanguage={auth === 'authed'}>
      <Shell
        auth={auth}
        onSignedIn={() => setAuth('authed')}
        onSignedOut={() => setAuth('guest')}
      />
    </I18nProvider>
  )
}

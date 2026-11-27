import { useEffect, useState } from 'react'
import Overview from './components/Overview'
import Positions from './components/Positions'
import Signals from './components/Signals'
import MuseTab from './components/MuseTab'
import News from './components/News'
import Backtest from './components/Backtest'
import Activity from './components/Activity'
import Settings from './components/Settings'
import { I18nProvider, useI18n, type I18nKey, type Lang } from './i18n'

const TABS = [
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

function Shell() {
  const { t } = useI18n()
  const [tab, setTab] = useState<TabId>('overview')
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem('dx10-theme') === 'dark' } catch { return false }
  })

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light')
    try { localStorage.setItem('dx10-theme', dark ? 'dark' : 'light') } catch { /* ignore */ }
  }, [dark])

  return (
    <div className="app">
      <header className="header">
        <div className="brand"><h1>DiamondX10</h1><span>Trading — Demo</span></div>
        <div className="header-actions">
          <LanguageToggle />
          <button className="btn secondary" onClick={() => setDark(!dark)} aria-label={t('header.themeLabel')}>
            {dark ? t('header.themeLight') : t('header.themeDark')}
          </button>
        </div>
      </header>
      <nav className="tabs">
        {TABS.map((tr) => (
          <button key={tr.id} className={`tab${tab === tr.id ? ' active' : ''}`} onClick={() => setTab(tr.id)}>{t(tr.label as I18nKey)}</button>
        ))}
      </nav>
      <main>
        {tab === 'overview' && <Overview onOpenNews={() => setTab('news')} />}
        {tab === 'positions' && <Positions />}
        {tab === 'signals' && <Signals />}
        {tab === 'muse' && <MuseTab />}
        {tab === 'news' && <News />}
        {tab === 'backtest' && <Backtest />}
        {tab === 'activity' && <Activity />}
        {tab === 'settings' && <Settings />}
      </main>
      <footer className="footer">{t('footer')}</footer>
    </div>
  )
}

export default function App() {
  return (
    <I18nProvider>
      <Shell />
    </I18nProvider>
  )
}

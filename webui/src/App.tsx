import { useEffect, useState } from 'react'
import Overview from './components/Overview'
import Positions from './components/Positions'
import Signals from './components/Signals'
import MuseTab from './components/MuseTab'
import News from './components/News'
import Backtest from './components/Backtest'
import Activity from './components/Activity'
import Settings from './components/Settings'

const TABS = [
  { id: 'overview', label: 'Tong quan' },
  { id: 'positions', label: 'Vi the' },
  { id: 'signals', label: 'Tin hieu' },
  { id: 'muse', label: 'Muse' },
  { id: 'news', label: 'Tin tuc' },
  { id: 'backtest', label: 'Backtest' },
  { id: 'activity', label: 'Hoat dong' },
  { id: 'settings', label: 'Cai dat' },
] as const

type TabId = (typeof TABS)[number]['id']

export default function App() {
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
        <button className="btn secondary" onClick={() => setDark(!dark)} aria-label="Doi giao dien">
          {dark ? 'Che do sang' : 'Che do toi'}
        </button>
      </header>
      <nav className="tabs">
        {TABS.map((t) => (
          <button key={t.id} className={`tab${tab === t.id ? ' active' : ''}`} onClick={() => setTab(t.id)}>{t.label}</button>
        ))}
      </nav>
      <main>
        {tab === 'overview' && <Overview />}
        {tab === 'positions' && <Positions />}
        {tab === 'signals' && <Signals />}
        {tab === 'muse' && <MuseTab />}
        {tab === 'news' && <News />}
        {tab === 'backtest' && <Backtest />}
        {tab === 'activity' && <Activity />}
        {tab === 'settings' && <Settings />}
      </main>
      <footer className="footer">DiamondX10 Trading — demo only, khong dung tien that.</footer>
    </div>
  )
}

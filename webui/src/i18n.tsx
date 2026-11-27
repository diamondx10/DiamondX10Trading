// Frontend i18n for the DiamondX10 web UI.
// Vietnamese labels stay WITHOUT diacritics (the tool's existing convention).
// News article titles/sources are data, not labels — they are never translated.
// Language choice: localStorage (dx10-language) + POST /api/language so the
// backend (Telegram/briefings) follows. On load, GET /api/language wins on
// conflict. If the backend endpoints are not implemented yet, the UI keeps
// the local choice and degrades gracefully (no crash).
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { apiGet, apiPost } from './api'

export type Lang = 'vi' | 'en'
export const LANG_KEY = 'dx10-language'

const VI = {
  // Tabs
  'tab.overview': 'Tong quan',
  'tab.positions': 'Vi the',
  'tab.signals': 'Tin hieu',
  'tab.muse': 'Muse',
  'tab.news': 'Tin tuc',
  'tab.backtest': 'Backtest',
  'tab.activity': 'Hoat dong',
  'tab.settings': 'Cai dat',
  // Header / footer
  'header.themeLight': 'Che do sang',
  'header.themeDark': 'Che do toi',
  'header.themeLabel': 'Doi giao dien',
  'header.language': 'Ngon ngu',
  'footer': 'DiamondX10 Trading — demo only, khong dung tien that.',
  // Common
  'common.loading': 'Dang tai...',
  'common.empty': 'Chua co du lieu',
  'common.loadError': 'Khong tai duoc du lieu',
  'common.retry': 'Thu lai',
  'common.refresh': 'Lam moi',
  'common.failed': 'that bai',
  'common.ok': 'OK',
  'common.desk': 'Desk',
  'common.symbol': 'Symbol',
  // Overview
  'ov.capital': 'Von',
  'ov.drawdown': 'Drawdown',
  'ov.ddLimit': 'Gioi han: 10% — canh bao 5%',
  'ov.openPositions': 'Vi the mo',
  'ov.allDesks': 'Tong cac desk',
  'ov.status': 'Trang thai',
  'ov.killSwitch': 'Kill switch',
  'ov.ksOn': 'DANG BAT — moi lenh deu bi chan',
  'ov.ksOff': 'Dang tat — giao dich binh thuong',
  'ov.ksNote': 'Bat kill switch se chan moi lenh moi cho den khi tat lai.',
  'ov.ksOnAction': 'Bat kill switch',
  'ov.ksOffAction': 'Tat kill switch',
  'ov.liveListener': 'Live & Listener',
  'ov.startLiveRec': 'Start live — Recommend',
  'ov.startLiveAuto': 'Start live — Auto',
  'ov.stopLive': 'Stop live',
  'ov.startListener': 'Start listener',
  'ov.stopListener': 'Stop listener',
  'ov.refreshStatus': 'Cap nhat trang thai',
  'ov.liveRunning': 'dang chay',
  'ov.liveStopped': 'dung',
  'ov.equityByDesk': 'Equity theo desk',
  'ov.thDesk': 'Desk',
  'ov.thEquity': 'Equity',
  'ov.thOpen': 'Vi the mo',
  // Homepage analyzed-news section
  'teamNews.title': 'Tin team da phan tich',
  'teamNews.empty': 'Chua co tin team da phan tich',
  'teamNews.viewNews': 'Xem tin tuc',
  'teamNews.verdicts': 'Verdict moi nhat theo desk',
  'teamNews.noVerdict': 'Chua co verdict',
  'teamNews.confidence': 'Do tin cay',
  'teamNews.viewBriefing': 'Xem briefing',
  'teamNews.latestBriefing': 'Briefing moi nhat',
  'teamNews.noBriefing': 'Chua co briefing',
  // Analysis feed (homepage)
  'feed.title': 'Bang tin phan tich',
  'feed.composerPlaceholder': 'Dang bai phan tich...',
  'feed.composerTitle': 'Bai phan tich moi',
  'feed.action': 'Ket luan',
  'feed.actionBuy': 'MUA',
  'feed.actionSell': 'BAN',
  'feed.actionNeutral': 'CHO',
  'feed.summary': 'Tom tat',
  'feed.summaryPlaceholder': 'Tom tat ket luan phan tich...',
  'feed.confidence': 'Do tin cay (%)',
  'feed.driversLabel': 'Drivers (moi dong 1 muc)',
  'feed.risksLabel': 'Risks (moi dong 1 muc)',
  'feed.post': 'Dang bai',
  'feed.cancel': 'Huy',
  'feed.posted': 'Da dang bai phan tich.',
  'feed.validation': 'Nhap symbol va tom tat truoc khi dang.',
  'feed.empty': 'Chua co bai phan tich nao',
  'feed.filterAll': 'Tat ca',
  'feed.showMore': 'Xem them',
  'feed.showLess': 'Thu gon',
  'feed.sourceSynthesis': 'Tong hop TA+FA',
  'feed.sourceManual': 'Dang tay',
  'feed.verdict': 'Verdict',
  'feed.timeNow': 'Vua xong',
  'feed.timeMinutes': '{n} phut truoc',
  'feed.timeHours': '{n} gio truoc',
  'feed.timeDays': '{n} ngay truoc',
  'feed.publishFromSynthesis': 'Dang tu tong hop',
  'feed.publishDone': 'Da dang {n} bai tu tong hop.',
  'feed.symbolPlaceholder': 'EURUSD, XAUUSD...',
  // Positions
  'pos.pendingTitle': 'Khuyen nghi cho duyet',
  'pos.empty': 'Chua co vi the mo',
  'pos.pendingEmpty': 'Chua co khuyen nghi cho duyet',
  'pos.thDirection': 'Huong',
  'pos.thEntry': 'Entry',
  'pos.thSl': 'SL',
  'pos.thTp': 'TP',
  'pos.thVolume': 'Volume',
  'pos.thPnl': 'P&L chua thuc hien',
  'pos.thOpened': 'Mo luc',
  'pos.thOrder': 'Lenh',
  'pos.thRisk': 'Rui ro',
  'pos.thExpires': 'Het han',
  'pos.thStatus': 'Trang thai',
  'pos.approve': 'Duyet — Dat lenh',
  'pos.ignore': 'Bo qua',
  'pos.placed': 'Da dat lenh — ticket #{ticket}',
  'pos.ignored': 'Da bo qua khuyen nghi',
  'pos.placeFailed': 'Dat lenh',
  'pos.ignoreFailed': 'Bo qua',
  'pos.genericFail': 'That bai',
  // Signals
  'sig.chart': 'Bieu do nen — {symbol}',
  'sig.ta': 'Tin hieu ky thuat (TA)',
  'sig.taEmpty': 'Chua co tin hieu cho desk nay',
  'sig.noPattern': 'Khong co pattern',
  'sig.synthesis': 'Tong hop TA + FA (Yuling)',
  'sig.synEmpty': 'Chua co tong hop cho desk nay',
  'sig.thTa': 'TA',
  'sig.thFa': 'FA',
  'sig.thConfidence': 'Do tin cay',
  'sig.thRecommendation': 'Khuyen nghi',
  'sig.thSize': 'Size',
  'sig.thVerdictAge': 'Tuoi verdict',
  'sig.noBars': 'Chua co du lieu nen cho {symbol}',
  // Muse tab
  'muse.newBriefing': 'Tao briefing moi',
  'muse.days': 'So ngay',
  'muse.createBriefing': 'Tao briefing',
  'muse.briefings': 'Briefings',
  'muse.briefingsEmpty': 'Chua co briefing nao',
  'muse.sendStatus': 'Trang thai gui',
  'muse.pasteVerdict': 'Dan verdict (JSON)',
  'muse.pasteHint': 'Dan JSON verdict Muse tra ve (ca object hoac chi phan verdict), roi bam Luu verdict. Loi validation se hien o day.',
  'muse.saveVerdict': 'Luu verdict',
  'muse.savedVerdicts': 'Verdicts da luu',
  'muse.savedEmpty': 'Chua co verdict nao',
  'muse.sendFailed': 'Gui that bai: {msg}. Neu backend bao 503, module trinh duyet Muse chua co tren may nay.',
  'muse.sent': 'Da gui {file} — dang cho Muse phan hoi...',
  'muse.briefingCreated': 'Da tao briefing: {file}',
  'muse.verdictSaved': 'Da luu verdict.',
  'muse.thAnalyst': 'Analyst',
  'muse.thDirection': 'Huong',
  'muse.thConfidence': 'Do tin cay',
  'muse.thDrivers': 'Drivers',
  'muse.thRisks': 'Risks',
  'muse.thAge': 'Tuoi',
  // News tab
  'news.tier1': 'Tier 1 — Nguon chinh thuc',
  'news.tier2': 'Tier 2 — Bao chi',
  'news.tier3': 'Tier 3 — Tin ro ri, chua xac minh',
  'news.empty': 'Chua co tin tuc cho desk nay',
  // Backtest
  'bt.latest': 'Backtest gan nhat',
  'bt.empty': 'Chua co du lieu backtest — chay backtest truoc roi quay lai',
  'bt.trades': 'Giao dich',
  // Activity
  'act.title': 'Lich su quyet dinh (50 dong gan nhat)',
  'act.empty': 'Chua co hoat dong nao',
  'act.thTime': 'Thoi gian',
  'act.thAction': 'Hanh dong',
  'act.thReason': 'Ly do',
  'act.thManager': 'Quan ly',
  // Settings
  'set.connections': 'Ket noi',
  'set.mt5Connected': 'Dang ket noi',
  'set.mt5NotConnected': 'Chua ket noi',
  'set.tgReady': 'San sang',
  'set.tgNotReady': 'Chua cau hinh',
  'set.liveRunning': 'Dang chay',
  'set.liveStopped': 'Dung',
  'set.note1': 'Duong dan MT5 terminal va token Telegram duoc cau hinh o backend (config.yaml / bien moi truong). Trang nay chi hien thi, khong chinh sua trong phien ban nay.',
  'set.fundLimits': 'Gioi han quy',
  'set.capital': 'Von',
  'set.maxDd': 'Drawdown toi da',
  'set.maxDdValue': '10% (canh bao 5%)',
  'set.currentDd': 'Drawdown hien tai',
  'set.killSwitch': 'Kill switch',
  'set.ksOn': 'DANG BAT',
  'set.ksOff': 'Tat',
  'set.synthesis': 'Tong hop TA + FA',
  'set.verdictValidity': 'Verdict hieu luc',
  'set.verdictValidityValue': '24 gio',
  'set.requireFa': 'Yeu cau FA',
  'set.requireFaValue': 'Khong bat buoc (require_fa: false)',
  'set.confThreshold': 'Nguong tin cay',
  'set.note2': 'Cac gia tri nay la mac dinh da chot theo rule 39. Chi hien thi, khong chinh sua trong phien ban nay.',
} as const

export type I18nKey = keyof typeof VI

const EN: Record<I18nKey, string> = {
  'tab.overview': 'Overview',
  'tab.positions': 'Positions',
  'tab.signals': 'Signals',
  'tab.muse': 'Muse',
  'tab.news': 'News',
  'tab.backtest': 'Backtest',
  'tab.activity': 'Activity',
  'tab.settings': 'Settings',
  'header.themeLight': 'Light mode',
  'header.themeDark': 'Dark mode',
  'header.themeLabel': 'Switch theme',
  'header.language': 'Language',
  'footer': 'DiamondX10 Trading — demo only, no real money.',
  'common.loading': 'Loading...',
  'common.empty': 'No data yet',
  'common.loadError': 'Could not load data',
  'common.retry': 'Retry',
  'common.refresh': 'Refresh',
  'common.failed': 'failed',
  'common.ok': 'OK',
  'common.desk': 'Desk',
  'common.symbol': 'Symbol',
  'ov.capital': 'Capital',
  'ov.drawdown': 'Drawdown',
  'ov.ddLimit': 'Limit: 10% — warning at 5%',
  'ov.openPositions': 'Open positions',
  'ov.allDesks': 'Across all desks',
  'ov.status': 'Status',
  'ov.killSwitch': 'Kill switch',
  'ov.ksOn': 'ON — all new orders are blocked',
  'ov.ksOff': 'Off — trading normally',
  'ov.ksNote': 'Turning on the kill switch blocks all new orders until it is turned off again.',
  'ov.ksOnAction': 'Turn kill switch on',
  'ov.ksOffAction': 'Turn kill switch off',
  'ov.liveListener': 'Live & Listener',
  'ov.startLiveRec': 'Start live — Recommend',
  'ov.startLiveAuto': 'Start live — Auto',
  'ov.stopLive': 'Stop live',
  'ov.startListener': 'Start listener',
  'ov.stopListener': 'Stop listener',
  'ov.refreshStatus': 'Refresh status',
  'ov.liveRunning': 'running',
  'ov.liveStopped': 'stopped',
  'ov.equityByDesk': 'Equity by desk',
  'ov.thDesk': 'Desk',
  'ov.thEquity': 'Equity',
  'ov.thOpen': 'Open positions',
  'teamNews.title': 'News the team has analyzed',
  'teamNews.empty': 'No analyzed news yet',
  'teamNews.viewNews': 'View news',
  'teamNews.verdicts': 'Latest verdict by desk',
  'teamNews.noVerdict': 'No verdict yet',
  'teamNews.confidence': 'Confidence',
  'teamNews.viewBriefing': 'View briefing',
  'teamNews.latestBriefing': 'Latest briefing',
  'teamNews.noBriefing': 'No briefing yet',
  'feed.title': 'Analysis feed',
  'feed.composerPlaceholder': 'Post an analysis...',
  'feed.composerTitle': 'New analysis post',
  'feed.action': 'Conclusion',
  'feed.actionBuy': 'BUY',
  'feed.actionSell': 'SELL',
  'feed.actionNeutral': 'WAIT',
  'feed.summary': 'Summary',
  'feed.summaryPlaceholder': 'Summarise the analysis conclusion...',
  'feed.confidence': 'Confidence (%)',
  'feed.driversLabel': 'Drivers (one per line)',
  'feed.risksLabel': 'Risks (one per line)',
  'feed.post': 'Post',
  'feed.cancel': 'Cancel',
  'feed.posted': 'Analysis posted.',
  'feed.validation': 'Enter a symbol and a summary before posting.',
  'feed.empty': 'No analysis posts yet',
  'feed.filterAll': 'All',
  'feed.showMore': 'Show more',
  'feed.showLess': 'Show less',
  'feed.sourceSynthesis': 'TA+FA synthesis',
  'feed.sourceManual': 'Posted manually',
  'feed.verdict': 'Verdict',
  'feed.timeNow': 'Just now',
  'feed.timeMinutes': '{n}m ago',
  'feed.timeHours': '{n}h ago',
  'feed.timeDays': '{n}d ago',
  'feed.publishFromSynthesis': 'Post from synthesis',
  'feed.publishDone': 'Posted {n} posts from synthesis.',
  'feed.symbolPlaceholder': 'EURUSD, XAUUSD...',
  'pos.pendingTitle': 'Recommendations awaiting approval',
  'pos.empty': 'No open positions',
  'pos.pendingEmpty': 'No recommendations awaiting approval',
  'pos.thDirection': 'Direction',
  'pos.thEntry': 'Entry',
  'pos.thSl': 'SL',
  'pos.thTp': 'TP',
  'pos.thVolume': 'Volume',
  'pos.thPnl': 'Unrealised P&L',
  'pos.thOpened': 'Opened',
  'pos.thOrder': 'Order',
  'pos.thRisk': 'Risk',
  'pos.thExpires': 'Expires',
  'pos.thStatus': 'Status',
  'pos.approve': 'Approve — Place order',
  'pos.ignore': 'Ignore',
  'pos.placed': 'Order placed — ticket #{ticket}',
  'pos.ignored': 'Recommendation ignored',
  'pos.placeFailed': 'Place order',
  'pos.ignoreFailed': 'Ignore',
  'pos.genericFail': 'Failed',
  'sig.chart': 'Candlestick chart — {symbol}',
  'sig.ta': 'Technical signals (TA)',
  'sig.taEmpty': 'No signals for this desk yet',
  'sig.noPattern': 'No patterns',
  'sig.synthesis': 'TA + FA synthesis (Yuling)',
  'sig.synEmpty': 'No synthesis for this desk yet',
  'sig.thTa': 'TA',
  'sig.thFa': 'FA',
  'sig.thConfidence': 'Confidence',
  'sig.thRecommendation': 'Recommendation',
  'sig.thSize': 'Size',
  'sig.thVerdictAge': 'Verdict age',
  'sig.noBars': 'No candle data for {symbol} yet',
  'muse.newBriefing': 'Create new briefing',
  'muse.days': 'Days',
  'muse.createBriefing': 'Create briefing',
  'muse.briefings': 'Briefings',
  'muse.briefingsEmpty': 'No briefings yet',
  'muse.sendStatus': 'Send status',
  'muse.pasteVerdict': 'Paste verdict (JSON)',
  'muse.pasteHint': 'Paste the verdict JSON Muse returned (the full object or just the verdict part), then click Save verdict. Validation errors will show here.',
  'muse.saveVerdict': 'Save verdict',
  'muse.savedVerdicts': 'Saved verdicts',
  'muse.savedEmpty': 'No verdicts saved yet',
  'muse.sendFailed': 'Send failed: {msg}. If the backend reports 503, the Muse browser module is not installed on this machine.',
  'muse.sent': 'Sent {file} — waiting for Muse\u2019s reply...',
  'muse.briefingCreated': 'Briefing created: {file}',
  'muse.verdictSaved': 'Verdict saved.',
  'muse.thAnalyst': 'Analyst',
  'muse.thDirection': 'Direction',
  'muse.thConfidence': 'Confidence',
  'muse.thDrivers': 'Drivers',
  'muse.thRisks': 'Risks',
  'muse.thAge': 'Age',
  'news.tier1': 'Tier 1 — Official source',
  'news.tier2': 'Tier 2 — Press',
  'news.tier3': 'Tier 3 — Leak, unverified',
  'news.empty': 'No news for this desk yet',
  'bt.latest': 'Latest backtest',
  'bt.empty': 'No backtest data yet — run a backtest first, then come back',
  'bt.trades': 'Trades',
  'act.title': 'Decision history (latest 50 rows)',
  'act.empty': 'No activity yet',
  'act.thTime': 'Time',
  'act.thAction': 'Action',
  'act.thReason': 'Reason',
  'act.thManager': 'Manager',
  'set.connections': 'Connections',
  'set.mt5Connected': 'Connected',
  'set.mt5NotConnected': 'Not connected',
  'set.tgReady': 'Ready',
  'set.tgNotReady': 'Not configured',
  'set.liveRunning': 'Running',
  'set.liveStopped': 'Stopped',
  'set.note1': 'The MT5 terminal path and Telegram token are configured in the backend (config.yaml / environment variables). This page is display-only and cannot be edited in this version.',
  'set.fundLimits': 'Fund limits',
  'set.capital': 'Capital',
  'set.maxDd': 'Max drawdown',
  'set.maxDdValue': '10% (warning at 5%)',
  'set.currentDd': 'Current drawdown',
  'set.killSwitch': 'Kill switch',
  'set.ksOn': 'ON',
  'set.ksOff': 'Off',
  'set.synthesis': 'TA + FA synthesis',
  'set.verdictValidity': 'Verdict validity',
  'set.verdictValidityValue': '24 hours',
  'set.requireFa': 'FA required',
  'set.requireFaValue': 'Not required (require_fa: false)',
  'set.confThreshold': 'Confidence threshold',
  'set.note2': 'These are the agreed defaults per rule 39. Display-only, not editable in this version.',
}

const STRINGS: Record<Lang, Record<I18nKey, string>> = { vi: VI, en: EN }

function readStoredLanguage(): Lang {
  try {
    const v = localStorage.getItem(LANG_KEY)
    return v === 'en' || v === 'vi' ? v : 'vi'
  } catch {
    return 'vi'
  }
}

interface I18nCtx {
  lang: Lang
  setLang: (l: Lang) => void
  t: (key: I18nKey, vars?: Record<string, string | number>) => string
}

const Ctx = createContext<I18nCtx>({
  lang: 'vi',
  setLang: () => undefined,
  t: (key) => VI[key],
})

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readStoredLanguage)

  // Backend wins on conflict: sync from GET /api/language on load.
  // If the endpoint does not exist yet, keep the local choice.
  useEffect(() => {
    let cancelled = false
    apiGet<{ language: string }>('/api/language')
      .then((r) => {
        if (cancelled) return
        if (r.language === 'vi' || r.language === 'en') {
          setLangState(r.language)
          try { localStorage.setItem(LANG_KEY, r.language) } catch { /* ignore */ }
        }
      })
      .catch(() => { /* endpoint not implemented yet — keep local choice */ })
    return () => { cancelled = true }
  }, [])

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    try { localStorage.setItem(LANG_KEY, l) } catch { /* ignore */ }
    // Persist server-side so Telegram/briefings follow; ignore failure
    // (endpoint may not exist yet).
    apiPost('/api/language', { language: l }).catch(() => { /* ignore */ })
  }, [])

  const t = useCallback((key: I18nKey, vars?: Record<string, string | number>) => {
    let s = STRINGS[lang][key] ?? VI[key] ?? key
    if (vars) {
      for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v))
    }
    return s
  }, [lang])

  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>
}

export function useI18n(): I18nCtx {
  return useContext(Ctx)
}

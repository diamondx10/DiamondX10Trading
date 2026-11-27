// Frontend i18n for the DiamondX10 web UI.
// Vietnamese labels use proper diacritics (tiếng Việt có dấu).
// CLI/console/log output still stays WITHOUT diacritics.
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
  'tab.overview': 'Tổng quan',
  'tab.positions': 'Vị thế',
  'tab.signals': 'Tín hiệu',
  'tab.muse': 'Muse',
  'tab.news': 'Tin tức',
  'tab.backtest': 'Backtest',
  'tab.activity': 'Hoạt động',
  'tab.settings': 'Cài đặt',
  // Header / footer
  'header.themeLight': 'Chế độ sáng',
  'header.themeDark': 'Chế độ tối',
  'header.themeLabel': 'Đổi giao diện',
  'header.language': 'Ngôn ngữ',
  'footer': 'DiamondX10 Trading — demo only, không dùng tiền thật.',
  // Common
  'common.loading': 'Đang tải...',
  'common.empty': 'Chưa có dữ liệu',
  'common.loadError': 'Không tải được dữ liệu',
  'common.retry': 'Thử lại',
  'common.refresh': 'Làm mới',
  'common.failed': 'thất bại',
  'common.ok': 'OK',
  'common.desk': 'Desk',
  'common.symbol': 'Symbol',
  // Overview
  'ov.capital': 'Vốn',
  'ov.drawdown': 'Drawdown',
  'ov.ddLimit': 'Giới hạn: 10% — cảnh báo 5%',
  'ov.openPositions': 'Vị thế mở',
  'ov.allDesks': 'Tổng các desk',
  'ov.status': 'Trạng thái',
  'ov.killSwitch': 'Kill switch',
  'ov.ksOn': 'ĐANG BẬT — mọi lệnh đều bị chặn',
  'ov.ksOff': 'Đang tắt — giao dịch bình thường',
  'ov.ksNote': 'Bật kill switch sẽ chặn mọi lệnh mới cho đến khi tắt lại.',
  'ov.ksOnAction': 'Bật kill switch',
  'ov.ksOffAction': 'Tắt kill switch',
  'ov.liveListener': 'Live & Listener',
  'ov.startLiveRec': 'Start live — Recommend',
  'ov.startLiveAuto': 'Start live — Auto',
  'ov.stopLive': 'Stop live',
  'ov.startListener': 'Start listener',
  'ov.stopListener': 'Stop listener',
  'ov.refreshStatus': 'Cập nhật trạng thái',
  'ov.liveRunning': 'đang chạy',
  'ov.liveStopped': 'dừng',
  'ov.equityByDesk': 'Equity theo desk',
  'ov.thDesk': 'Desk',
  'ov.thEquity': 'Equity',
  'ov.thOpen': 'Vị thế mở',
  // Homepage analyzed-news section
  'teamNews.title': 'Tin team đã phân tích',
  'teamNews.empty': 'Chưa có tin team đã phân tích',
  'teamNews.viewNews': 'Xem tin tức',
  'teamNews.verdicts': 'Verdict mới nhất theo desk',
  'teamNews.noVerdict': 'Chưa có verdict',
  'teamNews.confidence': 'Độ tin cậy',
  'teamNews.viewBriefing': 'Xem briefing',
  'teamNews.latestBriefing': 'Briefing mới nhất',
  'teamNews.noBriefing': 'Chưa có briefing',
  // Analysis feed (homepage)
  'feed.title': 'Bảng tin phân tích',
  'feed.composerPlaceholder': 'Đăng bài phân tích...',
  'feed.composerTitle': 'Bài phân tích mới',
  'feed.action': 'Kết luận',
  'feed.actionBuy': 'MUA',
  'feed.actionSell': 'BÁN',
  'feed.actionNeutral': 'CHỜ',
  'feed.summary': 'Tóm tắt',
  'feed.summaryPlaceholder': 'Tóm tắt kết luận phân tích...',
  'feed.confidence': 'Độ tin cậy (%)',
  'feed.driversLabel': 'Drivers (mỗi dòng 1 mục)',
  'feed.risksLabel': 'Risks (mỗi dòng 1 mục)',
  'feed.post': 'Đăng bài',
  'feed.cancel': 'Hủy',
  'feed.posted': 'Đã đăng bài phân tích.',
  'feed.validation': 'Nhập symbol và tóm tắt trước khi đăng.',
  'feed.empty': 'Chưa có bài phân tích nào',
  'feed.filterAll': 'Tất cả',
  'feed.showMore': 'Xem thêm',
  'feed.showLess': 'Thu gọn',
  'feed.sourceSynthesis': 'Tổng hợp TA+FA',
  'feed.sourceManual': 'Đăng tay',
  'feed.verdict': 'Verdict',
  'feed.timeNow': 'Vừa xong',
  'feed.timeMinutes': '{n} phút trước',
  'feed.timeHours': '{n} giờ trước',
  'feed.timeDays': '{n} ngày trước',
  'feed.publishFromSynthesis': 'Đăng từ tổng hợp',
  'feed.publishDone': 'Đã đăng {n} bài từ tổng hợp.',
  'feed.symbolPlaceholder': 'EURUSD, XAUUSD...',
  // Positions
  'pos.pendingTitle': 'Khuyến nghị chờ duyệt',
  'pos.empty': 'Chưa có vị thế mở',
  'pos.pendingEmpty': 'Chưa có khuyến nghị chờ duyệt',
  'pos.thDirection': 'Hướng',
  'pos.thEntry': 'Entry',
  'pos.thSl': 'SL',
  'pos.thTp': 'TP',
  'pos.thVolume': 'Volume',
  'pos.thPnl': 'P&L chưa thực hiện',
  'pos.thOpened': 'Mở lúc',
  'pos.thOrder': 'Lệnh',
  'pos.thRisk': 'Rủi ro',
  'pos.thExpires': 'Hết hạn',
  'pos.thStatus': 'Trạng thái',
  'pos.approve': 'Duyệt — Đặt lệnh',
  'pos.ignore': 'Bỏ qua',
  'pos.placed': 'Đã đặt lệnh — ticket #{ticket}',
  'pos.ignored': 'Đã bỏ qua khuyến nghị',
  'pos.placeFailed': 'Đặt lệnh',
  'pos.ignoreFailed': 'Bỏ qua',
  'pos.genericFail': 'Thất bại',
  // Signals
  'sig.chart': 'Biểu đồ nến — {symbol}',
  'sig.ta': 'Tín hiệu kỹ thuật (TA)',
  'sig.taEmpty': 'Chưa có tín hiệu cho desk này',
  'sig.noPattern': 'Không có pattern',
  'sig.synthesis': 'Tổng hợp TA + FA (Yuling)',
  'sig.synEmpty': 'Chưa có tổng hợp cho desk này',
  'sig.thTa': 'TA',
  'sig.thFa': 'FA',
  'sig.thConfidence': 'Độ tin cậy',
  'sig.thRecommendation': 'Khuyến nghị',
  'sig.thSize': 'Size',
  'sig.thVerdictAge': 'Tuổi verdict',
  'sig.noBars': 'Chưa có dữ liệu nến cho {symbol}',
  // Muse tab
  'muse.newBriefing': 'Tạo briefing mới',
  'muse.days': 'Số ngày',
  'muse.createBriefing': 'Tạo briefing',
  'muse.briefings': 'Briefings',
  'muse.briefingsEmpty': 'Chưa có briefing nào',
  'muse.sendStatus': 'Trạng thái gửi',
  'muse.pasteVerdict': 'Dán verdict (JSON)',
  'muse.pasteHint': 'Dán JSON verdict Muse trả về (cả object hoặc chỉ phần verdict), rồi bấm Lưu verdict. Lỗi validation sẽ hiện ở đây.',
  'muse.saveVerdict': 'Lưu verdict',
  'muse.savedVerdicts': 'Verdicts đã lưu',
  'muse.savedEmpty': 'Chưa có verdict nào',
  'muse.sendFailed': 'Gửi thất bại: {msg}. Nếu backend báo 503, module trình duyệt Muse chưa có trên máy này.',
  'muse.sent': 'Đã gửi {file} — đang chờ Muse phản hồi...',
  'muse.briefingCreated': 'Đã tạo briefing: {file}',
  'muse.verdictSaved': 'Đã lưu verdict.',
  'muse.thAnalyst': 'Analyst',
  'muse.thDirection': 'Hướng',
  'muse.thConfidence': 'Độ tin cậy',
  'muse.thDrivers': 'Drivers',
  'muse.thRisks': 'Risks',
  'muse.thAge': 'Tuổi',
  // News tab
  'news.tier1': 'Tier 1 — Nguồn chính thức',
  'news.tier2': 'Tier 2 — Báo chí',
  'news.tier3': 'Tier 3 — Tin rò rỉ, chưa xác minh',
  'news.empty': 'Chưa có tin tức cho desk này',
  // Backtest
  'bt.latest': 'Backtest gần nhất',
  'bt.empty': 'Chưa có dữ liệu backtest — chạy backtest trước rồi quay lại',
  'bt.trades': 'Giao dịch',
  // Activity
  'act.title': 'Lịch sử quyết định (50 dòng gần nhất)',
  'act.empty': 'Chưa có hoạt động nào',
  'act.thTime': 'Thời gian',
  'act.thAction': 'Hành động',
  'act.thReason': 'Lý do',
  'act.thManager': 'Quản lý',
  // Settings
  'set.connections': 'Kết nối',
  'set.mt5Connected': 'Đang kết nối',
  'set.mt5NotConnected': 'Chưa kết nối',
  'set.tgReady': 'Sẵn sàng',
  'set.tgNotReady': 'Chưa cấu hình',
  'set.liveRunning': 'Đang chạy',
  'set.liveStopped': 'Dừng',
  'set.note1': 'Đường dẫn MT5 terminal và token Telegram được cấu hình ở backend (config.yaml / biến môi trường). Trang này chỉ hiển thị, không chỉnh sửa trong phiên bản này.',
  'set.fundLimits': 'Giới hạn quỹ',
  'set.capital': 'Vốn',
  'set.maxDd': 'Drawdown tối đa',
  'set.maxDdValue': '10% (cảnh báo 5%)',
  'set.currentDd': 'Drawdown hiện tại',
  'set.killSwitch': 'Kill switch',
  'set.ksOn': 'ĐANG BẬT',
  'set.ksOff': 'Tắt',
  'set.synthesis': 'Tổng hợp TA + FA',
  'set.verdictValidity': 'Verdict hiệu lực',
  'set.verdictValidityValue': '24 giờ',
  'set.requireFa': 'Yêu cầu FA',
  'set.requireFaValue': 'Không bắt buộc (require_fa: false)',
  'set.confThreshold': 'Ngưỡng tin cậy',
  'set.note2': 'Các giá trị này là mặc định đã chốt theo rule 39. Chỉ hiển thị, không chỉnh sửa trong phiên bản này.',
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

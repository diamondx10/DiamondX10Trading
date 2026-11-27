import { useEffect, useRef } from 'react'
import { createChart, type IChartApi, type ISeriesApi } from 'lightweight-charts'
import { apiGet, type Bar } from '../api'
import { useI18n } from '../i18n'
import { Empty, Err, Loading } from './shared'
import { useFetch } from './shared'

export default function CandleChart({ symbol }: { symbol: string }) {
  const { t } = useI18n()
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const { data, loading, error } = useFetch(() => apiGet<{ symbol: string; bars: Bar[] }>(`/api/bars?symbol=${encodeURIComponent(symbol)}&n=60`), [symbol])

  useEffect(() => {
    if (!containerRef.current) return
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 320,
      layout: { background: { color: 'transparent' }, textColor: '#6e6e73' },
      grid: { vertLines: { color: 'rgba(0,0,0,0.06)' }, horzLines: { color: 'rgba(0,0,0,0.06)' } },
      timeScale: { timeVisible: true },
    })
    const series = chart.addCandlestickSeries({ upColor: '#1d9e4b', downColor: '#d70015', wickUpColor: '#1d9e4b', wickDownColor: '#d70015' })
    chartRef.current = chart
    seriesRef.current = series
    const onResize = () => chart.applyOptions({ width: containerRef.current?.clientWidth ?? 600 })
    window.addEventListener('resize', onResize)
    return () => { window.removeEventListener('resize', onResize); chart.remove() }
  }, [])

  useEffect(() => {
    if (!data || !seriesRef.current) return
    const rows = data.bars.map((b) => ({ time: Math.floor(new Date(b.time).getTime() / 1000), open: b.open, high: b.high, low: b.low, close: b.close }))
    seriesRef.current.setData(rows as never)
    chartRef.current?.timeScale().fitContent()
  }, [data])

  if (loading) return <Loading />
  if (error) return <Err message={error} />
  if (!data || data.bars.length === 0) return <Empty text={t('sig.noBars', { symbol })} />
  return <div className="chart-wrap" ref={containerRef} />
}

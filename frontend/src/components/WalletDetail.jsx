import { useEffect, useState, useRef } from 'react'
import { api } from '../lib/api'
import { ScoreBar } from './ScoreBar'
import { StatPill } from './StatPill'
import { RadarChart, Radar, PolarGrid, PolarAngleAxis, ResponsiveContainer, Tooltip } from 'recharts'

const fmt = (n, decimals = 2) => n == null ? '—' : Number(n).toFixed(decimals)
const pct = (n) => n == null ? '—' : `${(n * 100).toFixed(1)}%`
const addr = (w) => w ? `${w.slice(0, 6)}...${w.slice(-4)}` : '—'
const copy = (text) => navigator.clipboard.writeText(text)

const RECOMMENDATION_COLORS = {
  'STRONG BUY': '#00e5a0',
  'BUY':        '#00e5a0',
  'WATCH':      '#f5a623',
  'PASS':       '#ff4d6d',
  'HARD PASS':  '#ff4d6d',
}

export function WalletDetail({ wallet, onClose, onBlacklisted, onSelectWallet }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [blacklisting, setBlacklisting] = useState(false)
  const [note, setNote] = useState('')
  const [savingNote, setSavingNote] = useState(false)
  const [noteSaved, setNoteSaved] = useState(false)
  const [noteError, setNoteError] = useState(null)
  const [triggeringReview, setTriggeringReview] = useState(false)
  const noteRef = useRef(null)
  const pollRef = useRef(null)

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  useEffect(() => {
    if (!wallet) { setData(null); stopPolling(); return }
    setLoading(true)
    setBlacklisting(false)
    stopPolling()
    api.getCandidate(wallet)
      .then(d => { setData(d); setNote(d?.note || '') })
      .catch(() => setData(null))
      .finally(() => setLoading(false))
    return stopPolling
  }, [wallet])

  // Poll while ai_review_pending is true
  useEffect(() => {
    if (!wallet || !data?.ai_review_pending) { stopPolling(); return }
    if (pollRef.current) return  // already polling
    pollRef.current = setInterval(() => {
      api.getCandidate(wallet).then(d => {
        setData(d)
        if (!d.ai_review_pending) stopPolling()
      }).catch(() => stopPolling())
    }, 3000)
    return stopPolling
  }, [data?.ai_review_pending, wallet])

  if (!wallet) return null

  const radarData = data ? [
    { metric: 'Win Rate', value: Math.round(data.win_rate * 100) },
    { metric: 'ROI', value: Math.min(100, Math.round(data.roi * 50)) },
    { metric: 'Early Entry', value: Math.round(data.early_entry_score * 200) },
    { metric: 'Consistency', value: Math.min(100, Math.round(data.distinct_markets * 5)) },
    { metric: 'Volume', value: Math.min(100, Math.round(data.total_trades * 2)) },
  ] : []

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0,
          background: 'rgba(0,0,0,0.6)',
          zIndex: 40,
          animation: 'fadeIn 0.15s ease',
        }}
      />

      {/* Panel */}
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0,
        width: 480,
        background: 'var(--surface)',
        borderLeft: '1px solid var(--border2)',
        zIndex: 50,
        overflowY: 'auto',
        animation: 'slideIn 0.2s ease',
        display: 'flex',
        flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{
          padding: '20px 24px',
          borderBottom: '1px solid var(--border)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          position: 'sticky', top: 0,
          background: 'var(--surface)',
          zIndex: 1,
        }}>
          <div>
            <div style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', marginBottom: 4 }}>
              WALLET
            </div>
            {data?.username && (
              <div style={{ fontSize: 13, color: 'var(--text)', fontFamily: 'var(--font-mono)', marginBottom: 4 }}>
                {data.username}
              </div>
            )}
            <div style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 15,
              color: 'var(--accent)',
              cursor: 'pointer',
              display: 'flex', alignItems: 'center', gap: 8,
            }} onClick={() => copy(wallet)}>
              {addr(wallet)}
              <span style={{ fontSize: 10, color: 'var(--text-faint)' }}>copy</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button
              disabled={blacklisting}
              onClick={async () => {
                if (!confirm(`Blacklist ${addr(wallet)}? It won't appear in future scans.`)) return
                setBlacklisting(true)
                try {
                  await api.deleteCandidate(wallet)
                  onBlacklisted?.(wallet)
                  onClose()
                } catch {
                  setBlacklisting(false)
                }
              }}
              style={{
                background: 'rgba(255,77,109,0.08)',
                border: '1px solid rgba(255,77,109,0.3)',
                color: 'var(--danger)',
                padding: '6px 12px',
                fontSize: 12,
                fontFamily: 'var(--font-mono)',
                cursor: blacklisting ? 'not-allowed' : 'pointer',
                opacity: blacklisting ? 0.5 : 1,
              }}
            >
              {blacklisting ? '...' : 'BLACKLIST'}
            </button>
            <button
              onClick={onClose}
              style={{
                background: 'var(--surface2)',
                border: '1px solid var(--border)',
                color: 'var(--text-muted)',
                padding: '6px 12px',
                fontSize: 13,
              }}
            >✕</button>
          </div>
        </div>

        {loading ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-faint)' }}>
            Loading...
          </div>
        ) : !data ? (
          <div style={{ padding: 32, textAlign: 'center', color: 'var(--danger)' }}>
            Failed to load wallet data.
          </div>
        ) : (
          <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 24 }}>

            {/* Composite score */}
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>
                COMPOSITE SCORE
              </div>
              <ScoreBar score={data.composite_score} />
            </div>

            {/* Flags */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {data.arb_flag && (
                <span style={{ background: 'rgba(255,77,109,0.12)', color: 'var(--danger)', border: '1px solid rgba(255,77,109,0.3)', borderRadius: 4, padding: '2px 8px', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                  ARB DETECTED
                </span>
              )}
              {data.rotation_confidence > 0 && (
                <span style={{ background: 'rgba(245,166,35,0.12)', color: 'var(--warn)', border: '1px solid rgba(245,166,35,0.3)', borderRadius: 4, padding: '2px 8px', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                  ROTATED WALLET
                </span>
              )}
              {data.is_new && (
                <span style={{ background: 'var(--accent-dim)', color: 'var(--accent)', border: '1px solid rgba(0,229,160,0.3)', borderRadius: 4, padding: '2px 8px', fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                  NEW
                </span>
              )}
            </div>

            {/* Copy-trade viability */}
            {data.copy_trade_viability !== 'VIABLE' && (
              <div style={{
                background: data.copy_trade_viability === 'LIKELY_BOT'
                  ? 'rgba(255,77,109,0.06)' : 'rgba(245,166,35,0.06)',
                border: `1px solid ${data.copy_trade_viability === 'LIKELY_BOT'
                  ? 'rgba(255,77,109,0.25)' : 'rgba(245,166,35,0.25)'}`,
                borderRadius: 'var(--radius)',
                padding: 14,
              }}>
                <div style={{
                  fontSize: 11,
                  fontFamily: 'var(--font-mono)',
                  color: data.copy_trade_viability === 'LIKELY_BOT' ? 'var(--danger)' : 'var(--warn)',
                  marginBottom: 8,
                }}>
                  {data.copy_trade_viability === 'LIKELY_BOT' ? 'LIKELY BOT — SKIP AI REVIEW' : 'SUSPECT — REVIEW CAREFULLY'}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {(data.viability_reasons || []).map((r, i) => (
                    <div key={i} style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'flex-start', gap: 6 }}>
                      <span style={{ color: data.copy_trade_viability === 'LIKELY_BOT' ? 'var(--danger)' : 'var(--warn)', flexShrink: 0 }}>›</span>
                      {r}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Key stats */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
              <StatPill label="Win Rate" value={pct(data.win_rate)} color={data.win_rate >= 0.6 ? 'var(--accent)' : 'var(--warn)'} />
              <StatPill label="ROI" value={`${(data.roi * 100).toFixed(1)}%`} color={data.roi > 0 ? 'var(--accent)' : 'var(--danger)'} />
              <StatPill label="Trades" value={data.total_trades} />
              <StatPill label="Markets" value={data.distinct_markets} />
              <StatPill label="Invested" value={`$${Math.round(data.total_invested_usdc).toLocaleString()}`} />
              <StatPill label="Early Entry" value={fmt(data.early_entry_score, 3)} color="var(--info)" />
            </div>

            {/* Recent win rate */}
            {data.win_rate_7d != null && (
              <div style={{
                background: 'var(--surface2)',
                border: `1px solid ${data.win_rate_7d >= 0.6 ? 'rgba(0,229,160,0.2)' : 'rgba(245,166,35,0.2)'}`,
                borderRadius: 'var(--radius)',
                padding: '10px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: 16,
              }}>
                <div>
                  <div style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', marginBottom: 3 }}>RECENT WIN RATE</div>
                  <div style={{
                    fontSize: 20,
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 700,
                    color: data.win_rate_7d >= 0.6 ? 'var(--accent)' : 'var(--warn)',
                  }}>
                    {pct(data.win_rate_7d)}
                  </div>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
                  {data.wins_7d} win{data.wins_7d !== 1 ? 's' : ''} / {(data.wins_7d ?? 0) + (data.losses_7d ?? 0)} resolved
                  <br />
                  <span style={{ fontSize: 10, opacity: 0.7 }}>recently closed markets</span>
                </div>
              </div>
            )}

            {/* Note */}
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
                NOTE
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <textarea
                  ref={noteRef}
                  value={note}
                  onChange={e => setNote(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) noteRef.current?.blur()
                  }}
                  placeholder="Add a note..."
                  rows={2}
                  style={{
                    flex: 1,
                    background: 'var(--surface2)',
                    border: '1px solid var(--border2)',
                    borderRadius: 'var(--radius)',
                    color: 'var(--text)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 12,
                    padding: '8px 10px',
                    resize: 'vertical',
                    outline: 'none',
                  }}
                />
                <button
                  disabled={savingNote || note === (data?.note || '')}
                  onClick={async () => {
                    setSavingNote(true)
                    setNoteError(null)
                    setNoteSaved(false)
                    try {
                      const updated = await api.setNote(wallet, note || null)
                      setData(updated)
                      setNoteSaved(true)
                      setTimeout(() => setNoteSaved(false), 2000)
                    } catch (e) {
                      setNoteError(e.message || 'Save failed')
                    } finally {
                      setSavingNote(false)
                    }
                  }}
                  style={{
                    alignSelf: 'flex-end',
                    background: noteSaved ? 'rgba(0,229,160,0.15)' : 'var(--accent-dim)',
                    border: `1px solid ${noteSaved ? 'rgba(0,229,160,0.6)' : 'rgba(0,229,160,0.3)'}`,
                    color: 'var(--accent)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11,
                    padding: '6px 12px',
                    cursor: savingNote || note === (data?.note || '') ? 'not-allowed' : 'pointer',
                    opacity: savingNote || note === (data?.note || '') ? 0.4 : 1,
                  }}
                >
                  {savingNote ? '...' : noteSaved ? 'SAVED ✓' : 'SAVE'}
                </button>
              </div>
              {noteError && (
                <div style={{ fontSize: 11, color: 'var(--danger)', fontFamily: 'var(--font-mono)', marginTop: 4 }}>
                  Error: {noteError}
                </div>
              )}
            </div>

            {/* lb-api verified P&L */}
            {data.pnl_all != null && (
              <div style={{ background: 'var(--surface2)', border: '1px solid var(--border2)', borderRadius: 'var(--radius)', padding: 14 }}>
                <div style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', marginBottom: 10 }}>
                  VERIFIED P&L (POLYMARKET)
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 8 }}>
                  {[
                    { label: 'Lifetime', value: data.pnl_all },
                    { label: 'Last 30d', value: data.pnl_30d },
                    { label: 'Last 7d',  value: data.pnl_7d  },
                  ].map(({ label, value }) => (
                    <div key={label} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                      <span style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>{label}</span>
                      <span style={{
                        fontSize: 13,
                        fontFamily: 'var(--font-mono)',
                        color: value == null ? 'var(--text-faint)' : value >= 0 ? 'var(--accent)' : 'var(--danger)',
                      }}>
                        {value == null ? '—' : `${value >= 0 ? '+' : ''}$${Math.round(value).toLocaleString()}`}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Radar chart */}
            <div>
              <div style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>
                SIGNAL BREAKDOWN
              </div>
              <ResponsiveContainer width="100%" height={200}>
                <RadarChart data={radarData}>
                  <PolarGrid stroke="var(--border2)" />
                  <PolarAngleAxis dataKey="metric" tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'Space Mono' }} />
                  <Radar dataKey="value" stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.15} strokeWidth={1.5} />
                  <Tooltip
                    contentStyle={{ background: 'var(--surface2)', border: '1px solid var(--border2)', fontFamily: 'Space Mono', fontSize: 11 }}
                    labelStyle={{ color: 'var(--text)' }}
                    itemStyle={{ color: 'var(--accent)' }}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>

            {/* Rotation info */}
            {data.rotation_confidence > 0 && (
              <div style={{ background: 'rgba(245,166,35,0.06)', border: '1px solid rgba(245,166,35,0.2)', borderRadius: 'var(--radius)', padding: 14 }}>
                <div style={{ fontSize: 11, color: 'var(--warn)', fontFamily: 'var(--font-mono)', marginBottom: 8 }}>
                  ROTATION DETECTED — {(data.rotation_confidence * 100).toFixed(0)}% CONFIDENCE
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 6 }}>
                  Linked from:{' '}
                  <span
                    onClick={() => onSelectWallet?.(data.linked_from)}
                    style={{ fontFamily: 'var(--font-mono)', color: 'var(--warn)', cursor: onSelectWallet ? 'pointer' : 'default', textDecoration: onSelectWallet ? 'underline' : 'none' }}
                  >
                    {addr(data.linked_from)}
                  </span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {(data.rotation_signals || []).map((s, i) => (
                    <div key={i} style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ color: 'var(--warn)' }}>›</span> {s}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Arb reason */}
            {data.arb_flag && data.arb_reason && (
              <div style={{ background: 'rgba(255,77,109,0.06)', border: '1px solid rgba(255,77,109,0.2)', borderRadius: 'var(--radius)', padding: 14 }}>
                <div style={{ fontSize: 11, color: 'var(--danger)', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
                  ARB SIGNALS
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {data.arb_reason.split(' | ').map((r, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 6, marginBottom: 4 }}>
                      <span style={{ color: 'var(--danger)' }}>›</span> {r}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* AI Review */}
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <div style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
                  AI REVIEW
                </div>
                {!data.ai_review && !data.ai_review_pending && (
                  <button
                    disabled={triggeringReview}
                    onClick={async () => {
                      setTriggeringReview(true)
                      try {
                        const updated = await api.triggerReview(wallet)
                        setData(updated)
                      } catch (e) {
                        alert(e.message || 'Failed to trigger review')
                      } finally {
                        setTriggeringReview(false)
                      }
                    }}
                    style={{
                      background: 'var(--accent-dim)',
                      border: '1px solid rgba(0,229,160,0.3)',
                      color: 'var(--accent)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 11,
                      padding: '5px 12px',
                      cursor: triggeringReview ? 'not-allowed' : 'pointer',
                      opacity: triggeringReview ? 0.5 : 1,
                    }}
                  >
                    {triggeringReview ? '...' : 'GENERATE'}
                  </button>
                )}
                {data.ai_review && !data.ai_review_pending && (
                  <button
                    onClick={async () => {
                      setTriggeringReview(true)
                      try {
                        const updated = await api.triggerReview(wallet)
                        setData(updated)
                      } catch (e) {
                        alert(e.message || 'Failed to trigger review')
                      } finally {
                        setTriggeringReview(false)
                      }
                    }}
                    disabled={triggeringReview}
                    style={{
                      background: 'transparent',
                      border: '1px solid var(--border2)',
                      color: 'var(--text-faint)',
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10,
                      padding: '4px 10px',
                      cursor: triggeringReview ? 'not-allowed' : 'pointer',
                      opacity: triggeringReview ? 0.4 : 1,
                    }}
                  >
                    REFRESH
                  </button>
                )}
              </div>

              {data.ai_review_pending && (
                <div style={{
                  background: 'var(--surface2)', border: '1px solid var(--border2)',
                  borderRadius: 'var(--radius)', padding: '14px 16px',
                  color: 'var(--text-faint)', fontSize: 12, fontFamily: 'var(--font-mono)',
                  display: 'flex', alignItems: 'center', gap: 8,
                }}>
                  <span style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }}>⟳</span>
                  Analysing wallet... this may take 15–30 seconds.
                </div>
              )}

              {!data.ai_review_pending && !data.ai_review && data.ai_review_error && (
                <div style={{
                  background: 'rgba(255,77,109,0.06)', border: '1px solid rgba(255,77,109,0.25)',
                  borderRadius: 'var(--radius)', padding: '12px 14px',
                  color: 'var(--danger)', fontSize: 11, fontFamily: 'var(--font-mono)',
                }}>
                  Review failed: {data.ai_review_error}
                </div>
              )}

              {data.ai_review && !data.ai_review_pending && (() => {
                const r = data.ai_review
                const recColor = RECOMMENDATION_COLORS[r.recommendation] || 'var(--text-muted)'
                return (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    {/* Recommendation banner */}
                    <div style={{
                      background: `${recColor}14`,
                      border: `1px solid ${recColor}44`,
                      borderRadius: 'var(--radius)',
                      padding: '10px 14px',
                      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    }}>
                      <div>
                        <span style={{ fontSize: 13, fontFamily: 'var(--font-mono)', color: recColor, fontWeight: 600 }}>
                          {r.recommendation}
                        </span>
                        <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-faint)', marginLeft: 8 }}>
                          {r.suitability_score}/10
                        </span>
                      </div>
                      {data.ai_review_at && (
                        <span style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
                          {new Date(data.ai_review_at).toLocaleDateString()}
                        </span>
                      )}
                    </div>

                    {/* Summary */}
                    {r.summary && (
                      <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
                        {r.summary}
                      </div>
                    )}

                    {/* Recommendation reason */}
                    {r.recommendation_reason && (
                      <div style={{ fontSize: 12, color: 'var(--text)', lineHeight: 1.6, fontStyle: 'italic' }}>
                        {r.recommendation_reason}
                      </div>
                    )}

                    {/* Sections */}
                    {[
                      { label: 'STRATEGY',               value: r.strategy },
                      { label: 'MARKET PREFERENCES',     value: r.market_preferences },
                      { label: 'ARB ASSESSMENT',         value: r.arbitrage_assessment },
                      { label: 'WALLET AGE RISK',        value: r.wallet_age_risk },
                      { label: 'COPY TRADING VIABILITY', value: r.copy_trading_viability },
                    ].filter(s => s.value).map(({ label, value }) => (
                      <div key={label}>
                        <div style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', marginBottom: 4 }}>
                          {label}
                        </div>
                        <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6 }}>
                          {value}
                        </div>
                      </div>
                    ))}

                    {/* Green flags */}
                    {r.green_flags?.length > 0 && (
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--accent)', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
                          GREEN FLAGS
                        </div>
                        {r.green_flags.map((f, i) => (
                          <div key={i} style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', gap: 6, marginBottom: 3 }}>
                            <span style={{ color: 'var(--accent)' }}>✓</span> {f}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Red flags */}
                    {r.red_flags?.length > 0 && (
                      <div>
                        <div style={{ fontSize: 10, color: 'var(--danger)', fontFamily: 'var(--font-mono)', marginBottom: 6 }}>
                          RED FLAGS
                        </div>
                        {r.red_flags.map((f, i) => (
                          <div key={i} style={{ fontSize: 12, color: 'var(--text-muted)', display: 'flex', gap: 6, marginBottom: 3 }}>
                            <span style={{ color: 'var(--danger)' }}>✗</span> {f}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })()}
            </div>

            {/* Timeline */}
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 16 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-faint)' }}>
                <div>
                  <div style={{ marginBottom: 2 }}>FIRST TRADE</div>
                  <div style={{ color: 'var(--text-muted)' }}>{data.first_trade_at ? new Date(data.first_trade_at).toLocaleDateString() : '—'}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ marginBottom: 2 }}>LAST TRADE</div>
                  <div style={{ color: 'var(--text-muted)' }}>{data.last_trade_at ? new Date(data.last_trade_at).toLocaleDateString() : '—'}</div>
                </div>
              </div>
            </div>

            {/* Polymarket link */}
            <a
              href={`https://polymarket.com/profile/${wallet}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'block',
                textAlign: 'center',
                background: 'var(--accent-dim)',
                border: '1px solid rgba(0,229,160,0.25)',
                borderRadius: 'var(--radius)',
                padding: '10px',
                color: 'var(--accent)',
                fontFamily: 'var(--font-mono)',
                fontSize: 12,
                textDecoration: 'none',
              }}
            >
              View on Polymarket ↗
            </a>
          </div>
        )}
      </div>

      <style>{`
        @keyframes fadeIn { from { opacity:0 } to { opacity:1 } }
        @keyframes slideIn { from { transform:translateX(40px); opacity:0 } to { transform:translateX(0); opacity:1 } }
        @keyframes spin { from { transform:rotate(0deg) } to { transform:rotate(360deg) } }
      `}</style>
    </>
  )
}

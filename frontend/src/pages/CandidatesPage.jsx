import { useState, useEffect, useCallback } from 'react'
import { api } from '../lib/api'
import { ScoreBar } from '../components/ScoreBar'
import { WalletDetail } from '../components/WalletDetail'

const addr = (w) => w ? `${w.slice(0, 6)}...${w.slice(-4)}` : '—'
const pct = (n) => n == null ? '—' : `${(n * 100).toFixed(1)}%`
const roi = (n) => n == null ? '—' : `${n >= 0 ? '+' : ''}${(n * 100).toFixed(1)}%`

const SORT_KEYS = {
  SCORE: 'composite_score',
  'WIN RATE': 'win_rate',
  '7D WIN': 'win_rate_7d',
  ROI: 'roi',
  'EARLY ENTRY': 'early_entry_score',
}

export function CandidatesPage() {
  const [candidates, setCandidates] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)
  const [filters, setFilters] = useState({
    min_score: 0,
    rotated_only: false,
    hide_arb: true,
    hide_bots: true,
    sort: 'composite_score',
  })

  const load = useCallback(() => {
    setLoading(true)
    const params = { min_score: filters.min_score }
    if (filters.rotated_only) params.rotated_only = true
    api.getCandidates(params)
      .then(data => {
        let rows = data
        if (filters.hide_arb) rows = rows.filter(c => !c.arb_flag)
        if (filters.hide_bots) rows = rows.filter(c => c.copy_trade_viability !== 'LIKELY_BOT')
        if (filters.sort === 'win_rate') rows.sort((a, b) => b.win_rate - a.win_rate)
        else if (filters.sort === 'win_rate_7d') rows.sort((a, b) => (b.win_rate_7d ?? -1) - (a.win_rate_7d ?? -1))
        else if (filters.sort === 'roi') rows.sort((a, b) => b.roi - a.roi)
        else if (filters.sort === 'early_entry_score') rows.sort((a, b) => b.early_entry_score - a.early_entry_score)
        else rows.sort((a, b) => b.composite_score - a.composite_score)
        setCandidates(rows)
      })
      .catch(() => setCandidates([]))
      .finally(() => setLoading(false))
  }, [filters])

  useEffect(() => { load() }, [load])

  const setSort = (key) => setFilters(f => ({ ...f, sort: key }))

  return (
    <div>
      {/* Filter bar */}
      <div style={{
        display: 'flex',
        gap: 12,
        marginBottom: 20,
        alignItems: 'center',
        flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>MIN SCORE</span>
          <input
            type="number"
            min={0}
            max={100}
            value={filters.min_score}
            onChange={e => setFilters(f => ({ ...f, min_score: Number(e.target.value) }))}
            style={{ width: 64 }}
          />
        </div>

        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          <input
            type="checkbox"
            checked={filters.rotated_only}
            onChange={e => setFilters(f => ({ ...f, rotated_only: e.target.checked }))}
            style={{ accentColor: 'var(--warn)', width: 13, height: 13 }}
          />
          ROTATED ONLY
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          <input
            type="checkbox"
            checked={filters.hide_arb}
            onChange={e => setFilters(f => ({ ...f, hide_arb: e.target.checked }))}
            style={{ accentColor: 'var(--accent)', width: 13, height: 13 }}
          />
          HIDE ARB
        </label>

        <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)' }}>
          <input
            type="checkbox"
            checked={filters.hide_bots}
            onChange={e => setFilters(f => ({ ...f, hide_bots: e.target.checked }))}
            style={{ accentColor: 'var(--accent)', width: 13, height: 13 }}
          />
          HIDE BOTS
        </label>

        <div style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
          {candidates.length} candidates
        </div>
      </div>

      {/* Table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {['WALLET', 'SCORE', 'WIN RATE', '7D WIN', 'ROI', 'TRADES', 'MARKETS', 'EARLY ENTRY', 'FLAGS'].map(h => {
                const sortKey = SORT_KEYS[h]
                const active = sortKey && filters.sort === sortKey
                return (
                  <th
                    key={h}
                    onClick={sortKey ? () => setSort(sortKey) : undefined}
                    style={{
                      padding: '8px 12px',
                      textAlign: 'left',
                      fontSize: 10,
                      fontFamily: 'var(--font-mono)',
                      color: active ? 'var(--accent)' : 'var(--text-faint)',
                      letterSpacing: '0.08em',
                      borderBottom: active ? '1px solid var(--accent)' : '1px solid var(--border)',
                      whiteSpace: 'nowrap',
                      cursor: sortKey ? 'pointer' : 'default',
                      userSelect: 'none',
                    }}
                  >
                    {h}{active ? ' ▼' : ''}
                  </th>
                )
              })}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={9} style={{ padding: 32, textAlign: 'center', color: 'var(--text-faint)' }}>Scanning...</td></tr>
            ) : candidates.length === 0 ? (
              <tr><td colSpan={9} style={{ padding: 32, textAlign: 'center', color: 'var(--text-faint)' }}>
                No candidates yet. Trigger a scan or wait for the scheduled scan.
              </td></tr>
            ) : candidates.map(c => (
              <tr
                key={c.wallet}
                onClick={() => setSelected(c.wallet)}
                style={{
                  cursor: 'pointer',
                  borderBottom: '1px solid var(--border)',
                  transition: 'background 0.1s',
                  background: selected === c.wallet ? 'var(--accent-dim)' : 'transparent',
                  opacity: c.copy_trade_viability === 'LIKELY_BOT' ? 0.45 : 1,
                }}
                onMouseEnter={e => { if (selected !== c.wallet) e.currentTarget.style.background = 'var(--surface)' }}
                onMouseLeave={e => { if (selected !== c.wallet) e.currentTarget.style.background = 'transparent' }}
              >
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent)' }}>
                          {addr(c.wallet)}
                        </span>
                        {c.is_new && (
                          <span style={{
                            fontSize: 9,
                            fontFamily: 'var(--font-mono)',
                            background: 'var(--accent-dim)',
                            color: 'var(--accent)',
                            border: '1px solid rgba(0,229,160,0.3)',
                            borderRadius: 3,
                            padding: '1px 5px',
                          }}>NEW</span>
                        )}
                      </div>
                      {c.username && (
                        <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                          {c.username}
                        </span>
                      )}
                    </div>
                    {c.note && (
                      <span style={{
                        fontSize: 11,
                        color: 'var(--warn)',
                        fontFamily: 'var(--font-mono)',
                        maxWidth: 180,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        opacity: 0.85,
                      }} title={c.note}>
                        {c.note}
                      </span>
                    )}
                  </div>
                </td>
                <td style={{ padding: '10px 12px', minWidth: 140 }}>
                  <ScoreBar score={c.composite_score} size="sm" />
                </td>
                <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: c.win_rate >= 0.6 ? 'var(--accent)' : 'var(--text)' }}>
                  {pct(c.win_rate)}
                </td>
                <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                  {c.win_rate_7d != null ? (
                    <span style={{ color: c.win_rate_7d >= 0.6 ? 'var(--accent)' : 'var(--warn)' }}>
                      {pct(c.win_rate_7d)}
                      <span style={{ fontSize: 10, color: 'var(--text-faint)', marginLeft: 4 }}>
                        ({(c.wins_7d ?? 0) + (c.losses_7d ?? 0)}r)
                      </span>
                    </span>
                  ) : <span style={{ color: 'var(--text-faint)' }}>—</span>}
                </td>
                <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: c.roi >= 0 ? 'var(--accent)' : 'var(--danger)' }}>
                  {roi(c.roi)}
                </td>
                <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
                  {c.total_trades}
                </td>
                <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)' }}>
                  {c.distinct_markets}
                </td>
                <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--info)' }}>
                  {c.early_entry_score?.toFixed(3)}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {c.arb_flag && <Flag color="var(--danger)" label="ARB" />}
                    {c.rotation_confidence > 0 && <Flag color="var(--warn)" label="ROT" />}
                    {c.copy_trade_viability === 'LIKELY_BOT' && <Flag color="var(--danger)" label="BOT" />}
                    {c.copy_trade_viability === 'SUSPECT' && <Flag color="var(--warn)" label="SUSPECT" />}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <WalletDetail
        wallet={selected}
        onClose={() => setSelected(null)}
        onBlacklisted={(w) => setCandidates(cs => cs.filter(c => c.wallet !== w))}
        onSelectWallet={(w) => setSelected(w)}
      />
    </div>
  )
}

function Flag({ color, label }) {
  return (
    <span style={{
      fontSize: 9,
      fontFamily: 'var(--font-mono)',
      color,
      border: `1px solid ${color}44`,
      borderRadius: 3,
      padding: '1px 5px',
      background: `${color}11`,
    }}>{label}</span>
  )
}

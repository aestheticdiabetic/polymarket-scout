import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import { WalletDetail } from '../components/WalletDetail'

const addr = (w) => w ? `${w.slice(0, 6)}...${w.slice(-4)}` : '—'

export function RotationsPage() {
  const [rotations, setRotations] = useState([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState(null)

  useEffect(() => {
    api.getRotations()
      .then(data => setRotations(data.sort((a, b) => b.confidence - a.confidence)))
      .catch(() => setRotations([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div style={{ marginBottom: 20 }}>
        <p style={{ color: 'var(--text-muted)', fontSize: 13, lineHeight: 1.6 }}>
          Wallets flagged as likely rotations — the same trader using a new address to avoid being copy-traded.
          Confidence is based on shared funding source, bet-sizing patterns, market selection overlap, and activity timing.
        </p>
      </div>

      {loading ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-faint)' }}>Loading...</div>
      ) : rotations.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
          No rotation links detected yet.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {rotations.map((r, i) => (
            <div
              key={i}
              style={{
                background: 'var(--surface)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-lg)',
                padding: 16,
                display: 'grid',
                gridTemplateColumns: '1fr auto 1fr auto',
                alignItems: 'center',
                gap: 16,
              }}
            >
              {/* Old wallet */}
              <div>
                <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-faint)', marginBottom: 4 }}>OLD WALLET</div>
                <button
                  onClick={() => setSelected(r.old_wallet)}
                  style={{
                    background: 'none',
                    color: 'var(--text-muted)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 13,
                    borderRadius: 'var(--radius)',
                    padding: '2px 6px',
                    border: '1px solid var(--border)',
                    textDecoration: 'none',
                  }}
                >{addr(r.old_wallet)}</button>
              </div>

              {/* Arrow */}
              <div style={{ textAlign: 'center' }}>
                <div style={{ color: 'var(--warn)', fontSize: 18 }}>→</div>
                <div style={{
                  fontSize: 10, fontFamily: 'var(--font-mono)',
                  color: r.confidence >= 0.85 ? 'var(--accent)' : r.confidence >= 0.7 ? 'var(--warn)' : 'var(--text-faint)',
                  marginTop: 2,
                }}>
                  {(r.confidence * 100).toFixed(0)}% conf.
                </div>
              </div>

              {/* New wallet */}
              <div>
                <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-faint)', marginBottom: 4 }}>NEW WALLET</div>
                <button
                  onClick={() => setSelected(r.new_wallet)}
                  style={{
                    background: 'none',
                    color: 'var(--accent)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 13,
                    borderRadius: 'var(--radius)',
                    padding: '2px 6px',
                    border: '1px solid rgba(0,229,160,0.3)',
                  }}
                >{addr(r.new_wallet)}</button>
              </div>

              {/* Signals */}
              <div style={{ minWidth: 180 }}>
                <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-faint)', marginBottom: 4 }}>SIGNALS</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {r.signals?.map((s, si) => (
                    <div key={si} style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', gap: 5 }}>
                      <span style={{ color: 'var(--warn)' }}>›</span>
                      <span>{s}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <WalletDetail wallet={selected} onClose={() => setSelected(null)} />
    </div>
  )
}

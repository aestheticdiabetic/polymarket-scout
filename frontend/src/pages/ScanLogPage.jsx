import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import toast from 'react-hot-toast'

function dur(start, end) {
  if (!start || !end) return '—'
  const s = Math.round((new Date(end) - new Date(start)) / 1000)
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`
}

export function ScanLogPage() {
  const [log, setLog] = useState([])
  const [loading, setLoading] = useState(true)
  const [scanning, setScanning] = useState(false)
  const [rescoring, setRescoring] = useState(false)

  const load = () => {
    api.getScanLog()
      .then(data => setLog([...data].reverse()))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const triggerScan = async () => {
    setScanning(true)
    try {
      await api.triggerScan()
      toast.success('Scan started in background')
      setTimeout(load, 3000)
    } catch {
      toast.error('Failed to start scan')
    } finally {
      setScanning(false)
    }
  }

  const rescoreAll = async () => {
    if (!confirm('Re-fetch and re-score all candidates with current logic? Stale/unprofitable wallets will be evicted.')) return
    setRescoring(true)
    try {
      await api.rescoreAll()
      toast.success('Rescore started in background — candidates will update shortly')
    } catch {
      toast.error('Failed to start rescore')
    } finally {
      setRescoring(false)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          Scan history and manual trigger. Scans run automatically on the configured interval.
        </p>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            onClick={rescoreAll}
            disabled={rescoring}
            style={{
              background: 'rgba(245,166,35,0.08)',
              border: '1px solid rgba(245,166,35,0.3)',
              color: 'var(--warn)',
              padding: '8px 16px',
              fontWeight: 700,
              whiteSpace: 'nowrap',
            }}
          >
            {rescoring ? 'Starting...' : '↺ Rescore All'}
          </button>
          <button
            onClick={triggerScan}
            disabled={scanning}
            style={{
              background: 'var(--accent-dim)',
              border: '1px solid rgba(0,229,160,0.3)',
              color: 'var(--accent)',
              padding: '8px 16px',
              fontWeight: 700,
              whiteSpace: 'nowrap',
            }}
          >
            {scanning ? 'Starting...' : '▶ Run Scan Now'}
          </button>
        </div>
      </div>

      {loading ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-faint)' }}>Loading...</div>
      ) : log.length === 0 ? (
        <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-faint)', fontFamily: 'var(--font-mono)' }}>
          No scans yet.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {log.map((s, i) => (
            <div
              key={i}
              style={{
                background: 'var(--surface)',
                border: `1px solid ${s.errors?.length > 0 ? 'rgba(255,77,109,0.2)' : 'var(--border)'}`,
                borderRadius: 'var(--radius)',
                padding: '12px 16px',
                display: 'grid',
                gridTemplateColumns: '140px 1fr 1fr 1fr 1fr',
                gap: 16,
                alignItems: 'center',
              }}
            >
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-faint)' }}>
                {s.started_at ? new Date(s.started_at).toLocaleString() : '—'}
              </div>
              <Stat label="Wallets" value={s.wallets_scanned} />
              <Stat label="New candidates" value={s.new_candidates} color={s.new_candidates > 0 ? 'var(--accent)' : undefined} />
              <Stat label="Rotations" value={s.rotation_links_found} color={s.rotation_links_found > 0 ? 'var(--warn)' : undefined} />
              <Stat label="Duration" value={dur(s.started_at, s.completed_at)} />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Stat({ label, value, color }) {
  return (
    <div>
      <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-faint)' }}>{label}</div>
      <div style={{ fontSize: 14, fontFamily: 'var(--font-mono)', color: color || 'var(--text-muted)', marginTop: 2 }}>{value ?? '—'}</div>
    </div>
  )
}

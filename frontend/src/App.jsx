import { useState, useEffect } from 'react'
import { Toaster } from 'react-hot-toast'
import { CandidatesPage } from './pages/CandidatesPage'
import { RotationsPage } from './pages/RotationsPage'
import { ScanLogPage } from './pages/ScanLogPage'
import { ConfigPanel } from './components/ConfigPanel'
import { useAlertPoller } from './hooks/useAlerts'
import { api } from './lib/api'

const NAV = [
  { id: 'candidates', label: 'Candidates' },
  { id: 'rotations',  label: 'Rotations' },
  { id: 'scan',       label: 'Scan Log' },
  { id: 'config',     label: 'Config' },
]

export default function App() {
  const [tab, setTab] = useState('candidates')
  const [online, setOnline] = useState(null)
  const [candidateCount, setCandidateCount] = useState(null)
  const [pendingAlerts, setPendingAlerts] = useState(0)

  useAlertPoller()

  useEffect(() => {
    const check = async () => {
      try {
        await api.health()
        setOnline(true)
      } catch {
        setOnline(false)
      }
    }
    check()
    const id = setInterval(check, 30_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    api.getCandidates().then(d => setCandidateCount(d.length)).catch(() => {})
    const id = setInterval(() => {
      api.getCandidates().then(d => setCandidateCount(d.length)).catch(() => {})
      api.getPendingAlerts().then(d => setPendingAlerts(d.length)).catch(() => {})
    }, 20_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>

      {/* Top bar */}
      <header style={{
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg2)',
        padding: '0 24px',
        height: 52,
        display: 'flex',
        alignItems: 'center',
        gap: 24,
        flexShrink: 0,
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 180 }}>
          <div style={{
            width: 28, height: 28,
            background: 'var(--accent-dim)',
            border: '1px solid rgba(0,229,160,0.35)',
            borderRadius: 6,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 14,
          }}>⬡</div>
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, fontWeight: 700, color: 'var(--text)', letterSpacing: '-0.02em' }}>
              SCOUT
            </div>
            <div style={{ fontSize: 9, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', letterSpacing: '0.1em' }}>
              POLYMARKET
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav style={{ display: 'flex', gap: 4, flex: 1 }}>
          {NAV.map(n => (
            <button
              key={n.id}
              onClick={() => setTab(n.id)}
              style={{
                background: tab === n.id ? 'var(--accent-dim)' : 'transparent',
                border: tab === n.id ? '1px solid rgba(0,229,160,0.25)' : '1px solid transparent',
                color: tab === n.id ? 'var(--accent)' : 'var(--text-muted)',
                padding: '5px 12px',
                fontSize: 12,
                position: 'relative',
              }}
            >
              {n.label}
              {n.id === 'candidates' && candidateCount != null && (
                <span style={{
                  marginLeft: 6,
                  fontSize: 10,
                  background: 'var(--border2)',
                  color: 'var(--text-faint)',
                  borderRadius: 10,
                  padding: '0 5px',
                }}>{candidateCount}</span>
              )}
            </button>
          ))}
        </nav>

        {/* Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexShrink: 0 }}>
          {pendingAlerts > 0 && (
            <div style={{
              background: 'var(--accent-dim2)',
              border: '1px solid rgba(0,229,160,0.4)',
              borderRadius: 4,
              padding: '3px 8px',
              fontSize: 10,
              fontFamily: 'var(--font-mono)',
              color: 'var(--accent)',
              cursor: 'pointer',
            }} onClick={() => setTab('candidates')}>
              {pendingAlerts} new alert{pendingAlerts > 1 ? 's' : ''}
            </div>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-faint)' }}>
            <div style={{
              width: 6, height: 6, borderRadius: '50%',
              background: online === null ? 'var(--text-faint)' : online ? 'var(--accent)' : 'var(--danger)',
              boxShadow: online ? '0 0 5px var(--accent)' : 'none',
            }} />
            {online === null ? 'connecting' : online ? 'online' : 'offline'}
          </div>
        </div>
      </header>

      {/* Page content */}
      <main style={{ flex: 1, overflow: 'auto', padding: 24 }}>
        {tab === 'candidates' && <CandidatesPage />}
        {tab === 'rotations'  && <RotationsPage />}
        {tab === 'scan'       && <ScanLogPage />}
        {tab === 'config'     && <ConfigPanel />}
      </main>
    </div>
  )
}

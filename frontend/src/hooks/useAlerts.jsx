import { useEffect, useRef } from 'react'
import toast from 'react-hot-toast'
import { api } from '../lib/api'

export function useAlertPoller() {
  const permission = useRef(Notification.permission)

  useEffect(() => {
    if (Notification.permission === 'default') {
      Notification.requestPermission().then(p => { permission.current = p })
    }
  }, [])

  useEffect(() => {
    const poll = async () => {
      try {
        const alerts = await api.getPendingAlerts()
        for (const alert of alerts) {
          // Browser notification
          if (permission.current === 'granted') {
            new Notification('🎯 New Copy-Trade Candidate', {
              body: `Score ${alert.composite_score.toFixed(1)}/100\n${alert.reason}`,
              tag: alert.id,
            })
          }

          // In-app toast
          toast.custom(
            (t) => (
              <div style={{
                background: 'var(--surface)',
                border: '1px solid var(--accent)',
                borderRadius: '6px',
                padding: '12px 16px',
                fontFamily: 'var(--font-mono)',
                fontSize: '13px',
                maxWidth: '360px',
                opacity: t.visible ? 1 : 0,
                transition: 'opacity 0.2s',
              }}>
                <div style={{ color: 'var(--accent)', marginBottom: 4, fontWeight: 700 }}>
                  NEW CANDIDATE
                </div>
                <div style={{ color: 'var(--text)', marginBottom: 2 }}>
                  {alert.wallet.slice(0, 6)}...{alert.wallet.slice(-4)}
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: 11 }}>
                  Score {alert.composite_score.toFixed(1)} · {alert.reason}
                </div>
              </div>
            ),
            { duration: 8000 }
          )

          // Ack so it doesn't re-appear
          await api.ackAlert(alert.id)
        }
      } catch (_) {
        // backend might not be running yet
      }
    }

    poll()
    const id = setInterval(poll, 15_000)  // poll every 15s
    return () => clearInterval(id)
  }, [])
}

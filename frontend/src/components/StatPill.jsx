export function StatPill({ label, value, color }) {
  const c = color || 'var(--text-muted)'
  return (
    <div style={{
      display: 'inline-flex',
      flexDirection: 'column',
      background: 'var(--surface2)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius)',
      padding: '6px 10px',
      minWidth: 80,
    }}>
      <span style={{ fontSize: 10, color: 'var(--text-faint)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
        {label}
      </span>
      <span style={{ fontSize: 15, fontFamily: 'var(--font-mono)', color: c, fontWeight: 700, marginTop: 2 }}>
        {value}
      </span>
    </div>
  )
}

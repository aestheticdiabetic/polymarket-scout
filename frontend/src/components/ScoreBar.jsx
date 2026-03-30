export function ScoreBar({ score, size = 'md' }) {
  const pct = Math.min(100, Math.max(0, score))
  const color = pct >= 75 ? 'var(--accent)' : pct >= 50 ? 'var(--warn)' : 'var(--danger)'
  const h = size === 'sm' ? 3 : 5

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{
        flex: 1,
        height: h,
        background: 'var(--border)',
        borderRadius: 99,
        overflow: 'hidden',
      }}>
        <div style={{
          width: `${pct}%`,
          height: '100%',
          background: color,
          borderRadius: 99,
          transition: 'width 0.4s ease',
          boxShadow: `0 0 6px ${color}55`,
        }} />
      </div>
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: size === 'sm' ? 11 : 13,
        color,
        minWidth: 36,
        textAlign: 'right',
      }}>
        {pct.toFixed(1)}
      </span>
    </div>
  )
}

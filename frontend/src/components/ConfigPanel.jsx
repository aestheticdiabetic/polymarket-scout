import { useState, useEffect } from 'react'
import { api } from '../lib/api'
import toast from 'react-hot-toast'

function Slider({ label, desc, name, value, min, max, step, onChange, format }) {
  const display = format ? format(value) : value
  return (
    <div style={{ marginBottom: 20 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <div>
          <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{label}</div>
          {desc && <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 2 }}>{desc}</div>}
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent)', minWidth: 48, textAlign: 'right' }}>
          {display}
        </div>
      </div>
      <input
        type="range"
        name={name}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(name, parseFloat(e.target.value))}
        style={{ width: '100%' }}
      />
    </div>
  )
}

function NumberInput({ label, desc, name, value, min, max, step, onChange }) {
  return (
    <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
      <div>
        <div style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>{label}</div>
        {desc && <div style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 2 }}>{desc}</div>}
      </div>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={e => onChange(name, parseFloat(e.target.value))}
        style={{ width: 80, textAlign: 'right' }}
      />
    </div>
  )
}

export function ConfigPanel() {
  const [cfg, setCfg] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.getConfig().then(setCfg).catch(() => {})
  }, [])

  const update = (name, value) => {
    setCfg(prev => ({ ...prev, [name]: value }))
  }

  const save = async () => {
    setSaving(true)
    try {
      await api.updateConfig(cfg)
      toast.success('Config saved & applied')
    } catch {
      toast.error('Failed to save config')
    } finally {
      setSaving(false)
    }
  }

  if (!cfg) return (
    <div style={{ padding: 32, textAlign: 'center', color: 'var(--text-faint)' }}>
      Loading config...
    </div>
  )

  // Validate weights sum
  const weightSum = (cfg.win_rate_weight + cfg.roi_weight + cfg.early_entry_weight + cfg.consistency_weight)
  const weightsOk = Math.abs(weightSum - 1.0) < 0.01

  return (
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      <h2 style={{ fontFamily: 'var(--font-mono)', fontSize: 14, color: 'var(--text-faint)', marginBottom: 24, textTransform: 'uppercase', letterSpacing: '0.1em' }}>
        Scoring Configuration
      </h2>

      {/* Minimum thresholds */}
      <Section title="Minimum thresholds">
        <NumberInput label="Min trades" desc="Wallets with fewer trades are skipped" name="min_trades" value={cfg.min_trades} min={5} max={200} step={5} onChange={update} />
        <NumberInput label="Min markets" desc="Minimum distinct markets traded" name="min_markets" value={cfg.min_markets} min={1} max={30} step={1} onChange={update} />
        <Slider label="Min win rate" desc="Minimum resolved win rate" name="min_win_rate" value={cfg.min_win_rate} min={0.4} max={0.95} step={0.01} onChange={update} format={v => `${(v*100).toFixed(0)}%`} />
        <Slider label="Min ROI" desc="Minimum return on investment" name="min_roi" value={cfg.min_roi} min={0} max={2} step={0.01} onChange={update} format={v => `${(v*100).toFixed(0)}%`} />
      </Section>

      {/* Score weights */}
      <Section title="Score weights">
        <div style={{
          padding: '8px 12px',
          borderRadius: 'var(--radius)',
          background: weightsOk ? 'var(--accent-dim)' : 'rgba(255,77,109,0.08)',
          border: `1px solid ${weightsOk ? 'rgba(0,229,160,0.2)' : 'rgba(255,77,109,0.3)'}`,
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          color: weightsOk ? 'var(--accent)' : 'var(--danger)',
          marginBottom: 16,
        }}>
          Weights sum: {weightSum.toFixed(2)} {weightsOk ? '✓' : '— must equal 1.00'}
        </div>
        <Slider label="Win rate weight" name="win_rate_weight" value={cfg.win_rate_weight} min={0} max={1} step={0.05} onChange={update} format={v => `${(v*100).toFixed(0)}%`} />
        <Slider label="ROI weight" name="roi_weight" value={cfg.roi_weight} min={0} max={1} step={0.05} onChange={update} format={v => `${(v*100).toFixed(0)}%`} />
        <Slider label="Early entry weight" name="early_entry_weight" value={cfg.early_entry_weight} min={0} max={1} step={0.05} onChange={update} format={v => `${(v*100).toFixed(0)}%`} />
        <Slider label="Consistency weight" name="consistency_weight" value={cfg.consistency_weight} min={0} max={1} step={0.05} onChange={update} format={v => `${(v*100).toFixed(0)}%`} />
      </Section>

      {/* Arb detection */}
      <Section title="Arbitrage detection">
        <NumberInput label="Max hold time (sec)" desc="Trades exited faster than this are flagged as potential arb" name="arb_max_hold_seconds" value={cfg.arb_max_hold_seconds} min={10} max={3600} step={10} onChange={update} />
      </Section>

      {/* Rotation detection */}
      <Section title="Rotation detection">
        <Slider label="Similarity threshold" desc="Minimum combined signal score to flag a wallet as rotated" name="rotation_similarity_threshold" value={cfg.rotation_similarity_threshold} min={0.3} max={1.0} step={0.05} onChange={update} format={v => `${(v*100).toFixed(0)}%`} />
      </Section>

      <button
        onClick={save}
        disabled={saving || !weightsOk}
        style={{
          width: '100%',
          padding: '12px',
          background: weightsOk ? 'var(--accent)' : 'var(--border2)',
          color: weightsOk ? '#000' : 'var(--text-faint)',
          fontWeight: 700,
          fontSize: 13,
          marginTop: 8,
        }}
      >
        {saving ? 'Saving...' : 'Apply Changes'}
      </button>
      <div style={{ fontSize: 11, color: 'var(--text-faint)', textAlign: 'center', marginTop: 8 }}>
        Changes take effect on the next scan. No restart required.
      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div style={{
      background: 'var(--surface)',
      border: '1px solid var(--border)',
      borderRadius: 'var(--radius-lg)',
      padding: 20,
      marginBottom: 16,
    }}>
      <div style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 16 }}>
        {title}
      </div>
      {children}
    </div>
  )
}

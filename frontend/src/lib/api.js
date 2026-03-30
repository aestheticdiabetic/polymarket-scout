const BASE = '/api'

async function req(path, opts = {}) {
  const r = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  if (r.status === 204) return null
  return r.json()
}

export const api = {
  getCandidates: (params = {}) => {
    const q = new URLSearchParams(params).toString()
    return req(`/candidates${q ? '?' + q : ''}`)
  },
  getCandidate: (wallet) => req(`/candidates/${wallet}`),
  deleteCandidate: (wallet) => req(`/candidates/${wallet}`, { method: 'DELETE' }),
  getRotations: () => req('/rotations'),
  getPendingAlerts: () => req('/alerts/pending'),
  ackAlert: (id) => req(`/alerts/ack/${id}`, { method: 'POST' }),
  triggerScan: () => req('/scan', { method: 'POST' }),
  getScanLog: () => req('/scan/log'),
  getConfig: () => req('/config'),
  updateConfig: (body) => req('/config', { method: 'POST', body: JSON.stringify(body) }),
  setNote: (wallet, note) => req(`/candidates/${wallet}/note`, { method: 'PATCH', body: JSON.stringify({ note }) }),
  triggerReview: (wallet) => req(`/candidates/${wallet}/review`, { method: 'POST' }),
  rescoreViability: () => req('/rescore-viability', { method: 'POST' }),
  rescoreAll: () => req('/rescore-all', { method: 'POST' }),
  getBlacklist: () => req('/blacklist'),
  removeFromBlacklist: (wallet) => req(`/blacklist/${wallet}`, { method: 'DELETE' }),
  health: () => req('/health'),
}

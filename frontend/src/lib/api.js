// Thin wrappers around the SilentVoice backend (proxied at /api by Vite).

async function request(path, options = {}) {
  const res = await fetch(path, options)
  const isJson = res.headers.get('content-type')?.includes('application/json')
  const body = isJson ? await res.json() : null
  if (!res.ok) {
    const detail = body?.detail
    throw new Error(typeof detail === 'string' ? detail : `Request failed (${res.status})`)
  }
  return body
}

const json = (method, data) => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
})

export const api = {
  health: () => request('/api/health'),
  profile: () => request('/api/profile'),
  saveProfile: (patch) => request('/api/profile', json('PUT', patch)),
  setup: (use) => request('/api/profile/setup', json('POST', { use })),
  resetProfile: () => request('/api/profile/reset', { method: 'POST' }),
  secrets: () => request('/api/settings/secrets'),
  saveSecrets: (values) => request('/api/settings/secrets', json('PUT', values)),
  log: () => request('/api/log?limit=300'),
  addLog: (entry) => request('/api/log', json('POST', entry)),
  clearLog: () => request('/api/log', { method: 'DELETE' }),
  voice: () => request('/api/voice'),
  deleteVoice: () => request('/api/voice', { method: 'DELETE' }),
  cloneVoice: (files, name) => {
    const form = new FormData()
    form.append('name', name || 'My SilentVoice')
    for (const f of files) form.append('files', f, f.name)
    return request('/api/voice/clone', { method: 'POST', body: form })
  },
  lipread: ({ blob, mimeType, prefs, partnerText, history }) => {
    const form = new FormData()
    form.append('video', blob, `clip${mimeType.includes('mp4') ? '.mp4' : '.webm'}`)
    form.append('mode', prefs.recognition_mode || 'fast')
    form.append('phrases_only', String(Boolean(prefs.phrases_only)))
    form.append('hflip', String(Boolean(prefs.unmirror)))
    form.append('enhance', String(prefs.low_light_boost !== false))
    form.append('partner_text', partnerText || '')
    form.append('history_json', JSON.stringify(history || []))
    return request('/api/lipread', { method: 'POST', body: form })
  },
}

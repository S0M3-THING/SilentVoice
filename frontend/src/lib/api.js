// Thin wrappers around the SilentVoice backend (proxied at /api by Vite).

const OFFLINE = 'Can’t reach the SilentVoice server, so this wasn’t saved. Check that ./start.sh is still running in Terminal, then try again.'

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(path, options)
  } catch {
    throw new Error(OFFLINE) // the browser's "Failed to fetch": the server isn't answering
  }
  const isJson = res.headers.get('content-type')?.includes('application/json')
  const body = isJson ? await res.json().catch(() => null) : null
  if (!res.ok) {
    const detail = body?.detail
    if (typeof detail === 'string') throw new Error(detail)
    // No JSON from a 5xx means the dev server couldn't reach the backend at all.
    throw new Error(res.status >= 500 ? OFFLINE : `Request failed (${res.status})`)
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
  warmVoice: () => request('/api/voice/warmup', { method: 'POST' }),
  deleteVoice: () => request('/api/voice', { method: 'DELETE' }),
  setVoiceTranscript: (transcript) => request('/api/voice/transcript', json('PUT', { transcript })),
  createVoice: ({ files, transcript, consent, source }) => {
    const form = new FormData()
    for (const f of files) form.append('files', f, f.name || 'recording.webm')
    form.append('transcript', transcript || '')
    form.append('consent', String(Boolean(consent)))
    form.append('source', source)
    return request('/api/voice/reference', { method: 'POST', body: form })
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

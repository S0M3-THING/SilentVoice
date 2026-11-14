// Speaking out loud on the speaker the user picked (the Mac's speakers or a Bluetooth device).
// Order: the user's own cloned voice -> the Mac's voice (macOS `say`) -> the browser's voice.
// The first two come back as audio files, which a browser can send to any speaker.
// The browser's own speech can only use the system default speaker, so it is the last resort.

let currentAudio = null
let macVoices = null

export async function listMacVoices() {
  if (macVoices) return macVoices
  try {
    const res = await fetch('/api/voices/system')
    const data = await res.json()
    macVoices = data.available ? data.voices : []
  } catch {
    macVoices = []
  }
  return macVoices
}

export function listBrowserVoices() {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return []
  return window.speechSynthesis
    .getVoices()
    .filter((v) => v.lang?.toLowerCase().startsWith('en'))
    .sort((a, b) => a.name.localeCompare(b.name))
}

function speakBrowser(text, prefs) {
  return new Promise((resolve) => {
    if (!('speechSynthesis' in window)) return resolve(false)
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text)
    const voice = listBrowserVoices().find((v) => v.name === prefs?.voice_name)
    if (voice) u.voice = voice
    u.rate = Number(prefs?.voice_rate) || 1
    u.onend = () => resolve(true)
    u.onerror = () => resolve(false)
    window.speechSynthesis.speak(u)
  })
}

/** Play a WAV response on the chosen speaker. */
async function playOn(res, speakerId) {
  if (!res.ok) throw new Error('voice unavailable')
  const url = URL.createObjectURL(await res.blob())
  currentAudio?.pause()
  const audio = new Audio(url)
  currentAudio = audio
  if (speakerId && typeof audio.setSinkId === 'function') {
    try {
      await audio.setSinkId(speakerId)
    } catch {
      // The speaker went away (Bluetooth disconnected): play on the default one instead.
    }
  }
  await audio.play()
  return new Promise((resolve) => {
    audio.onended = () => {
      URL.revokeObjectURL(url)
      resolve(true)
    }
  })
}

const post = (url, body) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export async function speak(text, prefs, voiceStatus) {
  if (!text) return
  const speakerId = prefs?.speaker_id || ''
  if (prefs?.use_my_voice && voiceStatus?.has_voice) {
    try {
      return await playOn(await post('/api/tts', { text }), speakerId)
    } catch {
      // fall through so the user is never left silent
    }
  }
  try {
    return await playOn(
      await post('/api/tts/system', { text, voice: prefs?.voice_name || '', rate: Number(prefs?.voice_rate) || 1 }),
      speakerId,
    )
  } catch {
    return speakBrowser(text, prefs)
  }
}

export function stopSpeaking() {
  currentAudio?.pause()
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
}

// Three rising beeps to get a nurse's attention for urgent messages, on the chosen speaker.
export function playAlert(speakerId = '') {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    if (speakerId && typeof ctx.setSinkId === 'function') ctx.setSinkId(speakerId).catch(() => {})
    const t0 = ctx.currentTime + 0.05
    ;[0, 0.22, 0.44].forEach((offset, i) => {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sine'
      osc.frequency.value = 880 + i * 220
      gain.gain.setValueAtTime(0.0001, t0 + offset)
      gain.gain.exponentialRampToValueAtTime(0.35, t0 + offset + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, t0 + offset + 0.18)
      osc.connect(gain).connect(ctx.destination)
      osc.start(t0 + offset)
      osc.stop(t0 + offset + 0.2)
    })
    setTimeout(() => ctx.close(), 1200)
  } catch {
    /* audio not available */
  }
}

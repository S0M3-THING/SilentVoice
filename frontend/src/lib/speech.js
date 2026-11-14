// Speaking out loud: the user's own cloned voice when available, system voice otherwise.

let currentAudio = null

export function listSystemVoices() {
  if (typeof window === 'undefined' || !('speechSynthesis' in window)) return []
  return window.speechSynthesis
    .getVoices()
    .filter((v) => v.lang?.toLowerCase().startsWith('en'))
    .sort((a, b) => a.name.localeCompare(b.name))
}

function speakSystem(text, prefs) {
  return new Promise((resolve) => {
    if (!('speechSynthesis' in window)) return resolve(false)
    window.speechSynthesis.cancel()
    const u = new SpeechSynthesisUtterance(text)
    const voice = listSystemVoices().find((v) => v.name === prefs?.voice_name)
    if (voice) u.voice = voice
    u.rate = Number(prefs?.voice_rate) || 1
    u.pitch = Number(prefs?.voice_pitch) || 1
    u.onend = () => resolve(true)
    u.onerror = () => resolve(false)
    window.speechSynthesis.speak(u)
  })
}

async function speakOwnVoice(text) {
  const res = await fetch('/api/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  })
  if (!res.ok) throw new Error('voice unavailable')
  const url = URL.createObjectURL(await res.blob())
  currentAudio?.pause()
  currentAudio = new Audio(url)
  await currentAudio.play()
  return new Promise((resolve) => {
    currentAudio.onended = () => {
      URL.revokeObjectURL(url)
      resolve(true)
    }
  })
}

export async function speak(text, prefs, voiceStatus) {
  if (!text) return
  if (prefs?.use_my_voice && voiceStatus?.has_voice) {
    try {
      return await speakOwnVoice(text)
    } catch {
      // fall through to the system voice so the user is never left silent
    }
  }
  return speakSystem(text, prefs)
}

export function stopSpeaking() {
  currentAudio?.pause()
  if ('speechSynthesis' in window) window.speechSynthesis.cancel()
}

// Three rising beeps to get a nurse's attention for urgent messages.
export function playAlert() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)()
    const t0 = ctx.currentTime
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
    setTimeout(() => ctx.close(), 1000)
  } catch {
    /* audio not available */
  }
}

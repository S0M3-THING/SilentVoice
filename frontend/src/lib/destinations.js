// Where a finished sentence goes. Same list for everyone; the first-run answer only picks the default.

export const canShare = typeof navigator !== 'undefined' && typeof navigator.share === 'function'

export function destinations(voiceStatus) {
  return [
    {
      id: 'loud',
      label: 'Out loud',
      hint: voiceStatus?.has_voice ? 'In your own voice' : 'Through this device’s speaker',
      action: 'Say it',
      again: 'Say it again',
    },
    {
      id: 'copy',
      label: 'Copy',
      hint: 'Paste it into any app or message',
      action: 'Copy it',
      again: 'Copy again',
    },
    {
      id: 'share',
      label: 'Share',
      hint: canShare ? 'Send it with your device’s share menu' : 'This browser can’t share, so it copies instead',
      action: 'Share it',
      again: 'Share again',
    },
    {
      id: 'show',
      label: 'On screen',
      hint: 'Large text for the person next to you',
      action: 'Show it',
      again: 'Show it again',
    },
  ]
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    return false
  }
}

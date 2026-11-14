import { useState } from 'react'

const CHOICES = [
  {
    id: 'care',
    label: 'I can’t use my voice right now',
    hint: 'Your voice isn’t working right now: after surgery, with a breathing tube, after a stroke, or with a condition that affects speech. SilentVoice speaks for you.',
    defaults: [
      'Sentences are spoken out loud, on this computer or a Bluetooth speaker',
      'Shortcuts for the nurse, pain, breathing and the bathroom',
      'It checks with you before saying anything it’s unsure of',
      'Large text you can show across the bed',
      'Your own voice, made from old recordings, whenever you’re ready',
    ],
  },
  {
    id: 'quiet',
    label: 'I can talk, but need to stay quiet',
    hint: 'Your voice works, but you shouldn’t speak out loud: a library, an open office, a train, someone asleep nearby. Or for security, when you need to share a password, PIN, account number or medical detail without anyone overhearing.',
    defaults: [
      'Sentences are shown on screen, never spoken',
      'Shortcuts for quick everyday replies',
      'Earlier lines blur so people walking past can’t read them',
      'Nothing is saved, and the screen clears after 2 minutes, so private details don’t stay on screen',
    ],
  },
]

/** First run: one question that picks sensible starting settings. */
export default function Setup({ onDone, busy }) {
  const [use, setUse] = useState('care')
  const chosen = CHOICES.find((c) => c.id === use)
  return (
    <main className="setup">
      <h1 className="setup-title">How will you use SilentVoice?</h1>
      <fieldset className="setup-choices">
        <legend className="sr-only">Choose one</legend>
        {CHOICES.map((c) => (
          <label key={c.id} className={`setup-choice ${use === c.id ? 'on' : ''}`}>
            <input type="radio" name="use" checked={use === c.id} onChange={() => setUse(c.id)} />
            <span>
              <span className="setup-label">{c.label}</span>
              <span className="setup-hint">{c.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <section className="setup-defaults" aria-label="What this sets up">
        <h2>We’ll start you with</h2>
        <ul>
          {chosen.defaults.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
        <p className="muted small">You can change any of this later in Settings.</p>
      </section>
      <button className="btn btn-primary btn-lg setup-go" disabled={busy} onClick={() => onDone(use)}>
        Continue
      </button>
    </main>
  )
}

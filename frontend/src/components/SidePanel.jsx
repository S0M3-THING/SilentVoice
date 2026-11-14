import { useState } from 'react'
import { partnerMicSupported } from '../lib/usePartnerMic.js'

const fmt = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

/** Where it goes, what the other person said, and what was said earlier. */
export default function SidePanel({
  dests,
  dest,
  onDest,
  partner,
  onPartnerTyped,
  onToggleMic,
  entries,
  blur,
  keepHistory,
  onRepeat,
}) {
  const [draft, setDraft] = useState('')
  const recent = entries.slice(-8).reverse()

  return (
    <aside className="side" aria-label="Where it goes and conversation">
      <fieldset className="dest-list">
        <legend>Goes to</legend>
        {dests.map((d) => (
          <label key={d.id} className="dest">
            <input type="radio" name="dest" checked={dest === d.id} onChange={() => onDest(d.id)} />
            <span>
              <span className="dest-label">{d.label}</span>
              <span className="dest-hint">{d.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>

      <section className="partner" aria-label="What they said">
        <div className="side-head">
          <h2>They said</h2>
          {partnerMicSupported && (
            <button className="text-btn" onClick={onToggleMic} aria-pressed={partner.micOn}>
              {partner.micOn ? (partner.listening ? 'Stop listening' : 'Starting…') : 'Listen to them'}
            </button>
          )}
        </div>
        <p className={`partner-text ${partner.text || partner.interim ? '' : 'muted'}`}>
          {partner.interim ? <span className="interim">{partner.interim}</span> : partner.text || 'Nothing yet. Their question helps SilentVoice pick the right answer.'}
        </p>
        {partner.error && <p className="hint-warn">{partner.error}</p>}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (draft.trim()) onPartnerTyped(draft.trim())
            setDraft('')
          }}
        >
          <label className="sr-only" htmlFor="partner-input">Type what they said</label>
          <input id="partner-input" className="input" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Or type what they asked" />
        </form>
      </section>

      <section className="earlier" aria-label="Earlier">
        <div className="side-head">
          <h2>Earlier</h2>
          {keepHistory ? (
            <a className="text-btn" href="/api/log/export?format=txt" download>Export</a>
          ) : (
            <span className="fine">Not saved</span>
          )}
        </div>
        {recent.length === 0 ? (
          <p className="muted small">Nothing yet.</p>
        ) : (
          <ol className="earlier-list">
            {recent.map((e) => (
              <li key={e.id}>
                <button
                  className={`earlier-item ${e.speaker === 'partner' ? 'from-them' : ''} ${blur ? 'veil' : ''}`}
                  onClick={() => e.speaker === 'user' && onRepeat(e.text)}
                  title={e.speaker === 'user' ? 'Use this again' : undefined}
                >
                  <time>{fmt(e.ts)}</time>
                  <span>{e.speaker === 'partner' ? `Them: ${e.text}` : e.text}</span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>
    </aside>
  )
}

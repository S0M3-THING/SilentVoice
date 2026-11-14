import { useState } from 'react'
import { Mic, MicOff } from 'lucide-react'
import { partnerMicSupported } from '../lib/usePartnerMic.js'

/**
 * What the other person said. It sits right above your sentence, large, because answering
 * them is the point, and their question helps SilentVoice pick the right reading.
 */
export default function PartnerPanel({ partner, onPartnerTyped, onToggleMic }) {
  const [draft, setDraft] = useState('')
  const heard = partner.interim || partner.text

  return (
    <section className={`partner-panel ${heard ? 'has-text' : ''}`} aria-label="They said">
      <div className="partner-head">
        <h2>They said</h2>
        {partnerMicSupported && (
          <button className={`btn btn-small ${partner.micOn ? 'is-on' : ''}`} onClick={onToggleMic} aria-pressed={partner.micOn}>
            {partner.micOn ? <MicOff size={18} aria-hidden="true" /> : <Mic size={18} aria-hidden="true" />}
            {partner.micOn ? (partner.listening ? 'Stop listening' : 'Starting…') : 'Listen to them'}
          </button>
        )}
      </div>
      <p className={`partner-said ${heard ? '' : 'is-empty'}`} aria-live="polite">
        {partner.interim ? <span className="interim">{partner.interim}</span> : partner.text || 'Nothing yet. Turn on listening, or type their question below.'}
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
        <input id="partner-input" className="input" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Type what they said, then press Enter" />
      </form>
    </section>
  )
}

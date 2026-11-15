/**
 * The sentence about to be said. The one loud element on the page: large serif text,
 * underlined in the colour of how sure SilentVoice is.
 */
export default function Sentence({ current, reading, error, dest, onDeliver, onPickAlt, onFallback }) {
  if (reading) {
    return (
      <section className="sentence is-empty" aria-live="polite">
        <p className="sentence-wait">Reading your lips…</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="sentence is-empty" role="alert">
        <p className="sentence-note">{error}</p>
        <div className="fallback-links">
          <button className="link" onClick={() => onFallback('spell')}>Spell it</button>
          <button className="link" onClick={() => onFallback('phrases')}>Pick a phrase</button>
          <button className="link" onClick={() => onFallback('yesno')}>Answer yes or no</button>
        </div>
      </section>
    )
  }

  if (!current) {
    return (
      <section className="sentence is-empty">
        <p className="sentence-note">
          Mouth a short sentence. It appears here, and you choose where it goes.
        </p>
        <div className="fallback-links">
          <button className="link" onClick={() => onFallback('spell')}>Spell instead</button>
          <button className="link" onClick={() => onFallback('phrases')}>Pick a phrase</button>
          <button className="link" onClick={() => onFallback('yesno')}>Answer yes or no</button>
        </div>
      </section>
    )
  }

  const ask = current.needsConfirm && !current.done
  const alts = (current.alternatives || []).filter((a) => a && a !== current.text).slice(0, 2)
  const label = current.label || 'high'

  let note = ''
  if (current.repaired) note = `AI changed words that look alike on the lips. Your lips read: “${current.raw}”.`
  else if (ask) note = 'Two readings were close, so SilentVoice is checking with you first.'
  else if (current.done) note = current.doneNote || ''
  else if (current.source === 'lipread') note = `Clear read. Press ${dest.action} when you’re ready.`

  return (
    <section className={`sentence conf-${label} ${current.urgent ? 'is-urgent' : ''}`} aria-label="Your sentence">
      {ask && <p className="ask">Is this what you said?</p>}
      <p className="sentence-text" aria-live="assertive">
        {current.text}
      </p>
      {note && <p className="sentence-note small">{note}</p>}

      <div className="sentence-actions">
        <button className="btn btn-primary btn-lg" onClick={() => onDeliver(current.text)}>
          {ask ? `Yes, ${dest.action.toLowerCase()}` : current.done ? dest.again : dest.action}
        </button>
        <button
          type="button"
          className="btn btn-lg"
          onClick={() => onFallback('spell', current.text)}
        >
          Edit
        </button>
      </div>

      {current.source === 'lipread' ? (
        <div className="guesses">
          {alts.length > 0 && <p className="guesses-label">Or did you mean</p>}
          {alts.map((a) => (
            <button key={a} className="guess" onClick={() => onPickAlt(a)}>
              {a}
            </button>
          ))}
          <div className="fallback-links">
            <button className="link" onClick={() => onFallback('spell')}>None of these: spell it</button>
            <button className="link" onClick={() => onFallback('phrases')}>Pick a phrase</button>
            <button className="link" onClick={() => onFallback('yesno')}>Answer yes or no</button>
          </div>
        </div>
      ) : (
        <div className="fallback-links">
          <button className="link" onClick={() => onFallback('spell')}>Spell something else</button>
          <button className="link" onClick={() => onFallback('phrases')}>Pick a phrase</button>
          <button className="link" onClick={() => onFallback('yesno')}>Answer yes or no</button>
        </div>
      )}
    </section>
  )
}

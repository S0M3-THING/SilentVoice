const fmt = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

/** Where the sentence goes, and what was said earlier. */
export default function SidePanel({ dests, destKey, onDest, entries, blur, keepHistory, onRepeat }) {
  const recent = entries.slice(-8).reverse()

  return (
    <aside className="side" aria-label="Where it goes and earlier messages">
      <fieldset className="dest-list">
        <legend>Goes to</legend>
        {dests.map((d) => (
          <label key={d.key} className="dest">
            <input type="radio" name="dest" checked={destKey === d.key} onChange={() => onDest(d)} />
            <span>
              <span className="dest-label">{d.label}</span>
              <span className="dest-hint">{d.hint}</span>
            </span>
          </label>
        ))}
        <p className="fine dest-note">Bluetooth speakers show up here once they’re connected to this computer.</p>
      </fieldset>

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

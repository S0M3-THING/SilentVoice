import { useEffect, useState } from 'react'

/** Full-screen text for the person next to you. Flip turns it around for someone facing you. */
export default function PartnerView({ text, onClose }) {
  const [flipped, setFlipped] = useState(false)

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="show-large" role="dialog" aria-modal="true" aria-label="Large text">
      <p className={`show-large-text ${flipped ? 'flipped' : ''}`}>{text || '…'}</p>
      <div className="show-large-tools">
        <button className="btn btn-lg" onClick={() => setFlipped((f) => !f)} aria-pressed={flipped}>
          {flipped ? 'Turn back to me' : 'Flip for the person facing me'}
        </button>
        <button className="btn btn-dark btn-lg" onClick={onClose}>
          Done
        </button>
      </div>
    </div>
  )
}

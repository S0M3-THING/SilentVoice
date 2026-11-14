import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'

export default function Modal({ title, onClose, children, wide = false, labelledBy }) {
  const ref = useRef(null)

  useEffect(() => {
    const prev = document.activeElement
    ref.current?.focus()
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      prev?.focus?.()
    }
  }, [onClose])

  return (
    <div className="scrim" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        className={`sheet ${wide ? 'sheet-wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        ref={ref}
      >
        <header className="sheet-head">
          <h2 id={labelledBy}>{title}</h2>
          <button className="icon-only" onClick={onClose} aria-label="Close">
            <X size={22} />
          </button>
        </header>
        <div className="sheet-body">{children}</div>
      </div>
    </div>
  )
}

import { useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'

// A same-route history entry closes the detail before leaving search results.
export const useOverlayHistory = (scope, onDismiss) => {
  const location = useLocation()
  const navigate = useNavigate()
  const owned = location.state?.placeOverlay === scope
  const previous = useRef(owned)
  const dismiss = useRef(onDismiss)
  dismiss.current = onDismiss
  useEffect(() => {
    if (previous.current && !owned) dismiss.current()
    previous.current = owned
  }, [owned, location.key])
  const open = () => {
    if (!owned) navigate(`${location.pathname}${location.search}${location.hash}`, { state: { ...location.state, placeOverlay: scope } })
  }
  const close = () => {
    dismiss.current()
    if (owned) navigate(-1)
  }
  return { open, close }
}

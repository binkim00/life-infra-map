import { useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
const levels = ['collapsed', 'peek', 'expanded']

// Same-route entries let browser Back reduce a result sheet without resetting search.
export const usePanelHistory = (scope, hasResults, applyLevel) => {
 const location = useLocation()
 const navigate = useNavigate()
 const initialized = useRef(false)
 const apply = useRef(applyLevel)
 apply.current = applyLevel
 const state = location.state || {}
 const owned = state.searchPanel?.scope === scope
 const current = owned ? state.searchPanel.level : 'collapsed'
 const push = (level) => navigate(`${location.pathname}${location.search}${location.hash}`, { state: { ...state, searchPanel: { scope, level } } })
 useEffect(() => {
   if (!hasResults) { initialized.current = false; return }
   if (!initialized.current) {
     initialized.current = true
     if (!owned) { push('peek'); push('expanded'); return }
   }
   if (!state.placeOverlay) apply.current(current)
   // History changes alone drive the presentation; application does not create entries.
   // eslint-disable-next-line react-hooks/exhaustive-deps
 }, [hasResults, location.key])
 return (level) => {
   if (!hasResults) { apply.current(level); return }
   const target = levels.indexOf(level)
   const from = levels.indexOf(current)
   if (target < from) navigate(target - from)
   else for (let index = from + 1; index <= target; index += 1) push(levels[index])
   if (target === from) apply.current(level)
 }
}

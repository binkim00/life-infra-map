const RouteMascot = ({
  activeMascotState,
  mascotImageStyle,
  runPosition,
  fetchPhase,
  fetchedMarkerLabel,
  isMarkerChoiceMenuOpen,
  isSearchLoading,
  isLoggedIn,
  onMascotClick,
}) => {
  const classNames = [
    'route-mascot',
    `mascot-${activeMascotState.key}`,
    isLoggedIn ? 'is-tier-mascot' : '',
    fetchPhase === 'fetching' ? 'is-fetching' : '',
    fetchPhase === 'carrying' ? 'is-carrying' : '',
    isSearchLoading && !fetchPhase ? 'is-search-loading' : '',
    isMarkerChoiceMenuOpen ? 'is-choice-menu-open' : '',
  ].filter(Boolean).join(' ')

  return (
    <aside
      className={classNames}
      style={{
        ...mascotImageStyle,
        '--mascot-run-x': runPosition.x,
        '--mascot-run-y': runPosition.y,
        '--mascot-run-mid-x': runPosition.midX,
        '--mascot-run-mid-y': runPosition.midY,
        '--mascot-run-near-x': runPosition.nearX,
        '--mascot-run-near-y': runPosition.nearY,
      }}
      aria-live="polite"
    >
      <div className="mascot-speech">{activeMascotState.message}</div>
      <div
        className="mascot-dog"
        aria-hidden="true"
        onClick={(event) => {
          event.stopPropagation()
          onMascotClick()
        }}
      >
        <span className="mascot-ear left" />
        <span className="mascot-ear right" />
        <span className="mascot-head">
          <span className="mascot-eye left" />
          <span className="mascot-eye right" />
          <span className="mascot-mouth" />
        </span>
        <span className="mascot-body">
          <span className="mascot-paw left" />
          <span className="mascot-paw right" />
        </span>
        <span className="mascot-collar">
          <span className="mascot-pendant" />
        </span>
        <span className="mascot-tail" />
        <span className="mascot-fetch-bone">{fetchedMarkerLabel}</span>
        {activeMascotState.prop ? (
          <span className="mascot-prop">{activeMascotState.prop}</span>
        ) : null}
      </div>
    </aside>
  )
}

export default RouteMascot

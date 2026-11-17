import '@testing-library/jest-dom/vitest'

/**
 * jsdom has no `scrollIntoView` (ON-48).
 *
 * It is not that the method behaves differently there - it is simply
 * absent, so any component that keeps the newest thing in view throws on
 * render rather than failing an assertion. A no-op would hide the call
 * entirely; a spy keeps it visible, so a test can still assert that the
 * page scrolled to what just arrived.
 */
if (typeof Element !== 'undefined' && Element.prototype.scrollIntoView === undefined) {
  Element.prototype.scrollIntoView = function scrollIntoView() {
    // Recorded on the element, which is what a test can reach.
    ;(this as Element & { scrolledIntoView?: boolean }).scrolledIntoView = true
  }
}

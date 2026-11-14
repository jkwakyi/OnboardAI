/**
 * Where the login token is kept (ON-38).
 *
 * Two things matter here and neither is "does setItem work". The first is
 * that the token survives a refresh, which is TD-18's complaint and the
 * reason this module exists. The second is that every access survives
 * storage being unavailable — a private window, blocked site data, a full
 * quota — because a login form that throws because storage is disabled is
 * worse than one that signs you out on refresh.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import { TOKEN_KEY, clearStoredToken, readStoredToken, storeToken } from './storage'

afterEach(() => {
  window.sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('keeping a token', () => {
  it('reads back what was stored', () => {
    storeToken('a-token')

    expect(readStoredToken()).toBe('a-token')
  })

  it('is nothing before anything is stored', () => {
    expect(readStoredToken()).toBeNull()
  })

  it('is nothing after being cleared', () => {
    storeToken('a-token')

    clearStoredToken()

    expect(readStoredToken()).toBeNull()
  })

  it('replaces an older token rather than keeping both', () => {
    storeToken('first')
    storeToken('second')

    expect(readStoredToken()).toBe('second')
  })

  it('is in sessionStorage, not localStorage', () => {
    // The decision in TD-24. localStorage would survive closing the
    // browser on a shared machine; sessionStorage dies with the tab, which
    // is the narrowest window that still fixes TD-18.
    storeToken('a-token')

    expect(window.sessionStorage.getItem(TOKEN_KEY)).toBe('a-token')
    expect(window.localStorage.getItem(TOKEN_KEY)).toBeNull()
  })
})

describe('when storage is not available', () => {
  // Spied on Storage.prototype, not on window.sessionStorage. jsdom's
  // sessionStorage is a Proxy, and defining an own property on the
  // instance does not shadow the prototype method - so the spy attached
  // and intercepted nothing, and all three of these tests passed whether
  // or not the try/catch they exist for was there at all. The fault
  // injection pass is what noticed.
  function makeStorageThrow(method: 'getItem' | 'setItem' | 'removeItem') {
    vi.spyOn(Storage.prototype, method).mockImplementation(() => {
      throw new DOMException('The operation is insecure.', 'SecurityError')
    })
  }

  it('the spy actually intercepts', () => {
    // Guards the fix above. Without this, a future change to jsdom or to
    // vitest could quietly make the three tests below vacuous again, and
    // nothing would say so.
    makeStorageThrow('getItem')

    expect(() => window.sessionStorage.getItem('anything')).toThrow()
  })

  it('reads as nothing rather than throwing', () => {
    makeStorageThrow('getItem')

    expect(readStoredToken()).toBeNull()
  })

  it('stores without throwing', () => {
    // Signing in still worked; it just will not survive a refresh.
    makeStorageThrow('setItem')

    expect(() => storeToken('a-token')).not.toThrow()
  })

  it('clears without throwing', () => {
    makeStorageThrow('removeItem')

    expect(() => clearStoredToken()).not.toThrow()
  })
})

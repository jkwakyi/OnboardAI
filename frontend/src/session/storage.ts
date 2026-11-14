/**
 * Where the login token is kept (ON-38).
 *
 * `sessionStorage`, which was a decision between three bad options and is
 * recorded as TD-24.
 *
 * In memory only was what ON-65 shipped, and TD-18 is the complaint about
 * it: a refresh signs you out, which during a demo means losing your place
 * every time somebody reloads. `localStorage` survives a refresh and also
 * survives closing the browser, on a shared machine, for as long as the
 * token lasts. `sessionStorage` survives the refresh and dies with the tab,
 * which is the narrowest window that fixes the actual complaint.
 *
 * The textbook answer is an httpOnly cookie the browser never exposes to
 * JavaScript. That needs the backend to set cookies and brings CSRF into
 * scope, and the contracts say the API Client "sends requests with the
 * login token", which reads as a header rather than a cookie. So: a header,
 * a token this code can read, and an honest note that script running on
 * this page can read it too.
 *
 * Every access is wrapped. A private window, blocked site data, or a
 * storage quota all make these throw rather than return nothing, and a
 * login form that explodes because storage is disabled is worse than one
 * that signs you out on refresh.
 */

export const TOKEN_KEY = 'onboardai.token'

export function readStoredToken(): string | null {
  try {
    return window.sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function storeToken(token: string): void {
  try {
    window.sessionStorage.setItem(TOKEN_KEY, token)
  } catch {
    // Signing in still worked; it just will not survive a refresh. Saying
    // nothing is right here: there is nothing the person can do about it,
    // and the session in memory is already good.
  }
}

export function clearStoredToken(): void {
  try {
    window.sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // Nothing to do. The in-memory session is cleared either way, which is
    // what signing out means to the page in front of them.
  }
}

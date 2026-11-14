"""Faults for the Login Page and API Client (ON-38).

The frontend, so the tests are vitest rather than pytest — the harness runs
whatever `TESTS` names, and a non-zero exit is a non-zero exit.

Two of these are worth singling out. "the token is kept in localStorage"
and "no CORS origins are configured" are both changes somebody would make
for a good reason: the first makes a demo less annoying, the second makes a
teammate's dev server work. Each gives away more than it looks, so each has
a test that says no.
"""

TESTS = "src"
RUNNER = "vitest"
ROOT = "frontend"

CLIENT = "src/api/client.ts"
ERRORS = "src/api/errors.ts"
TOKEN = "src/session/token.ts"
STORAGE = "src/session/storage.ts"
CONTEXT = "src/session/SessionContext.tsx"
LOGIN = "src/shell/LoginPage.tsx"

FAULTS = [
    # --- the token reaches the backend, and only a good one counts ---
    (
        "the login token is never sent",
        CLIENT,
        "      headers.Authorization = `Bearer ${token}`",
        "      void token",
    ),
    (
        "a 401 does not sign anybody out",
        CLIENT,
        "      onUnauthorised?.()",
        "      void onUnauthorised",
    ),
    (
        "a 403 signs somebody out as well",
        CLIENT,
        "    if (response.status === 401) {",
        "    if (response.status === 401 || response.status === 403) {",
    ),
    (
        "a content type is forced onto a file upload",
        CLIENT,
        "    if (body !== undefined) {",
        "    if (true) {",
    ),
    (
        "an aborted request is reported as a network failure",
        CLIENT,
        "      if (failure instanceof DOMException && failure.name === 'AbortError') throw failure",
        "      // the abort check was here",
    ),
    (
        "a validation list is shown to the employee as the error",
        ERRORS,
        "  return typeof detail === 'string' && detail.trim() !== '' ? detail : null",
        "  return detail === undefined ? null : String(detail)",
    ),
    # --- a token that cannot be trusted is not a session ---
    (
        "an expired token is treated as a live one",
        TOKEN,
        "  if (expiresAt.getTime() <= Date.now()) return null",
        "  void expiresAt",
    ),
    (
        "a role this frontend does not know is accepted",
        TOKEN,
        "  if (!isRole(role)) return null",
        "  if (false) return null",
    ),
    (
        "a token with the wrong number of segments is read anyway",
        TOKEN,
        "  if (segments.length !== 3) return null",
        "  if (segments.length < 2) return null",
    ),
    (
        "a non-ASCII name comes back mangled",
        TOKEN,
        "  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0))\n  return new TextDecoder().decode(bytes)",
        "  return binary",
    ),
    # --- where the token is kept ---
    (
        "the token is kept in localStorage",
        STORAGE,
        "    return window.sessionStorage.getItem(TOKEN_KEY)",
        "    return window.localStorage.getItem(TOKEN_KEY)",
    ),
    (
        "storage being unavailable throws instead of degrading",
        STORAGE,
        "  try {\n    return window.sessionStorage.getItem(TOKEN_KEY)\n  } catch {\n    return null\n  }",
        "  return window.sessionStorage.getItem(TOKEN_KEY)",
    ),
    (
        "signing out leaves the token in storage",
        CONTEXT,
        "    clearStoredToken()\n    setToken(null)",
        "    setToken(null)",
    ),
    (
        "a token that cannot be read is accepted at sign-in",
        CONTEXT,
        "    if (readToken(next) === null) return false",
        "    if (false) return false",
    ),
    (
        "an expired token left in storage starts a session",
        CONTEXT,
        "    if (readToken(candidate) === null) {",
        "    if (candidate === undefined) {",
    ),
    # --- the login page ---
    (
        "a failed sign-in says nothing",
        LOGIN,
        "        setProblem(failure.message)",
        "        void failure",
    ),
    (
        "the old problem is left on screen when trying again",
        LOGIN,
        "    setProblem(null)\n    setSigningIn(true)",
        "    setSigningIn(true)",
    ),
    (
        "a token the page cannot read looks like a successful sign-in",
        LOGIN,
        "      if (!signIn(token)) {",
        "      if (false) {",
    ),
    (
        "the password field stops hiding what is typed",
        LOGIN,
        '              type="password"',
        '              type="text"',
    ),
    (
        "the error is not announced",
        LOGIN,
        '              <p className="login__problem" role="alert">',
        '              <p className="login__problem">',
    ),
    (
        "a development bypass comes back",
        LOGIN,
        "export default function LoginPage() {",
        "export default function LoginPage() {\n"
        "  if (import.meta.env.DEV) {\n"
        "    // Continue as Employee\n"
        "  }",
    ),
]

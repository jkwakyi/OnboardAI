/**
 * Reading a login token in the browser (ON-38).
 *
 * `POST /api/auth/login` returns the token and nothing else, which is what
 * the contracts say it returns. Everything the interface needs to render —
 * the holder's name and their role — is already inside it, so this reads it
 * from there rather than asking the backend for the same facts twice.
 *
 * These claims are NOT verified
 * -----------------------------
 * A browser cannot check the signature: the key is on the server and must
 * stay there. So everything here is the token's own account of itself, good
 * enough to decide which navigation to draw and what name to show, and not
 * good enough to protect anything. Auth Check (ON-14) verifies the
 * signature and the role on every request, and that is what actually
 * enforces access. Editing the token in devtools changes the rail and
 * changes nothing the server will honour.
 *
 * The expiry is checked all the same. Not as a security measure — it is the
 * server's to enforce — but because showing somebody a signed-in page whose
 * every request will 401 is a worse experience than sending them to the
 * login form.
 */
import { ROLES, type Role } from './roles'

export interface TokenClaims {
  userId: number
  email: string
  fullName: string
  role: Role
  expiresAt: Date
}

/** Decode base64url, as JWT uses it, into text. */
function decodeSegment(segment: string): string {
  const base64 = segment.replace(/-/g, '+').replace(/_/g, '/')
  const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
  const binary = atob(padded)
  // Through bytes and TextDecoder rather than atob alone, because atob
  // yields one character per byte: a name with a non-ASCII letter in it
  // would otherwise come back mojibake, and names are the one thing this
  // function exists to read.
  const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

function isRole(value: unknown): value is Role {
  return typeof value === 'string' && (ROLES as readonly string[]).includes(value)
}

/**
 * What the token says, or null if it says nothing usable.
 *
 * Null for anything malformed, expired, or carrying a role this frontend
 * does not know. One return value for all of them, because the only thing
 * the caller can do with any of them is treat the person as signed out.
 */
export function readToken(token: string | null | undefined): TokenClaims | null {
  if (typeof token !== 'string' || token === '') return null

  const segments = token.split('.')
  if (segments.length !== 3) return null

  let claims: Record<string, unknown>
  try {
    const parsed: unknown = JSON.parse(decodeSegment(segments[1]))
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    claims = parsed as Record<string, unknown>
  } catch {
    return null
  }

  const { sub, email, name, role, exp } = claims

  if (!isRole(role)) return null
  if (typeof email !== 'string' || typeof name !== 'string') return null
  if (typeof exp !== 'number' || !Number.isFinite(exp)) return null

  const userId = Number.parseInt(String(sub), 10)
  if (!Number.isFinite(userId)) return null

  // `exp` is seconds since the epoch, as RFC 7519 has it; Date wants
  // milliseconds.
  const expiresAt = new Date(exp * 1000)
  if (expiresAt.getTime() <= Date.now()) return null

  return { userId, email, fullName: name, role, expiresAt }
}

/** True if this token is readable and has not run out. */
export function isUsable(token: string | null | undefined): boolean {
  return readToken(token) !== null
}

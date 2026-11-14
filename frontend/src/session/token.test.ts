/**
 * Reading a login token in the browser (ON-38).
 *
 * The claims are the token's own account of itself — a browser cannot
 * check the signature. So what is tested here is not "is this token
 * genuine", which is Auth Check's question, but "can this be read, and is
 * anything that cannot be read treated as signed out".
 *
 * That second half is the whole point. Every malformed shape has to come
 * back as null, because the alternative is a page that renders half a
 * session and fails somewhere further on.
 */
import { describe, expect, it } from 'vitest'

import { makeToken } from '../test/tokens'
import { isUsable, readToken } from './token'

describe('a usable token', () => {
  it('says who its holder is', () => {
    const claims = readToken(
      makeToken({
        role: 'hr_administrator',
        fullName: 'Jordan Blake',
        email: 'hr@onboardai.example',
        userId: 8,
      }),
    )

    expect(claims).not.toBeNull()
    expect(claims?.userId).toBe(8)
    expect(claims?.fullName).toBe('Jordan Blake')
    expect(claims?.email).toBe('hr@onboardai.example')
    expect(claims?.role).toBe('hr_administrator')
  })

  it('carries an expiry as a date', () => {
    const claims = readToken(makeToken({ expiresInMinutes: 60 }))

    expect(claims?.expiresAt.getTime()).toBeGreaterThan(Date.now())
    expect(claims?.expiresAt.getTime()).toBeLessThan(Date.now() + 61 * 60 * 1000)
  })

  it('reads a name that is not plain ASCII', () => {
    // Through bytes and TextDecoder rather than atob alone: atob yields one
    // character per byte, so this name would come back mojibake, and names
    // are the one thing the decoder exists to read.
    const claims = readToken(makeToken({ fullName: 'José Müller-Žukauskas' }))

    expect(claims?.fullName).toBe('José Müller-Žukauskas')
  })

  it('is usable', () => {
    expect(isUsable(makeToken())).toBe(true)
  })
})

describe('a token that cannot be used', () => {
  it('is null when it has expired', () => {
    expect(readToken(makeToken({ expiresInMinutes: -1 }))).toBeNull()
  })

  it('is null when it expires this very moment', () => {
    // Not a nicety: a token whose exp is now is one every request will
    // refuse, so treating it as live would show a signed-in page that
    // cannot do anything.
    const now = Math.floor(Date.now() / 1000)
    expect(readToken(makeToken({ claims: { exp: now } }))).toBeNull()
  })

  it.each([
    ['nothing at all', null],
    ['undefined', undefined],
    ['an empty string', ''],
    ['not a token', 'not-a-token'],
    ['two segments', 'header.payload'],
    ['four segments', 'a.b.c.d'],
    ['an unreadable payload', 'header.!!!not-base64!!!.signature'],
    ['a payload that is not JSON', 'header.bm90IGpzb24.signature'],
  ])('is null for %s', (_description, token) => {
    expect(readToken(token as string | null | undefined)).toBeNull()
    expect(isUsable(token as string | null | undefined)).toBe(false)
  })

  it('is null for a well-formed payload with the wrong number of segments', () => {
    // The earlier cases here used 'header.payload' and 'a.b.c.d', whose
    // payloads are not decodable - so they were rejected by the decode
    // rather than by the segment count, and removing the count check
    // changed nothing. This one has a payload that reads perfectly.
    const good = makeToken()
    const [header, payload] = good.split('.')

    expect(readToken(`${header}.${payload}`)).toBeNull()
    expect(readToken(`${good}.extra`)).toBeNull()
  })

  it.each([
    ['a JSON array', '[]'],
    ['a JSON string', '"a token"'],
    ['a JSON number', '42'],
    ['null', 'null'],
  ])('is null when the payload is %s', (_description, json) => {
    const payload = btoa(json).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

    expect(readToken(`header.${payload}.signature`)).toBeNull()
  })

  it.each([
    ['role', { role: undefined }],
    ['email', { email: undefined }],
    ['name', { name: undefined }],
    ['exp', { exp: undefined }],
    ['sub', { sub: undefined }],
  ])('is null when %s is missing', (_claim, claims) => {
    expect(readToken(makeToken({ claims }))).toBeNull()
  })

  it('is null for a role this frontend does not know', () => {
    // A role the system does not define is not a smaller set of
    // permissions, it is an unknown one — the same reading Auth Check
    // takes on the server.
    expect(readToken(makeToken({ claims: { role: 'superuser' } }))).toBeNull()
  })

  it.each([
    ['a string', { exp: '12345' }],
    ['not a number', { exp: 'soon' }],
    ['infinite', { exp: Number.POSITIVE_INFINITY }],
  ])('is null when exp is %s', (_description, claims) => {
    expect(readToken(makeToken({ claims }))).toBeNull()
  })

  it('is null when sub is not a number', () => {
    expect(readToken(makeToken({ claims: { sub: 'not-an-id' } }))).toBeNull()
  })
})

describe('what the token is not', () => {
  it('does not verify anything', () => {
    // Worth a test rather than only a comment, because somebody will
    // eventually wonder whether the frontend checks this. It does not, it
    // cannot, and the signature here is the literal word "signature".
    const claims = readToken(makeToken())

    expect(claims).not.toBeNull()
    expect(makeToken().split('.')[2]).toBe('signature')
  })
})

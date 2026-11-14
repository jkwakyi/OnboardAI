/**
 * The Login API, from the browser (ON-38).
 *
 * `POST /api/auth/login` — "login credentials in, login token out".
 *
 * Its own module, and its own client, because it is the one call that is
 * made with no token: everything else goes through the client the session
 * holds. Reusing that one here would mean a login request carrying a stale
 * Authorization header, which Auth Check would read before the body and
 * refuse for the wrong reason.
 */
import { createApiClient } from './client'

interface LoginResponse {
  token: string
}

/**
 * Sign in, returning the login token.
 *
 * Throws `ApiError` for a refusal — 401 for bad credentials, 422 for a
 * malformed request, 429 when the attempt limit has been reached — and
 * `NetworkError` when the backend could not be reached at all.
 */
export async function login(
  email: string,
  password: string,
  { client = createApiClient() } = {},
): Promise<string> {
  const response = await client.request<LoginResponse>('/auth/login', {
    method: 'POST',
    body: { email, password },
  })

  if (typeof response?.token !== 'string' || response.token === '') {
    // A 200 with no token in it. Not something the backend does, but the
    // alternative to checking is handing `undefined` to the session and
    // watching it fail somewhere less obvious.
    throw new Error('The server did not return a login token.')
  }

  return response.token
}

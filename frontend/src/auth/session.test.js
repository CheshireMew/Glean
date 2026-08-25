import { beforeEach, describe, expect, it } from 'vitest'

import { getAuthToken, setAuthToken } from './session'

function tokenWithExpiry(exp) {
  const payload = btoa(JSON.stringify({ exp })).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '')
  return `header.${payload}.signature`
}

describe('auth session', () => {
  beforeEach(() => localStorage.clear())

  it('returns a non-expired token', () => {
    const token = tokenWithExpiry(Math.floor(Date.now() / 1000) + 60)
    setAuthToken(token)
    expect(getAuthToken()).toBe(token)
  })

  it('removes expired and malformed tokens', () => {
    setAuthToken(tokenWithExpiry(Math.floor(Date.now() / 1000) - 60))
    expect(getAuthToken()).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()

    localStorage.setItem('token', 'not-a-jwt')
    expect(getAuthToken()).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
  })
})

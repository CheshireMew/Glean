import { beforeEach, describe, expect, it } from 'vitest'

import { getCsrfToken, setBrowserSession, clearAuthToken } from './session'

describe('auth session', () => {
  beforeEach(() => { localStorage.clear(); clearAuthToken(); })

  it('keeps only the CSRF token in memory', () => {
    setBrowserSession('csrf-test')
    expect(getCsrfToken()).toBe('csrf-test')
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it('removes old stored credentials and current CSRF state on logout', () => {
    localStorage.setItem('token', 'legacy-bearer')
    setBrowserSession('csrf-test')
    clearAuthToken()
    expect(getCsrfToken()).toBeNull()
    expect(localStorage.getItem('token')).toBeNull()
  })
})

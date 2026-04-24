import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { APIError, safeFetchJSON } from '../lib/apiClient'
import { apiPath } from '../lib/apiPaths'

export interface User {
  id: string
  email?: string | null
  emailVerified: boolean
  accountStatus: string
  createdAt?: string | null
  hasPassword?: boolean
}

interface AuthContextValue {
  user: User | null
  token: string | null
  isAuthenticated: boolean
  login: (token: string, user: User) => void
  logout: () => void
  refreshUser: () => Promise<User | null>
  updateUser: (user: User) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

const TOKEN_KEY = 'auth_token'
const USER_KEY = 'auth_user'

function parseStoredUser(): User | null {
  try {
    const stored = localStorage.getItem(USER_KEY)
    if (!stored) return null
    return JSON.parse(stored) as User
  } catch {
    return null
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => parseStoredUser())
  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_KEY))

  const persistUser = useCallback((nextUser: User | null) => {
    if (nextUser) {
      localStorage.setItem(USER_KEY, JSON.stringify(nextUser))
    } else {
      localStorage.removeItem(USER_KEY)
    }
    setUser(nextUser)
  }, [])

  const login = useCallback((newToken: string, newUser: User) => {
    localStorage.setItem(TOKEN_KEY, newToken)
    setToken(newToken)
    persistUser(newUser)
  }, [persistUser])

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setToken(null)
    setUser(null)
  }, [])

  const userRef = useRef(user)
  useEffect(() => { userRef.current = user }, [user])

  const updateUser = useCallback((nextUser: User) => {
    persistUser(nextUser)
  }, [persistUser])

  const refreshUser = useCallback(async () => {
    const currentToken = localStorage.getItem(TOKEN_KEY)
    if (!currentToken) {
      persistUser(null)
      setToken(null)
      return null
    }

    try {
      const payload = await safeFetchJSON<{ user?: User }>(apiPath('/auth/me'), {
        headers: { Authorization: `Bearer ${currentToken}` },
      })
      if (payload.user) {
        persistUser(payload.user)
        return payload.user
      }
      return null
    } catch (err) {
      // Handle 401 specifically for logout
      if ((err instanceof APIError && err.status === 401) || (err instanceof Error && err.message.includes('登录已过期'))) {
        logout()
        return null
      }
      return userRef.current
    }
  }, [logout, persistUser])

  useEffect(() => {
    if (!token) return
    void refreshUser()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token])

  const value = useMemo<AuthContextValue>(() => ({
    user,
    token,
    isAuthenticated: !!token,
    login,
    logout,
    refreshUser,
    updateUser,
  }), [login, logout, refreshUser, token, updateUser, user])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}

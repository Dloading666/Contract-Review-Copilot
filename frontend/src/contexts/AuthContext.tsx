import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'

export interface User {
  id: string
  email?: string | null
  emailVerified: boolean
  phone?: string | null
  phoneVerified: boolean
  accountStatus: string
  walletBalanceFen: number
  freeReviewRemaining: number
  mustBindPhone: boolean
  createdAt?: string | null
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
      const response = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${currentToken}` },
      })
      if (!response.ok) {
        if (response.status === 401) {
          logout()
        }
        return null
      }

      const payload = await response.json() as { user?: User }
      if (payload.user) {
        persistUser(payload.user)
        return payload.user
      }
      return null
    } catch {
      return user
    }
  }, [logout, persistUser, user])

  useEffect(() => {
    if (!token) return
    void refreshUser()
  }, [refreshUser, token])

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

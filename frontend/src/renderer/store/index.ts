import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type UserRole = 'ADMIN' | 'AUDITOR' | 'TECNICO'

interface User {
  id: number
  email: string
  nombre: string
  role: UserRole
}

// Roles con permisos de administración (incluye técnico, que tiene admin + logs)
export const ADMIN_ROLES: UserRole[] = ['ADMIN', 'TECNICO']
export const isAdminRole = (role?: UserRole) => !!role && ADMIN_ROLES.includes(role)
export const canSeeLogs = (role?: UserRole) => role === 'TECNICO' || role === 'ADMIN'

interface AuthState {
  user: User | null
  token: string | null
  login: (user: User, token: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      login: (user, token) => {
        localStorage.setItem('oag_token', token)
        localStorage.setItem('oag_user', JSON.stringify(user))
        set({ user, token })
      },
      logout: () => {
        localStorage.removeItem('oag_token')
        localStorage.removeItem('oag_user')
        set({ user: null, token: null })
      },
    }),
    {
      name: 'oag-auth',
    }
  )
)

// Notificaciones
interface Notification {
  id: string
  type: 'success' | 'error' | 'info' | 'warning'
  message: string
}

interface NotificationState {
  notifications: Notification[]
  push: (type: Notification['type'], message: string) => void
  remove: (id: string) => void
}

export const useNotificationStore = create<NotificationState>((set) => ({
  notifications: [],
  push: (type, message) => {
    const id = Math.random().toString(36).slice(2)
    set((s) => ({ notifications: [...s.notifications, { id, type, message }] }))
    setTimeout(() => {
      set((s) => ({ notifications: s.notifications.filter((n) => n.id !== id) }))
    }, 5000)
  },
  remove: (id) => set((s) => ({ notifications: s.notifications.filter((n) => n.id !== id) })),
}))

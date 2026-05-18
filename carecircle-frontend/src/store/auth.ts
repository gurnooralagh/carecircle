import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AuthState {
  access_token: string | null
  user_id: string | null
  is_authenticated: boolean
  login: (token: string, user_id: string) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      access_token: null,
      user_id: null,
      is_authenticated: false,
      login: (token: string, user_id: string) =>
        set({ access_token: token, user_id, is_authenticated: true }),
      logout: () =>
        set({ access_token: null, user_id: null, is_authenticated: false }),
    }),
    {
      name: 'carecircle-auth',
    }
  )
)

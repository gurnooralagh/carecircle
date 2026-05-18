import axios from 'axios'
import { supabase } from './supabase'

// In dev, use '' so Vite proxy handles /api/* (avoids CORS).
// In production, use the full backend URL.
const baseURL = import.meta.env.DEV ? '' : (import.meta.env.VITE_API_BASE_URL as string)

const api = axios.create({ baseURL })

// Attach current Supabase session token to every request
api.interceptors.request.use(async (config) => {
  const {
    data: { session },
  } = await supabase.auth.getSession()
  if (session?.access_token) {
    config.headers.Authorization = `Bearer ${session.access_token}`
  }
  return config
})

// On 401, clear auth and redirect to /login
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api

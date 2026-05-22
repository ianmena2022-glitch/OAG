import axios from 'axios'

// URL del backend — configurable por variable de entorno
const getBaseUrl = (): string => {
  if (typeof window !== 'undefined' && (window as any).electron) {
    // En Electron usamos la URL del proceso main
    return localStorage.getItem('oag_backend_url') || 'https://oag-backend.up.railway.app'
  }
  return import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'
}

export const api = axios.create({
  baseURL: getBaseUrl(),
  timeout: 120000, // 2 min para operaciones con IA
})

// Interceptor para auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('oag_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Interceptor para errores
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('oag_token')
      localStorage.removeItem('oag_user')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export const setBackendUrl = (url: string) => {
  localStorage.setItem('oag_backend_url', url)
  api.defaults.baseURL = url
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export const authAPI = {
  login: (email: string, password: string) =>
    api.post('/api/auth/login', { email, password }),
  me: () => api.get('/api/auth/me'),
  changePassword: (current: string, newPwd: string) =>
    api.post('/api/auth/change-password', { current_password: current, new_password: newPwd }),
}

// ── Expedientes ───────────────────────────────────────────────────────────────

export const expedientesAPI = {
  listar: () => api.get('/api/expedientes'),
  crear: (data: { nombre_distribuidor: string; cuit_distribuidor: string; anio_analisis: number }) =>
    api.post('/api/expedientes', data),
  obtener: (id: number) => api.get(`/api/expedientes/${id}`),
  actualizar: (id: number, data: any) => api.put(`/api/expedientes/${id}`, data),
  eliminar: (id: number) => api.delete(`/api/expedientes/${id}`),
  listarArchivos: (id: number) => api.get(`/api/expedientes/${id}/archivos`),
  subirArchivo: (id: number, tipo: string, file: File) => {
    const form = new FormData()
    form.append('tipo', tipo)
    form.append('file', file)
    return api.post(`/api/expedientes/${id}/archivos`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
}

// ── Pasos ─────────────────────────────────────────────────────────────────────

export const pasosAPI = {
  ejecutarPaso: (expId: number, paso: number) =>
    api.post(`/api/expedientes/${expId}/pasos/${paso}/ejecutar`),
  resultadoPaso: (expId: number, paso: number) =>
    api.get(`/api/expedientes/${expId}/pasos/${paso}/resultado`),
  descargarPaso: (expId: number, paso: number) =>
    api.get(`/api/expedientes/${expId}/pasos/${paso}/descargar`, { responseType: 'blob' }),
}

// ── Admin ─────────────────────────────────────────────────────────────────────

export const adminAPI = {
  listarUsuarios: () => api.get('/api/admin/usuarios'),
  crearUsuario: (data: any) => api.post('/api/admin/usuarios', data),
  toggleUsuario: (id: number) => api.put(`/api/admin/usuarios/${id}/estado`),
  cargarMaestro: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/api/admin/maestro-syngenta', form)
  },
  obtenerMaestro: () => api.get('/api/admin/maestro-syngenta'),
  cargarGlosario: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/api/admin/glosario', form)
  },
  obtenerGlosario: () => api.get('/api/admin/glosario'),
}

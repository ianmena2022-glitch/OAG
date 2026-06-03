import axios from 'axios'

// URL del backend
const BACKEND_URL = localStorage.getItem('oag_backend_url') || 'https://ogsa.up.railway.app'

export const api = axios.create({
  baseURL: BACKEND_URL,
  // 10 min: Paso 2 (clasificación IA) y Paso 3 (justificaciones IA) pueden
  // tardar varios minutos cuando hay muchos productos/diferencias. Si el
  // frontend mata la request, el backend igual la termina pero queda perdida.
  timeout: 600000,
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
      window.location.hash = '#/login'
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
  eliminarArchivo: (expId: number, archivoId: number) =>
    api.delete(`/api/expedientes/${expId}/archivos/${archivoId}`),
  // Colaboradores
  listarColaboradores: (id: number) =>
    api.get(`/api/expedientes/${id}/colaboradores`),
  invitarColaborador: (id: number, email: string) =>
    api.post(`/api/expedientes/${id}/colaboradores`, { email }),
  removerColaborador: (id: number, userId: number) =>
    api.delete(`/api/expedientes/${id}/colaboradores/${userId}`),
}

// ── Logs (TECNICO / ADMIN) ────────────────────────────────────────────────────

export const logsAPI = {
  listar: (expId: number, limit = 500) =>
    api.get(`/api/expedientes/${expId}/logs`, { params: { limit } }),
  descargar: (expId: number) =>
    api.get(`/api/expedientes/${expId}/logs/descargar`, { responseType: 'blob' }),
}

// ── Pasos ─────────────────────────────────────────────────────────────────────

export const pasosAPI = {
  ejecutarPaso: (expId: number, paso: number) =>
    api.post(`/api/expedientes/${expId}/pasos/${paso}/ejecutar`),
  resultadoPaso: (expId: number, paso: number) =>
    api.get(`/api/expedientes/${expId}/pasos/${paso}/resultado`),
  descargarPaso: (expId: number, paso: number) =>
    api.get(`/api/expedientes/${expId}/pasos/${paso}/descargar`, { responseType: 'blob' }),
  exportarPaso: (expId: number, paso: number) =>
    api.get(`/api/expedientes/${expId}/pasos/${paso}/exportar`, { responseType: 'blob' }),
}

// ── Anotaciones de Conciliación ───────────────────────────────────────────────

export const anotacionesAPI = {
  guardar: (expId: number, key: string, data: {
    tipo?: string; numero?: string; fecha?: string
    cliente?: string; monto_gestion_usd?: number
    es_agroquimico?: boolean; producto?: string
    cantidad?: number; unidad?: string
  }) => api.put(`/api/expedientes/${expId}/pasos/1/anotaciones/${encodeURIComponent(key)}`, data),
  listar: (expId: number) =>
    api.get(`/api/expedientes/${expId}/pasos/1/anotaciones`),
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
  cargarTiposCambio: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/api/admin/tipos-cambio', form)
  },
  obtenerTiposCambio: () => api.get('/api/admin/tipos-cambio'),
}


// ── Revisión con IA (Opus) ───────────────────────────────────────────────────

export const revisionAPI = {
  revisar: (expId: number | string, paso: number, archivo?: File | null) => {
    const form = new FormData()
    if (archivo) form.append('archivo_referencia', archivo)
    // 5 minutos: Opus con thinking puede tardar
    return api.post(`/api/expedientes/${expId}/pasos/${paso}/revisar`, form, {
      timeout: 300_000,
    })
  },
  aplicarFix: (expId: number | string, paso: number, payload: any) =>
    api.post(`/api/expedientes/${expId}/pasos/${paso}/aplicar-fix`, payload),
  listarAprendizajes: () => api.get('/api/expedientes/aprendizajes'),
  toggleAprendizaje: (id: number) => api.put(`/api/expedientes/aprendizajes/${id}/toggle`),
}

import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader } from 'lucide-react'
import { authAPI } from '../lib/api'
import { useAuthStore, useNotificationStore } from '../store'

export default function Login() {
  const [email, setEmail] = useState('admin@oag.com')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { login } = useAuthStore()
  const { push } = useNotificationStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    try {
      const res = await authAPI.login(email, password)
      const { access_token, user_id, nombre, role } = res.data
      login({ id: user_id, email, nombre, role }, access_token)
      navigate('/')
    } catch (err: any) {
      push('error', err.response?.data?.detail || 'Error al iniciar sesión')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-oag-light flex items-center justify-center">
      <div className="w-full max-w-sm">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-14 h-14 bg-oag-dark rounded-lg mb-4">
            <span className="text-white font-bold text-xl">OAG</span>
          </div>
          <h1 className="text-xl font-semibold text-oag-text">Sistema de Auditorías</h1>
          <p className="text-oag-muted text-sm mt-1">Ingresá tus credenciales para continuar</p>
        </div>

        {/* Form */}
        <div className="card p-6 shadow-sm">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="label">Email</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="input-field"
                placeholder="usuario@oag.com"
                required
                autoFocus
              />
            </div>
            <div>
              <label className="label">Contraseña</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="input-field"
                placeholder="••••••••"
                required
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="btn-primary w-full flex items-center justify-center gap-2 py-2.5 mt-2"
            >
              {loading ? <Loader size={16} className="animate-spin" /> : null}
              {loading ? 'Ingresando...' : 'Ingresar'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-oag-muted mt-6">
          OAG Auditores © {new Date().getFullYear()}
        </p>
      </div>
    </div>
  )
}

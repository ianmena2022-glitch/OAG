import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { adminAPI } from '../../lib/api'
import { useNotificationStore } from '../../store'
import FileUpload from '../../components/FileUpload'
import { Users, Database, BookOpen, Loader, CheckCircle, XCircle, Plus } from 'lucide-react'
import { cn } from '../../lib/utils'

type Tab = 'usuarios' | 'maestro' | 'glosario'

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>('usuarios')

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-oag-text">Administración</h1>
        <p className="text-xs text-oag-muted mt-0.5">Gestión de usuarios y datos maestros del sistema</p>
      </div>

      {/* Tabs */}
      <div className="flex gap-0 border-b border-oag-border mb-6">
        {[
          { key: 'usuarios', label: 'Usuarios', icon: Users },
          { key: 'maestro', label: 'Maestro Syngenta', icon: Database },
          { key: 'glosario', label: 'Glosario', icon: BookOpen },
        ].map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => setTab(key as Tab)}
            className={cn(
              'flex items-center gap-2 px-4 py-2.5 text-sm border-b-2 transition-colors',
              tab === key
                ? 'border-oag-blue text-oag-blue font-medium'
                : 'border-transparent text-oag-muted hover:text-oag-text'
            )}
          >
            <Icon size={14} />
            {label}
          </button>
        ))}
      </div>

      {tab === 'usuarios' && <TabUsuarios />}
      {tab === 'maestro' && <TabMaestro />}
      {tab === 'glosario' && <TabGlosario />}
    </div>
  )
}

function TabUsuarios() {
  const qc = useQueryClient()
  const { push } = useNotificationStore()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ email: '', nombre: '', password: '', role: 'AUDITOR' })

  const { data: usuarios, isLoading } = useQuery({
    queryKey: ['admin-usuarios'],
    queryFn: () => adminAPI.listarUsuarios().then((r) => r.data),
  })

  const crearMutation = useMutation({
    mutationFn: () => adminAPI.crearUsuario(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-usuarios'] })
      push('success', 'Usuario creado correctamente')
      setShowForm(false)
      setForm({ email: '', nombre: '', password: '', role: 'AUDITOR' })
    },
    onError: (err: any) => push('error', err.response?.data?.detail || 'Error al crear usuario'),
  })

  const toggleMutation = useMutation({
    mutationFn: (id: number) => adminAPI.toggleUsuario(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['admin-usuarios'] }),
    onError: () => push('error', 'Error al actualizar usuario'),
  })

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-sm font-semibold text-oag-text">Usuarios del sistema</h2>
        <button className="btn-primary flex items-center gap-2" onClick={() => setShowForm(true)}>
          <Plus size={14} />
          Nuevo usuario
        </button>
      </div>

      {showForm && (
        <div className="card p-5 border-oag-blue border">
          <h3 className="section-title">Nuevo Usuario</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="label">Nombre completo</label>
              <input className="input-field" value={form.nombre} onChange={(e) => setForm({ ...form, nombre: e.target.value })} />
            </div>
            <div>
              <label className="label">Email</label>
              <input type="email" className="input-field" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </div>
            <div>
              <label className="label">Contraseña</label>
              <input type="password" className="input-field" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </div>
            <div>
              <label className="label">Rol</label>
              <select className="input-field" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="AUDITOR">Auditor</option>
                <option value="ADMIN">Administrador</option>
              </select>
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button
              className="btn-primary"
              onClick={() => crearMutation.mutate()}
              disabled={crearMutation.isPending || !form.email || !form.nombre || !form.password}
            >
              Crear
            </button>
            <button className="btn-secondary" onClick={() => setShowForm(false)}>Cancelar</button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className="flex justify-center py-8"><Loader size={20} className="animate-spin text-oag-muted" /></div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr>
                {['Nombre', 'Email', 'Rol', 'Estado', ''].map((h) => (
                  <th key={h} className="table-header text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {usuarios?.map((u: any, i: number) => (
                <tr key={u.id} className={i % 2 === 0 ? 'bg-white' : 'bg-oag-zebra'}>
                  <td className="table-cell font-medium">{u.nombre}</td>
                  <td className="table-cell text-oag-muted">{u.email}</td>
                  <td className="table-cell">
                    <span className={cn('px-2 py-0.5 rounded text-xs font-medium',
                      u.role === 'ADMIN' ? 'bg-blue-100 text-blue-700' : 'bg-gray-100 text-gray-700'
                    )}>
                      {u.role === 'ADMIN' ? 'Administrador' : 'Auditor'}
                    </span>
                  </td>
                  <td className="table-cell">
                    {u.is_active
                      ? <span className="flex items-center gap-1 text-green-700"><CheckCircle size={12} /> Activo</span>
                      : <span className="flex items-center gap-1 text-red-600"><XCircle size={12} /> Inactivo</span>
                    }
                  </td>
                  <td className="table-cell">
                    <button
                      className="text-oag-muted hover:text-oag-text text-xs underline"
                      onClick={() => toggleMutation.mutate(u.id)}
                    >
                      {u.is_active ? 'Desactivar' : 'Activar'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function TabMaestro() {
  const qc = useQueryClient()
  const { push } = useNotificationStore()
  const [uploading, setUploading] = useState(false)

  const { data: maestro, isLoading } = useQuery({
    queryKey: ['maestro-syngenta'],
    queryFn: () => adminAPI.obtenerMaestro().then((r) => r.data),
  })

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      await adminAPI.cargarMaestro(file)
      qc.invalidateQueries({ queryKey: ['maestro-syngenta'] })
      push('success', 'Maestro de productos Syngenta actualizado')
    } catch (err: any) {
      push('error', err.response?.data?.detail || 'Error al cargar maestro')
    } finally {
      setUploading(false) }
  }

  return (
    <div className="space-y-5">
      <div className="card p-5">
        <h3 className="section-title">Maestro de Productos Syngenta</h3>
        <p className="text-xs text-oag-muted mb-4">
          Archivo Excel con la lista oficial de productos de Syngenta Argentina.
          Columnas esperadas: código (opcional), nombre_estandar, principio_activo (opcional), categoría (opcional).
          Al cargar un nuevo archivo, reemplaza el maestro completo.
        </p>
        <div className="max-w-sm">
          <FileUpload
            label="Archivo Maestro Syngenta (.xlsx)"
            onUpload={handleUpload}
            isLoading={uploading}
            isUploaded={maestro?.length > 0}
            uploadedName={maestro?.length > 0 ? `${maestro.length} productos cargados` : undefined}
          />
        </div>
      </div>

      {isLoading ? (
        <Loader size={20} className="animate-spin text-oag-muted" />
      ) : maestro?.length > 0 && (
        <div className="card p-5">
          <h3 className="section-title">Productos en el sistema ({maestro.length})</h3>
          <div className="overflow-auto max-h-80">
            <table className="w-full text-xs border-collapse">
              <thead><tr>
                {['Código', 'Nombre Estandarizado', 'Principio Activo', 'Categoría'].map((h) => (
                  <th key={h} className="table-header text-left">{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {maestro.map((p: any, i: number) => (
                  <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-oag-zebra'}>
                    <td className="table-cell text-oag-muted">{p.codigo || '—'}</td>
                    <td className="table-cell font-medium">{p.nombre_estandar}</td>
                    <td className="table-cell text-oag-muted">{p.principio_activo || '—'}</td>
                    <td className="table-cell text-oag-muted">{p.categoria || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

function TabGlosario() {
  const { push } = useNotificationStore()
  const [uploading, setUploading] = useState(false)
  const [uploadedCount, setUploadedCount] = useState<number | null>(null)

  const { data: glosario, isLoading } = useQuery({
    queryKey: ['glosario-summary'],
    queryFn: () => adminAPI.obtenerGlosario().then((r) => r.data),
  })

  const total = glosario?.total ?? 0
  const items = glosario?.items ?? []

  const handleUpload = async (file: File) => {
    setUploading(true)
    try {
      const res = await adminAPI.cargarGlosario(file)
      setUploadedCount(res.data.count)
      push('success', res.data.message)
    } catch (err: any) {
      push('error', err.response?.data?.detail || 'Error al cargar glosario')
    } finally {
      setUploading(false)
    }
  }

  const displayTotal = uploadedCount ?? total

  return (
    <div className="space-y-5">
      <div className="card p-5">
        <h3 className="section-title">Glosario de Productos</h3>
        <p className="text-xs text-oag-muted mb-4">
          Archivo Excel con dos columnas: <strong>nombre_original</strong> (como aparece en las facturas) y
          <strong> nombre_estandar</strong> (nombre unificado). Al cargar, reemplaza el glosario completo.
        </p>
        <div className="max-w-sm">
          <FileUpload
            label="Archivo Glosario (.xlsx)"
            onUpload={handleUpload}
            isLoading={uploading}
            isUploaded={displayTotal > 0}
            uploadedName={displayTotal > 0 ? `${displayTotal} entradas cargadas` : undefined}
          />
        </div>
      </div>

      {isLoading ? (
        <Loader size={20} className="animate-spin text-oag-muted" />
      ) : items.length > 0 && (
        <div className="card p-5">
          <h3 className="section-title">
            Muestra del glosario ({items.length} de {total} entradas)
          </h3>
          <div className="overflow-auto max-h-80">
            <table className="w-full text-xs border-collapse">
              <thead><tr>
                <th className="table-header text-left">Nombre Original</th>
                <th className="table-header text-left">Nombre Estandarizado</th>
              </tr></thead>
              <tbody>
                {items.map((g: any, i: number) => (
                  <tr key={i} className={i % 2 === 0 ? 'bg-white' : 'bg-oag-zebra'}>
                    <td className="table-cell">{g.nombre_original}</td>
                    <td className="table-cell font-medium text-oag-blue">{g.nombre_estandar}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}

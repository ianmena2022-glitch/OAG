import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, FolderOpen, Trash2, Calendar, Building2, Loader } from 'lucide-react'
import { expedientesAPI } from '../lib/api'
import { useNotificationStore } from '../store'
import { formatDate, PASO_LABELS } from '../lib/utils'
import { cn } from '../lib/utils'

const ESTADO_COLORS: Record<string, string> = {
  BORRADOR: 'bg-gray-100 text-gray-700',
  EN_PROCESO: 'bg-blue-100 text-blue-700',
  COMPLETADO: 'bg-green-100 text-green-700',
}

const ESTADO_LABELS: Record<string, string> = {
  BORRADOR: 'Borrador',
  EN_PROCESO: 'En Proceso',
  COMPLETADO: 'Completado',
}

export default function Dashboard() {
  const navigate = useNavigate()
  const { push } = useNotificationStore()
  const qc = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ nombre_distribuidor: '', cuit_distribuidor: '', anio_analisis: new Date().getFullYear() })

  const { data: expedientes, isLoading } = useQuery({
    queryKey: ['expedientes'],
    queryFn: () => expedientesAPI.listar().then((r) => r.data),
  })

  const crearMutation = useMutation({
    mutationFn: (data: typeof form) => expedientesAPI.crear(data),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: ['expedientes'] })
      push('success', 'Expediente creado')
      setShowForm(false)
      setForm({ nombre_distribuidor: '', cuit_distribuidor: '', anio_analisis: new Date().getFullYear() })
      navigate(`/expediente/${res.data.id}`)
    },
    onError: (err: any) => push('error', err.response?.data?.detail || 'Error al crear expediente'),
  })

  const eliminarMutation = useMutation({
    mutationFn: (id: number) => expedientesAPI.eliminar(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['expedientes'] })
      push('success', 'Expediente eliminado')
    },
    onError: (err: any) => push('error', err.response?.data?.detail || 'Error al eliminar'),
  })

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-oag-text">Expedientes de Auditoría</h1>
          <p className="text-xs text-oag-muted mt-0.5">
            {expedientes?.length ?? 0} expediente{expedientes?.length !== 1 ? 's' : ''}
          </p>
        </div>
        <button className="btn-primary flex items-center gap-2" onClick={() => setShowForm(true)}>
          <Plus size={15} />
          Nuevo Expediente
        </button>
      </div>

      {/* Formulario nuevo expediente */}
      {showForm && (
        <div className="card p-5 mb-6 border-oag-blue border">
          <h2 className="section-title">Nuevo Expediente</h2>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="label">Distribuidor</label>
              <input
                className="input-field"
                placeholder="Nombre o razón social"
                value={form.nombre_distribuidor}
                onChange={(e) => setForm({ ...form, nombre_distribuidor: e.target.value })}
              />
            </div>
            <div>
              <label className="label">CUIT</label>
              <input
                className="input-field"
                placeholder="XX-XXXXXXXX-X"
                value={form.cuit_distribuidor}
                onChange={(e) => setForm({ ...form, cuit_distribuidor: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Año bajo análisis</label>
              <input
                type="number"
                className="input-field"
                value={form.anio_analisis}
                min={2020}
                max={2030}
                onChange={(e) => setForm({ ...form, anio_analisis: Number(e.target.value) })}
              />
            </div>
          </div>
          <div className="flex gap-2 mt-4">
            <button
              className="btn-primary flex items-center gap-2"
              onClick={() => crearMutation.mutate(form)}
              disabled={crearMutation.isPending || !form.nombre_distribuidor || !form.cuit_distribuidor}
            >
              {crearMutation.isPending && <Loader size={14} className="animate-spin" />}
              Crear Expediente
            </button>
            <button className="btn-secondary" onClick={() => setShowForm(false)}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      {/* Lista de expedientes */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <Loader size={24} className="animate-spin text-oag-muted" />
        </div>
      ) : expedientes?.length === 0 ? (
        <div className="card p-12 text-center">
          <FolderOpen size={40} className="mx-auto text-oag-border mb-3" />
          <p className="text-sm text-oag-muted">No hay expedientes aún.</p>
          <p className="text-xs text-oag-muted mt-1">Creá uno nuevo para comenzar.</p>
        </div>
      ) : (
        <div className="grid gap-3">
          {expedientes?.map((exp: any) => (
            <div
              key={exp.id}
              className="card p-4 hover:border-oag-blue transition-colors cursor-pointer group"
              onClick={() => navigate(`/expediente/${exp.id}`)}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={cn('text-xs px-2 py-0.5 rounded font-medium', ESTADO_COLORS[exp.estado])}>
                      {ESTADO_LABELS[exp.estado]}
                    </span>
                    <span className="text-xs text-oag-muted">Exp. #{exp.id}</span>
                  </div>
                  <h3 className="font-semibold text-sm text-oag-text truncate">{exp.nombre_distribuidor}</h3>
                  <div className="flex items-center gap-4 mt-1.5 text-xs text-oag-muted">
                    <span className="flex items-center gap-1">
                      <Building2 size={11} />
                      CUIT: {exp.cuit_distribuidor}
                    </span>
                    <span className="flex items-center gap-1">
                      <Calendar size={11} />
                      Período: {exp.anio_analisis}
                    </span>
                  </div>
                </div>

                {/* Progreso de pasos */}
                <div className="flex items-center gap-1 ml-4">
                  {[1, 2, 3, 4, 5, 6].map((p) => {
                    const done = exp.pasos_completados?.includes(p)
                    const current = exp.paso_actual === p
                    return (
                      <div
                        key={p}
                        title={PASO_LABELS[p]}
                        className={cn(
                          'w-6 h-6 rounded text-xs flex items-center justify-center font-medium',
                          done
                            ? 'bg-oag-success text-white'
                            : current
                            ? 'bg-oag-blue text-white'
                            : 'bg-oag-border text-oag-muted'
                        )}
                      >
                        {p}
                      </div>
                    )
                  })}
                </div>

                <button
                  className="ml-3 p-1.5 text-oag-muted hover:text-oag-error hover:bg-red-50 rounded opacity-0 group-hover:opacity-100 transition-all"
                  onClick={(e) => {
                    e.stopPropagation()
                    if (confirm(`¿Eliminar expediente "${exp.nombre_distribuidor}"?`)) {
                      eliminarMutation.mutate(exp.id)
                    }
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
              <p className="text-xs text-oag-muted mt-2">
                Creado: {formatDate(exp.created_at)}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { expedientesAPI } from '../lib/api'
import { useNotificationStore } from '../store'
import { Users, UserPlus, X, Crown, Loader, Mail } from 'lucide-react'
import { cn } from '../lib/utils'

interface Props {
  expedienteId: number
  /** Cierra el panel desde el botón "X" */
  onClose: () => void
}

interface Colaborador {
  id: number
  email: string
  nombre: string
  role: string
  invited_at?: string
}

export default function ColaboradoresPanel({ expedienteId, onClose }: Props) {
  const qc = useQueryClient()
  const { push } = useNotificationStore()
  const [email, setEmail] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['colaboradores', expedienteId],
    queryFn: () => expedientesAPI.listarColaboradores(expedienteId).then((r) => r.data),
  })

  const invitarMut = useMutation({
    mutationFn: (em: string) => expedientesAPI.invitarColaborador(expedienteId, em),
    onSuccess: (res) => {
      push('success', res.data.message)
      setEmail('')
      qc.invalidateQueries({ queryKey: ['colaboradores', expedienteId] })
    },
    onError: (err: any) => push('error', err.response?.data?.detail || 'Error al invitar'),
  })

  const removerMut = useMutation({
    mutationFn: (userId: number) => expedientesAPI.removerColaborador(expedienteId, userId),
    onSuccess: () => {
      push('success', 'Colaborador removido')
      qc.invalidateQueries({ queryKey: ['colaboradores', expedienteId] })
    },
    onError: (err: any) => push('error', err.response?.data?.detail || 'Error al remover'),
  })

  const owner = data?.owner
  const soyOwner = data?.soy_owner
  const soyAdmin = data?.soy_admin
  const puedeGestionar = soyOwner || soyAdmin
  const colaboradores: Colaborador[] = data?.colaboradores || []

  const handleInvitar = (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) return
    invitarMut.mutate(email.trim())
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3.5 border-b border-oag-border">
          <div className="flex items-center gap-2">
            <Users size={16} className="text-oag-blue" />
            <h2 className="text-sm font-semibold text-oag-text">Colaboradores del expediente</h2>
          </div>
          <button onClick={onClose} className="text-oag-muted hover:text-oag-text">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-5 py-4">
          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader size={20} className="animate-spin text-oag-muted" />
            </div>
          ) : (
            <>
              {/* Owner */}
              {owner && (
                <div className="mb-4">
                  <p className="text-xs font-medium text-oag-muted uppercase tracking-wide mb-1.5">
                    Propietario
                  </p>
                  <div className="flex items-center gap-2.5 p-2.5 rounded border border-oag-border bg-oag-light">
                    <Crown size={14} className="text-yellow-600 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-oag-text truncate">{owner.nombre}</p>
                      <p className="text-xs text-oag-muted truncate">{owner.email}</p>
                    </div>
                    {soyOwner && (
                      <span className="text-xs bg-yellow-100 text-yellow-800 px-2 py-0.5 rounded font-medium">
                        Vos
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Lista colaboradores */}
              <div className="mb-4">
                <p className="text-xs font-medium text-oag-muted uppercase tracking-wide mb-1.5">
                  Colaboradores ({colaboradores.length})
                </p>
                {colaboradores.length === 0 ? (
                  <p className="text-xs text-oag-muted italic py-2">
                    No hay colaboradores invitados.
                  </p>
                ) : (
                  <div className="space-y-1.5">
                    {colaboradores.map((c) => (
                      <div
                        key={c.id}
                        className="flex items-center gap-2.5 p-2.5 rounded border border-oag-border"
                      >
                        <div className="w-7 h-7 bg-oag-dark text-white text-xs font-semibold rounded-full flex items-center justify-center flex-shrink-0">
                          {c.nombre.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-oag-text truncate">{c.nombre}</p>
                          <p className="text-xs text-oag-muted truncate">{c.email}</p>
                        </div>
                        <span className={cn(
                          'text-xs px-2 py-0.5 rounded font-medium',
                          c.role === 'ADMIN' ? 'bg-purple-100 text-purple-800' : 'bg-blue-100 text-blue-800'
                        )}>
                          {c.role === 'ADMIN' ? 'Admin' : 'Auditor'}
                        </span>
                        {puedeGestionar && (
                          <button
                            onClick={() => {
                              if (confirm(`¿Remover a ${c.nombre} de este expediente?`)) {
                                removerMut.mutate(c.id)
                              }
                            }}
                            disabled={removerMut.isPending}
                            className="text-oag-muted hover:text-red-600 transition-colors flex-shrink-0"
                            title="Remover colaborador"
                          >
                            <X size={14} />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Invitar */}
              {puedeGestionar && (
                <form onSubmit={handleInvitar} className="border-t border-oag-border pt-4">
                  <p className="text-xs font-medium text-oag-muted uppercase tracking-wide mb-1.5">
                    Invitar a un usuario
                  </p>
                  <div className="flex gap-2">
                    <div className="flex-1 relative">
                      <Mail size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-oag-muted pointer-events-none" />
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="email@empresa.com"
                        className="w-full pl-8 pr-3 py-2 text-sm border border-oag-border rounded focus:outline-none focus:border-oag-blue"
                        disabled={invitarMut.isPending}
                        required
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={!email.trim() || invitarMut.isPending}
                      className="btn-primary flex items-center gap-1.5 px-3"
                    >
                      {invitarMut.isPending ? (
                        <Loader size={13} className="animate-spin" />
                      ) : (
                        <UserPlus size={13} />
                      )}
                      Invitar
                    </button>
                  </div>
                  <p className="text-xs text-oag-muted mt-1.5">
                    El usuario debe estar ya registrado en el sistema.
                  </p>
                </form>
              )}

              {!puedeGestionar && (
                <div className="border-t border-oag-border pt-4 text-xs text-oag-muted italic">
                  Sos colaborador en este expediente. Solo el propietario o un admin pueden invitar o remover colaboradores.
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

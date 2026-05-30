import React, { useState } from 'react'
import { useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { expedientesAPI } from '../../lib/api'
import { useAuthStore, isAdminRole, canSeeLogs } from '../../store'
import { cn, PASO_LABELS } from '../../lib/utils'
import { Loader, CheckCircle, Circle, ArrowRight, Users, Terminal } from 'lucide-react'
import Paso1 from './Paso1'
import Paso2 from './Paso2'
import Paso3 from './Paso3'
import Paso4 from './Paso4'
import Paso5 from './Paso5'
import Paso6 from './Paso6'
import ColaboradoresPanel from '../../components/ColaboradoresPanel'
import LogsPanel from '../../components/LogsPanel'

const PASO_COMPONENTS: Record<number, React.ComponentType<{ expediente: any }>> = {
  1: Paso1,
  2: Paso2,
  3: Paso3,
  4: Paso4,
  5: Paso5,
  6: Paso6,
}

const ESTADO_COLORS: Record<string, string> = {
  BORRADOR: 'bg-gray-100 text-gray-700',
  EN_PROCESO: 'bg-blue-100 text-blue-700',
  COMPLETADO: 'bg-green-100 text-green-700',
}

export default function ExpedientePage() {
  const { id } = useParams<{ id: string }>()
  const [pasoActivo, setPasoActivo] = useState(1)
  const [colabOpen, setColabOpen] = useState(false)
  const [logsOpen, setLogsOpen] = useState(false)
  const currentUser = useAuthStore((s) => s.user)
  const puedeVerLogs = canSeeLogs(currentUser?.role)

  const { data: expediente, isLoading, refetch } = useQuery({
    queryKey: ['expediente', id],
    queryFn: () => expedientesAPI.obtener(Number(id)).then((r) => r.data),
    refetchInterval: 5000,
  })

  const esColaborador =
    expediente && currentUser && expediente.user_id !== currentUser.id && !isAdminRole(currentUser.role)

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader size={24} className="animate-spin text-oag-muted" />
      </div>
    )
  }

  if (!expediente) return <div>Expediente no encontrado</div>

  const PasoComponent = PASO_COMPONENTS[pasoActivo]

  return (
    <div className="flex gap-6 h-full">
      {/* Sidebar de pasos */}
      <div className="w-52 flex-shrink-0">
        <div className="card p-4 mb-4">
          <h2 className="font-semibold text-sm text-oag-text truncate">{expediente.nombre_distribuidor}</h2>
          <p className="text-xs text-oag-muted mt-0.5">CUIT: {expediente.cuit_distribuidor}</p>
          <p className="text-xs text-oag-muted">Período: {expediente.anio_analisis}</p>
          <div className="flex items-center gap-1.5 mt-2 flex-wrap">
            <span className={cn('text-xs px-2 py-0.5 rounded font-medium', ESTADO_COLORS[expediente.estado])}>
              {expediente.estado === 'BORRADOR' ? 'Borrador' : expediente.estado === 'EN_PROCESO' ? 'En Proceso' : 'Completado'}
            </span>
            {esColaborador && (
              <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded font-medium">
                Colaborador
              </span>
            )}
          </div>
          <button
            onClick={() => setColabOpen(true)}
            className="mt-3 w-full flex items-center justify-center gap-1.5 text-xs px-2 py-1.5 border border-oag-border rounded hover:bg-oag-light transition-colors text-oag-text"
          >
            <Users size={12} />
            Colaboradores
          </button>
          {puedeVerLogs && (
            <button
              onClick={() => setLogsOpen(!logsOpen)}
              className={cn(
                'mt-2 w-full flex items-center justify-center gap-1.5 text-xs px-2 py-1.5 border rounded transition-colors',
                logsOpen
                  ? 'border-purple-300 bg-purple-50 text-purple-700'
                  : 'border-oag-border text-oag-text hover:bg-oag-light'
              )}
            >
              <Terminal size={12} />
              {logsOpen ? 'Volver al paso' : 'Ver logs (técnico)'}
            </button>
          )}
        </div>

        <div className="card overflow-hidden">
          {[1, 2, 3, 4, 5, 6].map((p) => {
            const done = expediente.pasos_completados?.includes(p)
            const active = pasoActivo === p
            const available = p === 1 || expediente.pasos_completados?.includes(p - 1) || done

            return (
              <button
                key={p}
                disabled={!available}
                onClick={() => setPasoActivo(p)}
                className={cn(
                  'w-full flex items-center gap-2.5 px-3 py-2.5 text-left transition-colors border-b border-oag-border last:border-0',
                  active ? 'bg-oag-blue text-white' : available ? 'hover:bg-oag-light' : 'opacity-40 cursor-not-allowed',
                  !active && available && 'text-oag-text'
                )}
              >
                <div className="flex-shrink-0">
                  {done ? (
                    <CheckCircle size={14} className={active ? 'text-white' : 'text-oag-success'} />
                  ) : (
                    <Circle size={14} className={active ? 'text-white/60' : 'text-oag-border'} />
                  )}
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-medium">Paso {p}</div>
                  <div className={cn('text-xs truncate', active ? 'text-white/80' : 'text-oag-muted')}>
                    {PASO_LABELS[p]}
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      </div>

      {/* Contenido del paso (o logs si el técnico los pidió) */}
      <div className="flex-1 min-w-0">
        {logsOpen && puedeVerLogs ? (
          <LogsPanel expedienteId={Number(id)} />
        ) : (
          PasoComponent && <PasoComponent expediente={{ ...expediente, refetch }} />
        )}
      </div>

      {colabOpen && (
        <ColaboradoresPanel
          expedienteId={Number(id)}
          onClose={() => setColabOpen(false)}
        />
      )}
    </div>
  )
}

import React, { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { anotacionesAPI } from '../lib/api'
import { useNotificationStore } from '../store'
import { X, Save, Loader } from 'lucide-react'
import { cn } from '../lib/utils'

interface Anotacion {
  es_agroquimico?: boolean | null
  producto?: string | null
  cantidad?: number | null
  unidad?: string | null
  cliente?: string | null
  monto_gestion_usd?: number | null
}

interface Props {
  expedienteId: number
  row: {
    key: string
    tipo: string
    numero: string
    fecha: string
    monto_usd_arca?: number | null
    monto_usd_gestion?: number | null
    cliente?: string
    estado: string
    anotacion?: Anotacion
  }
  onClose: () => void
}

export default function EditAnotacionModal({ expedienteId, row, onClose }: Props) {
  const qc = useQueryClient()
  const { push } = useNotificationStore()

  // Estado local del formulario — inicializado con datos existentes
  const [cliente, setCliente]       = useState(row.anotacion?.cliente ?? row.cliente ?? '')
  const [montoGs, setMontoGs]       = useState<string>(
    row.anotacion?.monto_gestion_usd != null
      ? String(row.anotacion.monto_gestion_usd)
      : row.monto_usd_gestion && row.monto_usd_gestion !== 0
        ? String(row.monto_usd_gestion)
        : ''
  )
  const [esAgro, setEsAgro]         = useState<boolean | null>(
    row.anotacion?.es_agroquimico ?? null
  )
  const [producto, setProducto]     = useState(row.anotacion?.producto ?? '')
  const [cantidad, setCantidad]     = useState<string>(
    row.anotacion?.cantidad != null ? String(row.anotacion.cantidad) : ''
  )
  const [unidad, setUnidad]         = useState(row.anotacion?.unidad ?? '')

  const mutation = useMutation({
    mutationFn: () =>
      anotacionesAPI.guardar(expedienteId, row.key, {
        tipo: row.tipo,
        numero: row.numero,
        fecha: row.fecha,
        cliente: cliente || undefined,
        monto_gestion_usd: montoGs !== '' ? parseFloat(montoGs) : undefined,
        es_agroquimico: esAgro ?? undefined,
        producto: esAgro && producto ? producto : undefined,
        cantidad: esAgro && cantidad !== '' ? parseFloat(cantidad) : undefined,
        unidad: esAgro && unidad ? unidad : undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['paso1', expedienteId] })
      push('success', 'Anotación guardada')
      onClose()
    },
    onError: () => push('error', 'Error al guardar la anotación'),
  })

  // Cerrar con Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 overflow-hidden">

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-oag-border bg-oag-blue/5">
          <div>
            <p className="text-sm font-semibold text-oag-text">
              Editar comprobante — {row.tipo} {row.numero}
            </p>
            <p className="text-xs text-oag-muted mt-0.5">
              Fecha: {row.fecha} · ARCA: US$ {row.monto_usd_arca?.toLocaleString('es-AR', { minimumFractionDigits: 2 })}
            </p>
          </div>
          <button onClick={onClose} className="p-1.5 rounded hover:bg-black/5 text-oag-muted hover:text-oag-text transition-colors">
            <X size={16} />
          </button>
        </div>

        {/* Body */}
        <div className="px-5 py-4 space-y-4">

          {/* Cliente */}
          <div>
            <label className="block text-xs font-medium text-oag-text mb-1">Cliente</label>
            <input
              type="text"
              value={cliente}
              onChange={e => setCliente(e.target.value)}
              placeholder="Nombre del cliente..."
              className="w-full border border-oag-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-oag-blue/30"
            />
          </div>

          {/* Monto Gestión */}
          <div>
            <label className="block text-xs font-medium text-oag-text mb-1">Monto Gestión (USD)</label>
            <input
              type="number"
              step="0.01"
              min="0"
              value={montoGs}
              onChange={e => setMontoGs(e.target.value)}
              placeholder="0.00"
              className="w-full border border-oag-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-oag-blue/30"
            />
            {montoGs !== '' && row.monto_usd_arca != null && (
              <p className="text-xs text-oag-muted mt-1">
                Diferencia: <span className={cn('font-medium', Math.abs(parseFloat(montoGs) - row.monto_usd_arca) > 1 ? 'text-red-600' : 'text-green-600')}>
                  US$ {(parseFloat(montoGs) - row.monto_usd_arca).toLocaleString('es-AR', { minimumFractionDigits: 2 })}
                </span>
              </p>
            )}
          </div>

          {/* Toggle ¿Es agroquímico? */}
          <div>
            <p className="text-xs font-medium text-oag-text mb-2">¿Es agroquímico Syngenta?</p>
            <div className="flex gap-2">
              {[
                { val: true,  label: 'Sí' },
                { val: false, label: 'No' },
              ].map(opt => (
                <button
                  key={String(opt.val)}
                  type="button"
                  onClick={() => setEsAgro(esAgro === opt.val ? null : opt.val)}
                  className={cn(
                    'flex-1 py-2 rounded-lg border text-sm font-medium transition-colors',
                    esAgro === opt.val
                      ? opt.val
                        ? 'border-green-500 bg-green-50 text-green-700'
                        : 'border-red-400 bg-red-50 text-red-700'
                      : 'border-oag-border text-oag-muted hover:border-oag-text'
                  )}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          {/* Producto y cantidad — solo si es agroquímico */}
          {esAgro === true && (
            <div className="rounded-lg border border-green-200 bg-green-50/40 p-3 space-y-3">
              <p className="text-xs font-semibold text-green-800">Datos del agroquímico</p>

              <div>
                <label className="block text-xs font-medium text-oag-text mb-1">Producto</label>
                <input
                  type="text"
                  value={producto}
                  onChange={e => setProducto(e.target.value)}
                  placeholder="Nombre del producto Syngenta..."
                  className="w-full border border-oag-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400/30 bg-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-oag-text mb-1">Cantidad</label>
                  <input
                    type="number"
                    step="0.001"
                    min="0"
                    value={cantidad}
                    onChange={e => setCantidad(e.target.value)}
                    placeholder="0"
                    className="w-full border border-oag-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400/30 bg-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-oag-text mb-1">Unidad</label>
                  <select
                    value={unidad}
                    onChange={e => setUnidad(e.target.value)}
                    className="w-full border border-oag-border rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-green-400/30 bg-white"
                  >
                    <option value="">Seleccionar...</option>
                    <option value="L">Litros (L)</option>
                    <option value="kg">Kilogramos (kg)</option>
                    <option value="un">Unidades</option>
                    <option value="tn">Toneladas (tn)</option>
                  </select>
                </div>
              </div>
            </div>
          )}

          {esAgro === false && (
            <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2">
              <p className="text-xs text-oag-muted">
                El comprobante quedará registrado como <strong>no agroquímico</strong>. No se incluirá en el análisis del Paso 2.
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 px-5 py-3 border-t border-oag-border bg-gray-50">
          <button onClick={onClose} className="px-4 py-2 text-sm text-oag-muted hover:text-oag-text transition-colors">
            Cancelar
          </button>
          <button
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
            className="btn-primary flex items-center gap-2"
          >
            {mutation.isPending ? <Loader size={13} className="animate-spin" /> : <Save size={13} />}
            Guardar
          </button>
        </div>
      </div>
    </div>
  )
}

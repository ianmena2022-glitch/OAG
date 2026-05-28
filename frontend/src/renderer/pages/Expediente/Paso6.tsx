import React from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { pasosAPI } from '../../lib/api'
import { useNotificationStore } from '../../store'
import { downloadBlob } from '../../lib/utils'
import { Play, Download, Loader, FileSpreadsheet, CheckCircle, BookOpen } from 'lucide-react'
import PasoFeedback from '../../components/PasoFeedback'

interface Props { expediente: any }

export default function Paso6({ expediente }: Props) {
  const qc = useQueryClient()
  const { push } = useNotificationStore()
  const [ran, setRan] = React.useState(false)

  const { data: resultado } = useQuery({
    queryKey: ['paso6', expediente.id],
    queryFn: () => pasosAPI.resultadoPaso(expediente.id, 6).then((r) => r.data),
    enabled: !!expediente.pasos_completados?.includes(6) || ran,
    retry: false,
  })

  const ejecutarMutation = useMutation({
    mutationFn: () => pasosAPI.ejecutarPaso(expediente.id, 6),
    onSuccess: () => {
      setRan(true)
      qc.invalidateQueries({ queryKey: ['expediente', String(expediente.id)] })
      qc.invalidateQueries({ queryKey: ['paso6', expediente.id] })
      push('success', 'Informe final con glosario generado')
    },
    onError: (err: any) => push('error', err.response?.data?.detail || 'Error en Paso 6'),
  })

  const downloadMutation = useMutation({
    mutationFn: () => pasosAPI.descargarPaso(expediente.id, 6),
    onSuccess: (res) => {
      downloadBlob(res.data, `OGSA_Informe_Final_Exp${expediente.id}.xlsx`)
      push('success', 'Descarga iniciada')
    },
    onError: () => push('error', 'Error al descargar'),
  })

  const canRun = expediente.pasos_completados?.includes(5)
  const totales = resultado?.totales

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-semibold text-oag-text">Paso 6 — Informe Final con Glosario</h2>
        <p className="text-xs text-oag-muted mt-0.5">
          Igual al Paso 5, con mapeo automático de productos al glosario estandarizado mediante IA.
        </p>
      </div>

      <div className="card p-5">
        <div className="flex items-start gap-3 mb-4">
          <BookOpen size={18} className="text-oag-blue mt-0.5 flex-shrink-0" />
          <div>
            <h3 className="text-sm font-semibold text-oag-text">¿Qué agrega el glosario?</h3>
            <p className="text-xs text-oag-muted mt-1 leading-relaxed">
              En el Anexo II (Venta de Agroquímicos) se agrega una columna <strong>"Nombre Glosario"</strong> al lado
              del nombre original del producto facturado. Esta columna muestra el nombre estandarizado del glosario
              con el que se mapea ese producto, usando IA para el matching (considera variaciones de nombre, abreviaturas
              y presentaciones diferentes del mismo producto).
            </p>
          </div>
        </div>

        <div className="bg-oag-light rounded border border-oag-border p-4">
          <p className="text-xs font-medium text-oag-text mb-2">El glosario debe estar cargado en Administración → Glosario</p>
          <div className="grid grid-cols-3 gap-3 text-xs">
            <div className="bg-white p-2 rounded border border-oag-border">
              <p className="text-oag-muted">Nombre en factura (DS)</p>
              <p className="font-medium mt-1">"ENGEO PLENO 400ml"</p>
            </div>
            <div className="flex items-center justify-center text-oag-muted">→ IA mapea →</div>
            <div className="bg-white p-2 rounded border border-oag-border">
              <p className="text-oag-muted">Nombre glosario</p>
              <p className="font-medium mt-1 text-oag-blue">"ENGEO PLENO"</p>
            </div>
          </div>
        </div>

        {!canRun && (
          <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-xs text-yellow-800">
            Completar el Paso 5 para habilitar la generación del informe final.
          </div>
        )}
      </div>

      <div className="flex gap-3">
        <button
          className="btn-primary flex items-center gap-2"
          onClick={() => ejecutarMutation.mutate()}
          disabled={!canRun || ejecutarMutation.isPending}
        >
          {ejecutarMutation.isPending ? <Loader size={14} className="animate-spin" /> : <Play size={14} />}
          {ejecutarMutation.isPending ? 'Generando con IA...' : 'Generar Informe Final'}
        </button>

        {expediente.pasos_completados?.includes(6) && (
          <button
            className="btn-secondary flex items-center gap-2"
            onClick={() => downloadMutation.mutate()}
            disabled={downloadMutation.isPending}
          >
            {downloadMutation.isPending ? <Loader size={14} className="animate-spin" /> : <Download size={14} />}
            Descargar Excel Final
          </button>
        )}
      </div>

      {resultado?.validacion && (
        <PasoFeedback validacion={resultado.validacion} />
      )}

      {totales && (
        <div className="card p-5">
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle size={18} className="text-oag-success" />
            <h3 className="text-sm font-semibold text-oag-text">Informe final generado correctamente</h3>
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <p className="text-xs text-oag-muted">Proveedores (top 90%)</p>
              <p className="text-lg font-bold text-oag-text">{totales.proveedores_incluidos}</p>
            </div>
            <div>
              <p className="text-xs text-oag-muted">Líneas con glosario</p>
              <p className="text-lg font-bold text-oag-text">{totales.lineas_apertura}</p>
            </div>
            <div>
              <p className="text-xs text-oag-muted">Líneas CRM</p>
              <p className="text-lg font-bold text-oag-text">{totales.lineas_crm}</p>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-2 p-3 bg-green-50 border border-green-200 rounded">
            <FileSpreadsheet size={16} className="text-green-700" />
            <div>
              <p className="text-xs font-medium text-green-800">OGSA_Informe_Final_Exp{expediente.id}.xlsx</p>
              <p className="text-xs text-green-700">4 hojas con Anexo II incluyendo columna Nombre Glosario</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

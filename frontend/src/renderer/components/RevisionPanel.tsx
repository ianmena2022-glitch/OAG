import React, { useState } from 'react'
import { Sparkles, Upload, Loader, CheckCircle, XCircle, AlertTriangle, Brain } from 'lucide-react'
import { useDropzone } from 'react-dropzone'
import { revisionAPI } from '../lib/api'
import { useNotificationStore } from '../store'
import { useQueryClient } from '@tanstack/react-query'
import { cn } from '../lib/utils'

interface Props {
  expedienteId: number | string
  paso: number
  /** Llamado tras aplicar el fix con éxito (para refrescar resultado del paso) */
  onApplied?: () => void
}

export default function RevisionPanel({ expedienteId, paso, onApplied }: Props) {
  const qc = useQueryClient()
  const { push } = useNotificationStore()
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [analizando, setAnalizando] = useState(false)
  const [resultado, setResultado] = useState<any | null>(null)
  const [aplicando, setAplicando] = useState(false)
  const [guardarAprendizaje, setGuardarAprendizaje] = useState(true)

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
      'application/vnd.ms-excel': ['.xls'],
    },
    multiple: false,
    onDrop: (files) => {
      if (files[0]) setFile(files[0])
    },
  })

  const reset = () => {
    setFile(null)
    setResultado(null)
    setAplicando(false)
    setAnalizando(false)
    setGuardarAprendizaje(true)
  }

  const handleClose = () => {
    setOpen(false)
    reset()
  }

  const handleAnalizar = async () => {
    if (!file) return
    setAnalizando(true)
    setResultado(null)
    try {
      const res = await revisionAPI.revisar(expedienteId, paso, file)
      setResultado(res.data)
      if (res.data.error_parsing) {
        push('warning', 'Opus respondió pero no parseo JSON válido — ver detalle')
      }
    } catch (err: any) {
      push('error', err.response?.data?.detail || `Error: ${err.message}`)
    } finally {
      setAnalizando(false)
    }
  }

  const handleAplicar = async () => {
    if (!resultado) return
    setAplicando(true)
    try {
      const payload = {
        fix_inmediato: resultado.fix_inmediato,
        aprendizaje: guardarAprendizaje ? resultado.aprendizaje : null,
        analisis: resultado.analisis,
        causa_raiz: resultado.causa_raiz,
        confianza: resultado.confianza,
      }
      const res = await revisionAPI.aplicarFix(expedienteId, paso, payload)
      push('success',
        `Fix aplicado · ${res.data.cambios_aplicados?.length || 0} cambios` +
        (res.data.aprendizaje_id ? ' · aprendizaje guardado' : '')
      )
      qc.invalidateQueries({ queryKey: ['expediente', String(expedienteId)] })
      onApplied?.()
      handleClose()
    } catch (err: any) {
      push('error', err.response?.data?.detail || `Error al aplicar: ${err.message}`)
    } finally {
      setAplicando(false)
    }
  }

  const conf = resultado?.confianza ?? 0
  const fix = resultado?.fix_inmediato
  const apr = resultado?.aprendizaje
  const meta = resultado?._meta

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded border border-purple-300 bg-purple-50 text-purple-800 hover:bg-purple-100 transition-colors"
        title="Subí el archivo del auditor humano y Opus diagnostica las divergencias"
      >
        <Sparkles size={12} />
        Revisar con IA (Opus)
      </button>

      {open && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
            {/* Header */}
            <div className="px-5 py-3 border-b border-oag-border flex items-center justify-between bg-purple-50">
              <div className="flex items-center gap-2">
                <Brain size={16} className="text-purple-700" />
                <h2 className="text-sm font-semibold text-oag-text">
                  Revisión con IA — Paso {paso}
                </h2>
              </div>
              <button onClick={handleClose} className="text-oag-muted hover:text-oag-text">✕</button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto p-5">
              {!resultado && (
                <>
                  <p className="text-xs text-oag-muted mb-3 leading-relaxed">
                    Subí el archivo del <strong>auditor humano</strong> (la versión que
                    considerás correcta para este paso). Opus va a comparar contra el output
                    actual de OGSA y los archivos de entrada que usaste, y va a diagnosticar
                    automáticamente las divergencias significativas — sin que tengas que
                    describir nada.
                  </p>

                  <div
                    {...getRootProps()}
                    className={cn(
                      'border-2 border-dashed rounded p-6 text-center cursor-pointer transition-colors',
                      isDragActive ? 'border-purple-500 bg-purple-50' :
                      file ? 'border-green-400 bg-green-50' :
                      'border-oag-border bg-oag-light hover:border-purple-300'
                    )}
                  >
                    <input {...getInputProps()} />
                    <Upload size={20} className={cn(
                      'mx-auto mb-2',
                      file ? 'text-green-600' : 'text-oag-muted'
                    )} />
                    {file ? (
                      <p className="text-xs font-medium text-green-800">
                        ✓ {file.name} ({(file.size/1024).toFixed(0)} KB)
                      </p>
                    ) : (
                      <p className="text-xs text-oag-muted">
                        Arrastrá el archivo del auditor o hacé click para seleccionar (.xlsx / .xls)
                      </p>
                    )}
                  </div>

                  <div className="mt-4 text-xs text-oag-muted bg-yellow-50/60 border border-yellow-200 rounded p-3">
                    <strong className="text-oag-text">⚠ Costo aproximado:</strong> $0.50 – $2 USD por análisis
                    (modelo Opus 4.5 con razonamiento extendido). Reservalo para casos donde
                    encuentres una divergencia importante con el auditor.
                  </div>
                </>
              )}

              {analizando && (
                <div className="flex flex-col items-center justify-center py-10 gap-3">
                  <Loader size={28} className="animate-spin text-purple-600" />
                  <p className="text-sm font-medium text-oag-text">Opus analizando...</p>
                  <p className="text-xs text-oag-muted">
                    Compara el archivo del auditor contra OGSA · puede tardar 30-60 seg.
                  </p>
                </div>
              )}

              {resultado && !analizando && (
                <div className="space-y-4">
                  {/* Confianza */}
                  <div className={cn(
                    'rounded border p-3 flex items-start gap-2',
                    conf >= 0.8 ? 'border-green-300 bg-green-50' :
                    conf >= 0.5 ? 'border-yellow-300 bg-yellow-50' :
                    'border-red-300 bg-red-50'
                  )}>
                    {conf >= 0.8 ? <CheckCircle size={14} className="text-green-700 mt-0.5" /> :
                     conf >= 0.5 ? <AlertTriangle size={14} className="text-yellow-700 mt-0.5" /> :
                     <XCircle size={14} className="text-red-700 mt-0.5" />}
                    <p className="text-xs">
                      <strong>Confianza Opus:</strong> {Math.round(conf * 100)}%
                      {meta && (
                        <span className="text-oag-muted ml-2">
                          · {meta.input_tokens}→{meta.output_tokens} tokens · ${meta.costo_usd}
                        </span>
                      )}
                    </p>
                  </div>

                  {resultado.error_parsing && (
                    <div className="rounded border border-red-300 bg-red-50 p-3 text-xs">
                      <strong>Opus respondió con JSON inválido.</strong> Respuesta cruda:
                      <pre className="mt-2 bg-white p-2 rounded text-xs whitespace-pre-wrap max-h-40 overflow-y-auto">
                        {resultado.raw_response}
                      </pre>
                    </div>
                  )}

                  {/* Análisis */}
                  {resultado.analisis && (
                    <div>
                      <h3 className="text-xs font-semibold text-oag-text mb-1">Análisis</h3>
                      <div className="text-xs bg-white border border-oag-border rounded p-3 whitespace-pre-wrap leading-relaxed">
                        {resultado.analisis}
                      </div>
                    </div>
                  )}

                  {/* Causa raíz */}
                  {resultado.causa_raiz && (
                    <div>
                      <h3 className="text-xs font-semibold text-oag-text mb-1">Causa raíz</h3>
                      <div className="text-xs bg-blue-50/40 border border-blue-200 rounded p-3 whitespace-pre-wrap leading-relaxed">
                        {resultado.causa_raiz}
                      </div>
                    </div>
                  )}

                  {/* Fix inmediato */}
                  {fix && (
                    <div>
                      <h3 className="text-xs font-semibold text-oag-text mb-1">
                        Fix inmediato para este expediente
                      </h3>
                      <div className="text-xs bg-purple-50/40 border border-purple-200 rounded p-3">
                        <p className="mb-2">
                          <strong>Tipo:</strong> <code className="bg-white px-1 py-0.5 rounded">{fix.tipo}</code>
                        </p>
                        <p className="mb-2">{fix.descripcion}</p>
                        {fix.cambios && Array.isArray(fix.cambios) && fix.cambios.length > 0 && (
                          <details className="mt-2">
                            <summary className="cursor-pointer text-xs text-purple-700">
                              Ver {fix.cambios.length} cambio(s) propuesto(s)
                            </summary>
                            <pre className="mt-2 bg-white p-2 rounded text-xs overflow-x-auto max-h-40 overflow-y-auto">
                              {JSON.stringify(fix.cambios, null, 2)}
                            </pre>
                          </details>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Aprendizaje */}
                  {apr && apr.titulo && (
                    <div>
                      <h3 className="text-xs font-semibold text-oag-text mb-1 flex items-center gap-2">
                        Aprendizaje universal (se aplica a futuros expedientes)
                        <label className="flex items-center gap-1 text-xs font-normal text-oag-muted">
                          <input
                            type="checkbox"
                            checked={guardarAprendizaje}
                            onChange={(e) => setGuardarAprendizaje(e.target.checked)}
                          />
                          Guardar
                        </label>
                      </h3>
                      <div className={cn(
                        'text-xs border rounded p-3',
                        guardarAprendizaje ? 'border-green-200 bg-green-50/40' : 'border-oag-border bg-oag-light opacity-60'
                      )}>
                        <p className="font-medium mb-1">{apr.titulo}</p>
                        <p className="text-oag-muted">{apr.descripcion}</p>
                        {apr.aplica_a && (
                          <p className="mt-2 text-xs">
                            <strong>Aplica a:</strong> <code className="bg-white px-1 rounded">{apr.aplica_a}</code>
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-5 py-3 border-t border-oag-border flex justify-end gap-2 bg-oag-light/50">
              {!resultado && !analizando && (
                <>
                  <button className="btn-secondary" onClick={handleClose}>Cancelar</button>
                  <button
                    className="btn-primary flex items-center gap-1.5"
                    disabled={!file || analizando}
                    onClick={handleAnalizar}
                  >
                    <Sparkles size={12} /> Analizar con Opus
                  </button>
                </>
              )}
              {resultado && !analizando && (
                <>
                  <button className="btn-secondary" onClick={handleClose}>Descartar</button>
                  <button className="btn-secondary" onClick={reset}>Analizar otro</button>
                  {fix && (
                    <button
                      className="btn-primary flex items-center gap-1.5"
                      disabled={aplicando}
                      onClick={handleAplicar}
                    >
                      {aplicando ? <Loader size={12} className="animate-spin" /> : <CheckCircle size={12} />}
                      Aplicar fix
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}

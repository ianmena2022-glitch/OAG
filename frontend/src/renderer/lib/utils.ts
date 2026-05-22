import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatUSD(value: number | null | undefined): string {
  if (value == null || isNaN(value)) return '—'
  return new Intl.NumberFormat('es-AR', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatNumber(value: number | null | undefined): string {
  if (value == null || isNaN(value)) return '—'
  return new Intl.NumberFormat('es-AR', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(value)
}

export function formatPercent(value: number | null | undefined): string {
  if (value == null || isNaN(value)) return '—'
  return `${value.toFixed(1)}%`
}

export function formatDate(dateStr: string | null | undefined): string {
  if (!dateStr) return '—'
  try {
    const d = new Date(dateStr + 'T00:00:00')
    return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' })
  } catch {
    return dateStr
  }
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export const PASO_LABELS: Record<number, string> = {
  1: 'Cruce de Base de Datos',
  2: 'Análisis Producto Ventas',
  3: 'Cruce CRM',
  4: 'Análisis de Compras',
  5: 'Informe Ejecutivo',
  6: 'Informe con Glosario',
}

export const TIPO_ARCHIVO_LABELS: Record<string, string> = {
  BAJADA_GESTION: 'Bajada de Gestión',
  COMPROBANTES_EMITIDOS: 'Comprobantes Emitidos (ARCA)',
  COMPROBANTES_RECIBIDOS: 'Comprobantes Recibidos (ARCA)',
  TIPOS_CAMBIO: 'Tipos de Cambio',
  CRM: 'Reporte CRM Syngenta',
  MAESTRO_SYNGENTA: 'Maestro Syngenta',
  GLOSARIO: 'Glosario de Productos',
  CLIENTES_ESPECIALES: 'Clientes Especiales (Muestreo)',
  PROVEEDORES_APERTURA: 'Proveedores con Apertura',
}

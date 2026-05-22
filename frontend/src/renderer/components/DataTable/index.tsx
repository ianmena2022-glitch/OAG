import React, { useState } from 'react'
import { ChevronUp, ChevronDown, ChevronsUpDown, Search } from 'lucide-react'
import { cn, formatUSD, formatNumber } from '../../lib/utils'

export interface Column<T> {
  key: keyof T | string
  label: string
  type?: 'text' | 'usd' | 'number' | 'date' | 'badge' | 'percent'
  align?: 'left' | 'right' | 'center'
  width?: string
  render?: (value: any, row: T) => React.ReactNode
}

interface DataTableProps<T> {
  columns: Column<T>[]
  data: T[]
  searchable?: boolean
  searchKeys?: string[]
  maxHeight?: string
  emptyMessage?: string
  rowClassName?: (row: T, index: number) => string
}

export default function DataTable<T extends Record<string, any>>({
  columns,
  data,
  searchable = false,
  searchKeys = [],
  maxHeight = '400px',
  emptyMessage = 'Sin datos para mostrar',
  rowClassName,
}: DataTableProps<T>) {
  const [search, setSearch] = useState('')
  const [sortKey, setSortKey] = useState<string | null>(null)
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc')

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(sortDir === 'asc' ? 'desc' : 'asc')
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  let filtered = data
  if (search && searchKeys.length > 0) {
    const q = search.toLowerCase()
    filtered = data.filter((row) =>
      searchKeys.some((k) => String(row[k] ?? '').toLowerCase().includes(q))
    )
  }

  if (sortKey) {
    filtered = [...filtered].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av
      }
      return sortDir === 'asc'
        ? String(av ?? '').localeCompare(String(bv ?? ''))
        : String(bv ?? '').localeCompare(String(av ?? ''))
    })
  }

  const renderCell = (col: Column<T>, row: T) => {
    const val = row[col.key as string]
    if (col.render) return col.render(val, row)
    switch (col.type) {
      case 'usd':
        return <span className="font-mono">{formatUSD(val)}</span>
      case 'number':
        return <span className="font-mono">{formatNumber(val)}</span>
      case 'percent':
        return <span className="font-mono">{val != null ? `${Number(val).toFixed(1)}%` : '—'}</span>
      case 'badge':
        if (val === 'SI' || val === 'OK') return <span className="badge-ok">{val}</span>
        if (val === 'NO' || val === 'DIFERENCIA') return <span className="badge-error">{val}</span>
        if (val === 'SOLO_ARCA' || val === 'SOLO_GESTION' || val === 'SOLO_CRM')
          return <span className="badge-warning">{val}</span>
        return <span className="badge-warning">{val}</span>
      default:
        return val != null ? String(val) : '—'
    }
  }

  return (
    <div className="flex flex-col gap-2">
      {searchable && (
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-oag-muted" />
          <input
            type="text"
            placeholder="Buscar..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-field pl-8 py-1.5 text-xs"
          />
        </div>
      )}
      <div className="overflow-auto border border-oag-border rounded" style={{ maxHeight }}>
        <table className="w-full border-collapse text-xs">
          <thead className="sticky top-0 z-10">
            <tr>
              {columns.map((col) => (
                <th
                  key={String(col.key)}
                  className="table-header text-left whitespace-nowrap cursor-pointer select-none"
                  style={{ width: col.width }}
                  onClick={() => handleSort(String(col.key))}
                >
                  <div className={cn('flex items-center gap-1', col.align === 'right' && 'justify-end')}>
                    {col.label}
                    {sortKey === String(col.key) ? (
                      sortDir === 'asc' ? <ChevronUp size={10} /> : <ChevronDown size={10} />
                    ) : (
                      <ChevronsUpDown size={10} className="opacity-40" />
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="table-cell text-center text-oag-muted py-8">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              filtered.map((row, i) => (
                <tr
                  key={i}
                  className={cn(
                    'hover:bg-blue-50/40 transition-colors',
                    i % 2 === 0 ? 'bg-white' : 'bg-oag-zebra',
                    rowClassName?.(row, i)
                  )}
                >
                  {columns.map((col) => (
                    <td
                      key={String(col.key)}
                      className={cn(
                        'table-cell',
                        col.align === 'right' && 'text-right',
                        col.align === 'center' && 'text-center'
                      )}
                    >
                      {renderCell(col, row)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-oag-muted text-right">
        {filtered.length} {filtered.length === 1 ? 'registro' : 'registros'}
        {search && data.length !== filtered.length && ` de ${data.length}`}
      </p>
    </div>
  )
}

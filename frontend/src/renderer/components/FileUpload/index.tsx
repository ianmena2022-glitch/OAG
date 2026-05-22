import React, { useCallback } from 'react'
import { useDropzone } from 'react-dropzone'
import { Upload, FileSpreadsheet, CheckCircle, Loader } from 'lucide-react'
import { cn } from '../../lib/utils'

interface FileUploadProps {
  label: string
  accept?: Record<string, string[]>
  onUpload: (file: File) => void
  isLoading?: boolean
  isUploaded?: boolean
  uploadedName?: string
  description?: string
}

export default function FileUpload({
  label,
  accept = {
    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'],
    'application/vnd.ms-excel': ['.xls'],
    'text/csv': ['.csv'],
  },
  onUpload,
  isLoading = false,
  isUploaded = false,
  uploadedName,
  description,
}: FileUploadProps) {
  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles[0]) onUpload(acceptedFiles[0])
    },
    [onUpload]
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept,
    maxFiles: 1,
    disabled: isLoading,
  })

  return (
    <div className="space-y-1">
      <p className="label">{label}</p>
      {description && <p className="text-xs text-oag-muted mb-2">{description}</p>}
      <div
        {...getRootProps()}
        className={cn(
          'border-2 border-dashed rounded-lg p-4 cursor-pointer transition-colors text-center',
          isDragActive
            ? 'border-oag-blue bg-blue-50'
            : isUploaded
            ? 'border-green-300 bg-green-50'
            : 'border-oag-border bg-white hover:border-oag-blue hover:bg-blue-50/30',
          isLoading && 'opacity-50 cursor-not-allowed'
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center gap-2">
          {isLoading ? (
            <Loader size={20} className="text-oag-blue animate-spin" />
          ) : isUploaded ? (
            <CheckCircle size={20} className="text-green-600" />
          ) : (
            <Upload size={20} className="text-oag-muted" />
          )}
          <div className="text-xs">
            {isLoading ? (
              <span className="text-oag-muted">Subiendo...</span>
            ) : isUploaded ? (
              <span className="text-green-700 font-medium">{uploadedName || 'Archivo cargado'}</span>
            ) : isDragActive ? (
              <span className="text-oag-blue">Soltá el archivo aquí</span>
            ) : (
              <span className="text-oag-muted">
                Arrastrá o hacé click para seleccionar (.xlsx, .xls, .csv)
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

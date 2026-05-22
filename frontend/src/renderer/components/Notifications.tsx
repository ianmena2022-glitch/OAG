import React from 'react'
import { CheckCircle, XCircle, AlertCircle, Info, X } from 'lucide-react'
import { useNotificationStore } from '../store'
import { cn } from '../lib/utils'

const icons = {
  success: CheckCircle,
  error: XCircle,
  warning: AlertCircle,
  info: Info,
}

const colors = {
  success: 'bg-green-50 border-green-300 text-green-800',
  error: 'bg-red-50 border-red-300 text-red-800',
  warning: 'bg-yellow-50 border-yellow-300 text-yellow-800',
  info: 'bg-blue-50 border-blue-300 text-blue-800',
}

export default function Notifications() {
  const { notifications, remove } = useNotificationStore()

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 w-80">
      {notifications.map((n) => {
        const Icon = icons[n.type]
        return (
          <div
            key={n.id}
            className={cn(
              'flex items-start gap-2 p-3 border rounded shadow-md text-sm',
              colors[n.type]
            )}
          >
            <Icon size={16} className="mt-0.5 flex-shrink-0" />
            <p className="flex-1">{n.message}</p>
            <button onClick={() => remove(n.id)} className="flex-shrink-0 opacity-60 hover:opacity-100">
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}

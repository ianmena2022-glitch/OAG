import React from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

export default function TopBar() {
  const location = useLocation()
  const navigate = useNavigate()

  const segments = location.pathname.split('/').filter(Boolean)

  const crumbs = [{ label: 'Expedientes', path: '/' }]
  if (segments[0] === 'expediente' && segments[1]) {
    crumbs.push({ label: `Expediente #${segments[1]}`, path: '' })
  }
  if (segments[0] === 'admin') {
    crumbs.push({ label: 'Administración', path: '' })
  }

  return (
    <div className="h-11 bg-white border-b border-oag-border flex items-center px-6 flex-shrink-0">
      <div className="flex items-center gap-1.5 text-xs text-oag-muted">
        {crumbs.map((crumb, i) => (
          <React.Fragment key={i}>
            {i > 0 && <ChevronRight size={12} className="text-oag-border" />}
            {crumb.path ? (
              <button
                className="hover:text-oag-text transition-colors"
                onClick={() => navigate(crumb.path)}
              >
                {crumb.label}
              </button>
            ) : (
              <span className="text-oag-text font-medium">{crumb.label}</span>
            )}
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}

import React from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { LayoutDashboard, Settings, LogOut, Users, BookOpen } from 'lucide-react'
import { useAuthStore } from '../../store'
import { cn } from '../../lib/utils'

export default function Sidebar() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <div className="w-56 h-full bg-oag-dark flex flex-col flex-shrink-0">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-white/10">
        <div className="text-white font-bold text-lg tracking-tight">OGSA</div>
        <div className="text-blue-300 text-xs mt-0.5 font-light">Sistema de Auditorías</div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-0.5">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            cn(
              'flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-colors',
              isActive
                ? 'bg-white/15 text-white font-medium'
                : 'text-blue-200 hover:bg-white/10 hover:text-white'
            )
          }
        >
          <LayoutDashboard size={15} />
          Expedientes
        </NavLink>

        <NavLink
          to="/admin"
          className={({ isActive }) =>
            cn(
              'flex items-center gap-2.5 px-3 py-2 rounded text-sm transition-colors',
              isActive
                ? 'bg-white/15 text-white font-medium'
                : 'text-blue-200 hover:bg-white/10 hover:text-white',
              user?.role !== 'ADMIN' && 'hidden'
            )
          }
        >
          <Settings size={15} />
          Administración
        </NavLink>
      </nav>

      {/* User info + logout */}
      <div className="px-3 py-4 border-t border-white/10">
        <div className="px-3 mb-3">
          <div className="text-white text-xs font-medium truncate">{user?.nombre}</div>
          <div className="text-blue-300 text-xs truncate">{user?.email}</div>
          <span className="inline-block mt-1 text-xs bg-white/10 text-blue-200 px-2 py-0.5 rounded">
            {user?.role === 'ADMIN' ? 'Administrador' : 'Auditor'}
          </span>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-2 px-3 py-2 w-full text-blue-300 hover:text-white hover:bg-white/10 rounded text-sm transition-colors"
        >
          <LogOut size={14} />
          Cerrar sesión
        </button>
      </div>
    </div>
  )
}

import { NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

export default function Layout({ children }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login')
  }

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h2>Support Triage</h2>
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/dashboard" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Dashboard
          </NavLink>
          <NavLink to="/tickets" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Tickets
          </NavLink>
          <NavLink to="/tickets/new" className={({ isActive }) => isActive ? 'nav-link active' : 'nav-link'}>
            Create Ticket
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          {user && (
            <div className="user-info">
              <div className="user-name">{user.name}</div>
              <div className="user-role">{user.role}</div>
            </div>
          )}
          <button className="btn btn-sm btn-outline" onClick={handleLogout}>
            Logout
          </button>
        </div>
      </aside>
      <main className="main-content">
        {children}
      </main>
    </div>
  )
}

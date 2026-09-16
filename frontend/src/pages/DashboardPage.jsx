import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import PriorityBadge from '../components/PriorityBadge'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorAlert from '../components/ErrorAlert'
import { formatDate } from '../utils/dates'

export default function DashboardPage() {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get('/dashboard/stats')
      .then(setStats)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <LoadingSpinner text="Loading dashboard..." />
  if (error) return <ErrorAlert message={error} />

  const cards = [
    { label: 'Open', value: stats.open_count, color: '#3b82f6' },
    { label: 'Assigned', value: stats.assigned_count, color: '#8b5cf6' },
    { label: 'In Progress', value: stats.in_progress_count, color: '#f59e0b' },
    { label: 'Critical', value: stats.critical_count, color: '#ef4444' },
    { label: 'Resolved', value: stats.resolved_count, color: '#10b981' },
    { label: 'Total', value: stats.total_count, color: '#1e293b' },
  ]

  return (
    <div className="page">
      <h1>Dashboard</h1>

      <div className="stats-grid">
        {cards.map((c) => (
          <div key={c.label} className="stat-card" style={{ borderTopColor: c.color }}>
            <div className="stat-value">{c.value}</div>
            <div className="stat-label">{c.label}</div>
          </div>
        ))}
      </div>

      <h2>Recent Tickets</h2>
      {stats.recent_tickets.length === 0 ? (
        <p className="empty-state">No tickets yet.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Subject</th>
              <th>Customer</th>
              <th>Status</th>
              <th>Priority</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {stats.recent_tickets.map((t) => (
              <tr key={t.id}>
                <td>
                  <Link to={`/tickets/${t.id}`}>#{t.id}</Link>
                </td>
                <td>
                  <Link to={`/tickets/${t.id}`}>{t.subject}</Link>
                </td>
                <td>{t.customer_name}</td>
                <td><StatusBadge status={t.status} /></td>
                <td><PriorityBadge priority={t.priority} /></td>
                <td>{formatDate(t.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

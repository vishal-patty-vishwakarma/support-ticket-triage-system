import { useEffect, useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import PriorityBadge from '../components/PriorityBadge'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorAlert from '../components/ErrorAlert'
import { formatDate } from '../utils/dates'

const STATUSES = ['Open', 'Assigned', 'In Progress', 'Waiting for Customer', 'Resolved', 'Closed']
const CATEGORIES = [
  'Authentication', 'Billing', 'Performance', 'Data Issue', 'Integration',
  'User Interface', 'Access Request', 'Feature Request', 'Security', 'General Support', 'Unknown',
]
const PRIORITIES = ['Low', 'Medium', 'High', 'Critical']

export default function TicketsPage() {
  const [tickets, setTickets] = useState([])
  const [teams, setTeams] = useState([])
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('')
  const [priorityFilter, setPriorityFilter] = useState('')
  const [teamFilter, setTeamFilter] = useState('')
  const [userFilter, setUserFilter] = useState('')

  const fetchTickets = useCallback(() => {
    setLoading(true)
    setError('')
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    if (statusFilter) params.set('status', statusFilter)
    if (categoryFilter) params.set('category', categoryFilter)
    if (priorityFilter) params.set('priority', priorityFilter)
    if (teamFilter) params.set('assigned_team_id', teamFilter)
    if (userFilter) params.set('assigned_user_id', userFilter)

    const qs = params.toString()
    api.get(`/tickets${qs ? '?' + qs : ''}`)
      .then(setTickets)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [search, statusFilter, categoryFilter, priorityFilter, teamFilter, userFilter])

  useEffect(() => {
    fetchTickets()
  }, [fetchTickets])

  useEffect(() => {
    Promise.all([api.get('/teams'), api.get('/users')])
      .then(([t, u]) => { setTeams(t); setUsers(u) })
      .catch(() => {})
  }, [])

  function handleSearch(e) {
    e.preventDefault()
    fetchTickets()
  }

  function clearFilters() {
    setSearch('')
    setStatusFilter('')
    setCategoryFilter('')
    setPriorityFilter('')
    setTeamFilter('')
    setUserFilter('')
  }

  return (
    <div className="page">
      <div className="page-header">
        <h1>Tickets</h1>
        <Link to="/tickets/new" className="btn btn-primary">Create Ticket</Link>
      </div>

      <ErrorAlert message={error} />

      <form className="filter-bar" onSubmit={handleSearch}>
        <input
          type="text"
          placeholder="Search tickets..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="filter-search"
        />
        <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All Statuses</option>
          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)}>
          <option value="">All Categories</option>
          {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
        <select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
          <option value="">All Priorities</option>
          {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={teamFilter} onChange={(e) => setTeamFilter(e.target.value)}>
          <option value="">All Teams</option>
          {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <select value={userFilter} onChange={(e) => setUserFilter(e.target.value)}>
          <option value="">All Users</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
        <button type="submit" className="btn btn-primary">Search</button>
        <button type="button" className="btn btn-outline" onClick={clearFilters}>Clear</button>
      </form>

      {loading ? (
        <LoadingSpinner text="Loading tickets..." />
      ) : tickets.length === 0 ? (
        <p className="empty-state">No tickets found.</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Subject</th>
              <th>Customer</th>
              <th>Category</th>
              <th>Priority</th>
              <th>Status</th>
              <th>Assigned Team</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {tickets.map((t) => (
              <tr key={t.id}>
                <td><Link to={`/tickets/${t.id}`}>#{t.id}</Link></td>
                <td><Link to={`/tickets/${t.id}`}>{t.subject}</Link></td>
                <td>{t.customer_name}</td>
                <td>{t.category || <span className="text-muted">-</span>}</td>
                <td><PriorityBadge priority={t.priority} /></td>
                <td><StatusBadge status={t.status} /></td>
                <td>{teams.find((tm) => tm.id === t.assigned_team_id)?.name || <span className="text-muted">-</span>}</td>
                <td>{formatDate(t.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

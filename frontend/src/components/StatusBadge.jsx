const STATUS_COLORS = {
  Open: '#3b82f6',
  Assigned: '#8b5cf6',
  'In Progress': '#f59e0b',
  'Waiting for Customer': '#6b7280',
  Resolved: '#10b981',
  Closed: '#6b7280',
}

export default function StatusBadge({ status }) {
  const color = STATUS_COLORS[status] || '#6b7280'
  return (
    <span className="badge" style={{ backgroundColor: color, color: '#fff' }}>
      {status}
    </span>
  )
}

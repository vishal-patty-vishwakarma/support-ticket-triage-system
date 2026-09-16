const PRIORITY_COLORS = {
  Low: '#6b7280',
  Medium: '#3b82f6',
  High: '#f59e0b',
  Critical: '#ef4444',
}

export default function PriorityBadge({ priority }) {
  if (!priority) return <span className="badge badge-muted">None</span>
  const color = PRIORITY_COLORS[priority] || '#6b7280'
  return (
    <span className="badge" style={{ backgroundColor: color, color: '#fff' }}>
      {priority}
    </span>
  )
}

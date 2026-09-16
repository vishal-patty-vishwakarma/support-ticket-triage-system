import { useEffect, useState, useCallback } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'
import api from '../api/client'
import StatusBadge from '../components/StatusBadge'
import PriorityBadge from '../components/PriorityBadge'
import LoadingSpinner from '../components/LoadingSpinner'
import ErrorAlert from '../components/ErrorAlert'
import { formatDateTime, timeAgo } from '../utils/dates'

const STATUSES = ['Open', 'Assigned', 'In Progress', 'Waiting for Customer', 'Resolved', 'Closed']
const CATEGORIES = [
  'Authentication', 'Billing', 'Performance', 'Data Issue', 'Integration',
  'User Interface', 'Access Request', 'Feature Request', 'Security', 'General Support', 'Unknown',
]
const PRIORITIES = ['Low', 'Medium', 'High', 'Critical']

export default function TicketDetailPage() {
  const { ticketId } = useParams()
  const [searchParams] = useSearchParams()

  const [ticket, setTicket] = useState(null)
  const [aiRun, setAiRun] = useState(null)
  const [activities, setActivities] = useState([])
  const [comments, setComments] = useState([])
  const [teams, setTeams] = useState([])
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [aiError, setAiError] = useState(searchParams.get('ai_error') ? 'Ticket saved successfully, but AI analysis is currently unavailable. You can retry analysis or triage the ticket manually.' : '')

  const [analyzing, setAnalyzing] = useState(false)
  const [reviewMode, setReviewMode] = useState(null)
  const [reviewForm, setReviewForm] = useState({})
  const [reviewLoading, setReviewLoading] = useState(false)
  const [manualMode, setManualMode] = useState(false)
  const [manualForm, setManualForm] = useState({})
  const [manualLoading, setManualLoading] = useState(false)
  const [assignmentTeam, setAssignmentTeam] = useState('')
  const [assignmentUser, setAssignmentUser] = useState('')
  const [assignmentLoading, setAssignmentLoading] = useState(false)
  const [statusValue, setStatusValue] = useState('')
  const [statusLoading, setStatusLoading] = useState(false)
  const [commentBody, setCommentBody] = useState('')
  const [commentLoading, setCommentLoading] = useState(false)
  const [feedback, setFeedback] = useState('')

  const loadAll = useCallback(async () => {
    try {
      const [t, acts, cmt, tm, us] = await Promise.all([
        api.get(`/tickets/${ticketId}`),
        api.get(`/tickets/${ticketId}/activities`),
        api.get(`/tickets/${ticketId}/comments`),
        api.get('/teams'),
        api.get('/users'),
      ])
      setTicket(t)
      setActivities(Array.isArray(acts) ? acts : [])
      setComments(Array.isArray(cmt) ? cmt : [])
      setTeams(Array.isArray(tm) ? tm : [])
      setUsers(Array.isArray(us) ? us : [])
      setStatusValue(t.status)
      setAssignmentTeam(t.assigned_team_id || '')
      setAssignmentUser(t.assigned_user_id || '')

      try {
        const latest = await api.get(`/tickets/${ticketId}/ai-analysis/latest`)
        setAiRun(latest)
      } catch {
        setAiRun(null)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [ticketId])

  useEffect(() => { loadAll() }, [loadAll])

  function showFeedback(msg) {
    setFeedback(msg)
    setTimeout(() => setFeedback(''), 4000)
  }

  // --- AI Analysis ---
  async function handleAnalyze() {
    setAnalyzing(true)
    setAiError('')
    try {
      const run = await api.post(`/tickets/${ticketId}/analyze`)
      setAiRun(run)
      showFeedback('AI analysis complete.')
    } catch (err) {
      setAiError('AI analysis failed. The ticket is saved and can be managed manually.')
    } finally {
      setAnalyzing(false)
    }
  }

  async function handleAccept() {
    setReviewLoading(true)
    try {
      await api.put(`/tickets/${ticketId}/review`, { action: 'ACCEPT', ai_run_id: aiRun.id })
      setReviewMode(null)
      await loadAll()
      showFeedback('AI suggestions accepted.')
    } catch (err) {
      setAiError(err.message)
    } finally {
      setReviewLoading(false)
    }
  }

  function handleEdit() {
    setReviewForm({
      summary: aiRun.summary || '',
      category: aiRun.category || '',
      priority: aiRun.priority || '',
      priority_reason: aiRun.priority_reason || '',
      recommended_team: aiRun.recommended_team || '',
      initial_response: aiRun.suggested_response || '',
    })
    setReviewMode('edit')
  }

  async function handleEditSubmit() {
    setReviewLoading(true)
    try {
      const payload = { action: 'EDIT', ai_run_id: aiRun.id }
      if (reviewForm.summary) payload.summary = reviewForm.summary
      if (reviewForm.category) payload.category = reviewForm.category
      if (reviewForm.priority) payload.priority = reviewForm.priority
      if (reviewForm.priority_reason) payload.priority_reason = reviewForm.priority_reason
      if (reviewForm.recommended_team) payload.recommended_team = reviewForm.recommended_team
      if (reviewForm.initial_response) payload.initial_response = reviewForm.initial_response
      await api.put(`/tickets/${ticketId}/review`, payload)
      setReviewMode(null)
      await loadAll()
      showFeedback('AI suggestions updated.')
    } catch (err) {
      setAiError(err.message)
    } finally {
      setReviewLoading(false)
    }
  }

  async function handleReject() {
    if (!window.confirm('Reject these AI suggestions?')) return
    setReviewLoading(true)
    try {
      await api.put(`/tickets/${ticketId}/review`, { action: 'REJECT', ai_run_id: aiRun.id })
      setReviewMode(null)
      await loadAll()
      showFeedback('AI suggestions rejected.')
    } catch (err) {
      setAiError(err.message)
    } finally {
      setReviewLoading(false)
    }
  }

  // --- Manual Triage ---
  function startManual() {
    setManualForm({
      summary: ticket.summary || '',
      category: ticket.category || '',
      priority: ticket.priority || '',
      priority_reason: ticket.priority_reason || '',
      recommended_team: '',
      initial_response: ticket.initial_response || '',
    })
    setManualMode(true)
  }

  async function handleManualSubmit() {
    setManualLoading(true)
    try {
      const payload = { action: 'MANUAL' }
      if (manualForm.summary) payload.summary = manualForm.summary
      if (manualForm.category) payload.category = manualForm.category
      if (manualForm.priority) payload.priority = manualForm.priority
      if (manualForm.priority_reason) payload.priority_reason = manualForm.priority_reason
      if (manualForm.recommended_team) payload.recommended_team = manualForm.recommended_team
      if (manualForm.initial_response) payload.initial_response = manualForm.initial_response
      await api.put(`/tickets/${ticketId}/review`, payload)
      setManualMode(false)
      await loadAll()
      showFeedback('Manual triage saved.')
    } catch (err) {
      setAiError(err.message)
    } finally {
      setManualLoading(false)
    }
  }

  // --- Assignment ---
  async function handleAssignment() {
    setAssignmentLoading(true)
    try {
      const payload = {}
      if (assignmentTeam) payload.team_id = parseInt(assignmentTeam)
      if (assignmentUser) payload.user_id = parseInt(assignmentUser)
      if (Object.keys(payload).length === 0) {
        setAssignmentLoading(false)
        return
      }
      await api.put(`/tickets/${ticketId}/assignment`, payload)
      await loadAll()
      showFeedback('Assignment updated.')
    } catch (err) {
      setAiError(err.message)
    } finally {
      setAssignmentLoading(false)
    }
  }

  // --- Status ---
  async function handleStatus() {
    setStatusLoading(true)
    try {
      await api.put(`/tickets/${ticketId}/status`, { status: statusValue })
      await loadAll()
      showFeedback('Status updated.')
    } catch (err) {
      setAiError(err.message)
    } finally {
      setStatusLoading(false)
    }
  }

  // --- Comment ---
  async function handleComment() {
    if (!commentBody.trim()) return
    setCommentLoading(true)
    try {
      await api.post(`/tickets/${ticketId}/comments`, { body: commentBody })
      setCommentBody('')
      await loadAll()
    } catch (err) {
      setAiError(err.message)
    } finally {
      setCommentLoading(false)
    }
  }

  if (loading) return <LoadingSpinner text="Loading ticket..." />
  if (error) return <ErrorAlert message={error} />
  if (!ticket) return <ErrorAlert message="Ticket not found" />

  const teamName = (id) => teams.find((t) => t.id === id)?.name || '-'
  const userName = (id) => users.find((u) => u.id === id)?.name || '-'

  return (
    <div className="page">
      {feedback && <div className="alert alert-success">{feedback}</div>}
      <ErrorAlert message={aiError} onDismiss={() => setAiError('')} />

      {/* ── Original Ticket ── */}
      <section className="detail-section">
        <h2>Ticket #{ticket.id}</h2>
        <div className="detail-grid">
          <div><strong>Customer:</strong> {ticket.customer_name}</div>
          <div><strong>Email:</strong> {ticket.customer_email}</div>
          <div><strong>Subject:</strong> {ticket.subject}</div>
          <div><strong>Product/Module:</strong> {ticket.product_module || '-'}</div>
          {ticket.attachment_link && (
            <div><strong>Attachment:</strong> <a href={ticket.attachment_link} target="_blank" rel="noreferrer">Link</a></div>
          )}
        </div>
        <div className="detail-description">
          <h4>Original Customer Description</h4>
          <p>{ticket.description_original}</p>
        </div>
      </section>

      {/* ── Active Triage ── */}
      <section className="detail-section">
        <h3>Active Triage</h3>
        <div className="detail-grid">
          <div>
            <strong>Status:</strong> <StatusBadge status={ticket.status} />
          </div>
          <div>
            <strong>Priority:</strong> <PriorityBadge priority={ticket.priority} />
          </div>
          <div><strong>Category:</strong> {ticket.category || <em>Not yet reviewed</em>}</div>
          <div><strong>Recommended Team:</strong> {ticket.recommended_team_id ? teamName(ticket.recommended_team_id) : <em>Not yet reviewed</em>}</div>
        </div>
        {ticket.summary && (
          <div className="detail-field">
            <strong>Summary:</strong> {ticket.summary}
          </div>
        )}
        {ticket.priority_reason && (
          <div className="detail-field">
            <strong>Priority Reason:</strong> {ticket.priority_reason}
          </div>
        )}
        {ticket.initial_response && (
          <div className="detail-field">
            <strong>Initial Response:</strong> {ticket.initial_response}
          </div>
        )}
        {!ticket.summary && !ticket.category && !ticket.priority && (
          <p className="text-muted">Not yet reviewed</p>
        )}
      </section>

      {/* ── AI Assistant ── */}
      <section className="detail-section">
        <h3>AI Suggestions</h3>
        <p className="text-muted">AI-generated suggestion — review before applying.</p>

        {!aiRun && (
          <div>
            <p>No AI analysis yet.</p>
            <button className="btn btn-primary" onClick={handleAnalyze} disabled={analyzing}>
              {analyzing ? 'Analyzing...' : 'Analyze Ticket'}
            </button>
          </div>
        )}

        {aiRun && aiRun.status === 'pending' && (
          <div>
            <p>Analysis in progress...</p>
            <div className="spinner" />
          </div>
        )}

        {aiRun && aiRun.status === 'failed' && (
          <div>
            <p className="text-muted">AI analysis failed. The ticket is saved and can be managed manually.</p>
            <div className="btn-group">
              <button className="btn btn-primary" onClick={handleAnalyze} disabled={analyzing}>
                {analyzing ? 'Retrying...' : 'Retry Analysis'}
              </button>
              <button className="btn btn-outline" onClick={startManual}>
                Triage Manually
              </button>
            </div>
          </div>
        )}

        {aiRun && aiRun.status === 'success' && reviewMode !== 'edit' && (
          <div className="ai-results">
            <div className="detail-grid">
              <div><strong>Summary:</strong> {aiRun.summary}</div>
              <div><strong>Category:</strong> {aiRun.category}</div>
              <div><strong>Priority:</strong> <PriorityBadge priority={aiRun.priority} /></div>
              <div><strong>Recommended Team:</strong> {aiRun.recommended_team}</div>
            </div>
            {aiRun.priority_reason && (
              <div className="detail-field"><strong>Priority Reason:</strong> {aiRun.priority_reason}</div>
            )}
            {aiRun.suggested_response && (
              <div className="detail-field"><strong>Suggested Response:</strong> {aiRun.suggested_response}</div>
            )}
            <div className="btn-group">
              <button className="btn btn-primary" onClick={handleAccept} disabled={reviewLoading}>
                {reviewLoading ? 'Saving...' : 'Accept Suggestions'}
              </button>
              <button className="btn btn-secondary" onClick={handleEdit} disabled={reviewLoading}>
                Edit Before Applying
              </button>
              <button className="btn btn-outline" onClick={handleReject} disabled={reviewLoading}>
                Reject Suggestions
              </button>
              <button className="btn btn-outline" onClick={handleAnalyze} disabled={analyzing}>
                {analyzing ? 'Retrying...' : 'Retry Analysis'}
              </button>
            </div>
          </div>
        )}

        {aiRun && aiRun.status === 'success' && reviewMode === 'edit' && (
          <div className="edit-form">
            <ReviewEditForm
              form={reviewForm}
              setForm={setReviewForm}
              teams={teams}
              onSubmit={handleEditSubmit}
              onCancel={() => setReviewMode(null)}
              loading={reviewLoading}
            />
          </div>
        )}
      </section>

      {/* ── Manual Triage ── */}
      <section className="detail-section">
        <h3>Manual Triage</h3>
        {!manualMode ? (
          <button className="btn btn-outline" onClick={startManual}>Triage Manually</button>
        ) : (
          <div className="manual-form">
            <ReviewEditForm
              form={manualForm}
              setForm={setManualForm}
              teams={teams}
              onSubmit={handleManualSubmit}
              onCancel={() => setManualMode(false)}
              loading={manualLoading}
              submitLabel="Save Manual Triage"
            />
          </div>
        )}
      </section>

      {/* ── Assignment ── */}
      <section className="detail-section">
        <h3>Assignment</h3>
        <div className="assignment-form">
          <div className="form-row">
            <div className="form-group">
              <label htmlFor="assign-team">Team</label>
              <select
                id="assign-team"
                value={assignmentTeam}
                onChange={(e) => setAssignmentTeam(e.target.value)}
              >
                <option value="">No team</option>
                {teams.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label htmlFor="assign-user">User</label>
              <select
                id="assign-user"
                value={assignmentUser}
                onChange={(e) => setAssignmentUser(e.target.value)}
              >
                <option value="">No user</option>
                {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
              </select>
            </div>
            <button
              className="btn btn-primary"
              onClick={handleAssignment}
              disabled={assignmentLoading}
            >
              {assignmentLoading ? 'Saving...' : 'Update Assignment'}
            </button>
          </div>
          <div className="detail-grid" style={{ marginTop: '0.5rem' }}>
            <div><strong>Assigned Team:</strong> {ticket.assigned_team_id ? teamName(ticket.assigned_team_id) : '-'}</div>
            <div><strong>Assigned User:</strong> {ticket.assigned_user_id ? userName(ticket.assigned_user_id) : '-'}</div>
          </div>
        </div>
      </section>

      {/* ── Status ── */}
      <section className="detail-section">
        <h3>Status</h3>
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="status-select">Status</label>
            <select
              id="status-select"
              value={statusValue}
              onChange={(e) => setStatusValue(e.target.value)}
            >
              {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleStatus}
            disabled={statusLoading || statusValue === ticket.status}
          >
            {statusLoading ? 'Saving...' : 'Update Status'}
          </button>
        </div>
      </section>

      {/* ── Comments ── */}
      <section className="detail-section">
        <h3>Internal Comments</h3>
        <div className="comments-list">
          {comments.length === 0 ? (
            <p className="text-muted">No comments yet.</p>
          ) : (
            comments.map((c) => (
              <div key={c.id} className="comment-item">
                <div className="comment-header">
                  <strong>{c.author_name}</strong>
                  <span className="text-muted">{timeAgo(c.created_at)}</span>
                </div>
                <p>{c.body}</p>
              </div>
            ))
          )}
        </div>
        <div className="comment-form">
          <textarea
            value={commentBody}
            onChange={(e) => setCommentBody(e.target.value)}
            placeholder="Add an internal comment..."
            rows={3}
          />
          <button
            className="btn btn-primary"
            onClick={handleComment}
            disabled={commentLoading || !commentBody.trim()}
          >
            {commentLoading ? 'Posting...' : 'Add Comment'}
          </button>
        </div>
      </section>

      {/* ── Activity Timeline ── */}
      <section className="detail-section">
        <h3>Activity Timeline</h3>
        <div className="timeline">
          {activities.length === 0 ? (
            <p className="text-muted">No activity recorded.</p>
          ) : (
            activities.map((a) => (
              <div key={a.id} className="timeline-item">
                <div className="timeline-dot" />
                <div className="timeline-content">
                  <div className="timeline-desc">{a.description}</div>
                  <div className="timeline-meta">
                    {a.actor_name && <span className="timeline-actor">{a.actor_name}</span>}
                    <span className="text-muted">{formatDateTime(a.created_at)}</span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </section>
    </div>
  )
}

function ReviewEditForm({ form, setForm, teams, onSubmit, onCancel, loading, submitLabel = 'Submit Review' }) {
  function handleChange(e) {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  return (
    <div className="form-card">
      <div className="form-group">
        <label htmlFor="rev-summary">Summary</label>
        <textarea id="rev-summary" name="summary" value={form.summary} onChange={handleChange} rows={3} />
      </div>
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="rev-category">Category</label>
          <select id="rev-category" name="category" value={form.category} onChange={handleChange}>
            <option value="">Select...</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="rev-priority">Priority</label>
          <select id="rev-priority" name="priority" value={form.priority} onChange={handleChange}>
            <option value="">Select...</option>
            {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>
      <div className="form-group">
        <label htmlFor="rev-priority-reason">Priority Reason</label>
        <input id="rev-priority-reason" name="priority_reason" value={form.priority_reason} onChange={handleChange} />
      </div>
      <div className="form-group">
        <label htmlFor="rev-team">Recommended Team</label>
        <select id="rev-team" name="recommended_team" value={form.recommended_team} onChange={handleChange}>
          <option value="">Select...</option>
          {teams.map((t) => <option key={t.code} value={t.code}>{t.name}</option>)}
        </select>
      </div>
      <div className="form-group">
        <label htmlFor="rev-response">Initial Response</label>
        <textarea id="rev-response" name="initial_response" value={form.initial_response} onChange={handleChange} rows={3} />
      </div>
      <div className="btn-group">
        <button className="btn btn-primary" onClick={onSubmit} disabled={loading}>
          {loading ? 'Saving...' : submitLabel}
        </button>
        <button className="btn btn-outline" onClick={onCancel} disabled={loading}>
          Cancel
        </button>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '../api/client'
import ErrorAlert from '../components/ErrorAlert'

export default function CreateTicketPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState({
    customer_name: '',
    customer_email: '',
    subject: '',
    description: '',
    product_module: '',
    attachment_link: '',
  })
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState('')
  const [loading, setLoading] = useState(false)

  function handleChange(e) {
    const { name, value } = e.target
    setForm((prev) => ({ ...prev, [name]: value }))
    if (errors[name]) {
      setErrors((prev) => ({ ...prev, [name]: '' }))
    }
  }

  function validate() {
    const errs = {}
    if (!form.customer_name.trim()) errs.customer_name = 'Required'
    if (form.customer_name.length > 100) errs.customer_name = 'Max 100 characters'
    if (!form.customer_email.trim()) errs.customer_email = 'Required'
    if (form.customer_email.length > 150) errs.customer_email = 'Max 150 characters'
    if (!form.customer_email.includes('@')) errs.customer_email = 'Invalid email'
    if (!form.subject.trim()) errs.subject = 'Required'
    if (form.subject.length < 10) errs.subject = 'Min 10 characters'
    if (form.subject.length > 200) errs.subject = 'Max 200 characters'
    if (!form.description.trim()) errs.description = 'Required'
    if (form.description.trim().length < 30) errs.description = 'Min 30 characters'
    if (form.attachment_link && !form.attachment_link.startsWith('http')) {
      errs.attachment_link = 'Must be a valid URL'
    }
    return errs
  }

  async function createTicket() {
    const payload = {
      customer_name: form.customer_name,
      customer_email: form.customer_email,
      subject: form.subject,
      description: form.description,
    }
    if (form.product_module.trim()) payload.product_module = form.product_module
    if (form.attachment_link.trim()) payload.attachment_link = form.attachment_link
    return api.post('/tickets', payload)
  }

  async function handleSave(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length > 0) {
      setErrors(errs)
      return
    }
    setServerError('')
    setLoading(true)
    try {
      const ticket = await createTicket()
      navigate(`/tickets/${ticket.id}`)
    } catch (err) {
      setServerError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleSaveAndAnalyze(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length > 0) {
      setErrors(errs)
      return
    }
    setServerError('')
    setLoading(true)
    try {
      const ticket = await createTicket()
      try {
        await api.post(`/tickets/${ticket.id}/analyze`)
      } catch {
        navigate(`/tickets/${ticket.id}?ai_error=1`)
        return
      }
      navigate(`/tickets/${ticket.id}`)
    } catch (err) {
      setServerError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page">
      <h1>Create Ticket</h1>

      <ErrorAlert message={serverError} />

      <form className="form-card" onSubmit={(e) => e.preventDefault()}>
        <div className="form-group">
          <label htmlFor="customer_name">Customer Name *</label>
          <input
            id="customer_name"
            name="customer_name"
            value={form.customer_name}
            onChange={handleChange}
            maxLength={100}
          />
          {errors.customer_name && <span className="field-error">{errors.customer_name}</span>}
        </div>

        <div className="form-group">
          <label htmlFor="customer_email">Customer Email *</label>
          <input
            id="customer_email"
            name="customer_email"
            type="email"
            value={form.customer_email}
            onChange={handleChange}
            maxLength={150}
          />
          {errors.customer_email && <span className="field-error">{errors.customer_email}</span>}
        </div>

        <div className="form-group">
          <label htmlFor="subject">Subject * (10-200 chars)</label>
          <input
            id="subject"
            name="subject"
            value={form.subject}
            onChange={handleChange}
            maxLength={200}
          />
          {errors.subject && <span className="field-error">{errors.subject}</span>}
        </div>

        <div className="form-group">
          <label htmlFor="description">Description * (min 30 chars)</label>
          <textarea
            id="description"
            name="description"
            value={form.description}
            onChange={handleChange}
            rows={6}
          />
          {errors.description && <span className="field-error">{errors.description}</span>}
        </div>

        <div className="form-group">
          <label htmlFor="product_module">Product / Module</label>
          <input
            id="product_module"
            name="product_module"
            value={form.product_module}
            onChange={handleChange}
          />
        </div>

        <div className="form-group">
          <label htmlFor="attachment_link">Attachment Link</label>
          <input
            id="attachment_link"
            name="attachment_link"
            value={form.attachment_link}
            onChange={handleChange}
            placeholder="https://..."
          />
          {errors.attachment_link && <span className="field-error">{errors.attachment_link}</span>}
        </div>

        <div className="form-actions">
          <button
            className="btn btn-primary"
            onClick={handleSave}
            disabled={loading}
          >
            {loading ? 'Saving...' : 'Save Ticket'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleSaveAndAnalyze}
            disabled={loading}
          >
            {loading ? 'Saving...' : 'Save & Analyze'}
          </button>
          <button
            className="btn btn-outline"
            onClick={() => navigate('/tickets')}
            disabled={loading}
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}

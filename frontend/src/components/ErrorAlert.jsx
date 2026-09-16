export default function ErrorAlert({ message, onDismiss }) {
  if (!message) return null
  return (
    <div className="alert alert-error">
      <span>{message}</span>
      {onDismiss && (
        <button className="alert-dismiss" onClick={onDismiss} aria-label="Dismiss">
          &times;
        </button>
      )}
    </div>
  )
}

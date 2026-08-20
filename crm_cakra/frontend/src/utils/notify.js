import { toast } from 'frappe-ui'

// "Error: Value missing for CRM Inquiry: Subject" -- one line per empty field,
// so a save can come back with a dozen of them.
const MANDATORY = /^Error:\s*Value missing for [^:]+:\s*/i
const MAX_LENGTH = 300

// Server messages are HTML fragments; a toast is one line, so flatten them.
function clean(html) {
  return String(html ?? '')
    .replace(/<br\s*\/?>/gi, ' ')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function truncate(text) {
  return text.length > MAX_LENGTH ? text.slice(0, MAX_LENGTH - 3) + '...' : text
}

export function errorMessage(err) {
  const messages = (err?.messages || []).map(clean).filter(Boolean)

  const missing = messages
    .filter((m) => MANDATORY.test(m))
    .map((m) => m.replace(MANDATORY, ''))
  const rest = messages.filter((m) => !MANDATORY.test(m))

  const parts = []
  if (missing.length) {
    parts.push(__('Missing required fields: {0}', [missing.join(', ')]))
  }
  parts.push(...rest)
  if (parts.length) return truncate(parts.join('. '))

  // frappeRequest builds err.message as "<url> <exc_type> <text>" -- drop the url
  const raw = clean(err?.message)
  if (raw && !raw.startsWith('/api')) return truncate(raw)
  if (err?.exc_type) return err.exc_type
  return __('Something went wrong')
}

// ponytail: plenty of callers already toast their own error, so drop anything
// that looks like a repeat of what is still on screen. Swap for a real toast id
// registry if the overlap ever gets smarter than "same text, same moment".
const recent = []
function isDuplicate(message) {
  const now = Date.now()
  while (recent.length && now - recent[0].at > 3000) recent.shift()
  const hit = recent.some(
    (r) => r.message.includes(message) || message.includes(r.message),
  )
  recent.push({ message, at: now })
  return hit
}

export function notify(message, type = 'error') {
  const text = clean(message)
  if (!text || isDuplicate(text)) return
  const show = toast[type] || toast.info
  show(text, { duration: type === 'error' ? 8 : 5 })
}

export function notifyError(err) {
  notify(errorMessage(err), 'error')
}

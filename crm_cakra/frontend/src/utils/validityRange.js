// Cerminan format_validity_range() di
// crm_cakra/fcrm/doctype/crm_quotation/crm_quotation.py — dipakai print
// fallback Ctrl+P supaya hasilnya sama persis dengan Print Format Jinja
// "Quotation Print Out". Kalau salah satu berubah, ubah dua-duanya.
const ID_MONTHS_SHORT = [
  'Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun',
  'Jul', 'Ags', 'Sep', 'Okt', 'Nov', 'Des',
]

// Sengaja parsing string, bukan new Date(), supaya tidak kena geser timezone.
function parseDate(value) {
  if (!value) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value).trim())
  if (!m) return null
  return { year: +m[1], month: +m[2], day: +m[3] }
}

function formatDay(d) {
  return String(d.day).padStart(2, '0')
}

function formatOne(d) {
  return `${formatDay(d)} ${ID_MONTHS_SHORT[d.month - 1]} ${d.year}`
}

export function formatValidityRange(start, end) {
  const from = parseDate(start)
  if (!from) return ''

  const to = parseDate(end)
  const sameDay =
    to && to.year === from.year && to.month === from.month && to.day === from.day
  if (!to || sameDay) return formatOne(from)

  if (from.year !== to.year) return `${formatOne(from)} - ${formatOne(to)}`
  // Tahun sama -> cukup ditulis sekali, di ujung kanan.
  return `${formatDay(from)} ${ID_MONTHS_SHORT[from.month - 1]} - ${formatOne(to)}`
}

/**
 * Format tanggal/jam Indonesia. Satu tempat, karena tiga halaman apps mandor
 * sudah menyalin fungsi yang sama persis.
 *
 * `String(v).replace(' ', 'T')` bukan hiasan: Frappe mengirim "2026-08-28
 * 08:27:12", dan Safari iOS menolak bentuk itu di `new Date()` -- hasilnya
 * "Invalid Date" di HP tertentu saja, yang paling lama ketahuannya.
 */
const d = (v) => new Date(String(v).replace(' ', 'T'))

const dua = (n) => String(n).padStart(2, '0')

/** 28 Agu 2026 */
export const tanggal = (v) =>
  v ? d(v).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' }) : ''

/** 28 Agu */
export const tanggalPendek = (v) =>
  v ? d(v).toLocaleDateString('id-ID', { day: '2-digit', month: 'short' }) : ''

/** 08:27 */
export const jam = (v) => (v ? `${dua(d(v).getHours())}:${dua(d(v).getMinutes())}` : '')

/** 28 Agu 08:27 */
export const waktu = (v) => (v ? `${tanggalPendek(v)} ${jam(v)}` : '')

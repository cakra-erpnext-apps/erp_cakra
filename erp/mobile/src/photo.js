/**
 * Selfie absensi: kecilkan lalu bubuhi stempel waktu & lokasi.
 *
 * Sumbernya bisa berupa File atau elemen <video> yang sedang live -- keduanya
 * digambar ke canvas yang sama, jadi frame dari kamera tidak perlu dikodekan
 * jadi JPEG dulu hanya untuk dibongkar lagi.
 *
 * Kamera HP sekarang 12 MP, sekitar 4 MB per foto, sementara sopir sering di
 * jaringan pelabuhan yang buruk. Jadi fotonya memang harus digambar ulang; dan
 * karena sudah di canvas, stempelnya gratis. Stempel itu untuk dibaca mata
 * manusia -- yang dipakai sistem memeriksa tetap lat/lng yang dikirim terpisah
 * sebagai field.
 */
const MAX_SIDE = 720
const QUALITY = 0.75

export async function stampedSelfie(source, lines) {
  const img = source instanceof Blob ? await load(source) : source
  const sw = img.videoWidth || img.naturalWidth || img.width
  const sh = img.videoHeight || img.naturalHeight || img.height

  const scale = Math.min(1, MAX_SIDE / Math.max(sw, sh))
  const w = Math.round(sw * scale)
  const h = Math.round(sh * scale)

  const c = document.createElement('canvas')
  c.width = w
  c.height = h
  const ctx = c.getContext('2d')
  ctx.drawImage(img, 0, 0, w, h)

  const size = Math.max(12, Math.round(w / 28))
  const pad = Math.round(size * 0.6)
  const box = lines.length * (size + pad / 2) + pad

  ctx.fillStyle = 'rgba(0,0,0,.55)'
  ctx.fillRect(0, h - box, w, box)
  ctx.font = `${size}px system-ui, sans-serif`
  ctx.fillStyle = '#fff'
  ctx.textBaseline = 'top'
  lines.forEach((line, i) => ctx.fillText(line, pad, h - box + pad / 2 + i * (size + pad / 2)))

  return c.toDataURL('image/jpeg', QUALITY)
}

function load(file) {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => {
      URL.revokeObjectURL(img.src)
      resolve(img)
    }
    img.onerror = reject
    img.src = URL.createObjectURL(file)
  })
}

import { io } from 'socket.io-client'
import { socketio_port } from '../../../../sites/common_site_config.json'
import { getCachedListResource, getCachedResource } from 'frappe-ui'

export function initSocket() {
  let siteName = window.site_name

  // Dev (vite serve): halamannya disajikan Vite dan proxy-nya TIDAK mencakup
  // /socket.io, jadi socket harus menembak langsung port socketio bench.
  //
  // Build produksi: halamannya disajikan nginx, dan nginx itu yang mem-proxy
  // /socket.io ke websocket:9000 -- jadi sambungannya ke origin yang sama.
  // Dulu aturannya "ada port di URL = pakai port 9000", dan di stack docker
  // (nginx :8080) port 9000 tidak dipublikasikan sama sekali: socket tidak
  // pernah tersambung, dan semua fitur realtime diam-diam mati.
  let url = import.meta.env.DEV
    ? `${window.location.protocol}//${window.location.hostname}:${socketio_port}/${siteName}`
    : `${window.location.origin}/${siteName}`

  let socket = io(url, {
    withCredentials: true,
    reconnectionAttempts: 5,
  })
  socket.on('refetch_resource', (data) => {
    if (data.cache_key) {
      let resource =
        getCachedResource(data.cache_key) ||
        getCachedListResource(data.cache_key)
      if (resource) {
        resource.reload()
      }
    }
  })
  return socket
}

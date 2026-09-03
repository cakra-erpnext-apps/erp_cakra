import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import path from 'path'

// Cap waktu build ditanam ke bundel. Dua kali sesi debug habis karena bundel
// lama masih nyangkut di HP dan tidak ada cara melihatnya dari layar.
const BUILD = new Date().toISOString().slice(0, 16).replace('T', ' ')

export default defineConfig({
  define: { __BUILD__: JSON.stringify(BUILD) },
  plugins: [
    vue(),
  ],
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  build: {
    outDir: '../erp/public/mobile',
    emptyOutDir: true,
    target: 'es2018',
    // Dua apps (sopir dan mandor) dari SATU project: komponen, gaya, dan api.js
    // dipakai bersama, dan memisahkannya jadi dua project berarti dua
    // node_modules, dua tailwind.config, dan dua tempat memperbaiki bug yang sama.
    rollupOptions: {
      input: {
        index: path.resolve(__dirname, 'index.html'),
        mandor: path.resolve(__dirname, 'mandor.html'),
      },
    },
  },
  server: {
    host: '0.0.0.0',
    port: parseInt(process.env.VITE_PORT || '8091'),
    strictPort: true,
    allowedHosts: ['localhost', '.localhost', 'erp.localhost'],
    proxy: {
      '^/(api|assets|files|private)': { target: 'http://erp.localhost:8080', changeOrigin: true },
    },
  },
})

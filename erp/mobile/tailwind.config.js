export default {
  content: ['./index.html', './src/**/*.{vue,js}'],
  theme: {
    extend: {
      // Tiga peran, ditulis sebagai CSS variable supaya SATU apps bisa memakai
      // palet lain tanpa mengubah satu pun class di komponen (lihat blok
      // `.mandor` di style.css). Nilai bawaannya = apps sopir, jadi mengganti
      // tema mandor tidak bisa merembet ke sana.
      //
      // brand  = warna utama / identitas. Header, tombol utama, tab aktif.
      // accent = penarik mata: peringatan lunak, yang belum dibaca, yang perlu
      //          dilirik -- bukan warna hiasan.
      // ok     = berhasil / tersedia / selesai. Dulu menumpang `brand` karena
      //          apps sopir kebetulan hijau; begitu ada apps beridentitas
      //          oranye, "berhasil" dan "identitas" jelas dua hal berbeda.
      colors: {
        brand: {
          50: 'rgb(var(--brand-50) / <alpha-value>)',
          100: 'rgb(var(--brand-100) / <alpha-value>)',
          200: 'rgb(var(--brand-200) / <alpha-value>)',
          300: 'rgb(var(--brand-300) / <alpha-value>)',
          400: 'rgb(var(--brand-400) / <alpha-value>)',
          500: 'rgb(var(--brand-500) / <alpha-value>)',
          600: 'rgb(var(--brand-600) / <alpha-value>)',
          700: 'rgb(var(--brand-700) / <alpha-value>)',
          800: 'rgb(var(--brand-800) / <alpha-value>)',
          900: 'rgb(var(--brand-900) / <alpha-value>)',
        },
        accent: {
          50: 'rgb(var(--accent-50) / <alpha-value>)',
          100: 'rgb(var(--accent-100) / <alpha-value>)',
          200: 'rgb(var(--accent-200) / <alpha-value>)',
          300: 'rgb(var(--accent-300) / <alpha-value>)',
          400: 'rgb(var(--accent-400) / <alpha-value>)',
          500: 'rgb(var(--accent-500) / <alpha-value>)',
          600: 'rgb(var(--accent-600) / <alpha-value>)',
          700: 'rgb(var(--accent-700) / <alpha-value>)',
          800: 'rgb(var(--accent-800) / <alpha-value>)',
          900: 'rgb(var(--accent-900) / <alpha-value>)',
        },
        ok: {
          50: 'rgb(var(--ok-50) / <alpha-value>)',
          100: 'rgb(var(--ok-100) / <alpha-value>)',
          200: 'rgb(var(--ok-200) / <alpha-value>)',
          300: 'rgb(var(--ok-300) / <alpha-value>)',
          400: 'rgb(var(--ok-400) / <alpha-value>)',
          500: 'rgb(var(--ok-500) / <alpha-value>)',
          600: 'rgb(var(--ok-600) / <alpha-value>)',
          700: 'rgb(var(--ok-700) / <alpha-value>)',
          800: 'rgb(var(--ok-800) / <alpha-value>)',
          900: 'rgb(var(--ok-900) / <alpha-value>)',
        },
      },
    },
  },
}

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Binds on all network interfaces, not just localhost, so a phone on
    // the same WiFi network (e.g. the Expo Go WebView in mobile/App.tsx)
    // can reach this dev server via the Mac's LAN IP.
    host: true,
    // Without this, Vite's default behavior when port 5173 is already
    // taken is to silently start on the next free port (5174, 5175...)
    // instead of failing — confirmed as the actual mechanism behind a
    // recurring real problem: a second `npm run dev` run by mistake in
    // another terminal never errored, it just quietly opened a second
    // frontend on a different port, leaving whoever loads the "old"
    // localhost:5173 tab talking to a stale/different process. Failing
    // loudly here makes a duplicate impossible to miss.
    strictPort: true,
  },
})

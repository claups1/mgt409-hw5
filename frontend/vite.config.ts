import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The backend (backend/main.py) allows CORS from local Vite ports 5100-5199.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
})

import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

// GitHub Pages serves a project site from /<repo>/, not from the domain root.
// The Pages workflow passes that prefix in as BASE_PATH (empty or "/" locally
// and for a custom domain); Vite wants it with a trailing slash.
const basePath = process.env.BASE_PATH || '/'
const base = basePath.endsWith('/') ? basePath : `${basePath}/`

// https://vite.dev/config/
export default defineConfig({
  base,
  plugins: [svelte()],
})

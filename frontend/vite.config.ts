import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [sveltekit()],
	server: {
		// In development the page is served by Vite and talks to the
		// practice backend on the usual Shortsmith port.
		proxy: {
			'/api': 'http://127.0.0.1:8484'
		}
	}
});

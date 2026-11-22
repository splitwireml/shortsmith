import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	kit: {
		// The built app is served by FastAPI; every route falls back to
		// index.html so a link to /videos/3 works when opened directly.
		adapter: adapter({ fallback: 'index.html' })
	}
};

export default config;

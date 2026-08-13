/** @type {import('next').NextConfig} */

/**
 * `NEXT_PUBLIC_API_BASE` is inlined at build time, which is fine locally where
 * the backend is always on :8000 but awkward for a split deployment where the
 * backend URL is not known until the service exists.
 *
 * So in deployed environments we set `NEXT_PUBLIC_API_BASE=/api` (a constant,
 * safe to inline) and point `BACKEND_ORIGIN` at the API service. The rewrite
 * below is evaluated when the server starts, so the browser talks to this
 * origin only and Next proxies through - which also removes CORS from the
 * picture entirely.
 */
// The deployment sets an absolute https URL. A bare hostname is still accepted
// and assumed to be https, so a misconfigured value fails loudly on connect
// rather than silently proxying to a relative path.
const rawBackendOrigin = process.env.BACKEND_ORIGIN?.trim();
const backendOrigin = rawBackendOrigin
  ? /^https?:\/\//.test(rawBackendOrigin)
    ? rawBackendOrigin
    : `https://${rawBackendOrigin}`
  : undefined;

const nextConfig = {
  reactStrictMode: true,
  env: {
    NEXT_PUBLIC_API_BASE:
      process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000/api',
  },
  async rewrites() {
    if (!backendOrigin) return [];
    return [
      {
        source: '/api/:path*',
        destination: `${backendOrigin.replace(/\/$/, '')}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

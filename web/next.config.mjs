/** @type {import('next').NextConfig} */
const API_BASE = process.env.API_BASE_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  experimental: {
    // Полный Garmin-синк идёт минуты (особенно под 429 rate-limit); дефолтные
    // ~30s dev-прокси рвали POST /api/sync (ECONNRESET), см. issue #45.
    proxyTimeout: 300_000,
  },
  async rewrites() {
    // Proxy API calls to the FastAPI backend so the browser talks same-origin.
    return [
      {
        source: "/api/:path*",
        destination: `${API_BASE}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

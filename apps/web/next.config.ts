import type { NextConfig } from "next";

// The browser only ever talks to this origin; Next proxies /api and /health to
// the local FastAPI server, so no CORS and no direct browser -> runner/AI path.
// NOTE: rewrites are resolved at BUILD time — rebuild after changing MLFORGE_API_ORIGIN.
const API_ORIGIN = process.env.MLFORGE_API_ORIGIN ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Lets the E2E suite keep its own build (pointing at an isolated API) next to the dev one.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  reactStrictMode: true,
  poweredByHeader: false,
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${API_ORIGIN}/api/:path*` },
      { source: "/health", destination: `${API_ORIGIN}/health` },
    ];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;

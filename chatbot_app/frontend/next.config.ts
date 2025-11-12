import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000",
    API_BASE_URL_SERVER: process.env.API_BASE_URL_SERVER || "http://127.0.0.1:8000",
  },
  async rewrites() {
    let backendUrl = process.env.API_BASE_URL_SERVER || process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
    if (process.env.NODE_ENV === "production" && !backendUrl.startsWith("http")) {
      backendUrl = `https://${backendUrl}`;
    }
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  eslint: {
    ignoreDuringBuilds: true,
  },
  experimental: {
    serverActions: {
      allowedOrigins: (() => {
        const origins = ["localhost:5000", "127.0.0.1:5000"];
        // Add Replit domain
        if (process.env.REPLIT_DEV_DOMAIN) {
          origins.push(`https://${process.env.REPLIT_DEV_DOMAIN}`);
        }
        // Add Railway domain
        if (process.env.RAILWAY_PUBLIC_DOMAIN) {
          origins.push(`https://${process.env.RAILWAY_PUBLIC_DOMAIN}`);
        }
        return origins;
      })(),
    },
  },
};

export default nextConfig;

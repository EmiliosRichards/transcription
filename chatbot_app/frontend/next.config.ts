import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000",
    // Expose for tooling only; not used in browser
    API_BASE_URL_SERVER: process.env.API_BASE_URL_SERVER || "http://127.0.0.1:8000",
  },
  async rewrites() {
    // Prefer private domain for server-to-server traffic if provided
    let backendUrl = (process.env.API_BASE_URL_SERVER || process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").trim();
    if (process.env.NODE_ENV === "production" && !backendUrl.startsWith("http")) {
      // Use http for Railway private domains; https for public hosts
      const isPrivate = /(^|\\.)railway\\.internal$/.test(backendUrl);
      backendUrl = `${isPrivate ? "http" : "https"}://${backendUrl}`;
    }
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
  eslint: {
    // Warning: This allows production builds to successfully complete even if
    // your project has ESLint errors.
    ignoreDuringBuilds: true,
  },
};

export default nextConfig;

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
    const hasScheme = /^https?:\\/\\//i.test(backendUrl);
    if (process.env.NODE_ENV === "production" && !hasScheme) {
      // If no scheme is provided, decide based on host
      const isPrivateHost = /(^|\\.)railway\\.internal(?::\\d+)?$/i.test(backendUrl);
      backendUrl = `${isPrivateHost ? "http" : "https"}://${backendUrl}`;
    }
    // Normalize and auto-append port 8080 for Railway private domains when missing
    try {
      const u = new URL(backendUrl);
      if (u.hostname.endsWith(".railway.internal") && !u.port) {
        u.port = "8080";
      }
      // Use origin (scheme://host[:port]) to avoid duplicate slashes
      backendUrl = u.origin;
    } catch {
      // leave as-is if URL parsing fails
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

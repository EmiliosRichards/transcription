import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000",
    API_BASE_URL_SERVER: process.env.API_BASE_URL_SERVER || "http://127.0.0.1:8000",
  },
  async rewrites() {
    // Prefer private domain for server-to-server traffic if provided
    let backendUrl = (process.env.API_BASE_URL_SERVER || process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").trim();
    
    console.log("🔍 [DIAGNOSTIC] Initial backendUrl:", backendUrl);
    console.log("🔍 [DIAGNOSTIC] API_BASE_URL_SERVER:", process.env.API_BASE_URL_SERVER);
    console.log("🔍 [DIAGNOSTIC] NEXT_PUBLIC_API_BASE_URL:", process.env.NEXT_PUBLIC_API_BASE_URL);
    console.log("🔍 [DIAGNOSTIC] NODE_ENV:", process.env.NODE_ENV);
    
    const hasScheme = backendUrl.startsWith("http://") || backendUrl.startsWith("https://");
    if (process.env.NODE_ENV === "production" && !hasScheme) {
      // Decide based on host when scheme is missing
      const hostCandidate = backendUrl.split("/")[0];
      const hostNoPort = hostCandidate.split(":")[0];
      const isPrivateHost = hostNoPort === "railway.internal" || hostNoPort.endsWith(".railway.internal");
      backendUrl = `${isPrivateHost ? "http" : "https"}://${backendUrl}`;
      console.log("🔍 [DIAGNOSTIC] Added scheme (no scheme detected):", backendUrl);
    }
    
    // Normalize URL but preserve port for Railway internal domains
    try {
      const u = new URL(backendUrl);
      const isRailwayInternal = u.hostname.endsWith(".railway.internal");
      
      // For Railway internal domains, we MUST include the port
      if (isRailwayInternal && !u.port) {
        console.warn("⚠️ [DIAGNOSTIC] Railway internal domain missing port! Add :8000 to your API_BASE_URL_SERVER");
        console.warn("⚠️ [DIAGNOSTIC] Example: API_BASE_URL_SERVER=backend.railway.internal:8000");
      }
      
      backendUrl = u.origin;
      console.log("🔍 [DIAGNOSTIC] Final backendUrl (normalized):", backendUrl);
      console.log("🔍 [DIAGNOSTIC] Is Railway internal?", isRailwayInternal);
      console.log("🔍 [DIAGNOSTIC] Port:", u.port || "(default for protocol)");
    } catch (error) {
      console.error("❌ [DIAGNOSTIC] URL parsing failed:", error);
      console.log("🔍 [DIAGNOSTIC] Using backendUrl as-is:", backendUrl);
    }
    
    console.log("✅ [DIAGNOSTIC] Proxy configuration: /api/* -> " + backendUrl + "/api/*");
    
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

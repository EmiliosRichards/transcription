import { spawn } from "node:child_process";
import path from "node:path";

const rawPort = process.env.PORT;
const port = rawPort ? Number(rawPort) : 5000;
if (!Number.isFinite(port) || port <= 0) {
  console.error(`[startup] Invalid PORT: ${rawPort ?? "(unset)"}`);
  process.exit(1);
}

// Railway (and most PaaS) expects binding on all interfaces.
// Do NOT bind to process.env.HOSTNAME (commonly set to a container hostname),
// because it can cause EADDRNOTAVAIL and crash on startup.
const host = "0.0.0.0";

// Run Next via Node for cross-platform reliability (no shell $PORT expansion needed).
const nextBin = path.join(process.cwd(), "node_modules", "next", "dist", "bin", "next");

console.log(`[startup] node=${process.version} cwd=${process.cwd()}`);
console.log(`[startup] PORT=${rawPort ?? "(unset)"} resolvedPort=${port} host=${host}`);
console.log(`[startup] nextBin=${nextBin}`);
console.log(`[startup] Starting Next.js on ${host}:${port}`);

const child = spawn(process.execPath, [nextBin, "start", "-H", host, "-p", String(port)], {
  stdio: "inherit",
  env: process.env,
});

child.on("error", (err) => {
  console.error("[startup] Failed to spawn Next.js process:", err);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    console.error(`[startup] Next.js exited from signal: ${signal}`);
    process.exit(1);
  }
  process.exit(code ?? 1);
});


import { spawn } from "node:child_process";
import path from "node:path";

const rawPort = process.env.PORT;
const port = rawPort ? Number(rawPort) : 5000;
if (!Number.isFinite(port) || port <= 0) {
  console.error(`[startup] Invalid PORT: ${rawPort ?? "(unset)"}`);
  process.exit(1);
}

// Railway (and most PaaS) expects binding on all interfaces.
const host = process.env.HOSTNAME || "0.0.0.0";

// Run Next via Node for cross-platform reliability (no shell $PORT expansion needed).
const nextBin = path.join(process.cwd(), "node_modules", "next", "dist", "bin", "next");

console.log(`[startup] Starting Next.js on ${host}:${port}`);

const child = spawn(process.execPath, [nextBin, "start", "-H", host, "-p", String(port)], {
  stdio: "inherit",
  env: process.env,
});

child.on("exit", (code, signal) => {
  if (signal) {
    console.error(`[startup] Next.js exited from signal: ${signal}`);
    process.exit(1);
  }
  process.exit(code ?? 1);
});


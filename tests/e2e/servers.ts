/* Starts/stops the real stack for E2E: FastAPI (+ embedded worker) and Next. */
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdirSync, openSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
export const ART = path.join(ROOT, "tests/e2e/.artifacts");
export const DATA = path.join(ART, "data");
export const API_PORT = 8100;
export const WEB_PORT = 3100;
export const WEB_URL = `http://127.0.0.1:${WEB_PORT}`;
const API_ORIGIN = `http://127.0.0.1:${API_PORT}`;

const apiEnv = () => ({ ...process.env, MLFORGE_DATA_DIR: DATA, MLFORGE_DATABASE_URL: "", ANTHROPIC_API_KEY: "" });

async function waitFor(url: string, timeoutMs: number) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(url);
      if (r.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  throw new Error(`timeout waiting for ${url}`);
}

function spawnLogged(name: string, cmd: string, args: string[], cwd: string, env: NodeJS.ProcessEnv) {
  mkdirSync(ART, { recursive: true });
  const out = openSync(path.join(ART, `${name}.log`), "a");
  const child = spawn(cmd, args, { cwd, env, detached: true, stdio: ["ignore", out, out] });
  child.unref();
  writeFileSync(path.join(ART, `${name}.pid`), String(child.pid));
}

function killByPidFile(name: string) {
  const file = path.join(ART, `${name}.pid`);
  if (!existsSync(file)) return;
  const pid = Number(readFileSync(file, "utf8"));
  try {
    process.kill(-pid, "SIGTERM");
  } catch {
    /* already gone */
  }
  rmSync(file);
}

export function resetData() {
  rmSync(DATA, { recursive: true, force: true });
  mkdirSync(DATA, { recursive: true });
  execFileSync("uv", ["run", "python", "-m", "mlforge_api.cli", "seed"], { cwd: ROOT, env: apiEnv(), stdio: "inherit" });
}

export async function startApi() {
  spawnLogged("api", "uv", ["run", "uvicorn", "mlforge_api.asgi:app", "--host", "127.0.0.1", "--port", String(API_PORT)], ROOT, apiEnv());
  await waitFor(`${API_ORIGIN}/health`, 60_000);
}

export async function stopApi() {
  killByPidFile("api");
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    try {
      await fetch(`${API_ORIGIN}/health`);
    } catch {
      return;
    }
    await new Promise((r) => setTimeout(r, 200));
  }
}

export function buildWeb() {
  execFileSync("pnpm", ["build"], {
    cwd: path.join(ROOT, "apps/web"),
    env: { ...process.env, MLFORGE_API_ORIGIN: API_ORIGIN, NEXT_DIST_DIR: ".next-e2e", NEXT_TELEMETRY_DISABLED: "1" },
    stdio: "inherit",
  });
}

export async function startWeb() {
  spawnLogged("web", "pnpm", ["exec", "next", "start", "-p", String(WEB_PORT), "-H", "127.0.0.1"], path.join(ROOT, "apps/web"), {
    ...process.env,
    NEXT_DIST_DIR: ".next-e2e",
    NEXT_TELEMETRY_DISABLED: "1",
  });
  await waitFor(`${WEB_URL}/health`, 60_000);
}

export function stopWeb() {
  killByPidFile("web");
}

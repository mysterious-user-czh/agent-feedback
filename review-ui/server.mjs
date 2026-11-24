import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { delimiter, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const appDir = fileURLToPath(new URL(".", import.meta.url));
const workspace = resolve(appDir, "..");
const project = existsSync(join(workspace, "pyproject.toml"))
  ? workspace
  : join(workspace, "agent-feedback");

function argument(name, fallback) {
  const exact = process.argv.indexOf(`--${name}`);
  if (exact >= 0 && process.argv[exact + 1]) return process.argv[exact + 1];
  const inline = process.argv.find((value) => value.startsWith(`--${name}=`));
  return inline ? inline.slice(name.length + 3) : fallback;
}

const host = argument("host", "127.0.0.1");
const port = argument("port", "7100");
const python = process.env.AGENT_FEEDBACK_PYTHON ||
  (existsSync(join(project, ".venv", "Scripts", "python.exe"))
    ? join(project, ".venv", "Scripts", "python.exe")
    : "python");
const db = process.env.AGENT_FEEDBACK_DB || join(appDir, "data", "review-demo.db");
const contracts = process.env.AGENT_FEEDBACK_CONTRACTS || join(project, "examples", "contracts.json");
const demo = !process.env.AGENT_FEEDBACK_DB;
const env = { ...process.env, PYTHONPATH: [join(project, "src"), process.env.PYTHONPATH].filter(Boolean).join(delimiter) };

if (!existsSync(db)) {
  if (!demo) {
    console.error("AGENT_FEEDBACK_DB 指向的数据库不存在，未创建或覆盖任何真实数据。");
    process.exit(1);
  }
  const seeded = spawnSync(python, [join(project, "examples", "review_demo.py"), "--output", db, "--contracts", contracts], {
    env, stdio: "inherit",
  });
  if (seeded.status !== 0) process.exit(seeded.status || 1);
}

const child = spawn(python, ["-m", "agent_feedback.review_server", "--db", db, "--contracts", contracts,
  "--static-dir", appDir, "--host", host, "--port", port, ...(demo ? ["--demo"] : [])], {
  env, stdio: "inherit",
});

let stopping = false;
function stop() {
  if (stopping) return;
  stopping = true;
  if (!child.killed) child.kill("SIGTERM");
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
process.on("exit", stop);
child.on("error", (error) => {
  console.error(`无法启动本地审核服务：${error.message}`);
  process.exitCode = 1;
});
child.on("exit", (code, signal) => {
  if (!stopping && code !== 0) console.error(`本地审核服务已退出（${code ?? signal}）。`);
  process.exitCode = stopping ? 0 : (code ?? 1);
});

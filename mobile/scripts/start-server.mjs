import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const expoCli = require.resolve("expo/bin/cli");
const envFile = fileURLToPath(new URL("../.env.server", import.meta.url));

const serverEnv = Object.fromEntries(
  readFileSync(envFile, "utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#") && line.includes("="))
    .map((line) => {
      const separator = line.indexOf("=");
      return [line.slice(0, separator).trim(), line.slice(separator + 1).trim()];
    }),
);

const child = spawn(process.execPath, [expoCli, "start", ...process.argv.slice(2)], {
  env: { ...process.env, ...serverEnv },
  stdio: "inherit",
});

child.on("error", (error) => {
  console.error(`Expo 실행에 실패했습니다: ${error.message}`);
  process.exitCode = 1;
});

child.on("exit", (code, signal) => {
  process.exitCode = code ?? (signal ? 1 : 0);
});

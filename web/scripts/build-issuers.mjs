#!/usr/bin/env node
/** Build a compact ticker → CIK map from company JSON. Does not change financial facts. */
import { createReadStream } from "node:fs";
import { readdir, writeFile } from "node:fs/promises";
import { createInterface } from "node:readline";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const companiesDir = join(root, "public/data/companies");
const outPath = join(root, "public/data/issuers.json");

async function readHead(path, maxLines = 16) {
  const lines = [];
  const rl = createInterface({ input: createReadStream(path, { encoding: "utf8" }), crlfDelay: Infinity });
  for await (const line of rl) {
    lines.push(line);
    if (lines.length >= maxLines) {
      rl.close();
      break;
    }
  }
  return lines.join("\n");
}

const files = (await readdir(companiesDir)).filter((f) => f.endsWith(".json")).sort();
const byTicker = {};
for (const file of files) {
  const head = await readHead(join(companiesDir, file));
  const ticker = /"ticker":\s*"([^"]+)"/.exec(head)?.[1];
  const cikRaw = /"cik":\s*("([^"]*)"|null)/.exec(head);
  if (!ticker) continue;
  byTicker[ticker] = cikRaw?.[2] ?? null;
}

const payload = { schemaVersion: 1, byTicker };
await writeFile(outPath, `${JSON.stringify(payload)}\n`);
console.log(`Wrote ${Object.keys(byTicker).length} issuers to ${outPath}`);

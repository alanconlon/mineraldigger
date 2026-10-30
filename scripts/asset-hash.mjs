import { createHash } from "node:crypto";
import { readdir, readFile, stat } from "node:fs/promises";
import { join, relative } from "node:path";

// Built files whose bytes decide the service worker cache name.
// HTML and sw.js are stamped with the hash, so they are not part of it.
const ASSET_PATHS = [
  "site.css",
  "pwa.js",
  "favicon.svg",
  "favicon.ico",
  "apple-touch-icon.png",
  "og-image.jpg",
  "logo.png",
  "manifest.webmanifest",
  "js",
  "fonts",
  "vendor",
  "icons",
];

const TEXT = new Set([".css", ".js", ".svg", ".webmanifest"]);

async function filesUnder(path, out) {
  const info = await stat(path);
  if (info.isDirectory()) {
    for (const name of await readdir(path)) await filesUnder(join(path, name), out);
    return;
  }
  if (info.isFile()) out.push(path);
}

function canonical(name, bytes) {
  const ext = name.slice(name.lastIndexOf("."));
  if (!TEXT.has(ext)) return bytes;
  return Buffer.from(bytes.toString("utf8").replace(/\?v=[0-9a-f]{12}/g, ""));
}

export async function assetHash(dist) {
  const files = [];
  for (const rel of ASSET_PATHS) await filesUnder(join(dist, rel), files);
  files.sort((a, b) => (a < b ? -1 : a > b ? 1 : 0));
  const hash = createHash("sha256");
  for (const file of files) {
    const name = relative(dist, file).split("\\").join("/");
    hash.update(name);
    hash.update("\0");
    hash.update(canonical(name, await readFile(file)));
    hash.update("\0");
  }
  return hash.digest("hex").slice(0, 12);
}

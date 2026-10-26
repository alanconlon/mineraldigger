import { createReadStream, createWriteStream } from "node:fs";
import { access, mkdir, stat } from "node:fs/promises";
import { createServer } from "node:http";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { validateSubmission } from "../functions/api/validate.js";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const dist = join(root, "dist");
const inbox = join(root, "data/inbox");
const port = Number(process.env.PORT || 4317);
const host = process.env.HOST || "0.0.0.0";

const types = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
  ".ics": "text/calendar; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".png": "image/png",
};

function send(response, status, body, type = "application/json; charset=utf-8") {
  response.writeHead(status, { "content-type": type });
  response.end(body);
}

async function readBody(request) {
  const chunks = [];
  let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 100_000) throw new Error("too large");
    chunks.push(chunk);
  }
  return Buffer.concat(chunks).toString("utf8");
}

async function saveLocal(clean) {
  await mkdir(inbox, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const file = join(inbox, `${stamp}.json`);
  await new Promise((resolve, reject) => {
    const stream = createWriteStream(file, { flags: "wx" });
    stream.on("error", reject);
    stream.end(JSON.stringify(clean, null, 2));
    stream.on("finish", resolve);
  });
}

async function handleSubmit(request, response) {
  let body;
  try {
    body = JSON.parse(await readBody(request));
  } catch {
    return send(response, 400, JSON.stringify({ ok: false, errors: ["Send the listing as JSON."] }));
  }
  const result = validateSubmission(body);
  if (!result.ok) return send(response, 400, JSON.stringify({ ok: false, errors: result.errors }));
  if (result.spam) return send(response, 200, JSON.stringify({ ok: true, delivery: "accepted" }));
  const hook = process.env.SUBMISSION_WEBHOOK_URL;
  if (hook) {
    const forwarded = await fetch(hook, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(result.clean),
    });
    if (!forwarded.ok) return send(response, 502, JSON.stringify({ ok: false, errors: ["The listing webhook did not accept it."] }));
    return send(response, 200, JSON.stringify({ ok: true, delivery: "forwarded" }));
  }
  await saveLocal(result.clean);
  return send(response, 200, JSON.stringify({ ok: true, delivery: "saved_local" }));
}

async function fileFor(urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0]);
  const safe = normalize(decoded).replace(/^(\.\.(\/|\\|$))+/, "");
  let path = join(dist, safe);
  if (!path.startsWith(dist)) return null;
  try {
    const info = await stat(path);
    if (info.isDirectory()) path = join(path, "index.html");
    await access(path);
    return path;
  } catch {
    return null;
  }
}

const server = createServer(async (request, response) => {
  try {
    const url = new URL(request.url || "/", `http://${request.headers.host || "localhost"}`);
    if (request.method === "POST" && url.pathname === "/api/submit") {
      return await handleSubmit(request, response);
    }
    if (request.method !== "GET" && request.method !== "HEAD") {
      return send(response, 405, JSON.stringify({ ok: false, errors: ["Method not allowed."] }));
    }
    const path = (await fileFor(url.pathname)) || join(dist, "404.html");
    const status = path.endsWith("404.html") && url.pathname !== "/404.html" ? 404 : 200;
    const type = types[extname(path)] || "application/octet-stream";
    response.writeHead(status, { "content-type": type });
    if (request.method === "HEAD") return response.end();
    createReadStream(path).pipe(response);
  } catch (error) {
    console.error(error);
    send(response, 500, JSON.stringify({ ok: false, errors: ["The server hit an error."] }));
  }
});

server.listen(port, host, () => {
  console.log(`MineralDigger at http://127.0.0.1:${port}`);
});

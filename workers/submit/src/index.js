import { validateSubmission } from "../../../functions/api/validate.js";
import { connectingIp, turnstilePasses, TURNSTILE_ERROR } from "../../../functions/api/turnstile.js";

export const MINERALDIGGER_SUBMIT_TO = "mineraldigger.hq@gmail.com";
export const MINERALDIGGER_SUBMIT_FROM = "submissions@mineraldigger.com";

export const ALLOWED_ORIGINS = new Set([
  "https://mineraldigger.com",
  "https://www.mineraldigger.com",
  "https://mineraldigger.co.uk",
  "https://www.mineraldigger.co.uk",
]);

// About 5 listings per 10 minutes in this isolate. The binding period can
// only be 10 or 60 seconds, so this window still applies when that binding
// would allow another burst, and when the binding is missing.
const WINDOW_MS = 10 * 60 * 1000;
const MAX_IN_WINDOW = 5;
const hits = new Map();

export function resetRateLimit() {
  hits.clear();
}

function json(body, status, origin) {
  const headers = {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  };
  if (origin) {
    headers["access-control-allow-origin"] = origin;
    headers.vary = "Origin";
  }
  return new Response(JSON.stringify(body), { status, headers });
}

function originDecision(request) {
  const origin = request.headers.get("Origin");
  if (!origin) return { ok: true, origin: null };
  if (ALLOWED_ORIGINS.has(origin)) return { ok: true, origin };
  return { ok: false, origin };
}

function clientIp(request) {
  return request.headers.get("cf-connecting-ip") || request.headers.get("x-forwarded-for") || "unknown";
}

function memoryLimited(ip) {
  const now = Date.now();
  const recent = (hits.get(ip) || []).filter((at) => now - at < WINDOW_MS);
  if (recent.length >= MAX_IN_WINDOW) {
    hits.set(ip, recent);
    return true;
  }
  recent.push(now);
  hits.set(ip, recent);
  return false;
}

async function limited(request, env) {
  const ip = clientIp(request);
  if (env.SUBMIT_LIMIT && typeof env.SUBMIT_LIMIT.limit === "function") {
    const result = await env.SUBMIT_LIMIT.limit({ key: ip });
    if (result && result.success === false) return true;
  }
  return memoryLimited(ip);
}

function listingText(clean) {
  const lines = [
    "MineralDigger show listing",
    `Organiser: ${clean.organiser_name}`,
    `Email: ${clean.email}`,
    clean.phone ? `Phone: ${clean.phone}` : "",
    `Show: ${clean.show_name}`,
    clean.website ? `Website: ${clean.website}` : "",
    `Types: ${clean.types.join(", ")}`,
    `Dates: ${clean.start_date} to ${clean.end_date}`,
    clean.times ? `Times: ${clean.times}` : "",
    `Venue: ${clean.venue_name}`,
    clean.street ? `Street: ${clean.street}` : "",
    `Town: ${clean.town}`,
    `Postcode: ${clean.postcode}`,
    `Entry: ${clean.entry_kind}${clean.entry_price ? ` £${clean.entry_price}` : ""}`,
    clean.entry_notes ? `Entry notes: ${clean.entry_notes}` : "",
    clean.notes ? `Notes: ${clean.notes}` : "",
  ];
  return lines.filter(Boolean).join("\n");
}

function mailFailureIsUnconfigured(error) {
  const message = String(error && error.message ? error.message : error).toLowerCase();
  return /not verified|unverified|destination|routing|not configured|no such|binding|sender/.test(message);
}

export default {
  async fetch(request, env) {
    const decision = originDecision(request);
    if (!decision.ok) return json({ ok: false, error: "Bad origin." }, 403, null);

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: {
          "access-control-allow-origin": decision.origin || "",
          "access-control-allow-methods": "POST",
          "access-control-allow-headers": "Content-Type",
          vary: "Origin",
          "cache-control": "no-store",
        },
      });
    }

    if (request.method !== "POST") return json({ ok: false, error: "POST only." }, 405, decision.origin);

    const length = Number(request.headers.get("content-length") || 0);
    if (length > 20_000) return json({ ok: false, error: "That listing is too long." }, 413, decision.origin);

    let body;
    try {
      body = await request.json();
    } catch {
      return json({ ok: false, error: "Couldn't read the form." }, 400, decision.origin);
    }

    const result = validateSubmission(body);
    if (result.spam) return json({ ok: true, delivery: "accepted" }, 200, decision.origin);
    if (!result.ok) {
      return json({ ok: false, error: result.errors[0], errors: result.errors }, 400, decision.origin);
    }

    // After the honeypot, before the rate limit and the email. A missing
    // secret, a bad token, or a siteverify failure all refuse the listing.
    const allowed = await turnstilePasses(body["cf-turnstile-response"], connectingIp(request), env);
    if (!allowed) return json({ ok: false, error: TURNSTILE_ERROR }, 403, decision.origin);

    if (await limited(request, env)) {
      return json(
        { ok: false, error: "Too many listings from this network. Try again later." },
        429,
        decision.origin,
      );
    }

    const to = (env && env.MINERALDIGGER_SUBMIT_TO) || MINERALDIGGER_SUBMIT_TO;
    const from = (env && env.MINERALDIGGER_SUBMIT_FROM) || MINERALDIGGER_SUBMIT_FROM;
    const text = listingText(result.clean);
    const message = {
      to,
      from: { email: from, name: "MineralDigger" },
      replyTo: result.clean.email,
      subject: `MineralDigger listing: ${result.clean.show_name}`,
      text,
    };

    if (!env || !env.SEND_EMAIL || typeof env.SEND_EMAIL.send !== "function") {
      return json({ ok: true, delivery: "unconfigured" }, 200, decision.origin);
    }

    try {
      await env.SEND_EMAIL.send(message);
    } catch (error) {
      if (mailFailureIsUnconfigured(error)) return json({ ok: true, delivery: "unconfigured" }, 200, decision.origin);
      return json({ ok: false, error: "The listing could not be emailed." }, 502, decision.origin);
    }

    return json({ ok: true, delivery: "emailed" }, 200, decision.origin);
  },
};

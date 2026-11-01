// Shared by the submit Worker and the Pages fallback.
// TURNSTILE_SECRET_KEY is a Worker secret. Do not write the value here.

export const TURNSTILE_ACTION = "submit";
export const TURNSTILE_ERROR = "The security check did not pass. Please try again.";

const SITEVERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify";

// Hostnames the submit form is served on. Local preview is not in this set.
export const TURNSTILE_HOSTS = new Set([
  "mineraldigger.com",
  "www.mineraldigger.com",
  "mineraldigger.co.uk",
  "www.mineraldigger.co.uk",
]);

function usableSecret(env) {
  const secret = env && env.TURNSTILE_SECRET_KEY;
  return typeof secret === "string" && secret.length > 0 ? secret : "";
}

export function connectingIp(request) {
  const ip = request && request.headers ? request.headers.get("CF-Connecting-IP") : "";
  if (typeof ip !== "string") return "";
  const trimmed = ip.trim();
  if (!trimmed || trimmed.length > 128 || /[\s,]/.test(trimmed)) return "";
  return trimmed;
}

export async function turnstilePasses(token, remoteip, env) {
  const secret = usableSecret(env);
  if (!secret) return false;
  if (typeof token !== "string" || token.length === 0 || token.length > 2048) return false;
  if (typeof remoteip !== "string" || remoteip.length === 0 || remoteip.length > 128) return false;

  let result;
  try {
    const response = await fetch(SITEVERIFY_URL, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      signal: AbortSignal.timeout(10_000),
      body: new URLSearchParams({
        secret,
        response: token,
        remoteip,
      }),
    });
    if (!response.ok) return false;
    result = await response.json();
  } catch {
    return false;
  }

  return Boolean(
    result &&
      result.success === true &&
      result.action === TURNSTILE_ACTION &&
      TURNSTILE_HOSTS.has(result.hostname),
  );
}

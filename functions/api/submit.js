// Pages fallback for /api/submit when the zone route is not attached.
// Production mail is workers/submit (Cloudflare send_email). That route wins on the custom domains.
import { validateSubmission } from "./validate.js";

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

export async function onRequestPost(context) {
  let body;
  try {
    body = await context.request.json();
  } catch {
    return json({ ok: false, errors: ["Send the listing as JSON."] }, 400);
  }
  const result = validateSubmission(body);
  if (!result.ok) return json({ ok: false, errors: result.errors }, 400);
  if (result.spam) return json({ ok: true, delivery: "accepted" });

  const hook = context.env && context.env.SUBMISSION_WEBHOOK_URL;
  if (!hook) return json({ ok: true, delivery: "unconfigured" });

  try {
    const response = await fetch(hook, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(result.clean),
    });
    if (!response.ok) return json({ ok: false, errors: ["The listing webhook did not accept it."] }, 502);
  } catch {
    return json({ ok: false, errors: ["The listing webhook could not be reached."] }, 502);
  }
  return json({ ok: true, delivery: "forwarded" });
}

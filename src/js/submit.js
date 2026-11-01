import { validateSubmission } from "./validate.js";

const TURNSTILE_SITEKEY = "0x4AAAAAAFvgWt9D_bkbp5-h";
const form = document.getElementById("submit-form");
let widgetId;

function renderWidget() {
  const slot = document.getElementById("submit-turnstile");
  if (!slot || widgetId !== undefined || !window.turnstile) return;
  widgetId = window.turnstile.render(slot, {
    sitekey: TURNSTILE_SITEKEY,
    action: "submit",
    "error-callback"() {
      return true;
    },
  });
}

function resetWidget() {
  if (widgetId === undefined || !window.turnstile || typeof window.turnstile.reset !== "function") return;
  window.turnstile.reset(widgetId);
}

function turnstileToken() {
  if (widgetId === undefined || !window.turnstile || typeof window.turnstile.getResponse !== "function") return "";
  const value = window.turnstile.getResponse(widgetId);
  return typeof value === "string" ? value : "";
}

// The local inbox does not call Turnstile. Production still checks the token.
function localPreview() {
  const host = window.location.hostname;
  return host === "localhost" || host === "127.0.0.1";
}

if (form) {
  window.mdRenderSubmitTurnstile = renderWidget;
  renderWidget();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errors = document.getElementById("form-errors");
    const ok = document.getElementById("form-ok");
    errors.hidden = true;
    ok.hidden = true;
    const data = new FormData(form);
    const token = turnstileToken();
    const body = {
      organiser_name: data.get("organiser_name"),
      email: data.get("email"),
      phone: data.get("phone"),
      show_name: data.get("show_name"),
      website: data.get("website"),
      types: data.getAll("types"),
      start_date: data.get("start_date"),
      end_date: data.get("end_date"),
      times: data.get("times"),
      venue_name: data.get("venue_name"),
      street: data.get("street"),
      town: data.get("town"),
      postcode: data.get("postcode"),
      entry_kind: data.get("entry_kind"),
      entry_price: data.get("entry_price"),
      entry_notes: data.get("entry_notes"),
      notes: data.get("notes"),
      confirm_permission: data.get("confirm_permission") ? "yes" : "",
      confirm_scope: data.get("confirm_scope") ? "yes" : "",
      company_website: data.get("company_website"),
      "cf-turnstile-response": token,
    };
    const checked = validateSubmission(body);
    if (!checked.ok) {
      showErrors(errors, checked.errors);
      return;
    }
    if (!token && !localPreview() && !checked.spam) {
      showErrors(errors, ["Please complete the security check, then send the listing again."]);
      resetWidget();
      return;
    }
    let response;
    try {
      response = await fetch("/api/submit", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      let payload = {};
      try {
        payload = await response.json();
      } catch {
        payload = {};
      }
      if (!response.ok || payload.ok === false) {
        const list = payload.errors || (payload.error ? [payload.error] : ["The listing was not accepted."]);
        showErrors(errors, list);
        return;
      }
      const receipt = receiptText(checked.clean || body);
      const line = document.getElementById("ok-line");
      const box = document.getElementById("receipt");
      if (payload.delivery === "saved_local") {
        line.textContent = "Saved in the local inbox on this machine. It has not been emailed.";
      } else if (payload.delivery === "emailed" || payload.delivery === "forwarded" || payload.delivery === "accepted") {
        line.textContent = "Sent. We check the organiser site before a show goes on the map.";
      } else {
        line.innerHTML = 'Mail is not connected on this host yet. Copy the listing below and send it to <a href="mailto:hello@mineraldigger.com">hello@mineraldigger.com</a>. Nothing was stored on the server.';
      }
      box.value = receipt;
      ok.hidden = false;
      ok.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch {
      showErrors(errors, ["The form could not be sent from this browser."]);
    } finally {
      resetWidget();
    }
  });
}

function showErrors(node, list) {
  node.hidden = false;
  node.innerHTML = `<p>Check these and try again.</p><ul>${list.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  node.scrollIntoView({ behavior: "smooth", block: "start" });
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function receiptText(clean) {
  const lines = [
    "MineralDigger show listing",
    `Organiser: ${clean.organiser_name || ""}`,
    `Email: ${clean.email || ""}`,
    clean.phone ? `Phone: ${clean.phone}` : "",
    `Show: ${clean.show_name || ""}`,
    clean.website ? `Website: ${clean.website}` : "",
    `Types: ${(clean.types || []).join(", ")}`,
    `Dates: ${clean.start_date || ""} to ${clean.end_date || ""}`,
    clean.times ? `Times: ${clean.times}` : "",
    `Venue: ${clean.venue_name || ""}`,
    clean.street ? `Street: ${clean.street}` : "",
    `Town: ${clean.town || ""}`,
    `Postcode: ${clean.postcode || ""}`,
    `Entry: ${clean.entry_kind || ""}${clean.entry_price ? ` £${clean.entry_price}` : ""}`,
    clean.entry_notes ? `Entry notes: ${clean.entry_notes}` : "",
    clean.notes ? `Notes: ${clean.notes}` : "",
  ];
  return lines.filter(Boolean).join("\n");
}

const TYPES = ["rock", "gem", "mineral", "fossil", "bead"];
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function normalisePostcode(value) {
  const compact = String(value || "").toUpperCase().replace(/\s+/g, "");
  const match = compact.match(/^([A-Z]{1,2}\d[A-Z\d]?)(\d[A-Z]{2})$/);
  if (!match) return null;
  return `${match[1]} ${match[2]}`;
}

function text(body, key) {
  return String(body[key] ?? "").trim().replace(/\s+/g, " ");
}

export function validateSubmission(body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return { ok: false, errors: ["The form was empty."] };
  }
  if (text(body, "company_website")) {
    return { ok: true, spam: true, clean: null };
  }

  const errors = [];
  const clean = {};
  const take = (key, label, max, required) => {
    const value = text(body, key);
    if (!value) {
      if (required) errors.push(`${label} is required.`);
      return;
    }
    if (value.length > max) {
      errors.push(`${label} is too long.`);
      return;
    }
    clean[key] = value;
  };

  take("organiser_name", "Organiser name", 120, true);
  take("email", "Email", 160, true);
  if (clean.email && !EMAIL.test(clean.email)) errors.push("Email does not look right.");
  take("phone", "Phone", 40, false);
  take("show_name", "Show name", 160, true);
  take("website", "Website", 300, false);
  if (clean.website && !/^https?:\/\//i.test(clean.website)) {
    errors.push("Website should start with http:// or https://.");
  }

  const incoming = Array.isArray(body.types) ? body.types : [];
  const types = [...new Set(incoming.filter((item) => TYPES.includes(item)))];
  if (!types.length) errors.push("Choose at least one of rock, gem, mineral, fossil or bead.");
  else clean.types = types;

  take("start_date", "Start date", 10, true);
  take("end_date", "End date", 10, true);
  if (clean.start_date && !/^\d{4}-\d{2}-\d{2}$/.test(clean.start_date)) errors.push("Start date should be YYYY-MM-DD.");
  if (clean.end_date && !/^\d{4}-\d{2}-\d{2}$/.test(clean.end_date)) errors.push("End date should be YYYY-MM-DD.");
  if (clean.start_date && clean.end_date && clean.end_date < clean.start_date) {
    errors.push("The end date is before the start date.");
  }

  take("times", "Opening times", 200, false);
  take("venue_name", "Venue", 160, true);
  take("street", "Street", 160, false);
  take("town", "Town", 80, true);
  const postcode = normalisePostcode(text(body, "postcode"));
  if (!postcode) errors.push("Postcode does not look like a UK postcode.");
  else clean.postcode = postcode;

  const kind = text(body, "entry_kind");
  if (!["free", "paid", "unknown"].includes(kind)) errors.push("Choose free, a price, or unknown for entry.");
  else clean.entry_kind = kind;
  if (kind === "paid") {
    const price = text(body, "entry_price");
    if (!/^\d{1,3}$/.test(price) || Number(price) <= 0) errors.push("Enter the adult price in pounds, as a whole number.");
    else clean.entry_price = Number(price);
  }

  take("entry_notes", "Entry notes", 300, false);
  take("notes", "Notes", 2000, false);

  const permission = body.confirm_permission === true || body.confirm_permission === "yes";
  const scope = body.confirm_scope === true || body.confirm_scope === "yes";
  if (!permission) errors.push("Confirm you can send this listing.");
  if (!scope) errors.push("Confirm this is a rock, gem, mineral, fossil or bead show.");
  if (permission) clean.confirm_permission = true;
  if (scope) clean.confirm_scope = true;

  return { ok: errors.length === 0, errors, clean: errors.length ? null : clean };
}

export function featuredIds(shows, featured, todayISO) {
  const ids = new Set();
  for (const row of featured.shows || []) {
    if (row && row.id && row.until >= todayISO) ids.add(row.id);
  }
  const organisers = new Set(
    (featured.organisers || [])
      .filter((row) => row && row.id && row.until >= todayISO)
      .map((row) => row.id),
  );
  for (const show of shows) {
    if (organisers.has(show.organiser.id) && show.end >= todayISO) ids.add(show.id);
  }
  return ids;
}

export function stripeReady(url) {
  return typeof url === "string" && url.trim().startsWith("https://");
}

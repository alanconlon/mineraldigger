export const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

export const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];
const SHORT_WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function parseISO(value) {
  const [year, month, day] = value.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function iso(date) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function addDays(date, count) {
  const copy = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  copy.setDate(copy.getDate() + count);
  return copy;
}

export function formatDay(value) {
  const date = typeof value === "string" ? parseISO(value) : value;
  return `${WEEKDAYS[date.getDay()]} ${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

export function formatRange(start, end) {
  if (start === end) return formatDay(start);
  return `${formatDay(start)} to ${formatDay(end)}`;
}

export function monthLabel(start) {
  const date = parseISO(start);
  return `${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

export function monthKey(start) {
  return start.slice(0, 7);
}

export function shortStack(start, end) {
  const open = parseISO(start);
  const close = parseISO(end);
  const span = start === end
    ? ""
    : `to ${SHORT_WEEKDAYS[close.getDay()]} ${close.getDate()} ${SHORT_MONTHS[close.getMonth()]}`;
  return {
    wd: SHORT_WEEKDAYS[open.getDay()],
    day: String(open.getDate()),
    mon: SHORT_MONTHS[open.getMonth()],
    span,
  };
}

export function thisWeekend(today) {
  const day = today.getDay();
  let friday = today;
  if (day === 6) friday = addDays(today, -1);
  else if (day === 0) friday = addDays(today, -2);
  else if (day === 5) friday = today;
  else friday = addDays(today, 5 - day);
  return { start: iso(friday), end: iso(addDays(friday, 2)) };
}

export function digestWeekend(today) {
  const day = today.getDay();
  let friday;
  if (day === 6) friday = addDays(today, 6);
  else if (day === 0) friday = addDays(today, 5);
  else if (day === 5) friday = today;
  else friday = addDays(today, 5 - day);
  return { start: iso(friday), end: iso(addDays(friday, 2)) };
}

export function overlaps(show, start, end) {
  return show.start <= end && show.end >= start;
}

export function comingLater(show, weekendEnd) {
  return show.start > weekendEnd;
}

const LONG_DATE = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

const DAY_MONTH = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "long",
  timeZone: "UTC",
});

/** Postgres hands back "2026-03-24"; read it as a date, not a moment in the local zone. */
function asDate(iso: string): Date {
  return new Date(`${iso}T00:00:00Z`);
}

export function formatDate(iso: string): string {
  return LONG_DATE.format(asDate(iso));
}

/** "26 March and 17 September 2026", dropping the year where it would repeat. */
export function formatRange(from: string, to: string): string {
  const sameYear = from.slice(0, 4) === to.slice(0, 4);
  const start = sameYear ? DAY_MONTH.format(asDate(from)) : LONG_DATE.format(asDate(from));
  return `${start} and ${LONG_DATE.format(asDate(to))}`;
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** en-US writes each currency with the symbol its readers expect: $, £, €, not "US$". */
export function money(value: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatMetric(value) {
  const number = Number(value || 0);
  if (number >= 1_000_000) return `${trimMetric(number / 1_000_000)}M`;
  if (number >= 1_000) return `${trimMetric(number / 1_000)}K`;
  return String(number);
}

function trimMetric(value) {
  return value.toFixed(value >= 10 ? 0 : 1).replace(/\.0$/, "");
}

export function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}


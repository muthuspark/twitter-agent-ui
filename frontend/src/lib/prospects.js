export const draftKey = (runId, url) => `twitter-workbench:prospect-draft:v1:${runId}:${url}`;

export function isRedditPost(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && ["reddit.com", "www.reddit.com", "old.reddit.com"].includes(parsed.hostname)
      && !parsed.username && !parsed.password && !parsed.port
      && /^\/r\/[^/]+\/comments\/[a-z0-9]+(?:\/|$)/i.test(parsed.pathname);
  } catch { return false; }
}

export const publicationBlocksPosting = publication => ["pending", "posted", "uncertain"].includes(publication?.status);

export function readRecovery(storage, key) {
  try {
    const value = JSON.parse(storage.getItem(key));
    return typeof value?.text === "string" ? value.text : null;
  } catch { return null; }
}

export function saveRecovery(storage, key, text) {
  storage.setItem(key, JSON.stringify({ text }));
}

export function clearRecovery(storage, key, savedText) {
  // A delayed save must not erase a newer edit made while the request was in flight.
  if (readRecovery(storage, key) === savedText) storage.removeItem(key);
}

export function sortProspects(posts, order) {
  const date = post => Date.parse(post.published_at) || 0;
  const fit = post => post.coverage_checked ? Number(post.coverage) : -1;
  return [...posts].sort((a, b) => {
    if (order === "newest") return date(b) - date(a) || fit(b) - fit(a);
    if (order === "signal") return b.confidence - a.confidence || fit(b) - fit(a);
    return fit(b) - fit(a) || b.confidence - a.confidence || date(b) - date(a);
  });
}

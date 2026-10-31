export function mergeFeedPage(existing, page, requestedCursor, visitedCursors = new Set()) {
  const tweets = [...existing];
  const ids = new Set(existing.map((tweet) => String(tweet.id)));
  for (const tweet of page.tweets ?? []) {
    if (!tweet?.id || ids.has(String(tweet.id))) continue;
    ids.add(String(tweet.id));
    tweets.push(tweet);
  }
  const nextCursor = page.next_cursor || null;
  const hasMore = Boolean(page.has_more && nextCursor && nextCursor !== requestedCursor && !visitedCursors.has(nextCursor));
  return { tweets, added: tweets.length - existing.length, nextCursor: hasMore ? nextCursor : null, hasMore };
}

export function safeMediaUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" ? parsed.href : "";
  } catch {
    return "";
  }
}

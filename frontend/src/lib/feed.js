import { buildTweetActionPayload } from "./workbench";

export function isEnglishFeedPost(tweet) {
  const isEnglish = (language) => typeof language === "string" && language.trim().toLowerCase() === "en";
  return isEnglish(tweet?.lang) && (!tweet.quotedTweet?.text || isEnglish(tweet.quotedTweet.lang));
}

export async function submitFeedAction(tweet, action, request = fetch) {
  if (!tweet?.id || !["like", "bookmark"].includes(action)) throw new Error("Choose a valid post action.");
  const response = await request("/api/growth/approve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(buildTweetActionPayload(tweet, action)),
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.ok !== true || body.record?.result?.ok === false) {
    throw new Error(body.detail || `Unable to ${action} this post. Please try again.`);
  }
  return body;
}

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

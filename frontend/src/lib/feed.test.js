import { describe, expect, it } from "vitest";
import { isEnglishFeedPost, mediaAltText, mergeFeedPage, safeMediaUrl, submitFeedAction } from "./feed";

describe("English-only feed", () => {
  it("accepts English-labelled posts", () => {
    expect(isEnglishFeedPost({ lang: "en", text: "Hello" })).toBe(true);
    expect(isEnglishFeedPost({ lang: " EN " })).toBe(true);
  });

  it.each(["hi", "ta", "es", "fr", "tr", "und", "", null, undefined])("excludes other or unknown language %s", (lang) => {
    expect(isEnglishFeedPost({ lang })).toBe(false);
  });

  it("excludes English posts that quote non-English or unlabelled text", () => {
    expect(isEnglishFeedPost({ lang: "en", quotedTweet: { text: "Hello", lang: "en" } })).toBe(true);
    expect(isEnglishFeedPost({ lang: "en", quotedTweet: { text: "नमस्ते", lang: "hi" } })).toBe(false);
    expect(isEnglishFeedPost({ lang: "en", quotedTweet: { text: "Unknown language" } })).toBe(false);
  });
});

describe("feed actions", () => {
  it.each(["like", "bookmark"])("submits %s with source context for preference history", async (action) => {
    const tweet = { id: "123", text: "A post I want to save", author: { name: "Author" }, createdAtISO: "2026-10-31T12:00:00Z" };
    let payload;
    await submitFeedAction(tweet, action, async (path, options) => {
      expect(path).toBe("/api/growth/approve");
      expect(options.method).toBe("POST");
      payload = JSON.parse(options.body);
      return { ok: true, json: async () => ({ ok: true, record: { result: { ok: true } } }) };
    });
    expect(payload.action).toBe(action);
    expect(payload.tweet_id).toBe("123");
    expect(payload.metadata.source_tweet.text).toBe(tweet.text);
    expect(payload.metadata.source_tweet.createdAtISO).toBe(tweet.createdAtISO);
  });

  it("surfaces API errors so the row can be retried", async () => {
    await expect(submitFeedAction({ id: "1" }, "like", async () => ({ ok: false, json: async () => ({ detail: "Rate limited" }) }))).rejects.toThrow("Rate limited");
  });

  it("does not report success when the CLI reports failure", async () => {
    await expect(submitFeedAction({ id: "1" }, "bookmark", async () => ({ ok: true, json: async () => ({ ok: true, record: { result: { ok: false } } }) }))).rejects.toThrow("Unable to bookmark");
  });

  it("rejects unsupported actions before sending a request", async () => {
    await expect(submitFeedAction({ id: "1" }, "delete", () => { throw new Error("Must not run"); })).rejects.toThrow("valid post action");
  });
});

describe("feed pagination", () => {
  it("appends new posts in order and removes overlap within and across pages", () => {
    const page = mergeFeedPage([{ id: "1" }], { tweets: [{ id: "1" }, { id: "2" }, { id: "2" }, { id: "3" }], next_cursor: "next", has_more: true }, "current");
    expect(page.tweets.map((tweet) => tweet.id)).toEqual(["1", "2", "3"]);
    expect(page.added).toBe(2);
    expect(page.hasMore).toBe(true);
  });

  it("continues through an empty page when Twitter supplies a fresh cursor", () => {
    const page = mergeFeedPage([{ id: "1" }], { tweets: [], next_cursor: "next", has_more: true }, "current");
    expect(page.tweets).toEqual([{ id: "1" }]);
    expect(page.nextCursor).toBe("next");
    expect(page.hasMore).toBe(true);
  });

  it.each([null, "current", "visited"])("stops on absent or looping cursor %s", (cursor) => {
    const page = mergeFeedPage([], { tweets: [], next_cursor: cursor, has_more: true }, "current", new Set(["visited"]));
    expect(page.hasMore).toBe(false);
    expect(page.nextCursor).toBeNull();
  });

  it("stops when Twitter indicates the end", () => {
    expect(mergeFeedPage([], { tweets: [], next_cursor: "next", has_more: false }, null).hasMore).toBe(false);
  });
});

describe("feed media", () => {
  it("uses author descriptions across supported media payloads", () => {
    for (const key of ["altText", "alt_text", "ext_alt_text", "description"]) {
      expect(mediaAltText({ [key]: "  A chart of monthly revenue  " })).toBe("A chart of monthly revenue");
    }
  });

  it("labels undescribed images without inventing their contents", () => {
    expect(mediaAltText({ altText: " ", alt_text: 42 }, 1)).toBe("Image 2. No description provided.");
  });

  it("accepts HTTPS images and rejects unsafe or malformed URLs", () => {
    expect(safeMediaUrl("https://pbs.twimg.com/media/example.jpg")).toBe("https://pbs.twimg.com/media/example.jpg");
    for (const url of ["javascript:alert(1)", "data:image/svg+xml,bad", "http://example.com/image.jpg", "bad"]) expect(safeMediaUrl(url)).toBe("");
  });
});

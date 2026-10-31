import { describe, expect, it } from "vitest";
import { mergeFeedPage, safeMediaUrl } from "./feed";

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
  it("accepts HTTPS images and rejects unsafe or malformed URLs", () => {
    expect(safeMediaUrl("https://pbs.twimg.com/media/example.jpg")).toBe("https://pbs.twimg.com/media/example.jpg");
    for (const url of ["javascript:alert(1)", "data:image/svg+xml,bad", "http://example.com/image.jpg", "bad"]) expect(safeMediaUrl(url)).toBe("");
  });
});

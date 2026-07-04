import { describe, expect, test } from "vitest";

import {
  buildCommandPreview,
  buildGrowthActionPayload,
  buildTweetLikePayload,
  combinedGrowthButtonState,
  buildRecommendationMetadata,
  formatMetric,
  loadWorkbenchCache,
  saveWorkbenchCache,
  growthActionLabel,
  normalizeRecommendations,
  normalizeResult,
  tweetUrl,
} from "./workbench";

describe("buildCommandPreview", () => {
  test("renders quoted search queries and max options", () => {
    const preset = {
      id: "search",
      fields: [
        { name: "query", type: "text" },
        { name: "max", type: "number", default: 20 },
      ],
    };

    expect(buildCommandPreview(preset, { query: "ai agents", max: 12 })).toBe(
      'twitter search "ai agents" --max 12 --json',
    );
  });
});

describe("formatMetric", () => {
  test("formats compact values for large counts", () => {
    expect(formatMetric(999)).toBe("999");
    expect(formatMetric(1200)).toBe("1.2K");
    expect(formatMetric(4800000)).toBe("4.8M");
  });
});

describe("normalizeResult", () => {
  test("extracts tweet arrays from cli response envelope", () => {
    const result = normalizeResult({
      ok: true,
      data: {
        ok: true,
        data: [
          {
            id: "1",
            text: "hello",
            author: { name: "Ada", screenName: "ada" },
            metrics: { likes: 4 },
          },
        ],
      },
    });

    expect(result.kind).toBe("tweets");
    expect(result.items).toHaveLength(1);
    expect(result.items[0].author.screenName).toBe("ada");
  });

  test("keeps non-array payloads as json", () => {
    const result = normalizeResult({ ok: true, data: { authenticated: true } });

    expect(result.kind).toBe("json");
    expect(result.value).toEqual({ authenticated: true });
  });
});

describe("normalizeRecommendations", () => {
  test("joins recommendations to candidate tweet details", () => {
    const recommendations = normalizeRecommendations(
      [
        {
          id: 1,
          tweet_id: "123",
          action: "comment",
          confidence: 80,
          reason: "Good AI founder fit.",
          comment_drafts: [
            "Evals are the bottleneck.",
            "Start by mapping failure cases.",
            "Agent loops need product judgment.",
          ],
          risk: "low",
        },
      ],
      [{ id: "123", text: "AI agents", author: { screenName: "ada" } }],
    );

    expect(recommendations[0].tweet.text).toBe("AI agents");
    expect(recommendations[0].actionLabel).toBe("Comment");
    expect(recommendations[0].draftOptions).toHaveLength(3);
    expect(recommendations[0].draft).toBe("Evals are the bottleneck.");
    expect(recommendations[0].postUrl).toBe("https://x.com/ada/status/123");
  });

  test("hides skip recommendations from the action queue", () => {
    const recommendations = normalizeRecommendations(
      [
        {
          id: 1,
          tweet_id: "skip-me",
          action: "skip",
          confidence: 95,
          reason: "Good skip decision.",
          risk: "low",
        },
        {
          id: 2,
          tweet_id: "like-me",
          action: "like",
          confidence: 75,
          reason: "Worth a like.",
          risk: "low",
        },
      ],
      [
        { id: "skip-me", text: "Skip", author: { screenName: "skip" } },
        { id: "like-me", text: "Like", author: { screenName: "like" } },
      ],
    );

    expect(recommendations).toHaveLength(1);
    expect(recommendations[0].tweet_id).toBe("like-me");
  });
});

describe("growthActionLabel", () => {
  test("formats supported action labels", () => {
    expect(growthActionLabel("like")).toBe("Like");
    expect(growthActionLabel("comment")).toBe("Comment");
    expect(growthActionLabel("skip")).toBe("Skip");
  });
});

describe("tweetUrl", () => {
  test("uses author handle when available", () => {
    expect(tweetUrl({ id: "123", author: { screenName: "ada" } })).toBe(
      "https://x.com/ada/status/123",
    );
  });
});

describe("buildRecommendationMetadata", () => {
  test("captures source tweet and draft context for memory", () => {
    const metadata = buildRecommendationMetadata({
      reason: "Relevant technical discussion.",
      draftOptions: ["First", "Second", "Third"],
      tweet: {
        id: "123",
        text: "AI agents need evals",
        author: { screenName: "ada" },
        metrics: { likes: 2 },
      },
    });

    expect(metadata.source_tweet.text).toBe("AI agents need evals");
    expect(metadata.recommendation_reason).toBe("Relevant technical discussion.");
    expect(metadata.comment_drafts).toEqual(["First", "Second", "Third"]);
  });
});

describe("buildGrowthActionPayload", () => {
  test("builds a direct like payload from a rendered recommendation", () => {
    const payload = buildGrowthActionPayload(
      {
        id: 9,
        action: "comment",
        tweet_id: "123",
        draft: "Useful point",
        reason: "Relevant technical discussion.",
        draftOptions: ["Useful point"],
        tweet: {
          id: "123",
          text: "AI agents need evals",
          author: { screenName: "ada" },
        },
      },
      "like",
    );

    expect(payload).toEqual({
      recommendation_id: 9,
      action: "like",
      tweet_id: "123",
      comment_text: "",
      metadata: {
        source_tweet: {
          id: "123",
          text: "AI agents need evals",
          author: { screenName: "ada" },
          metrics: {},
          createdAtISO: "",
          sourceQuery: "",
        },
        recommendation_reason: "Relevant technical discussion.",
        comment_drafts: ["Useful point"],
      },
    });
  });
});

describe("buildTweetLikePayload", () => {
  test("builds a direct like payload from a plain workbench tweet", () => {
    const payload = buildTweetLikePayload({
      id: "feed-123",
      text: "Shipping local agents",
      author: { screenName: "ada" },
      metrics: { likes: 4 },
      createdAtISO: "2026-07-04T04:00:00.000Z",
    });

    expect(payload).toEqual({
      action: "like",
      tweet_id: "feed-123",
      comment_text: "",
      metadata: {
        source_tweet: {
          id: "feed-123",
          text: "Shipping local agents",
          author: { screenName: "ada" },
          metrics: { likes: 4 },
          createdAtISO: "2026-07-04T04:00:00.000Z",
          sourceQuery: "",
        },
        recommendation_reason: "",
        comment_drafts: [],
      },
    });
  });
});

describe("workbench cache", () => {
  test("round-trips the last rendered workbench result", () => {
    const values = new Map();
    const storage = {
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
    };
    const cachedState = {
      selectedPresetId: "feed",
      options: { max: 20 },
      result: {
        ok: true,
        command: ["twitter", "feed", "--max", "20", "--json"],
        data: { data: [{ id: "feed-123", text: "Shipping local agents" }] },
      },
      selectedTweetId: "feed-123",
      rawVisible: false,
      lastRunMs: 321,
      likedTweetIds: ["feed-123"],
    };

    saveWorkbenchCache(storage, cachedState);

    expect(loadWorkbenchCache(storage)).toEqual(cachedState);
  });

  test("ignores invalid cached workbench state", () => {
    const storage = {
      getItem: () => "{not-json",
      setItem: () => {},
    };

    expect(loadWorkbenchCache(storage)).toBeNull();
  });
});

describe("combinedGrowthButtonState", () => {
  test("labels the combined growth run by current loading state", () => {
    expect(combinedGrowthButtonState({ loadingDiscover: false, loadingAnalyze: false })).toEqual({
      disabled: false,
      label: "Discover and analyze",
    });
    expect(combinedGrowthButtonState({ loadingDiscover: true, loadingAnalyze: false })).toEqual({
      disabled: true,
      label: "Discovering posts",
    });
    expect(combinedGrowthButtonState({ loadingDiscover: false, loadingAnalyze: true })).toEqual({
      disabled: true,
      label: "Analyzing with DeepSeek",
    });
  });
});

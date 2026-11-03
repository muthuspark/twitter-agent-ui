import { describe, expect, test } from "vitest";
import { formatMetric } from "./format";
import {
  buildGrowthActionPayload, buildTweetActionPayload, combinedGrowthButtonState,
  buildRecommendationMetadata, growthActionLabel, normalizeRecommendations, tweetUrl,
} from "./social";

describe("formatMetric", () => {
  test("formats compact values for large counts", () => {
    expect(formatMetric(999)).toBe("999");
    expect(formatMetric(1200)).toBe("1.2K");
    expect(formatMetric(4800000)).toBe("4.8M");
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
    expect(growthActionLabel("post")).toBe("Post");
    expect(growthActionLabel("skip")).toBe("Skip");
  });
});

describe("tweetUrl", () => {
  test("uses author handle when available", () => {
    expect(tweetUrl({ id: "123", author: { screenName: "ada" } })).toBe(
      "https://x.com/ada/status/123",
    );
  });

  test("uses author username when screen name is unavailable", () => {
    expect(tweetUrl({ id: "123", author: { username: "ada" } })).toBe(
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

describe("buildTweetActionPayload", () => {
  test("builds a direct like payload from a plain feed tweet", () => {
    const payload = buildTweetActionPayload({
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
      label: "Analyzing with Codex CLI",
    });
  });
});

 test("builds bookmark payloads with source context and no comment", () => {
  const payload = buildTweetActionPayload({ id: "123", text: "Save this" }, "bookmark");
  expect(payload.action).toBe("bookmark");
  expect(payload.tweet_id).toBe("123");
  expect(payload.comment_text).toBe("");
  expect(payload.metadata.source_tweet.text).toBe("Save this");
  expect(growthActionLabel("bookmark")).toBe("Bookmark");
});

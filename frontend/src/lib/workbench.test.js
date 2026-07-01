import { describe, expect, test } from "vitest";

import {
  buildCommandPreview,
  combinedGrowthButtonState,
  buildRecommendationMetadata,
  formatMetric,
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

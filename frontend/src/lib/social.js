export function growthActionLabel(action) {
  const labels = {
    like: "Like",
    bookmark: "Bookmark",
    comment: "Comment",
    post: "Post",
    skip: "Skip",
  };
  return labels[action] ?? "Review";
}

export function normalizeRecommendations(recommendations = [], candidates = []) {
  const candidateById = new Map(candidates.map((candidate) => [String(candidate.id), candidate]));
  return recommendations.filter((recommendation) => recommendation.action !== "skip").map((recommendation) => {
    const action = recommendation.action ?? "skip";
    const tweet = candidateById.get(String(recommendation.tweet_id)) ?? null;
    const draftOptions = Array.isArray(recommendation.comment_drafts)
      ? recommendation.comment_drafts.filter(Boolean).slice(0, 3)
      : [];
    if (recommendation.comment && !draftOptions.includes(recommendation.comment)) {
      draftOptions.unshift(recommendation.comment);
    }
    return {
      ...recommendation,
      tweet,
      actionLabel: growthActionLabel(action),
      draftOptions,
      draft: draftOptions[0] ?? recommendation.comment ?? "",
      postUrl: tweetUrl(tweet ?? { id: recommendation.tweet_id }),
    };
  });
}

export function tweetUrl(tweet) {
  const id = tweet?.id;
  if (!id) return "";
  const handle = tweet?.author?.screenName || tweet?.author?.username;
  if (handle) return `https://x.com/${handle}/status/${id}`;
  return `https://x.com/i/web/status/${id}`;
}

export function buildRecommendationMetadata(item) {
  return {
    source_tweet: {
      id: item?.tweet?.id ?? item?.tweet_id ?? "",
      text: item?.tweet?.text ?? "",
      author: item?.tweet?.author ?? {},
      metrics: item?.tweet?.metrics ?? {},
      createdAtISO: item?.tweet?.createdAtISO ?? "",
      sourceQuery: item?.tweet?.sourceQuery ?? "",
    },
    recommendation_reason: item?.reason ?? "",
    comment_drafts: item?.draftOptions ?? [],
  };
}

export function buildGrowthActionPayload(item, action = item?.action ?? "skip") {
  return {
    recommendation_id: item?.id,
    action,
    tweet_id: item?.tweet_id,
    comment_text: action === "comment" ? item?.draft ?? "" : "",
    metadata: buildRecommendationMetadata(item),
  };
}

export function buildTweetActionPayload(tweet, action = "like") {
  return {
    action,
    tweet_id: tweet?.id,
    comment_text: "",
    metadata: {
      source_tweet: {
        id: tweet?.id ?? "",
        text: tweet?.text ?? "",
        author: tweet?.author ?? {},
        metrics: tweet?.metrics ?? {},
        createdAtISO: tweet?.createdAtISO ?? tweet?.createdAtLocal ?? "",
        sourceQuery: tweet?.sourceQuery ?? "",
      },
      recommendation_reason: "",
      comment_drafts: [],
    },
  };
}

export function combinedGrowthButtonState({ loadingDiscover, loadingAnalyze }) {
  if (loadingDiscover) {
    return { disabled: true, label: "Discovering posts" };
  }
  if (loadingAnalyze) {
    return { disabled: true, label: "Analyzing with Codex CLI" };
  }
  return { disabled: false, label: "Discover and analyze" };
}

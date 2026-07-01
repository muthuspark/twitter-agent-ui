const COMMAND_LABELS = {
  feed: "feed",
  search: "search",
  bookmarks: "bookmarks",
  status: "status",
  whoami: "whoami",
};

export function shellQuote(value) {
  const text = String(value ?? "");
  return `"${text.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

export function buildCommandPreview(preset, options = {}) {
  if (!preset) return "twitter";

  const parts = ["twitter", COMMAND_LABELS[preset.id] ?? preset.id];
  if (preset.id === "search") {
    parts.push(shellQuote(options.query ?? ""));
  }

  const maxField = preset.fields?.find((field) => field.name === "max");
  if (maxField) {
    parts.push("--max", String(options.max || maxField.default || 20));
  }

  parts.push("--json");
  return parts.join(" ");
}

export function formatMetric(value) {
  const number = Number(value || 0);
  if (number >= 1_000_000) return `${trimMetric(number / 1_000_000)}M`;
  if (number >= 1_000) return `${trimMetric(number / 1_000)}K`;
  return String(number);
}

function trimMetric(value) {
  return value.toFixed(value >= 10 ? 0 : 1).replace(/\.0$/, "");
}

export function normalizeResult(response) {
  const payload = response?.data?.data ?? response?.data ?? response;
  if (Array.isArray(payload)) {
    return { kind: "tweets", items: payload };
  }
  return { kind: "json", value: payload ?? null };
}

export function defaultOptionsForPreset(preset) {
  const options = {};
  for (const field of preset?.fields ?? []) {
    if (field.default !== null && field.default !== undefined) {
      options[field.name] = field.default;
    } else {
      options[field.name] = "";
    }
  }
  return options;
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

export function growthActionLabel(action) {
  const labels = {
    like: "Like",
    comment: "Comment",
    skip: "Skip",
  };
  return labels[action] ?? "Review";
}

export function normalizeRecommendations(recommendations = [], candidates = []) {
  const candidateById = new Map(candidates.map((candidate) => [String(candidate.id), candidate]));
  return recommendations.map((recommendation) => {
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

export function combinedGrowthButtonState({ loadingDiscover, loadingAnalyze }) {
  if (loadingDiscover) {
    return { disabled: true, label: "Discovering posts" };
  }
  if (loadingAnalyze) {
    return { disabled: true, label: "Analyzing with DeepSeek" };
  }
  return { disabled: false, label: "Discover and analyze" };
}

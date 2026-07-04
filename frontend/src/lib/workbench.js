const COMMAND_LABELS = {
  feed: "feed",
  search: "search",
  bookmarks: "bookmarks",
  status: "status",
  whoami: "whoami",
};

const WORKBENCH_CACHE_KEY = "twitter-agent-ui:workbench-cache:v1";

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

export function buildTweetLikePayload(tweet) {
  return {
    action: "like",
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

export function saveWorkbenchCache(storage, state) {
  if (!storage) return;
  storage.setItem(
    WORKBENCH_CACHE_KEY,
    JSON.stringify({
      selectedPresetId: state?.selectedPresetId ?? "feed",
      options: state?.options ?? {},
      result: state?.result ?? null,
      selectedTweetId: state?.selectedTweetId ?? null,
      rawVisible: Boolean(state?.rawVisible),
      lastRunMs: state?.lastRunMs ?? null,
      likedTweetIds: Array.isArray(state?.likedTweetIds) ? state.likedTweetIds : [],
    }),
  );
}

export function loadWorkbenchCache(storage) {
  if (!storage) return null;
  try {
    const cached = JSON.parse(storage.getItem(WORKBENCH_CACHE_KEY) ?? "null");
    if (!cached || typeof cached !== "object" || !cached.result) return null;
    return {
      selectedPresetId: cached.selectedPresetId ?? "feed",
      options: cached.options && typeof cached.options === "object" ? cached.options : {},
      result: cached.result,
      selectedTweetId: cached.selectedTweetId ?? null,
      rawVisible: Boolean(cached.rawVisible),
      lastRunMs: cached.lastRunMs ?? null,
      likedTweetIds: Array.isArray(cached.likedTweetIds) ? cached.likedTweetIds : [],
    };
  } catch {
    return null;
  }
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

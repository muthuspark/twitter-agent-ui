const STORAGE_KEY = "twitter-agent-ui:feed-blocklist:v1";
const WORD_CHARACTER = /[\p{L}\p{N}\p{M}_]/u;

export function normalizeBlockedTerm(value) {
  return typeof value === "string" ? value.normalize("NFKC").replace(/\s+/gu, " ").trim() : "";
}

export function addBlockedTerm(terms, value) {
  const term = normalizeBlockedTerm(value);
  if (!term || term.length > 200) throw new Error("Enter a word or phrase of up to 200 characters.");
  if (terms.some((existing) => normalizeBlockedTerm(existing).toLowerCase() === term.toLowerCase())) return terms;
  return [...terms, term];
}

export function loadBlockedTerms(storage) {
  try {
    const values = JSON.parse(storage?.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(values)) return [];
    return values.reduce((terms, value) => {
      const term = normalizeBlockedTerm(value);
      return term && term.length <= 200 ? addBlockedTerm(terms, term) : terms;
    }, []);
  } catch {
    return [];
  }
}

export function saveBlockedTerms(storage, terms) {
  try {
    if (!storage) return false;
    storage.setItem(STORAGE_KEY, JSON.stringify(terms));
    return true;
  } catch {
    return false;
  }
}

export function createFeedBlockMatcher(terms) {
  const patterns = terms.map(normalizeBlockedTerm).filter(Boolean).map((term) => {
    const escaped = term.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const first = Array.from(term)[0];
    const last = Array.from(term).at(-1);
    const start = WORD_CHARACTER.test(first) ? "(?:^|[^\\p{L}\\p{N}\\p{M}_])" : "";
    const end = WORD_CHARACTER.test(last) ? "(?=$|[^\\p{L}\\p{N}\\p{M}_])" : "";
    return { term, regex: new RegExp(start + escaped + end, "u") };
  });
  return (tweet) => {
    const texts = [tweet?.text, tweet?.quotedTweet?.text].map((text) => normalizeBlockedTerm(text).toLowerCase());
    return patterns.find(({ regex }) => texts.some((text) => regex.test(text)))?.term ?? null;
  };
}

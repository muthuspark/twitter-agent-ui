import { describe, expect, it } from "vitest";
import { addBlockedTerm, createFeedBlockMatcher, loadBlockedTerms, normalizeBlockedTerm, saveBlockedTerms } from "./blocklist";

describe("feed block matching", () => {
  const example = "🚨Who doesn’t know Radhika Merchant, the wife of Anant Ambani. The couple tied the knot in 2024.";

  it("hides the example and future posts regardless of capitalization", () => {
    const matches = createFeedBlockMatcher(["Anant Ambani"]);
    expect(matches({ text: example })).toBe("Anant Ambani");
    expect(matches({ text: "A new post about ANANT AMBANI today." })).toBe("Anant Ambani");
    expect(matches({ text: "anant ambani's wedding" })).toBe("Anant Ambani");
    expect(matches({ text: "Unrelated content" })).toBeNull();
  });

  it("matches whole words and phrases without hiding parts of unrelated words", () => {
    const matches = createFeedBlockMatcher(["AI", "Anant Ambani"]);
    expect(matches({ text: "He said this yesterday" })).toBeNull();
    expect(matches({ text: "OpenAI" })).toBeNull();
    expect(matches({ text: "AI-powered tooling" })).toBe("AI");
    expect(matches({ text: "Anant Ambaniverse" })).toBeNull();
  });

  it("matches quoted text, but not author names or other metadata", () => {
    const matches = createFeedBlockMatcher(["Anant Ambani"]);
    expect(matches({ text: "Look at this", quotedTweet: { text: example } })).toBe("Anant Ambani");
    expect(matches({ text: "A gardening post", author: { name: "Anant Ambani" } })).toBeNull();
  });

  it("normalizes line breaks, extra spaces and Unicode spacing", () => {
    const matches = createFeedBlockMatcher([" Anant  Ambani "]);
    expect(matches({ text: "ANANT\n\tAMBANI" })).toBe("Anant Ambani");
    expect(matches({ text: "Anant\u00a0Ambani" })).toBe("Anant Ambani");
    expect(normalizeBlockedTerm(" ＡＩ ")).toBe("AI");
  });

  it("treats special characters as literal text, not regex instructions", () => {
    const matches = createFeedBlockMatcher(["C++", "[gossip]", ".*", "a.b"]);
    expect(matches({ text: "Learn C++ today" })).toBe("C++");
    expect(matches({ text: "[GOSSIP] News" })).toBe("[gossip]");
    expect(matches({ text: "Ordinary news" })).toBeNull();
    expect(matches({ text: "axb" })).toBeNull();
    expect(matches({ text: "a.b" })).toBe("a.b");
  });

  it("supports non-Latin words and punctuation", () => {
    const matches = createFeedBlockMatcher(["राजनीति"]);
    expect(matches({ text: "आज की राजनीति!" })).toBe("राजनीति");
    expect(matches({ text: "राजनीतिज्ञ" })).toBeNull();
  });

  it("stops matching when a term is removed", () => {
    const terms = addBlockedTerm([], "Anant Ambani");
    expect(createFeedBlockMatcher(terms)({ text: example })).toBeTruthy();
    expect(createFeedBlockMatcher(terms.filter((term) => term !== "Anant Ambani"))({ text: example })).toBeNull();
  });
});

describe("block list persistence", () => {
  it("keeps the display spelling and avoids case-insensitive duplicates", () => {
    expect(addBlockedTerm(["Anant Ambani"], "  ANANT   AMBANI ")).toEqual(["Anant Ambani"]);
  });

  it("round trips the list through browser storage", () => {
    const data = new Map();
    const storage = { getItem: (key) => data.get(key), setItem: (key, value) => data.set(key, value) };
    expect(saveBlockedTerms(storage, ["Anant Ambani", "Crypto"])).toBe(true);
    expect(loadBlockedTerms(storage)).toEqual(["Anant Ambani", "Crypto"]);
    expect(saveBlockedTerms(storage, ["Crypto"])).toBe(true);
    expect(loadBlockedTerms(storage)).toEqual(["Crypto"]);
  });

  it("recovers from malformed data and unavailable storage", () => {
    expect(loadBlockedTerms({ getItem: () => "invalid JSON" })).toEqual([]);
    expect(loadBlockedTerms({ getItem: () => JSON.stringify([null, 123, "AI", "ai", " "]) })).toEqual(["AI"]);
    expect(loadBlockedTerms(null)).toEqual([]);
    expect(saveBlockedTerms({ setItem: () => { throw new Error("Storage full"); } }, ["AI"])).toBe(false);
  });

  it("rejects empty or excessively long selections", () => {
    expect(() => addBlockedTerm([], "   ")).toThrow();
    expect(() => addBlockedTerm([], "a".repeat(201))).toThrow();
  });
});

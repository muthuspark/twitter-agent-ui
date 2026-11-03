import { describe, expect, it } from "vitest";
import { clearRecovery, draftKey, readRecovery, saveRecovery, sortProspects } from "./prospects";

const storage = () => { const data = new Map(); return { getItem: k => data.get(k) ?? null, setItem: (k,v) => data.set(k,v), removeItem: k => data.delete(k) }; };

describe("prospect draft recovery", () => {
  it("preserves blank edits and separates reports and prospects", () => {
    const s = storage(); const key = draftKey("one", "https://example.com/post");
    saveRecovery(s, key, "");
    expect(readRecovery(s,key)).toBe("");
    expect(readRecovery(s,draftKey("two","https://example.com/post"))).toBeNull();
    expect(readRecovery(s,draftKey("one","https://example.com/other"))).toBeNull();
  });
  it("does not clear newer edits when an older save finishes", () => {
    const s = storage(); saveRecovery(s,"draft","first"); saveRecovery(s,"draft","newer");
    clearRecovery(s,"draft","first"); expect(readRecovery(s,"draft")).toBe("newer");
    clearRecovery(s,"draft","newer"); expect(readRecovery(s,"draft")).toBeNull();
  });
  it("tolerates malformed and unavailable recovery storage", () => {
    const s = storage(); s.setItem("key","broken JSON"); expect(readRecovery(s,"key")).toBeNull();
    expect(readRecovery({getItem(){throw new Error("blocked");}},"key")).toBeNull();
  });
});

describe("prospect ranking", () => {
  const posts = [
    {url:"low-fit",coverage:8,coverage_checked:true,confidence:72,published_at:"2026-08-06"},
    {url:"best-fit",coverage:56,coverage_checked:true,confidence:49,published_at:"2026-11-01"},
    {url:"unknown",coverage:0,coverage_checked:false,confidence:80,published_at:""},
    {url:"zero",coverage:0,coverage_checked:true,confidence:20,published_at:"2026-11-02"},
  ];
  it("prioritizes actual coverage and keeps unknown fit below checked needs", () => {
    expect(sortProspects(posts,"fit").map(p=>p.url)).toEqual(["best-fit","low-fit","zero","unknown"]);
    expect(posts[0].url).toBe("low-fit");
  });
  it("supports explicit conversation-signal and date sorting", () => {
    expect(sortProspects(posts,"signal")[0].url).toBe("unknown");
    expect(sortProspects(posts,"newest")[0].url).toBe("zero");
    expect(sortProspects(posts,"newest").at(-1).url).toBe("unknown");
  });
});

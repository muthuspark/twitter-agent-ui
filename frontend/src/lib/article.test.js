import { describe, expect, it } from "vitest";
import { articleDate, renderArticleMarkdown } from "./article";

describe("article rendering", () => {
  it("retains paragraphs, nested headings, emphasis, lists and code", () => {
    const html=renderArticleMarkdown('First paragraph.\n\n# Section\n\n## Subsection\n\n**Bold** and *italic*.\n\n- Item\n\n```js\nconsole.log("test")\n```');
    expect(html).toContain('<p>First paragraph.</p>');
    expect(html).toContain('<h2>Section</h2>');expect(html).toContain('<h3>Subsection</h3>');
    expect(html).toContain('<strong>Bold</strong>');expect(html).toContain('<ul>');expect(html).toContain('<pre>');
    expect(html).not.toContain('<h1>');
  });
  it("escapes raw HTML and rejects executable links and inline image payloads", () => {
    const html=renderArticleMarkdown('<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>\n\n[x](javascript:alert(1))\n\n[x](data:text/html,test)\n\n![x](data:image/svg+xml,test)');
    expect(html).not.toContain('<script');expect(html).not.toContain('<img');
    expect(html).not.toMatch(/href=["'](?:javascript|data):/);
    expect(html).toContain('&lt;script&gt;');
  });
  it("starts body sections at h2 even when the source starts at h2 or h3", () => {
    expect(renderArticleMarkdown('## First section')).toContain('<h2>First section</h2>');
    expect(renderArticleMarkdown('### First section\n\n#### Nested section')).toContain('<h3>Nested section</h3>');
  });
  it("keeps source links safe and resolves relative X links against X", () => {
    const html=renderArticleMarkdown('[Profile](/someone) and [Source](https://example.com/path)');
    expect(html).toContain('href="https://x.com/someone"');
    expect(html).toContain('rel="noopener noreferrer"');expect(html).toContain('target="_blank"');
  });
  it("renders HTTPS images and never fetches local or insecure images", () => {
    expect(renderArticleMarkdown('![Photo](https://pbs.twimg.com/media/example.jpg)')).toContain('<img');
    expect(renderArticleMarkdown('![Photo](file:///etc/passwd)')).not.toContain('<img');
    expect(renderArticleMarkdown('![Photo](http://example.com/image.png)')).not.toContain('<img');
  });
  it("does not truncate long articles or invent dates", () => {
    const text='Paragraph.\n\n'.repeat(2000)+'THE FINAL PARAGRAPH';
    expect(renderArticleMarkdown(text)).toContain('THE FINAL PARAGRAPH');
    expect(articleDate(null)).toBe('');expect(articleDate('invalid')).toBe('');
    expect(articleDate('2026-11-02T10:29:07+00:00')).toContain('2026');
  });
});

 describe("print image readiness", () => {
  it("waits for image loads and identifies failures and stalled images", async () => {
    const { waitForArticleImages } = await import('./article');
    const loaded = Object.assign(new EventTarget(), { complete: true, naturalWidth: 100 });
    const pending = Object.assign(new EventTarget(), { complete: false, naturalWidth: 0 });
    const failed = Object.assign(new EventTarget(), { complete: true, naturalWidth: 0 });
    const root = { querySelectorAll: () => [loaded, pending, failed] };
    const waiting = waitForArticleImages(root, 100);
    pending.complete = true; pending.naturalWidth = 300;
    pending.dispatchEvent(new Event('load'));
    expect(await waiting).toBe(1);
    pending.complete = false; pending.naturalWidth = 0;
    expect(await waitForArticleImages(root, 1)).toBe(2);
    expect(await waitForArticleImages(null)).toBe(0);
  });
});

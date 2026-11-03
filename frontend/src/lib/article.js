import MarkdownIt from "markdown-it";

const markdown = new MarkdownIt({ html: false, linkify: false, typographer: false });
const defaultValidate = markdown.validateLink.bind(markdown);
markdown.validateLink = value => {
  if (!defaultValidate(value)) return false;
  try {
    const url = new URL(value, "https://x.com");
    return ["https:", "http:", "mailto:"].includes(url.protocol) && !url.username && !url.password;
  } catch { return false; }
};

markdown.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
  tokens[index].attrSet("href", new URL(tokens[index].attrGet("href"), "https://x.com").href);
  tokens[index].attrSet("target", "_blank");
  tokens[index].attrSet("rel", "noopener noreferrer");
  return renderer.renderToken(tokens, index, options);
};
const defaultImage = markdown.renderer.rules.image;
markdown.renderer.rules.image = (tokens, index, options, env, renderer) => {
  const token = tokens[index];
  try {
    const url = new URL(token.attrGet("src"));
    if (url.protocol !== "https:") return markdown.utils.escapeHtml(token.content);
  } catch { return markdown.utils.escapeHtml(token.content); }
  token.attrSet("referrerpolicy", "no-referrer");
  return defaultImage(tokens, index, options, env, renderer);
};

export function renderArticleMarkdown(text) {
  // Raw HTML is disabled. Never render untrusted article HTML directly.
  const tokens = markdown.parse(String(text || ""), {});
  const levels = tokens.filter(token => token.type === "heading_open").map(token => Number(token.tag.slice(1)));
  const shift = levels.length ? 2 - levels.reduce((smallest, level) => Math.min(smallest, level), 6) : 0;
  for (const token of tokens) {
    if (token.type === "heading_open" || token.type === "heading_close") token.tag = `h${Math.min(Number(token.tag.slice(1)) + shift, 6)}`;
  }
  return markdown.renderer.render(tokens, markdown.options, {});
}

export function articleDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : new Intl.DateTimeFormat("en", { year: "numeric", month: "long", day: "numeric" }).format(date);
}

export async function waitForArticleImages(root, timeoutMs = 20000) {
  const images = Array.from(root?.querySelectorAll("img") || []);
  await Promise.all(images.map(image => new Promise(resolve => {
    if (image.complete) { resolve(); return; }
    const finish = () => {
      clearTimeout(timer);
      image.removeEventListener("load", finish);
      image.removeEventListener("error", finish);
      resolve();
    };
    const timer = setTimeout(finish, timeoutMs);
    image.addEventListener("load", finish);
    image.addEventListener("error", finish);
  })));
  return images.filter(image => !image.complete || image.naturalWidth === 0).length;
}

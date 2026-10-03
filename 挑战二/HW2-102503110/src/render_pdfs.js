"use strict";

const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");
const { marked } = require("marked");
const { chromium } = require("playwright");

const root = path.resolve(__dirname, "..");
const documents = [
  ["src/docs/report.md", "report.pdf"],
  ["src/docs/AI 使用说明情况（第二次挑战）.md", "AI 使用说明情况（第二次挑战）.pdf"],
];

const style = `
  @page { size: A4; }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    color: #202a33;
    background: #fff;
    font-family: "Microsoft YaHei", "Noto Sans CJK SC", Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.55;
  }
  h1, h2, h3 { color: #142b36; page-break-after: avoid; }
  h1 { font-size: 19pt; line-height: 1.25; margin: 0 0 11mm; }
  h2 { font-size: 13.5pt; border-bottom: 1px solid #b9c9cf; padding-bottom: 2mm; margin: 8mm 0 3mm; }
  h3 { font-size: 11pt; margin: 5mm 0 2mm; }
  p { margin: 0 0 3mm; orphans: 2; widows: 2; }
  ul, ol { margin: 0 0 3mm; padding-left: 6mm; }
  li { margin-bottom: 1.5mm; }
  table { border-collapse: collapse; width: 100%; margin: 3mm 0 5mm; font-size: 8.3pt; table-layout: fixed; }
  th, td { border: 1px solid #c5d1d5; padding: 1.6mm 2mm; vertical-align: top; overflow-wrap: anywhere; }
  th { background: #eaf1f2; text-align: left; font-weight: 700; }
  tr { page-break-inside: avoid; }
  blockquote { background: #f1f6f3; border-left: 3px solid #477d6a; margin: 3mm 0 4mm; padding: 2.5mm 4mm; }
  blockquote p { margin: 0; }
  code { font-family: Consolas, "Courier New", monospace; font-size: 8.5pt; overflow-wrap: anywhere; }
  img { display: block; width: auto; max-width: 100%; max-height: 143mm; object-fit: contain; margin: 2mm auto 4mm; page-break-inside: avoid; }
  h2:has(+ p img) { break-after: avoid; }
`;

async function render(browser, sourceName, outputName) {
  const sourcePath = path.join(root, sourceName);
  const outputPath = path.join(root, outputName);
  const temporaryHtml = path.join(root, "." + outputName + ".print.html");
  const content = fs.readFileSync(sourcePath, "utf8");
  const baseHref = pathToFileURL(path.dirname(sourcePath) + path.sep).href;
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><base href="${baseHref}"><style>${style}</style></head><body>${marked.parse(content, { gfm: true })}</body></html>`;
  fs.writeFileSync(temporaryHtml, html, "utf8");
  try {
    const page = await browser.newPage();
    await page.goto(pathToFileURL(temporaryHtml).href, { waitUntil: "load" });
    await page.pdf({
      path: outputPath,
      format: "A4",
      printBackground: true,
      margin: { top: "16mm", bottom: "17mm", left: "17mm", right: "17mm" },
      displayHeaderFooter: true,
      headerTemplate: "<div></div>",
      footerTemplate: '<div style="width:100%;font:8px Arial;color:#697983;text-align:center;"><span class="pageNumber"></span></div>',
    });
    await page.close();
    console.log(outputPath);
  } finally {
    fs.unlinkSync(temporaryHtml);
  }
}

(async () => {
  const browser = await chromium.launch({ channel: "msedge", headless: true });
  try {
    for (const [source, output] of documents) {
      await render(browser, source, output);
    }
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});

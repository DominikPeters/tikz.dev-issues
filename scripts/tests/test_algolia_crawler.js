// Run with Node.js and Cheerio available (for example through NODE_PATH).
// Optional argument: a JSON object mapping rendered page paths to HTML, for
// checking additional deployed manuals without crawling or indexing them.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const cheerio = require("cheerio");
let config;
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../algolia-crawler.js"), "utf8"), {
  Crawler: function (value) { config = value; }, URL,
});

function extract(html, pathname) {
  const $ = cheerio.load(html);
  const originalIds = new Set($("[id]").map((_, el) => $(el).attr("id")).get());
  const url = new URL(pathname, "https://tikz.dev");
  let selectedDefinitions = 0;
  // Emulate the helper's heading inheritance to exercise our extractor's
  // anchor normalization, grouping, package metadata, and selector boundaries.
  // The real Algolia helper is also checked in the dashboard URL Tester.
  const helpers = {docsearch: ({recordProps}) => {
    const choose = value => (Array.isArray(value) ? value : [value]).find(s => $(s).length);
    const selectors = [1, 2, 3, 4].map(level => choose(recordProps["lvl" + level]));
    const current = {};
    const records = [];
    let anchor = "";
    $("section.textbody *").each((_, el) => {
      const node = $(el);
      const level = selectors.findIndex(selector => selector && node.is(selector)) + 1;
      if (level) {
        for (let i = level; i <= 4; i++) delete current["lvl" + i];
        current["lvl" + level] = node.text().replace(/\s+/g, " ").trim();
        anchor = node.attr("id") || "";
        if (level === 4) selectedDefinitions++;
      }
      if (level || node.is(recordProps.content)) {
        const part = choose(recordProps.lvl0.selectors);
        records.push({type: level ? "lvl" + level : "content", anchor,
          url: url.href + (anchor ? "#" + anchor : ""),
          hierarchy: {lvl0: part ? $(part).first().text() : recordProps.lvl0.defaultValue, ...current},
          content: level ? null : node.text(),
        });
      }
    });
    return records;
  }};
  const records = config.actions[0].recordExtractor({url, $, helpers});
  for (const record of records) {
    assert.ok(record.search_group.startsWith("https://tikz.dev/"));
    assert.ok(!record.search_group.includes("/monorepo/"));
    const target = new URL(record.url).hash.slice(1);
    assert.ok(!target || originalIds.has(decodeURIComponent(target)), `Invalid target: ${record.url}`);
    const groupTarget = record.search_group.split("#")[1];
    assert.ok(!groupTarget || originalIds.has(groupTarget), `Invalid group: ${record.search_group}`);
    assert.equal(record.tags.length, 1);
  }
  return {records, selectedDefinitions};
}

const fixture = `<section class="textbody"><h4 id="autosec-1"><a id="section-page"></a>
  <span class="sectionnumber" id="sec-1">1</span>Page</h4>
  <h5><span class="sectionnumber" id="sec-1.1">1.1</span>First</h5><p>Intro</p>
  <h6><span class="sectionnumber" id="sec-1.1.1">1.1.1</span>Details</h6>
  <div class="entryheadline"><li><p><a id="key-one"></a>One</p></li></div><p>First definition</p>
  <div class="example"><p>EXAMPLE_MUST_NOT_BE_INDEXED</p></div>
  <h5><a id="second-section"></a><span class="sectionnumber" id="sec-1.2">1.2</span>Second</h5>
  <div class="entryheadline"><li><p>Two<a class="anchor-link" id="key-two" href="#key-two">¶</a></p></li></div>
  <div class="entryheadline"><li><p>No anchor</p></li></div><p>Second definition</p>
  <h6><span class="sectionnumber" id="sec-1.2.1">1.2.1</span>Details</h6><p>Repeated title</p>
  <h4 id="next-page-section">Next</h4><p>Final</p></section>`;
const records = extract(fixture, "/tikz-shapes").records;
const find = title => records.find(r => r.hierarchy.lvl4 === title && r.type === "lvl4");
assert.equal(find("One").search_group, "https://tikz.dev/tikz-shapes#sec-1.1.1");
assert.equal(find("Two").search_group, "https://tikz.dev/tikz-shapes#second-section");
assert.equal(find("No anchor").url, "https://tikz.dev/tikz-shapes#second-section");
assert.equal(records.find(r => r.content === "Repeated title").search_group, "https://tikz.dev/tikz-shapes#sec-1.2.1");
assert.equal(records.find(r => r.content === "Final").search_group, "https://tikz.dev/tikz-shapes#next-page-section");
assert.ok(records.every(r => !String(r.content).includes("EXAMPLE_MUST_NOT_BE_INDEXED")));
assert.equal(records[0].manual, "pgf");
assert.equal(records[0].tags[0], "tikz");
assert.equal(extract(fixture, "/monorepo/tikz-shapes").records.length, 0);
assert.equal(extract(fixture, "/standalone/example").records.length, 0);
assert.equal(extract("<section class='textbody'><h1>Home</h1><p>Welcome</p></section>", "/forest/").records[0].url,
  "https://tikz.dev/forest/");
assert.equal(config.initialIndexSettings.tikz.attributeForDistinct, "search_group");
assert.equal(config.initialIndexSettings.tikz.distinct, 2);
assert.equal(config.startUrls.length, 12);

if (process.argv[2]) {
  const pages = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
  const totals = {};
  for (const [name, html] of Object.entries(pages)) {
    const pathname = "/" + name.replace(/index\.html$/, "").replace(/\.html$/, "");
    const {records, selectedDefinitions} = extract(html, pathname);
    assert.ok(records.length, `No records: ${name}`);
    const pkg = name.split("/")[0];
    assert.ok(records.every(r => r.manual === pkg && r.tags[0] === pkg), `Wrong manual: ${name}`);
    totals[pkg] = (totals[pkg] || 0) + records.length;
    const sourceDefinitions = cheerio.load(html)("section.textbody .entryheadline").length;
    assert.equal(selectedDefinitions, sourceDefinitions, `Missing definitions: ${name}`);
  }
  console.log("Rendered page extraction passed:", totals);
}
console.log("Crawler grouping, anchors, scope exclusions, and metadata passed.");

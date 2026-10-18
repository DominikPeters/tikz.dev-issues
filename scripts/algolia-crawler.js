new Crawler({
  // Paste into the crawler editor, retaining its existing crawler API key.
  // Keep `new Crawler` at the start: the dashboard rejects preceding comments.
  // This is the production configuration: /monorepo/ is deliberately excluded.
  appId: "JS6V5VZSDB",
  apiKey: "YOUR_CRAWLER_API_KEY",
  rateLimit: 8,
  renderJavaScript: false,
  startUrls: [
    "https://tikz.dev/", "https://tikz.dev/pgfplots/", "https://tikz.dev/tcolorbox/",
    "https://tikz.dev/tikz-cd/", "https://tikz.dev/pgf-pie/", "https://tikz.dev/tikz-feynman/",
    "https://tikz.dev/wheelchart/", "https://tikz.dev/pgfgantt/", "https://tikz.dev/tkz-euclide/",
    "https://tikz.dev/chemfig/", "https://tikz.dev/forest/", "https://tikz.dev/nicematrix/",
  ],
  sitemaps: [],
  ignoreCanonicalTo: false,
  discoveryPatterns: ["https://tikz.dev/**"],
  exclusionPatterns: [
    "https://tikz.dev/monorepo/**", "https://tikz.dev/editor/**", "https://tikz.dev/edit/**",
    "https://tikz.dev/standalone/**", "https://tikz.dev/svg2tikz/**",
  ],
  schedule: "at 9:49 PM on Monday",
  actions: [{
    indexName: "tikz",
    pathsToMatch: ["https://tikz.dev/**"],
    recordExtractor: ({ url, $, helpers }) => {
      const manuals = {
        pgf: ["tikz", "PGF/TikZ"], pgfplots: ["pgfplots", "PGFplots"],
        tcolorbox: ["tcolorbox", "tcolorbox"], "tikz-cd": ["tikz-cd", "tikz-cd"],
        "pgf-pie": ["pgf-pie", "pgf-pie"], "tikz-feynman": ["tikz-feynman", "TikZ-Feynman"],
        wheelchart: ["wheelchart", "wheelchart"], pgfgantt: ["pgfgantt", "pgfgantt"],
        "tkz-euclide": ["tkz-euclide", "tkz-euclide"], chemfig: ["chemfig", "chemfig"],
        forest: ["forest", "forest"], nicematrix: ["nicematrix", "nicematrix"],
      };
      const path = url.pathname.split("/").filter(Boolean);
      // Only root-level PGF pages and the known package directories are manuals.
      if (["monorepo", "editor", "edit", "standalone", "svg2tikz"].includes(path[0]) ||
          (path.length > 1 && !manuals[path[0]])) return [];
      const pkg = manuals[path[0]] ? path[0] : "pgf";
      const manual = manuals[pkg];
      const main = $("section.textbody");
      if (!main.length) return [];
      const pageUrl = (url.origin + url.pathname).replace(/\/index\.html$/, "/").replace(/\.html$/, "");
      const normalText = (text) => text.replace(/\s+/g, " ").trim();
      const groups = new Map();
      const targets = new Map();
      const hierarchyGroups = new Map();

      // Preserve definition permalinks before removing the decorative ¶ links.
      const entries = $("section.textbody .entryheadline");
      entries.each((i) => {
        const entry = entries.eq(i);
        entry.attr("data-docsearch-entry", String(i));
        const scope = `[data-docsearch-entry="${i}"]`;
        const anchor = $(`${scope} .anchor-link[href^='#']`).eq(0).attr("href");
        const id = (anchor && anchor.slice(1)) || $(`${scope} [id]`).eq(0).attr("id") || entry.attr("id");
        const helperId = id || `docsearch-definition-${i}`;
        entry.attr("data-docsearch-id", helperId);
        if (id) targets.set(helperId, id);
      });

      // Keep text extraction inside the manual, excluding examples and UI chrome.
      $(".example, .example-code, .example-image, .sidetoccontainer, .anchor-link, .anchor-pdf-link, " +
        ".anchor-html-link, .hl-default, .clipboardButton, [data-nosnippet], script, style").remove();

      // The same section/subsection/subsubsection structure is used by all manuals.
      // Move an existing source anchor onto each heading for the DocSearch helper.
      const numberedHeadings = $("section.textbody h4, section.textbody h5, section.textbody h6");
      numberedHeadings.each((i) => {
        const heading = numberedHeadings.eq(i);
        heading.attr("data-docsearch-heading", String(i));
        const scope = `[data-docsearch-heading="${i}"]`;
        const aliases = $(`${scope} a[id]`);
        let named;
        aliases.each((j) => {
          const id = aliases.eq(j).attr("id");
          if (!named && !/^(?:autosec-|sec-|.*-autopage-|LWR)/.test(id)) named = id;
        });
        const id = named || $(`${scope} .sectionnumber[id]`).eq(0).attr("id") || heading.attr("id");
        const helperId = id || `docsearch-heading-${i}`;
        if (id) targets.set(helperId, id);
        const children = $(`${scope} [id]`);
        children.each((j) => {
          const child = children.eq(j);
          if (child.attr("id") === helperId) child.removeAttr("id");
        });
        heading.attr("id", helperId);
      });
      if (!$("section.textbody h4").length) {
        // Start/part pages have a title but no numbered section heading.
        const title = $("section.textbody h2:not(.inserted)").eq(0).length ?
          $("section.textbody h2:not(.inserted)").eq(0) : $("section.textbody h1").eq(0);
        if (title.length && !title.attr("id")) {
          title.attr("id", "docsearch-page");
          targets.set("docsearch-page", "");
        }
      }
      $("section.textbody .sectionnumber").remove();
      entries.each((i) => {
        const entry = entries.eq(i);
        const id = entry.attr("data-docsearch-id");
        const children = $(`[data-docsearch-entry="${i}"] [id]`);
        children.each((j) => {
          const child = children.eq(j);
          if (child.attr("id") === id) child.removeAttr("id");
        });
        entry.attr("id", id);
      });

      let currentGroup = pageUrl;
      let headings = [null, null, null];
      const elements = $("section.textbody *");
      elements.each((i) => {
        const node = elements.eq(i);
        const level = ["h4", "h5", "h6"].findIndex((tag) => node.is(tag));
        if (level !== -1) {
          headings = headings.slice(0, level);
          headings[level] = normalText(node.text());
          const target = targets.get(node.attr("id"));
          currentGroup = target ? `${pageUrl}#${target}` : pageUrl;
          hierarchyGroups.set(JSON.stringify(headings), currentGroup);
        }
        const id = node.attr("id") || node.attr("name");
        if (id) {
          groups.set(id, currentGroup);
          // A definition without an anchor links to its enclosing source heading.
          if (!targets.has(id) && /^docsearch-definition-/.test(id)) {
            targets.set(id, currentGroup.slice(pageUrl.length).replace(/^#/, ""));
          }
        }
      });

      const records = helpers.docsearch({
        recordProps: {
          lvl0: { selectors: "section.textbody h2.inserted", defaultValue: manual[1] },
          lvl1: ["section.textbody h4", "section.textbody h2:not(.inserted)", "section.textbody h1"],
          lvl2: "section.textbody h5",
          lvl3: "section.textbody h6",
          lvl4: "section.textbody .entryheadline",
          content: "section.textbody p, section.textbody li",
        },
        aggregateContent: true,
        recordVersion: "v3",
      });
      for (const record of records) {
        let anchor = record.anchor || (record.url || "").split("#")[1] || "";
        try { anchor = decodeURIComponent(anchor); } catch (e) {
          // Keep literal percent signs in legacy anchors.
        }
        const hierarchy = record.hierarchy || {};
        const headingPath = [hierarchy.lvl1, hierarchy.lvl2, hierarchy.lvl3];
        while (headingPath.length && !headingPath[headingPath.length - 1]) headingPath.pop();
        const fallbackGroup = hierarchyGroups.get(JSON.stringify(headingPath.map((h) => h && normalText(h))));
        record.search_group = groups.get(anchor) || fallbackGroup || pageUrl;
        record.manual = pkg;
        record.tags = [manual[0]];
        record.isBaseOrSystem = pkg === "pgf" && ["The Basic Layer", "The System Layer"].includes(hierarchy.lvl0);
        record.url_without_anchor = pageUrl;
        if (targets.has(anchor)) {
          const target = targets.get(anchor);
          record.anchor = target;
          record.url = pageUrl + (target ? `#${target}` : "");
        }
      }
      return records;
    },
  }],
  initialIndexSettings: {
    tikz: {
      attributesForFaceting: ["lang", "tags", "type"],
      attributesToRetrieve: ["hierarchy", "content", "anchor", "url", "url_without_anchor", "type", "manual", "search_group"],
      attributesToHighlight: ["hierarchy", "content"],
      attributesToSnippet: ["content:10"],
      camelCaseAttributes: ["hierarchy", "content"],
      searchableAttributes: [
        "unordered(hierarchy.lvl0)", "unordered(hierarchy.lvl1)", "unordered(hierarchy.lvl4)",
        "unordered(hierarchy.lvl2)", "unordered(hierarchy.lvl3)", "unordered(hierarchy.lvl5)",
        "unordered(hierarchy.lvl6)", "content",
      ],
      distinct: 2,
      attributeForDistinct: "search_group",
      hitsPerPage: 10,
      ranking: ["words", "filters", "typo", "asc(isBaseOrSystem)", "attribute", "proximity", "exact", "custom"],
      customRanking: ["desc(weight.pageRank)", "desc(weight.level)", "asc(weight.position)"],
      separatorsToIndex: "->|\\/",
      highlightPreTag: '<span class="algolia-docsearch-suggestion--highlight">',
      highlightPostTag: "</span>",
      minWordSizefor1Typo: 3,
      minWordSizefor2Typos: 7,
      allowTyposOnNumericTokens: false,
      minProximity: 1,
      ignorePlurals: true,
      advancedSyntax: true,
      attributeCriteriaComputedByMinProximity: true,
      removeWordsIfNoResults: "allOptional",
    },
  },
});

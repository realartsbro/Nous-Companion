(function () {
  "use strict";

  const ICON_PATHS = {
    "arrow-right": [
      '<path d="M5 12h14"></path>',
      '<path d="m12 5 7 7-7 7"></path>'
    ],
    "chevron-left": [
      '<path d="m15 18-6-6 6-6"></path>'
    ],
    "chevron-right": [
      '<path d="m9 18 6-6-6-6"></path>'
    ],
    "folder-open": [
      '<path d="M6 14h10l2-5H8z"></path>',
      '<path d="M3 19h13a2 2 0 0 0 1.9-1.37L21 9a2 2 0 0 0-1.9-2.63H11l-2-2H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2Z"></path>'
    ],
    plus: [
      '<path d="M5 12h14"></path>',
      '<path d="M12 5v14"></path>'
    ],
    "refresh-cw": [
      '<path d="M21 12a9 9 0 0 0-15.5-6.36L3 8"></path>',
      '<path d="M3 3v5h5"></path>',
      '<path d="M3 12a9 9 0 0 0 15.5 6.36L21 16"></path>',
      '<path d="M16 16h5v5"></path>'
    ],
    "volume-2": [
      '<path d="M11 5 6 9H2v6h4l5 4z"></path>',
      '<path d="M15.54 8.46a5 5 0 0 1 0 7.07"></path>',
      '<path d="M19.07 4.93a10 10 0 0 1 0 14.14"></path>'
    ],
    x: [
      '<path d="M18 6 6 18"></path>',
      '<path d="m6 6 12 12"></path>'
    ],
    download: [
      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>',
      '<polyline points="7 10 12 15 17 10"></polyline>',
      '<line x1="12" y1="15" x2="12" y2="3"></line>'
    ],
    upload: [
      '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>',
      '<polyline points="17 8 12 3 7 8"></polyline>',
      '<line x1="12" y1="3" x2="12" y2="15"></line>'
    ],
    trash: [
      '<path d="M3 6h18"></path>',
      '<path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>',
      '<path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>'
    ],
    folder: [
      '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"></path>'
    ]
  };

  function makeSvg(name) {
    const paths = ICON_PATHS[name];
    if (!paths) return null;

    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("fill", "none");
    svg.setAttribute("stroke", "currentColor");
    svg.setAttribute("stroke-width", "2");
    svg.setAttribute("stroke-linecap", "round");
    svg.setAttribute("stroke-linejoin", "round");
    svg.setAttribute("aria-hidden", "true");
    svg.classList.add("lucide", "lucide-" + name);
    svg.innerHTML = paths.join("");
    return svg;
  }

  function createIcons(root) {
    const scope = root || document;
    const nodes = scope.querySelectorAll("[data-lucide]");
    nodes.forEach((node) => {
      const name = node.getAttribute("data-lucide");
      const svg = makeSvg(name);
      if (!svg) return;

      const extraClass = node.getAttribute("class");
      if (extraClass) {
        extraClass.split(/\s+/).filter(Boolean).forEach((className) => svg.classList.add(className));
      }

      const width = node.getAttribute("data-lucide-width");
      const height = node.getAttribute("data-lucide-height");
      if (width) svg.setAttribute("width", width);
      if (height) svg.setAttribute("height", height);

      for (const attr of node.attributes) {
        if (attr.name === "data-lucide" || attr.name === "class") continue;
        if (attr.name.startsWith("data-lucide-")) continue;
        svg.setAttribute(attr.name, attr.value);
      }

      node.replaceWith(svg);
    });
  }

  window.lucide = { createIcons };
})();

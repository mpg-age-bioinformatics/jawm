(() => {
  "use strict";

  const script = document.currentScript;
  if (!script) return;

  const docsRoot = new URL("../", script.src);

  fetch(new URL("versions.json", docsRoot))
    .then((response) => response.ok ? response.json() : [])
    .then((versions) => {
      const topic = document.querySelector(".md-header__topic:first-child");
      if (!topic || !versions.length || topic.querySelector(".md-version")) {
        return;
      }

      const selector = document.createElement("div");
      selector.className = "md-version";

      const current = document.createElement("button");
      current.type = "button";
      current.className = "md-version__current";
      current.setAttribute("aria-label", "Select version");
      current.textContent = "latest";
      selector.appendChild(current);

      const list = document.createElement("ul");
      list.className = "md-version__list";

      for (const version of versions) {
        if (version.properties?.hidden) continue;

        const versionRoot = version.version === "."
          ? docsRoot
          : new URL(`${encodeURIComponent(version.version)}/`, docsRoot);
        const item = document.createElement("li");
        item.className = "md-version__item";

        const link = document.createElement("a");
        link.className = "md-version__link";
        link.href = versionRoot;
        link.textContent = version.title;
        link.addEventListener("click", async (event) => {
          if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
            return;
          }
          event.preventDefault();

          const page = window.location.pathname.startsWith(docsRoot.pathname)
            ? window.location.pathname.slice(docsRoot.pathname.length)
            : "";
          const candidate = new URL(page, versionRoot);
          try {
            const response = await fetch(candidate, { method: "HEAD" });
            window.location.assign(response.ok ? candidate : versionRoot);
          } catch {
            window.location.assign(versionRoot);
          }
        });

        item.appendChild(link);
        list.appendChild(item);
      }

      selector.appendChild(list);
      topic.appendChild(selector);
    })
    .catch(() => {});
})();

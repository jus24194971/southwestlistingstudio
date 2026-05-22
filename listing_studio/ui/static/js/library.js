/**
 * Library view: the left sidebar listing all templates grouped by folder.
 */

(function () {
    "use strict";

    LS.loadTemplates = async function () {
        try {
            LS.state.templatesByFolder = await LS.api("GET", "/api/templates");
            LS.renderLibrary();
        } catch (err) {
            console.error("Failed to load templates:", err);
            LS.$("template-list").innerHTML =
                `<div class="empty-loading">Failed to load: ${err.message}</div>`;
        }
    };

    LS.renderLibrary = function () {
        const list = LS.$("template-list");
        list.innerHTML = "";

        const folders = Object.keys(LS.state.templatesByFolder).sort();
        const total = folders.reduce(
            (sum, f) => sum + LS.state.templatesByFolder[f].length, 0);
        LS.$("template-count").textContent = total;

        if (total === 0) {
            list.appendChild(LS.el("div", "empty-loading", "No templates yet."));
            return;
        }

        const search = LS.state.searchQuery.toLowerCase().trim();

        for (const folder of folders) {
            const templates = LS.state.templatesByFolder[folder].filter(t =>
                !search || t.name.toLowerCase().includes(search)
            );
            if (templates.length === 0) continue;

            const group = LS.el("div", "lib-group");
            const header = LS.el("div", "lib-group-header");
            header.appendChild(LS.el("span", null, folder));
            header.appendChild(LS.el("span", "lib-group-count", String(templates.length)));
            group.appendChild(header);

            for (const tmpl of templates) {
                group.appendChild(renderTemplateItem(tmpl));
            }
            list.appendChild(group);
        }
    };

    function renderTemplateItem(tmpl) {
        const item = LS.el("div", "lib-item");
        if (tmpl.id === LS.state.selectedTemplateId) item.classList.add("active");

        const row = LS.el("div", "lib-item-row");
        if (tmpl.is_starred) row.appendChild(LS.el("span", "star", "★"));
        row.appendChild(LS.el("span", "lib-item-name", tmpl.name));
        item.appendChild(row);

        const meta = `${LS.timeAgo(tmpl.last_posted_at)} · ${tmpl.post_count} time${tmpl.post_count === 1 ? "" : "s"}`;
        item.appendChild(LS.el("div", "lib-item-meta", meta));

        item.addEventListener("click", () => {
            if (LS.state.formDirty) {
                if (!confirm("Discard unsaved changes?")) return;
            }
            LS.selectTemplate(tmpl.id);
        });

        return item;
    }
})();

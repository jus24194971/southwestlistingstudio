/**
 * Library view: the left sidebar listing all templates grouped by folder.
 */

(function () {
    "use strict";

    LS.loadTemplates = async function () {
        try {
            // Load categories in parallel - they're rendered alongside templates
            const [templatesByFolder, _categories] = await Promise.all([
                LS.api("GET", "/api/templates"),
                LS.loadCategories ? LS.loadCategories() : Promise.resolve([]),
            ]);
            LS.state.templatesByFolder = templatesByFolder;
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

        // "+ New Template" and "+ New Category" buttons at top
        if (LS.renderNewTemplateButton) {
            LS.renderNewTemplateButton(list);
        }
        if (LS.renderNewCategoryButton) {
            LS.renderNewCategoryButton(list);
        }

        // Categories section
        const categories = LS.state.categories || [];
        if (categories.length > 0) {
            const catGroup = LS.el("div", "lib-group");
            catGroup.style.marginBottom = "16px";
            const catHeader = LS.el("div", "lib-group-header");
            catHeader.appendChild(LS.el("span", null, "Categories"));
            catHeader.appendChild(LS.el("span", "lib-group-count", String(categories.length)));
            catGroup.appendChild(catHeader);

            for (const cat of categories) {
                catGroup.appendChild(renderCategoryItem(cat));
            }
            list.appendChild(catGroup);
        }

        const folders = Object.keys(LS.state.templatesByFolder).sort();
        const total = folders.reduce(
            (sum, f) => sum + LS.state.templatesByFolder[f].length, 0);
        LS.$("template-count").textContent = total;

        if (total === 0 && categories.length === 0) {
            list.appendChild(LS.el("div", "empty-loading", "No templates or categories yet. Create a category to get started."));
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

    LS.refreshLibrary = function () {
        // Called from category editor when a category is created/edited/deleted.
        LS.renderLibrary();
    };

    function renderCategoryItem(cat) {
        const item = LS.el("div", "lib-item");
        item.style.cursor = "pointer";

        const row = LS.el("div", "lib-item-row");
        const nameEl = LS.el("span", "lib-item-name", cat.name);
        nameEl.style.color = "var(--gold-bright)";
        row.appendChild(nameEl);

        if (cat.template_count > 0) {
            const countBadge = LS.el("span", "lib-item-meta", `${cat.template_count}`);
            countBadge.style.marginLeft = "auto";
            countBadge.style.fontSize = "11px";
            row.appendChild(countBadge);
        }
        item.appendChild(row);

        if (cat.reverb_category_full_name) {
            const meta = LS.el("div", "lib-item-meta");
            meta.style.fontFamily = "var(--font-mono)";
            meta.style.fontSize = "10px";
            meta.textContent = cat.reverb_category_full_name;
            item.appendChild(meta);
        }

        item.addEventListener("click", () => {
            if (LS.openCategoryEditor) LS.openCategoryEditor(cat);
        });

        return item;
    }

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

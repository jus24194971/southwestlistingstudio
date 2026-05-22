/**
 * Library view: the left sidebar listing all templates grouped by category.
 *
 * Layout:
 *   ┌─ scrollable region ─────────────┐
 *   │ ▼ Tuners                  (3)   │  ← collapsible category group
 *   │     Kluson Vintage Nickel       │
 *   │     Locking Set Chrome          │
 *   │ ▶ Pickups                 (12)  │  ← collapsed (chevron right)
 *   │ ▼ Uncategorized           (4)   │  ← shows templates with no category
 *   │     Test Template               │
 *   ├─ pinned to bottom ──────────────┤
 *   │ [+ New Template ]               │  ← gold buttons
 *   │ [+ New Category ]               │
 *   └─────────────────────────────────┘
 *
 * Collapse state persisted to localStorage so it survives restarts.
 */

(function () {
    "use strict";

    const COLLAPSED_KEY = "ls.collapsed_categories";

    function getCollapsed() {
        try {
            return new Set(JSON.parse(localStorage.getItem(COLLAPSED_KEY) || "[]"));
        } catch {
            return new Set();
        }
    }

    function setCollapsed(set) {
        try {
            localStorage.setItem(COLLAPSED_KEY, JSON.stringify(Array.from(set)));
        } catch {
            // localStorage may be disabled - degrade silently
        }
    }

    function toggleCollapsed(key) {
        const collapsed = getCollapsed();
        if (collapsed.has(key)) {
            collapsed.delete(key);
        } else {
            collapsed.add(key);
        }
        setCollapsed(collapsed);
        LS.renderLibrary();
    }

    LS.loadTemplates = async function () {
        try {
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

        // Flatten templatesByFolder into a single array so we can re-group by category
        const allTemplates = [];
        for (const folder of Object.keys(LS.state.templatesByFolder)) {
            allTemplates.push(...LS.state.templatesByFolder[folder]);
        }
        LS.$("template-count").textContent = String(allTemplates.length);

        const categories = LS.state.categories || [];
        const collapsed = getCollapsed();
        const search = LS.state.searchQuery.toLowerCase().trim();

        // Index templates by category_id for fast grouping
        const byCategoryId = new Map();
        const uncategorized = [];
        for (const tmpl of allTemplates) {
            if (tmpl.category_id != null) {
                if (!byCategoryId.has(tmpl.category_id)) {
                    byCategoryId.set(tmpl.category_id, []);
                }
                byCategoryId.get(tmpl.category_id).push(tmpl);
            } else {
                uncategorized.push(tmpl);
            }
        }

        if (allTemplates.length === 0 && categories.length === 0) {
            list.appendChild(LS.el("div", "empty-loading",
                "Nothing here yet. Start by creating a Category, then a Template inside it."));
            renderFooterButtons(list);
            return;
        }

        // Render one group per category, in alphabetical order
        for (const cat of categories) {
            const templates = (byCategoryId.get(cat.id) || []).filter(t =>
                !search || t.name.toLowerCase().includes(search)
            );

            // Hide categories whose templates don't match the search filter
            // (but still show them when no search is active, even if empty)
            if (search && templates.length === 0) continue;

            const key = `cat:${cat.id}`;
            const isCollapsed = collapsed.has(key);
            const group = renderGroup({
                key,
                label: cat.name,
                count: templates.length,
                collapsed: isCollapsed,
                onHeaderClick: () => toggleCollapsed(key),
                onLabelClick: () => LS.openCategoryEditor && LS.openCategoryEditor(cat),
                templates,
                labelExtra: cat.reverb_category_full_name,
            });
            list.appendChild(group);
        }

        // Uncategorized templates (e.g. test data or templates created without a category)
        const filteredUncat = uncategorized.filter(t =>
            !search || t.name.toLowerCase().includes(search)
        );
        if (filteredUncat.length > 0) {
            const key = "cat:uncategorized";
            const isCollapsed = collapsed.has(key);
            const group = renderGroup({
                key,
                label: "Uncategorized",
                count: filteredUncat.length,
                collapsed: isCollapsed,
                onHeaderClick: () => toggleCollapsed(key),
                templates: filteredUncat,
            });
            list.appendChild(group);
        }

        renderFooterButtons(list);
    };

    LS.refreshLibrary = function () {
        LS.renderLibrary();
    };

    function renderGroup(opts) {
        const group = LS.el("div", "lib-group");

        const header = LS.el("div", "lib-group-header");
        header.style.cursor = "pointer";
        header.style.display = "flex";
        header.style.alignItems = "center";
        header.style.gap = "6px";

        const chevron = LS.el("span");
        chevron.style.fontSize = "10px";
        chevron.style.color = "var(--ink-3)";
        chevron.style.width = "10px";
        chevron.style.display = "inline-block";
        chevron.textContent = opts.collapsed ? "▶" : "▼";
        header.appendChild(chevron);

        const labelSpan = LS.el("span", null, opts.label);
        labelSpan.style.flex = "1";
        if (opts.onLabelClick) {
            labelSpan.style.cursor = "pointer";
            labelSpan.addEventListener("click", e => {
                e.stopPropagation();
                opts.onLabelClick();
            });
            labelSpan.title = "Click name to edit this category";
        }
        header.appendChild(labelSpan);
        header.appendChild(LS.el("span", "lib-group-count", String(opts.count)));

        header.addEventListener("click", opts.onHeaderClick);
        group.appendChild(header);

        if (!opts.collapsed && opts.labelExtra) {
            const extra = LS.el("div");
            extra.style.fontSize = "10px";
            extra.style.color = "var(--ink-3)";
            extra.style.fontFamily = "var(--font-mono)";
            extra.style.padding = "0 0 6px 24px";
            extra.style.marginTop = "-4px";
            extra.textContent = opts.labelExtra;
            group.appendChild(extra);
        }

        if (!opts.collapsed) {
            for (const tmpl of opts.templates) {
                group.appendChild(renderTemplateItem(tmpl));
            }
            if (opts.templates.length === 0) {
                const empty = LS.el("div");
                empty.style.padding = "8px 24px";
                empty.style.fontSize = "11px";
                empty.style.color = "var(--ink-3)";
                empty.style.fontStyle = "italic";
                empty.textContent = "No templates yet";
                group.appendChild(empty);
            }
        }
        return group;
    }

    function renderTemplateItem(tmpl) {
        const item = LS.el("div", "lib-item");
        item.style.position = "relative";
        if (tmpl.id === LS.state.selectedTemplateId) item.classList.add("active");

        const row = LS.el("div", "lib-item-row");
        if (tmpl.is_starred) row.appendChild(LS.el("span", "star", "★"));
        row.appendChild(LS.el("span", "lib-item-name", tmpl.name));
        item.appendChild(row);

        const meta = `${LS.timeAgo(tmpl.last_posted_at)} · ${tmpl.post_count} time${tmpl.post_count === 1 ? "" : "s"}`;
        item.appendChild(LS.el("div", "lib-item-meta", meta));

        // Delete button - shows on hover
        const delBtn = LS.el("button");
        delBtn.textContent = "×";
        delBtn.title = "Delete template";
        Object.assign(delBtn.style, {
            position: "absolute",
            top: "6px",
            right: "6px",
            width: "20px",
            height: "20px",
            borderRadius: "50%",
            background: "rgba(0,0,0,0.4)",
            border: "1px solid var(--line)",
            color: "var(--ink-3)",
            cursor: "pointer",
            fontSize: "14px",
            lineHeight: "1",
            padding: "0",
            opacity: "0",
            transition: "opacity 0.15s",
        });
        item.addEventListener("mouseenter", () => { delBtn.style.opacity = "1"; });
        item.addEventListener("mouseleave", () => { delBtn.style.opacity = "0"; });
        delBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            if (!confirm(`Delete template "${tmpl.name}"?\n\nThis removes it from your library. Listings already posted to marketplaces are not affected.`)) {
                return;
            }
            try {
                await LS.api("DELETE", `/api/templates/${tmpl.id}`);
                if (LS.state.selectedTemplateId === tmpl.id) {
                    LS.state.selectedTemplateId = null;
                    LS.state.currentTemplate = null;
                    const formPanel = LS.$("form-panel");
                    if (formPanel) {
                        formPanel.innerHTML = '<div class="empty-loading">Select a template to edit it.</div>';
                    }
                }
                await LS.loadTemplates();
            } catch (err) {
                alert(`Delete failed: ${err.message}`);
            }
        });
        item.appendChild(delBtn);

        item.addEventListener("click", () => {
            if (LS.state.formDirty) {
                if (!confirm("Discard unsaved changes?")) return;
            }
            LS.selectTemplate(tmpl.id);
        });

        return item;
    }

    /**
     * The "+ New Template" and "+ New Category" buttons, pinned to the bottom.
     * Gold-on-dark like the Post Listing button - these are primary actions.
     */
    function renderFooterButtons(host) {
        const footer = LS.el("div");
        Object.assign(footer.style, {
            display: "flex",
            flexDirection: "column",
            gap: "8px",
            paddingTop: "16px",
            marginTop: "auto",
            borderTop: "1px solid var(--line)",
        });

        const newTmplBtn = LS.el("button");
        applyPrimaryButtonStyle(newTmplBtn);
        newTmplBtn.innerHTML = `<span style="margin-right: 6px;">+</span>New Template`;
        newTmplBtn.addEventListener("click", () => {
            if (LS.openNewTemplateModal) LS.openNewTemplateModal();
        });
        footer.appendChild(newTmplBtn);

        const newCatBtn = LS.el("button");
        applyPrimaryButtonStyle(newCatBtn);
        newCatBtn.innerHTML = `<span style="margin-right: 6px;">+</span>New Category`;
        newCatBtn.addEventListener("click", () => {
            if (LS.openCategoryEditor) LS.openCategoryEditor();
        });
        footer.appendChild(newCatBtn);

        host.appendChild(footer);
    }

    function applyPrimaryButtonStyle(btn) {
        Object.assign(btn.style, {
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "10px 14px",
            background: "var(--gold-bright)",
            color: "var(--bg-deep)",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
            fontSize: "13px",
            fontWeight: "600",
            letterSpacing: "0.02em",
            transition: "opacity 0.15s",
        });
        btn.addEventListener("mouseenter", () => { btn.style.opacity = "0.9"; });
        btn.addEventListener("mouseleave", () => { btn.style.opacity = "1"; });
    }
})();

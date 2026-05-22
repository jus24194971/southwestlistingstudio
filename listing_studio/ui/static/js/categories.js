/**
 * Category management.
 *
 * Categories are Dad's organizational buckets (Tuners, Pickups, etc) that map
 * to Reverb's taxonomy UUIDs. This module owns:
 *   - The "+ New Category" button at the top of the library sidebar
 *   - The category creation modal with Reverb taxonomy search
 *   - Category list display in the sidebar
 *   - Category dropdown for the template form
 */

(function () {
    "use strict";

    // State
    LS.state.categories = [];  // populated by loadCategories()

    LS.loadCategories = async function () {
        try {
            LS.state.categories = await LS.api("GET", "/api/categories");
        } catch (err) {
            console.error("Failed to load categories:", err);
            LS.state.categories = [];
        }
        return LS.state.categories;
    };

    LS.getCategoryById = function (id) {
        if (id == null) return null;
        return LS.state.categories.find(c => c.id === id) || null;
    };

    // ------------------------------------------------------------------
    // "+ New Category" button - rendered into a host element
    // ------------------------------------------------------------------

    LS.renderNewCategoryButton = function (host) {
        const btn = LS.el("button", "btn-new-category");
        btn.innerHTML = `<span style="font-size: 16px;">+</span> <span>New Category</span>`;
        Object.assign(btn.style, {
            width: "100%",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            justifyContent: "center",
            padding: "8px 12px",
            background: "transparent",
            border: "1px dashed var(--line)",
            borderRadius: "4px",
            color: "var(--gold-bright)",
            cursor: "pointer",
            fontSize: "13px",
            marginBottom: "12px",
        });
        btn.addEventListener("mouseenter", () => {
            btn.style.background = "var(--bg-input)";
        });
        btn.addEventListener("mouseleave", () => {
            btn.style.background = "transparent";
        });
        btn.addEventListener("click", () => openCategoryEditor());
        host.appendChild(btn);
    };

    // ------------------------------------------------------------------
    // Category editor modal (create or edit)
    // ------------------------------------------------------------------

    /**
     * Open the category create/edit modal.
     * @param {object|null} existing - if present, edits this category; otherwise creates a new one
     */
    function openCategoryEditor(existing) {
        const isEdit = !!existing;
        const state = {
            name: existing ? existing.name : "",
            reverb_category_uuid: existing ? existing.reverb_category_uuid : null,
            reverb_category_full_name: existing ? existing.reverb_category_full_name : null,
            reverb_subcategory_uuids: existing ? [...(existing.reverb_subcategory_uuids || [])] : [],
            reverb_subcategory_names: existing ? [...(existing.reverb_subcategory_names || [])] : [],
            default_condition: existing ? existing.default_condition : null,
            default_weight_oz: existing ? existing.default_weight_oz : null,
            default_shipping_method: existing ? existing.default_shipping_method : null,
        };

        const backdrop = LS.el("div", "modal-backdrop");
        const card = LS.el("div", "modal-card");
        card.style.maxWidth = "680px";
        card.style.maxHeight = "85vh";
        card.style.overflowY = "auto";

        const h2 = LS.el("h2");
        h2.innerHTML = isEdit
            ? `Edit category <em>${LS.escapeHTML(existing.name)}</em>`
            : `New <em>category</em>`;
        card.appendChild(h2);

        card.appendChild(LS.el("div", "modal-sub",
            "Categories organize your templates and map them to each marketplace's taxonomy. Set this up once per category and reuse across many listings."));

        // Name field
        card.appendChild(buildLabel("Category Name", "What Dad calls this category (e.g. Tuners, Bridges, Acoustic Guitars)"));
        const nameInput = buildInput(state.name);
        nameInput.placeholder = "e.g. Tuners";
        nameInput.addEventListener("input", () => { state.name = nameInput.value; });
        card.appendChild(nameInput);

        // --- Reverb section ---
        const reverbSection = LS.el("div");
        reverbSection.style.marginTop = "24px";
        reverbSection.style.paddingTop = "20px";
        reverbSection.style.borderTop = "1px solid var(--line)";
        const reverbHeader = LS.el("div");
        reverbHeader.style.display = "flex";
        reverbHeader.style.alignItems = "center";
        reverbHeader.style.gap = "10px";
        reverbHeader.style.marginBottom = "12px";
        const reverbLogo = LS.el("span", null, "Reverb");
        reverbLogo.style.fontFamily = "var(--font-display)";
        reverbLogo.style.fontStyle = "italic";
        reverbLogo.style.color = "var(--gold-bright)";
        reverbLogo.style.fontSize = "16px";
        reverbHeader.appendChild(reverbLogo);
        const reverbTag = LS.el("span", null, "Taxonomy Mapping");
        reverbTag.style.fontSize = "10px";
        reverbTag.style.textTransform = "uppercase";
        reverbTag.style.letterSpacing = "0.08em";
        reverbTag.style.color = "var(--ink-3)";
        reverbHeader.appendChild(reverbTag);
        reverbSection.appendChild(reverbHeader);

        // Current selection display
        const currentDisplay = LS.el("div");
        currentDisplay.id = "category-reverb-current";
        Object.assign(currentDisplay.style, {
            padding: "12px",
            background: "var(--bg-input)",
            borderRadius: "4px",
            marginBottom: "12px",
            fontSize: "13px",
            minHeight: "44px",
        });
        renderCurrentReverbSelection(currentDisplay, state);
        reverbSection.appendChild(currentDisplay);

        // Search picker
        const searchHeading = LS.el("div", "pref-label", "Search Reverb's category tree");
        searchHeading.style.fontSize = "11px";
        searchHeading.style.textTransform = "uppercase";
        searchHeading.style.letterSpacing = "0.08em";
        searchHeading.style.color = "var(--ink-3)";
        searchHeading.style.marginBottom = "6px";
        reverbSection.appendChild(searchHeading);

        const searchInput = buildInput("");
        searchInput.placeholder = "Type to search (e.g. tuner, pickup, acoustic)";
        reverbSection.appendChild(searchInput);

        const resultsContainer = LS.el("div");
        Object.assign(resultsContainer.style, {
            marginTop: "8px",
            maxHeight: "260px",
            overflowY: "auto",
            border: "1px solid var(--line)",
            borderRadius: "4px",
        });
        reverbSection.appendChild(resultsContainer);

        // Search behavior - debounced
        let searchTimer = null;
        async function doSearch(query) {
            try {
                const results = await LS.api("GET",
                    `/api/platforms/reverb/taxonomy/search?q=${encodeURIComponent(query)}&limit=30`);
                renderSearchResults(resultsContainer, results, state, currentDisplay);
            } catch (err) {
                resultsContainer.innerHTML = "";
                const errMsg = LS.el("div");
                errMsg.style.padding = "12px";
                errMsg.style.color = "var(--rust-bright)";
                errMsg.style.fontSize = "12px";
                errMsg.textContent = `Search failed: ${err.message}. Make sure Reverb is connected in Settings.`;
                resultsContainer.appendChild(errMsg);
            }
        }
        searchInput.addEventListener("input", () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => doSearch(searchInput.value.trim()), 250);
        });
        // Show initial alphabetical list
        doSearch("");

        card.appendChild(reverbSection);

        // --- Defaults section ---
        const defaultsSection = LS.el("div");
        defaultsSection.style.marginTop = "24px";
        defaultsSection.style.paddingTop = "20px";
        defaultsSection.style.borderTop = "1px solid var(--line)";

        const defaultsHeader = LS.el("div");
        defaultsHeader.style.fontSize = "14px";
        defaultsHeader.style.fontWeight = "600";
        defaultsHeader.style.marginBottom = "4px";
        defaultsHeader.textContent = "Optional Defaults";
        defaultsSection.appendChild(defaultsHeader);

        const defaultsHelp = LS.el("div");
        defaultsHelp.style.fontSize = "12px";
        defaultsHelp.style.color = "var(--ink-3)";
        defaultsHelp.style.marginBottom = "12px";
        defaultsHelp.textContent = "When you create a new template in this category, these values pre-fill the form. You can always override per-template.";
        defaultsSection.appendChild(defaultsHelp);

        // Condition default
        defaultsSection.appendChild(buildLabel("Default Condition", "Most items in this category are usually..."));
        const conditionSelect = LS.el("select");
        conditionSelect.style.cssText = "width: 100%; background: var(--bg-input); border: 1px solid var(--line); border-radius: 4px; padding: 8px 12px; color: var(--ink); font-size: 13px;";
        for (const opt of [
            { value: "", label: "(no default - pick per template)" },
            { value: "brand_new", label: "Brand New" },
            { value: "mint", label: "Mint" },
            { value: "excellent", label: "Excellent" },
            { value: "very_good", label: "Very Good" },
            { value: "good", label: "Good" },
            { value: "fair", label: "Fair" },
            { value: "poor", label: "Poor" },
            { value: "b_stock", label: "B-Stock" },
        ]) {
            const o = LS.el("option", null, opt.label);
            o.value = opt.value;
            if (opt.value === (state.default_condition || "")) o.selected = true;
            conditionSelect.appendChild(o);
        }
        conditionSelect.addEventListener("change", () => {
            state.default_condition = conditionSelect.value || null;
        });
        defaultsSection.appendChild(conditionSelect);

        // Weight default
        defaultsSection.appendChild(buildLabel("Default Weight (oz)", "Typical weight - tuners ~3oz, bodies ~32oz, etc."));
        const weightInput = buildInput(state.default_weight_oz != null ? String(state.default_weight_oz) : "");
        weightInput.placeholder = "Leave blank for no default";
        weightInput.addEventListener("input", () => {
            const v = parseFloat(weightInput.value);
            state.default_weight_oz = isNaN(v) ? null : v;
        });
        defaultsSection.appendChild(weightInput);

        card.appendChild(defaultsSection);

        // --- Footer ---
        const footer = LS.el("div", "modal-footer-bar");
        footer.style.marginTop = "24px";

        // Delete button (only when editing, and only if no templates use it)
        if (isEdit && existing.template_count === 0) {
            const deleteBtn = LS.el("button", "btn-ghost", "Delete");
            deleteBtn.style.color = "var(--rust-bright)";
            deleteBtn.style.marginRight = "auto";
            deleteBtn.addEventListener("click", async () => {
                if (!confirm(`Delete category "${existing.name}"?`)) return;
                try {
                    await LS.api("DELETE", `/api/categories/${existing.id}`);
                    backdrop.remove();
                    await LS.loadCategories();
                    if (LS.refreshLibrary) LS.refreshLibrary();
                } catch (err) {
                    alert(`Delete failed: ${err.message}`);
                }
            });
            footer.appendChild(deleteBtn);
        }

        const cancelBtn = LS.el("button", "btn-ghost", "Cancel");
        cancelBtn.addEventListener("click", () => backdrop.remove());
        footer.appendChild(cancelBtn);

        const saveBtn = LS.el("button", "btn-update-now", isEdit ? "Save Changes" : "Create Category");
        saveBtn.addEventListener("click", async () => {
            const name = state.name.trim();
            if (!name) {
                alert("Category name is required");
                return;
            }
            saveBtn.disabled = true;
            saveBtn.textContent = "Saving…";

            const payload = {
                name,
                reverb_category_uuid: state.reverb_category_uuid,
                reverb_category_full_name: state.reverb_category_full_name,
                reverb_subcategory_uuids: state.reverb_subcategory_uuids,
                reverb_subcategory_names: state.reverb_subcategory_names,
                default_condition: state.default_condition,
                default_weight_oz: state.default_weight_oz,
                default_shipping_method: state.default_shipping_method,
            };

            try {
                if (isEdit) {
                    await LS.api("PATCH", `/api/categories/${existing.id}`, payload);
                } else {
                    await LS.api("POST", "/api/categories", payload);
                }
                backdrop.remove();
                await LS.loadCategories();
                if (LS.refreshLibrary) LS.refreshLibrary();
            } catch (err) {
                alert(`Save failed: ${err.message}`);
                saveBtn.disabled = false;
                saveBtn.textContent = isEdit ? "Save Changes" : "Create Category";
            }
        });
        footer.appendChild(saveBtn);

        card.appendChild(footer);

        backdrop.appendChild(card);
        backdrop.addEventListener("click", e => {
            if (e.target === backdrop) backdrop.remove();
        });
        document.body.appendChild(backdrop);

        setTimeout(() => nameInput.focus(), 50);
    }

    LS.openCategoryEditor = openCategoryEditor;

    // ------------------------------------------------------------------
    // Reverb taxonomy result rendering
    // ------------------------------------------------------------------

    function renderCurrentReverbSelection(host, state) {
        host.innerHTML = "";
        if (!state.reverb_category_uuid) {
            const empty = LS.el("div");
            empty.style.color = "var(--ink-3)";
            empty.style.fontStyle = "italic";
            empty.textContent = "No Reverb category selected yet";
            host.appendChild(empty);
            return;
        }

        const mainRow = LS.el("div");
        mainRow.style.display = "flex";
        mainRow.style.alignItems = "center";
        mainRow.style.gap = "8px";
        mainRow.style.marginBottom = state.reverb_subcategory_uuids.length > 0 ? "8px" : "0";

        const primaryLabel = LS.el("span");
        primaryLabel.style.fontSize = "10px";
        primaryLabel.style.background = "var(--gold-bright)";
        primaryLabel.style.color = "var(--bg-deep)";
        primaryLabel.style.padding = "2px 6px";
        primaryLabel.style.borderRadius = "3px";
        primaryLabel.style.fontWeight = "600";
        primaryLabel.textContent = "PRIMARY";
        mainRow.appendChild(primaryLabel);

        const nameEl = LS.el("span");
        nameEl.style.fontSize = "13px";
        nameEl.textContent = state.reverb_category_full_name || "(unknown)";
        mainRow.appendChild(nameEl);

        const clearBtn = LS.el("button");
        clearBtn.textContent = "×";
        clearBtn.title = "Clear selection";
        Object.assign(clearBtn.style, {
            marginLeft: "auto",
            background: "transparent",
            border: "none",
            color: "var(--ink-3)",
            cursor: "pointer",
            fontSize: "18px",
            padding: "0 4px",
        });
        clearBtn.addEventListener("click", () => {
            state.reverb_category_uuid = null;
            state.reverb_category_full_name = null;
            state.reverb_subcategory_uuids = [];
            state.reverb_subcategory_names = [];
            renderCurrentReverbSelection(host, state);
        });
        mainRow.appendChild(clearBtn);
        host.appendChild(mainRow);

        // Subcategories
        if (state.reverb_subcategory_uuids.length > 0) {
            const subRow = LS.el("div");
            subRow.style.display = "flex";
            subRow.style.gap = "6px";
            subRow.style.flexWrap = "wrap";
            state.reverb_subcategory_uuids.forEach((uuid, idx) => {
                const chip = LS.el("span");
                Object.assign(chip.style, {
                    fontSize: "12px",
                    padding: "3px 8px",
                    background: "var(--bg-panel)",
                    border: "1px solid var(--line)",
                    borderRadius: "12px",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "4px",
                });
                chip.appendChild(document.createTextNode(state.reverb_subcategory_names[idx] || "(?)"));
                const x = LS.el("button");
                x.textContent = "×";
                Object.assign(x.style, {
                    background: "transparent",
                    border: "none",
                    color: "var(--ink-3)",
                    cursor: "pointer",
                    padding: "0 0 0 4px",
                });
                x.addEventListener("click", () => {
                    state.reverb_subcategory_uuids.splice(idx, 1);
                    state.reverb_subcategory_names.splice(idx, 1);
                    renderCurrentReverbSelection(host, state);
                });
                chip.appendChild(x);
                subRow.appendChild(chip);
            });
            host.appendChild(subRow);
        }
    }

    function renderSearchResults(host, results, state, currentDisplay) {
        host.innerHTML = "";
        if (results.length === 0) {
            const empty = LS.el("div");
            empty.style.padding = "12px";
            empty.style.color = "var(--ink-3)";
            empty.style.fontSize = "12px";
            empty.style.fontStyle = "italic";
            empty.textContent = "No matches.";
            host.appendChild(empty);
            return;
        }

        for (const result of results) {
            const item = LS.el("div");
            Object.assign(item.style, {
                padding: "10px 12px",
                cursor: "pointer",
                borderBottom: "1px solid var(--line)",
                fontSize: "13px",
                display: "flex",
                gap: "8px",
                alignItems: "center",
            });
            item.addEventListener("mouseenter", () => {
                item.style.background = "var(--bg-input)";
            });
            item.addEventListener("mouseleave", () => {
                item.style.background = "transparent";
            });

            const text = LS.el("div");
            text.style.flex = "1";
            text.style.minWidth = "0";

            const nameEl = LS.el("div");
            nameEl.style.fontWeight = "500";
            nameEl.textContent = result.name;
            text.appendChild(nameEl);

            const fullEl = LS.el("div");
            fullEl.style.fontSize = "11px";
            fullEl.style.color = "var(--ink-3)";
            fullEl.style.fontFamily = "var(--font-mono)";
            fullEl.textContent = result.full_name;
            text.appendChild(fullEl);

            item.appendChild(text);

            // Action buttons
            const actions = LS.el("div");
            actions.style.display = "flex";
            actions.style.gap = "4px";

            const setPrimary = LS.el("button");
            setPrimary.textContent = "Set Primary";
            Object.assign(setPrimary.style, {
                fontSize: "11px",
                padding: "3px 8px",
                background: "transparent",
                border: "1px solid var(--gold)",
                color: "var(--gold-bright)",
                borderRadius: "3px",
                cursor: "pointer",
            });
            setPrimary.addEventListener("click", e => {
                e.stopPropagation();
                state.reverb_category_uuid = result.uuid;
                state.reverb_category_full_name = result.full_name;
                renderCurrentReverbSelection(currentDisplay, state);
            });
            actions.appendChild(setPrimary);

            if (state.reverb_subcategory_uuids.length < 2) {
                const addSub = LS.el("button");
                addSub.textContent = "+ Sub";
                Object.assign(addSub.style, {
                    fontSize: "11px",
                    padding: "3px 8px",
                    background: "transparent",
                    border: "1px solid var(--line)",
                    color: "var(--ink-2)",
                    borderRadius: "3px",
                    cursor: "pointer",
                });
                addSub.title = "Add as a subcategory (max 2)";
                addSub.addEventListener("click", e => {
                    e.stopPropagation();
                    if (state.reverb_subcategory_uuids.includes(result.uuid)) return;
                    if (state.reverb_subcategory_uuids.length >= 2) return;
                    state.reverb_subcategory_uuids.push(result.uuid);
                    state.reverb_subcategory_names.push(result.name);
                    renderCurrentReverbSelection(currentDisplay, state);
                });
                actions.appendChild(addSub);
            }

            item.appendChild(actions);
            host.appendChild(item);
        }
    }

    // ------------------------------------------------------------------
    // Helpers
    // ------------------------------------------------------------------

    function buildLabel(text, helpText) {
        const wrap = LS.el("div");
        wrap.style.marginTop = "12px";
        wrap.style.marginBottom = "4px";

        const label = LS.el("div");
        label.style.fontSize = "11px";
        label.style.color = "var(--ink-2)";
        label.style.textTransform = "uppercase";
        label.style.letterSpacing = "0.08em";
        label.style.fontWeight = "600";
        label.textContent = text;
        wrap.appendChild(label);

        if (helpText) {
            const help = LS.el("div");
            help.style.fontSize = "11px";
            help.style.color = "var(--ink-3)";
            help.style.marginTop = "2px";
            help.style.fontStyle = "italic";
            help.textContent = helpText;
            wrap.appendChild(help);
        }
        return wrap;
    }

    function buildInput(value) {
        const input = LS.el("input");
        input.type = "text";
        input.value = value || "";
        Object.assign(input.style, {
            width: "100%",
            background: "var(--bg-input)",
            border: "1px solid var(--line)",
            borderRadius: "4px",
            padding: "8px 12px",
            color: "var(--ink)",
            fontSize: "13px",
        });
        return input;
    }
})();

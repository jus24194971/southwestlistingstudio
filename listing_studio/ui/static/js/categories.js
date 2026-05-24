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
            // Reverb
            reverb_category_uuid: existing ? existing.reverb_category_uuid : null,
            reverb_category_full_name: existing ? existing.reverb_category_full_name : null,
            reverb_subcategory_uuids: existing ? [...(existing.reverb_subcategory_uuids || [])] : [],
            reverb_subcategory_names: existing ? [...(existing.reverb_subcategory_names || [])] : [],
            // eBay (single leaf only - no subcategories)
            ebay_category_id: existing ? existing.ebay_category_id : null,
            ebay_category_name: existing ? existing.ebay_category_name : null,
            ebay_category_path: existing ? existing.ebay_category_path : null,
            ebay_leaf: existing ? (existing.ebay_leaf !== false) : true,
            // Squarespace (store page assignment, not a strict taxonomy)
            squarespace_store_page_id: existing ? existing.squarespace_store_page_id : null,
            squarespace_store_page_name: existing ? existing.squarespace_store_page_name : null,
            // Shared defaults
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

        // Recent-used list above the Reverb search results. Refreshed each time
        // the modal opens; updates as Dad saves categories.
        const reverbRecent = LS.el("div");
        reverbRecent.style.marginTop = "8px";
        reverbSection.appendChild(reverbRecent);
        loadRecentUsed("reverb", reverbRecent, (entry) => {
            state.reverb_category_uuid = entry.external_id;
            state.reverb_category_full_name = entry.display_path || entry.display_name;
            renderCurrentReverbSelection(currentDisplay, state);
            refreshSuggestions();
        });

        // Search behavior - debounced
        let searchTimer = null;
        async function doSearch(query) {
            try {
                const results = await LS.api("GET",
                    `/api/platforms/reverb/taxonomy/search?q=${encodeURIComponent(query)}&limit=30`);
                renderSearchResults(resultsContainer, results, state, currentDisplay, refreshSuggestions);
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

        // Cross-platform suggestion callout: shown when Reverb is picked but
        // eBay isn't, suggesting an eBay category to match. Mirror on the
        // eBay section for the reverse direction. refreshSuggestions() is
        // declared further down (closure-captured here, defined later).
        const reverbSuggestion = LS.el("div");
        reverbSection.appendChild(reverbSuggestion);

        card.appendChild(reverbSection);

        // --- eBay section ---
        const ebaySection = buildEbaySection(state, refreshSuggestionsHandle());
        card.appendChild(ebaySection.el);

        // --- Squarespace section ---
        const squarespaceSection = buildSquarespaceSection(state);
        card.appendChild(squarespaceSection.el);

        // The actual suggestion-refresher closure - re-renders both callouts
        // whenever either picker's state changes. Pulled together here so it
        // can see the section refs.
        function refreshSuggestions() {
            renderSuggestionCallout(
                reverbSuggestion,
                "reverb", state.reverb_category_uuid, state.reverb_category_full_name,
                "ebay",
                (match) => {
                    state.ebay_category_id = parseInt(match.external_id, 10);
                    state.ebay_category_name = match.display_name;
                    state.ebay_category_path = match.display_path || match.display_name;
                    state.ebay_leaf = true; // assume true; UI warns if proven otherwise
                    ebaySection.refreshDisplay();
                    refreshSuggestions();
                },
            );
            ebaySection.refreshSuggestion();
        }
        // Now expose the handle that the eBay section needs at construction
        function refreshSuggestionsHandle() {
            // Returned to buildEbaySection so its picker can trigger us
            return () => refreshSuggestions();
        }
        refreshSuggestions(); // initial render

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
                ebay_category_id: state.ebay_category_id,
                ebay_category_name: state.ebay_category_name,
                ebay_category_path: state.ebay_category_path,
                ebay_leaf: state.ebay_leaf,
                squarespace_store_page_id: state.squarespace_store_page_id,
                squarespace_store_page_name: state.squarespace_store_page_name,
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

    // ------------------------------------------------------------------
    // eBay section (taxonomy picker + suggestion callout from Reverb side)
    // ------------------------------------------------------------------

    /**
     * Build the eBay taxonomy section parallel to the Reverb one above it.
     * eBay listings only go on leaf categories, so we surface a warning
     * pill when the user picks a non-leaf node.
     *
     * @param state The shared editor state object
     * @param onAnyChange Called whenever state.ebay_* fields change so the
     *                    outer scope can refresh cross-platform suggestions.
     * @returns {{el, refreshDisplay, refreshSuggestion}} - el is the DOM
     *          subtree; refreshDisplay re-renders the "current" pill when
     *          the eBay state was changed externally; refreshSuggestion
     *          re-renders the "suggested eBay match" callout if Reverb was
     *          picked but eBay wasn't.
     */
    function buildEbaySection(state, onAnyChange) {
        const section = LS.el("div");
        section.style.marginTop = "24px";
        section.style.paddingTop = "20px";
        section.style.borderTop = "1px solid var(--line)";

        const header = LS.el("div");
        header.style.display = "flex";
        header.style.alignItems = "center";
        header.style.gap = "10px";
        header.style.marginBottom = "12px";
        const logo = LS.el("span", null, "eBay");
        logo.style.fontFamily = "var(--font-display)";
        logo.style.fontStyle = "italic";
        logo.style.color = "var(--gold-bright)";
        logo.style.fontSize = "16px";
        header.appendChild(logo);
        const tag = LS.el("span", null, "Taxonomy Mapping");
        tag.style.fontSize = "10px";
        tag.style.textTransform = "uppercase";
        tag.style.letterSpacing = "0.08em";
        tag.style.color = "var(--ink-3)";
        header.appendChild(tag);
        section.appendChild(header);

        // Current selection pill
        const currentDisplay = LS.el("div");
        Object.assign(currentDisplay.style, {
            padding: "12px",
            background: "var(--bg-input)",
            borderRadius: "4px",
            marginBottom: "12px",
            fontSize: "13px",
            minHeight: "44px",
        });
        section.appendChild(currentDisplay);

        // Suggestion callout (filled from Reverb-side picks)
        const suggestionCallout = LS.el("div");
        section.appendChild(suggestionCallout);

        // Search input
        const searchLabel = LS.el("div", "pref-label", "Search eBay's category tree");
        searchLabel.style.fontSize = "11px";
        searchLabel.style.textTransform = "uppercase";
        searchLabel.style.letterSpacing = "0.08em";
        searchLabel.style.color = "var(--ink-3)";
        searchLabel.style.marginBottom = "6px";
        section.appendChild(searchLabel);

        const searchInput = buildInput("");
        searchInput.placeholder = "Type to search (e.g. tuner, pickup, body)";
        section.appendChild(searchInput);

        // Recent-used list above results
        const recentHost = LS.el("div");
        recentHost.style.marginTop = "8px";
        section.appendChild(recentHost);
        loadRecentUsed("ebay", recentHost, (entry) => {
            state.ebay_category_id = parseInt(entry.external_id, 10);
            state.ebay_category_name = entry.display_name;
            state.ebay_category_path = entry.display_path || entry.display_name;
            state.ebay_leaf = true;
            renderEbayCurrent();
            if (onAnyChange) onAnyChange();
        });

        // Search results container
        const resultsHost = LS.el("div");
        Object.assign(resultsHost.style, {
            marginTop: "8px",
            maxHeight: "260px",
            overflowY: "auto",
            border: "1px solid var(--line)",
            borderRadius: "4px",
        });
        section.appendChild(resultsHost);

        function renderEbayResults(results) {
            resultsHost.innerHTML = "";
            if (!results || results.length === 0) {
                const empty = LS.el("div");
                empty.style.padding = "12px";
                empty.style.color = "var(--ink-3)";
                empty.style.fontSize = "12px";
                empty.style.fontStyle = "italic";
                empty.textContent = "No matches.";
                resultsHost.appendChild(empty);
                return;
            }
            for (const r of results) {
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

                const nameRow = LS.el("div");
                nameRow.style.display = "flex";
                nameRow.style.alignItems = "center";
                nameRow.style.gap = "6px";
                const nameEl = LS.el("span", null, r.name);
                nameEl.style.fontWeight = "500";
                nameRow.appendChild(nameEl);
                if (!r.is_leaf) {
                    const nonLeaf = LS.el("span", null, "non-leaf");
                    nonLeaf.style.fontSize = "10px";
                    nonLeaf.style.padding = "1px 5px";
                    nonLeaf.style.background = "var(--rust)";
                    nonLeaf.style.color = "white";
                    nonLeaf.style.borderRadius = "3px";
                    nonLeaf.title = "eBay won't accept listings on non-leaf categories";
                    nameRow.appendChild(nonLeaf);
                }
                text.appendChild(nameRow);

                const pathEl = LS.el("div");
                pathEl.style.fontSize = "11px";
                pathEl.style.color = "var(--ink-3)";
                pathEl.style.fontFamily = "var(--font-mono)";
                pathEl.textContent = r.full_name;
                text.appendChild(pathEl);

                item.appendChild(text);

                const setBtn = LS.el("button");
                setBtn.textContent = "Select";
                Object.assign(setBtn.style, {
                    fontSize: "11px",
                    padding: "3px 8px",
                    background: "transparent",
                    border: "1px solid var(--gold)",
                    color: "var(--gold-bright)",
                    borderRadius: "3px",
                    cursor: "pointer",
                });
                setBtn.addEventListener("click", (e) => {
                    e.stopPropagation();
                    state.ebay_category_id = r.category_id;
                    state.ebay_category_name = r.name;
                    state.ebay_category_path = r.full_name;
                    state.ebay_leaf = r.is_leaf;
                    renderEbayCurrent();
                    if (onAnyChange) onAnyChange();
                });
                item.appendChild(setBtn);

                resultsHost.appendChild(item);
            }
        }

        let searchTimer = null;
        async function doSearch(q) {
            try {
                const results = await LS.api("GET",
                    `/api/platforms/ebay/taxonomy/search?q=${encodeURIComponent(q)}&limit=30`);
                renderEbayResults(results);
            } catch (err) {
                resultsHost.innerHTML = "";
                const errMsg = LS.el("div");
                errMsg.style.padding = "12px";
                errMsg.style.color = "var(--rust-bright)";
                errMsg.style.fontSize = "12px";
                errMsg.textContent = `Search failed: ${err.message}. Connect eBay in Settings to enable taxonomy search.`;
                resultsHost.appendChild(errMsg);
            }
        }
        searchInput.addEventListener("input", () => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => doSearch(searchInput.value.trim()), 250);
        });
        // Initial load
        doSearch("");

        function renderEbayCurrent() {
            currentDisplay.innerHTML = "";
            if (!state.ebay_category_id) {
                const empty = LS.el("div");
                empty.style.color = "var(--ink-3)";
                empty.style.fontStyle = "italic";
                empty.textContent = "No eBay category selected yet";
                currentDisplay.appendChild(empty);
                return;
            }
            const row = LS.el("div");
            row.style.display = "flex";
            row.style.alignItems = "center";
            row.style.gap = "8px";

            const idChip = LS.el("span");
            idChip.style.fontSize = "10px";
            idChip.style.background = "var(--gold-bright)";
            idChip.style.color = "var(--bg-deep)";
            idChip.style.padding = "2px 6px";
            idChip.style.borderRadius = "3px";
            idChip.style.fontWeight = "600";
            idChip.style.fontFamily = "var(--font-mono)";
            idChip.textContent = `ID ${state.ebay_category_id}`;
            row.appendChild(idChip);

            if (!state.ebay_leaf) {
                const warn = LS.el("span", null, "⚠ non-leaf");
                warn.style.fontSize = "10px";
                warn.style.background = "var(--rust)";
                warn.style.color = "white";
                warn.style.padding = "2px 6px";
                warn.style.borderRadius = "3px";
                warn.title = "eBay will reject listings on this category - pick a leaf instead";
                row.appendChild(warn);
            }

            const name = LS.el("span");
            name.style.fontSize = "13px";
            name.textContent = state.ebay_category_path || state.ebay_category_name;
            row.appendChild(name);

            const clear = LS.el("button");
            clear.textContent = "×";
            clear.title = "Clear selection";
            Object.assign(clear.style, {
                marginLeft: "auto",
                background: "transparent",
                border: "none",
                color: "var(--ink-3)",
                cursor: "pointer",
                fontSize: "18px",
                padding: "0 4px",
            });
            clear.addEventListener("click", () => {
                state.ebay_category_id = null;
                state.ebay_category_name = null;
                state.ebay_category_path = null;
                state.ebay_leaf = true;
                renderEbayCurrent();
                if (onAnyChange) onAnyChange();
            });
            row.appendChild(clear);

            currentDisplay.appendChild(row);
        }
        renderEbayCurrent();

        function refreshSuggestion() {
            // Suggest an eBay category if Reverb is picked but eBay isn't
            renderSuggestionCallout(
                suggestionCallout,
                "reverb", state.reverb_category_uuid, state.reverb_category_full_name,
                "ebay",
                (match) => {
                    state.ebay_category_id = parseInt(match.external_id, 10);
                    state.ebay_category_name = match.display_name;
                    state.ebay_category_path = match.display_path || match.display_name;
                    state.ebay_leaf = true; // suggestion source assumed leaf-valid
                    renderEbayCurrent();
                    if (onAnyChange) onAnyChange();
                },
                // Skip if eBay is already picked
                () => state.ebay_category_id == null,
            );
        }

        return {
            el: section,
            refreshDisplay: renderEbayCurrent,
            refreshSuggestion: refreshSuggestion,
        };
    }

    // ------------------------------------------------------------------
    // Squarespace section (store-page dropdown - not a strict taxonomy)
    // ------------------------------------------------------------------

    function buildSquarespaceSection(state) {
        const section = LS.el("div");
        section.style.marginTop = "24px";
        section.style.paddingTop = "20px";
        section.style.borderTop = "1px solid var(--line)";

        const header = LS.el("div");
        header.style.display = "flex";
        header.style.alignItems = "center";
        header.style.gap = "10px";
        header.style.marginBottom = "8px";
        const logo = LS.el("span", null, "Squarespace");
        logo.style.fontFamily = "var(--font-display)";
        logo.style.fontStyle = "italic";
        logo.style.color = "var(--gold-bright)";
        logo.style.fontSize = "16px";
        header.appendChild(logo);
        const tag = LS.el("span", null, "Store Page");
        tag.style.fontSize = "10px";
        tag.style.textTransform = "uppercase";
        tag.style.letterSpacing = "0.08em";
        tag.style.color = "var(--ink-3)";
        header.appendChild(tag);
        section.appendChild(header);

        const help = LS.el("div");
        help.style.fontSize = "12px";
        help.style.color = "var(--ink-3)";
        help.style.marginBottom = "10px";
        help.style.lineHeight = "1.5";
        help.textContent = "Squarespace doesn't have a fixed taxonomy. Products live on the store pages you've set up. Pick which page this category's listings should land on.";
        section.appendChild(help);

        const select = LS.el("select");
        select.style.cssText = "width: 100%; background: var(--bg-input); border: 1px solid var(--line); border-radius: 4px; padding: 8px 12px; color: var(--ink); font-size: 13px;";
        const loadingOpt = LS.el("option", null, "Loading pages…");
        loadingOpt.value = "";
        loadingOpt.disabled = true;
        select.appendChild(loadingOpt);
        section.appendChild(select);

        const fallback = LS.el("div");
        fallback.style.marginTop = "8px";
        fallback.style.fontSize = "11px";
        fallback.style.color = "var(--ink-3)";
        section.appendChild(fallback);

        // Fetch pages from the backend - may return empty if Squarespace
        // isn't connected or has no products yet.
        (async () => {
            let pages = [];
            try {
                pages = await LS.api("GET", "/api/platforms/squarespace/store-pages");
            } catch (err) {
                console.warn("Squarespace pages fetch failed:", err);
            }

            select.innerHTML = "";
            const noneOpt = LS.el("option", null, "(no page assigned)");
            noneOpt.value = "";
            if (!state.squarespace_store_page_id) noneOpt.selected = true;
            select.appendChild(noneOpt);

            // If the saved state has a page that isn't in the fetched list
            // (e.g. Squarespace disconnected since save), surface it as a
            // pinned option at the top with a "(saved)" marker.
            if (state.squarespace_store_page_id &&
                !pages.find(p => p.id === state.squarespace_store_page_id)) {
                const o = LS.el("option", null,
                    `${state.squarespace_store_page_name || state.squarespace_store_page_id} (saved)`);
                o.value = state.squarespace_store_page_id;
                o.selected = true;
                select.appendChild(o);
            }

            for (const p of pages) {
                const o = LS.el("option", null, p.name);
                o.value = p.id;
                if (p.id === state.squarespace_store_page_id) o.selected = true;
                select.appendChild(o);
            }

            if (pages.length === 0) {
                fallback.innerHTML = "Squarespace returned no store pages. Connect Squarespace in Settings or create your first product there to populate this dropdown.";
            }
        })();

        select.addEventListener("change", () => {
            const selectedOpt = select.options[select.selectedIndex];
            if (select.value) {
                state.squarespace_store_page_id = select.value;
                state.squarespace_store_page_name = selectedOpt.textContent;
            } else {
                state.squarespace_store_page_id = null;
                state.squarespace_store_page_name = null;
            }
        });

        return { el: section };
    }

    // ------------------------------------------------------------------
    // Recently-used helper - shared by Reverb and eBay sections
    // ------------------------------------------------------------------

    /**
     * Populate a "Recent" pill row with the most recently used categories
     * on a given platform. Clicking a pill applies it via the onSelect
     * callback. Hides itself if no entries are returned.
     */
    async function loadRecentUsed(platform, host, onSelect) {
        host.innerHTML = "";
        let entries = [];
        try {
            entries = await LS.api("GET",
                `/api/categories/usage/recent?platform=${platform}&limit=6`);
        } catch (err) {
            // Soft-fail; empty recent is just "no list shown"
            return;
        }
        if (!entries || entries.length === 0) return;

        const label = LS.el("div");
        label.style.fontSize = "10px";
        label.style.textTransform = "uppercase";
        label.style.letterSpacing = "0.08em";
        label.style.color = "var(--ink-3)";
        label.style.marginBottom = "6px";
        label.textContent = "Recently used";
        host.appendChild(label);

        const row = LS.el("div");
        row.style.display = "flex";
        row.style.flexWrap = "wrap";
        row.style.gap = "6px";
        row.style.marginBottom = "8px";

        for (const e of entries) {
            const pill = LS.el("button");
            pill.textContent = e.display_name;
            pill.title = e.display_path || e.display_name;
            Object.assign(pill.style, {
                fontSize: "12px",
                padding: "4px 10px",
                background: "var(--bg-panel)",
                border: "1px solid var(--line)",
                borderRadius: "12px",
                color: "var(--ink-2)",
                cursor: "pointer",
            });
            pill.addEventListener("mouseenter", () => {
                pill.style.background = "var(--bg-input)";
                pill.style.borderColor = "var(--gold)";
            });
            pill.addEventListener("mouseleave", () => {
                pill.style.background = "var(--bg-panel)";
                pill.style.borderColor = "var(--line)";
            });
            pill.addEventListener("click", () => onSelect(e));
            row.appendChild(pill);
        }
        host.appendChild(row);
    }

    // ------------------------------------------------------------------
    // Cross-platform suggestion callout
    // ------------------------------------------------------------------

    /**
     * Render a "suggested target-platform match" callout when ``fromId``
     * is set. Hides itself when ``shouldShow()`` returns false (typically
     * "the target platform isn't already picked").
     */
    async function renderSuggestionCallout(host, fromPlatform, fromId, fromName, toPlatform, onApply, shouldShow) {
        host.innerHTML = "";
        if (!fromId) return;
        if (shouldShow && !shouldShow()) return;

        let suggestions = [];
        try {
            const params = `from_platform=${fromPlatform}&from_id=${encodeURIComponent(fromId)}&to_platform=${toPlatform}`;
            suggestions = await LS.api("GET", `/api/categories/suggestions?${params}`);
        } catch (err) {
            return;
        }
        if (!suggestions || suggestions.length === 0) return;

        const top = suggestions[0];
        const platformLabel = toPlatform === "ebay" ? "eBay" :
                              toPlatform === "reverb" ? "Reverb" : toPlatform;

        const wrap = LS.el("div");
        Object.assign(wrap.style, {
            marginTop: "8px",
            marginBottom: "10px",
            padding: "10px 12px",
            background: "var(--bg-input)",
            border: "1px solid var(--moss)",
            borderRadius: "4px",
            fontSize: "12px",
            display: "flex",
            alignItems: "center",
            gap: "10px",
        });

        const sparkle = LS.el("span", null, top.source === "shipped" ? "✦" : top.source === "learned" ? "↺" : "✱");
        sparkle.style.color = "var(--moss-bright)";
        sparkle.style.fontSize = "14px";
        wrap.appendChild(sparkle);

        const text = LS.el("div");
        text.style.flex = "1";
        text.style.minWidth = "0";

        const headline = LS.el("div");
        headline.innerHTML = `Suggested <strong>${platformLabel}</strong> match: <strong style="color: var(--gold-bright);">${LS.escapeHTML(top.display_name)}</strong>`;
        text.appendChild(headline);

        if (top.display_path && top.display_path !== top.display_name) {
            const path = LS.el("div");
            path.style.fontSize = "11px";
            path.style.color = "var(--ink-3)";
            path.style.fontFamily = "var(--font-mono)";
            path.style.marginTop = "2px";
            path.textContent = top.display_path;
            text.appendChild(path);
        }

        const sourceLabel = LS.el("div");
        sourceLabel.style.fontSize = "10px";
        sourceLabel.style.color = "var(--ink-3)";
        sourceLabel.style.marginTop = "2px";
        sourceLabel.textContent = top.source === "shipped"
            ? "From shipped seed mappings"
            : top.source === "learned"
                ? "Learned from a previous category save"
                : `Fuzzy match (confidence ${(top.confidence * 100).toFixed(0)}%)`;
        text.appendChild(sourceLabel);

        wrap.appendChild(text);

        const apply = LS.el("button");
        apply.textContent = "Use this";
        Object.assign(apply.style, {
            fontSize: "11px",
            padding: "4px 10px",
            background: "var(--moss-bright)",
            color: "var(--bg-deep)",
            border: "none",
            borderRadius: "3px",
            cursor: "pointer",
            fontWeight: "600",
        });
        apply.addEventListener("click", () => onApply(top));
        wrap.appendChild(apply);

        host.appendChild(wrap);
    }

    function renderSearchResults(host, results, state, currentDisplay, onChange) {
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
                if (onChange) onChange();
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
                    if (onChange) onChange();
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

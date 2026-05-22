/**
 * "New Template" modal.
 *
 * Opens from the + New Template button at top of library sidebar. Collects
 * the minimum required fields, plus a category dropdown (which pre-fills
 * other fields with the category's defaults). After save, the new template
 * is loaded into the main form panel so Dad can finish filling it in.
 */

(function () {
    "use strict";

    LS.renderNewTemplateButton = function (host) {
        const btn = LS.el("button", "btn-new-template");
        btn.innerHTML = `<span style="font-size: 16px;">+</span> <span>New Template</span>`;
        Object.assign(btn.style, {
            width: "100%",
            display: "flex",
            alignItems: "center",
            gap: "8px",
            justifyContent: "center",
            padding: "8px 12px",
            background: "var(--gold-bright)",
            border: "1px solid var(--gold-bright)",
            borderRadius: "4px",
            color: "var(--bg-deep)",
            cursor: "pointer",
            fontSize: "13px",
            fontWeight: "600",
            marginBottom: "8px",
        });
        btn.addEventListener("mouseenter", () => {
            btn.style.opacity = "0.9";
        });
        btn.addEventListener("mouseleave", () => {
            btn.style.opacity = "1";
        });
        btn.addEventListener("click", () => openNewTemplateModal());
        host.appendChild(btn);
    };

    function openNewTemplateModal() {
        const categories = LS.state.categories || [];

        // State: starts mostly empty. Category triggers pre-fill of defaults.
        const state = {
            name: "",
            title: "",
            description: "",
            brand: "",
            model: "",
            year: "",
            finish: "",
            category_id: null,
            condition: "mint",
            base_price_cents: 0,
            quantity: 1,
            weight_oz: 0,
        };

        const backdrop = LS.el("div", "modal-backdrop");
        const card = LS.el("div", "modal-card");
        card.style.maxWidth = "720px";
        card.style.maxHeight = "85vh";
        card.style.overflowY = "auto";

        const h2 = LS.el("h2");
        h2.innerHTML = `New <em>Template</em>`;
        card.appendChild(h2);

        card.appendChild(LS.el("div", "modal-sub",
            "Set up the basics here. You can fine-tune the description, photos, and platform-specific settings on the next screen."));

        // --- Category dropdown FIRST (it drives defaults) ---
        card.appendChild(buildLabel("Category", "Pick a category to pre-fill condition, weight, and Reverb taxonomy."));

        const catSelect = LS.el("select");
        applyInputStyle(catSelect);
        const emptyOpt = LS.el("option", null, categories.length === 0
            ? "No categories yet — create one first"
            : "(no category)");
        emptyOpt.value = "";
        catSelect.appendChild(emptyOpt);
        for (const cat of categories) {
            const opt = LS.el("option", null, cat.name);
            opt.value = String(cat.id);
            catSelect.appendChild(opt);
        }
        card.appendChild(catSelect);

        const catHelp = LS.el("div");
        Object.assign(catHelp.style, {
            fontSize: "11px",
            color: "var(--ink-3)",
            marginTop: "4px",
            fontStyle: "italic",
            minHeight: "16px",
        });
        card.appendChild(catHelp);

        catSelect.addEventListener("change", () => {
            const id = catSelect.value === "" ? null : parseInt(catSelect.value, 10);
            state.category_id = id;
            const cat = id ? categories.find(c => c.id === id) : null;
            if (cat) {
                if (cat.default_condition) {
                    state.condition = cat.default_condition;
                    conditionSelect.value = cat.default_condition;
                }
                if (cat.default_weight_oz != null) {
                    state.weight_oz = cat.default_weight_oz;
                    weightInput.value = String(cat.default_weight_oz);
                }
                catHelp.innerHTML = cat.reverb_category_full_name
                    ? `Maps to Reverb: <span style="color: var(--gold-bright); font-family: var(--font-mono);">${LS.escapeHTML(cat.reverb_category_full_name)}</span>`
                    : "This category has no Reverb mapping yet — edit the category to add one.";
            } else {
                catHelp.textContent = "No category selected. Posting to Reverb will require setting one later.";
            }
        });

        // --- Name (required, internal identifier) ---
        card.appendChild(buildLabel("Internal Name *", "Short name only you'll see in the library sidebar (e.g. 'Kluson Vintage Nickel')."));
        const nameInput = buildInput();
        nameInput.placeholder = "e.g. Fender Affinity Strat Black";
        nameInput.addEventListener("input", () => { state.name = nameInput.value; });
        card.appendChild(nameInput);

        // --- Listing Title (required, public-facing) ---
        card.appendChild(buildLabel("Listing Title *", "Buyer-facing title used when posting (Reverb has a 100 char limit). Include brand, model, year, finish if relevant."));
        const titleInput = buildInput();
        titleInput.placeholder = "e.g. Fender Squier Affinity Stratocaster Black 2023";
        titleInput.addEventListener("input", () => { state.title = titleInput.value; });
        card.appendChild(titleInput);

        // Auto-suggest title from internal name if title still empty when user tabs away
        nameInput.addEventListener("blur", () => {
            if (!state.title.trim() && state.name.trim()) {
                state.title = state.name;
                titleInput.value = state.name;
            }
        });

        // --- Make / Model / Year / Finish ---
        const row1 = buildFieldRow(4);
        const brandField = buildField("Brand (Make)", "Reverb · eBay");
        const brandInput = buildInput();
        brandInput.placeholder = "e.g. Fender";
        brandInput.addEventListener("input", () => { state.brand = brandInput.value; });
        brandField.appendChild(brandInput);
        row1.appendChild(brandField);

        const modelField = buildField("Model", "Reverb · eBay");
        const modelInput = buildInput();
        modelInput.placeholder = "e.g. Affinity Stratocaster";
        modelInput.addEventListener("input", () => { state.model = modelInput.value; });
        modelField.appendChild(modelInput);
        row1.appendChild(modelField);

        const yearField = buildField("Year", "Reverb");
        const yearInput = buildInput();
        yearInput.placeholder = "e.g. 2023";
        yearInput.addEventListener("input", () => { state.year = yearInput.value; });
        yearField.appendChild(yearInput);
        row1.appendChild(yearField);

        const finishField = buildField("Finish/Color", "Reverb");
        const finishInput = buildInput();
        finishInput.placeholder = "e.g. Sunburst";
        finishInput.addEventListener("input", () => { state.finish = finishInput.value; });
        finishField.appendChild(finishInput);
        row1.appendChild(finishField);
        card.appendChild(row1);

        // --- Condition / Price / Quantity / Weight ---
        const row2 = buildFieldRow(4);
        const condField = buildField("Condition", "All platforms");
        const conditionSelect = LS.el("select");
        applyInputStyle(conditionSelect);
        for (const opt of [
            { value: "brand_new", label: "Brand New" },
            { value: "mint", label: "Mint" },
            { value: "excellent", label: "Excellent" },
            { value: "very_good", label: "Very Good" },
            { value: "good", label: "Good" },
            { value: "fair", label: "Fair" },
            { value: "poor", label: "Poor" },
            { value: "b_stock", label: "B-Stock" },
            { value: "non_functioning", label: "Non Functioning" },
        ]) {
            const o = LS.el("option", null, opt.label);
            o.value = opt.value;
            if (opt.value === state.condition) o.selected = true;
            conditionSelect.appendChild(o);
        }
        conditionSelect.addEventListener("change", () => { state.condition = conditionSelect.value; });
        condField.appendChild(conditionSelect);
        row2.appendChild(condField);

        const priceField = buildField("Base Price ($)", "All platforms");
        const priceInput = buildInput();
        priceInput.placeholder = "199.00";
        priceInput.addEventListener("input", () => {
            state.base_price_cents = LS.parseDollars(priceInput.value);
        });
        priceField.appendChild(priceInput);
        row2.appendChild(priceField);

        const qtyField = buildField("Quantity", "All platforms");
        const qtyInput = buildInput();
        qtyInput.value = "1";
        qtyInput.addEventListener("input", () => {
            state.quantity = parseInt(qtyInput.value, 10) || 1;
        });
        qtyField.appendChild(qtyInput);
        row2.appendChild(qtyField);

        const weightField = buildField("Weight (oz)", "Used for shipping");
        const weightInput = buildInput();
        weightInput.placeholder = "0";
        weightInput.addEventListener("input", () => {
            state.weight_oz = parseFloat(weightInput.value) || 0;
        });
        weightField.appendChild(weightInput);
        row2.appendChild(weightField);
        card.appendChild(row2);

        // --- Description (optional - they can fill in later too) ---
        card.appendChild(buildLabel("Description (optional)",
            "Product-specific description. Boilerplate ('About Southwest Acoustic Products') is auto-appended at post time from your Settings."));
        const descInput = LS.el("textarea");
        applyInputStyle(descInput);
        descInput.style.minHeight = "100px";
        descInput.style.fontFamily = "var(--font-body)";
        descInput.style.resize = "vertical";
        descInput.placeholder = "Brief description of this specific item...";
        descInput.addEventListener("input", () => { state.description = descInput.value; });
        card.appendChild(descInput);

        // --- Footer ---
        const footer = LS.el("div", "modal-footer-bar");
        footer.style.marginTop = "20px";

        const cancelBtn = LS.el("button", "btn-ghost", "Cancel");
        cancelBtn.addEventListener("click", () => backdrop.remove());
        footer.appendChild(cancelBtn);

        const saveBtn = LS.el("button", "btn-update-now", "Create Template");
        saveBtn.addEventListener("click", async () => {
            // Validate
            if (!state.name.trim()) {
                alert("Internal name is required");
                nameInput.focus();
                return;
            }
            if (!state.title.trim()) {
                alert("Listing title is required");
                titleInput.focus();
                return;
            }

            saveBtn.disabled = true;
            saveBtn.textContent = "Creating…";

            const payload = {
                name: state.name.trim(),
                title: state.title.trim(),
                description: state.description,
                brand: state.brand || null,
                model: state.model || null,
                year: state.year || null,
                finish: state.finish || null,
                condition: state.condition,
                base_price_cents: state.base_price_cents,
                quantity: state.quantity,
                weight_oz: state.weight_oz,
                category_id: state.category_id,
                folder: "Uncategorized",  // legacy folder field
            };

            try {
                const created = await LS.api("POST", "/api/templates", payload);
                backdrop.remove();
                // Refresh library and select the new template
                await LS.loadTemplates();
                if (LS.selectTemplate) {
                    await LS.selectTemplate(created.id);
                }
            } catch (err) {
                alert(`Create failed: ${err.message}`);
                saveBtn.disabled = false;
                saveBtn.textContent = "Create Template";
            }
        });
        footer.appendChild(saveBtn);

        card.appendChild(footer);

        backdrop.appendChild(card);
        backdrop.addEventListener("click", e => {
            if (e.target === backdrop) backdrop.remove();
        });
        document.body.appendChild(backdrop);

        // Initial state for help text
        catHelp.textContent = categories.length === 0
            ? "No categories yet. Create one from the sidebar first for the best experience."
            : "Pick a category above to pre-fill defaults.";

        setTimeout(() => nameInput.focus(), 50);
    }

    LS.openNewTemplateModal = openNewTemplateModal;

    // ------------------------------------------------------------------
    // Helpers (small subset; we don't reuse categories.js helpers because
    // we want the inputs styled consistently across modals)
    // ------------------------------------------------------------------

    function applyInputStyle(elt) {
        Object.assign(elt.style, {
            width: "100%",
            background: "var(--bg-input)",
            border: "1px solid var(--line)",
            borderRadius: "4px",
            padding: "8px 12px",
            color: "var(--ink)",
            fontSize: "13px",
            boxSizing: "border-box",
        });
    }

    function buildLabel(text, helpText) {
        const wrap = LS.el("div");
        wrap.style.marginTop = "16px";
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

    function buildInput() {
        const input = LS.el("input");
        input.type = "text";
        applyInputStyle(input);
        return input;
    }

    function buildFieldRow(cols) {
        const row = LS.el("div");
        Object.assign(row.style, {
            display: "grid",
            gridTemplateColumns: `repeat(${cols}, 1fr)`,
            gap: "12px",
            marginTop: "16px",
        });
        return row;
    }

    function buildField(label, platformHint) {
        const wrap = LS.el("div");

        const lbl = LS.el("div");
        lbl.style.fontSize = "11px";
        lbl.style.color = "var(--ink-2)";
        lbl.style.textTransform = "uppercase";
        lbl.style.letterSpacing = "0.08em";
        lbl.style.fontWeight = "600";
        lbl.style.marginBottom = "4px";

        const lblText = document.createElement("span");
        lblText.textContent = label;
        lbl.appendChild(lblText);

        if (platformHint) {
            const hint = LS.el("span");
            hint.style.marginLeft = "6px";
            hint.style.fontSize = "9px";
            hint.style.color = "var(--gold-bright)";
            hint.style.opacity = "0.7";
            hint.style.textTransform = "none";
            hint.style.fontWeight = "400";
            hint.style.letterSpacing = "0";
            hint.textContent = platformHint;
            lbl.appendChild(hint);
        }

        wrap.appendChild(lbl);
        return wrap;
    }
})();

/**
 * Form panel - the right side of the library view.
 *
 * Renders the selected template as an editable form: title, description,
 * platform-posting rows, save button, post button.
 */

(function () {
    "use strict";

    LS.selectTemplate = async function (templateId) {
        LS.state.selectedTemplateId = templateId;
        LS.state.formDirty = false;
        LS.renderLibrary();

        const panel = LS.$("form-panel");
        panel.innerHTML = `<div class="empty-loading">Loading template…</div>`;

        try {
            const tmpl = await LS.api("GET", `/api/templates/${templateId}`);
            LS.state.currentTemplate = tmpl;
            LS.state.enabledPlatforms = new Set(tmpl.default_platforms || []);
            renderForm();
        } catch (err) {
            panel.innerHTML = `<div class="empty-loading">Failed to load: ${err.message}</div>`;
        }
    };

    function renderForm() {
        const tmpl = LS.state.currentTemplate;
        if (!tmpl) return;

        const panel = LS.$("form-panel");
        panel.innerHTML = "";

        const inner = LS.el("div");
        inner.style.maxWidth = "920px";

        inner.appendChild(buildHeadline(tmpl));

        // Stale price hint
        const staleDays = LS.daysSince(tmpl.last_posted_at);
        if (staleDays !== null && staleDays > 60 && tmpl.last_posted_at) {
            const hint = LS.el("div", "hint");
            hint.innerHTML = `<span class="hint-icon">●</span> <strong>Heads up:</strong> Last posted ${staleDays} days ago at ${LS.dollars(tmpl.base_price_cents)}. Consider checking current market prices.`;
            inner.appendChild(hint);
        }

        inner.appendChild(buildDetailsSection(tmpl));
        inner.appendChild(buildPhotosSection(tmpl));
        inner.appendChild(buildPlatformsSection(tmpl));
        inner.appendChild(buildActionBar());

        panel.appendChild(inner);

        // Wire change tracking
        panel.querySelectorAll("input, textarea, select").forEach(elt => {
            elt.addEventListener("input", () => markDirty());
            elt.addEventListener("change", () => markDirty());
        });

        updatePostSummary();
    }

    function buildHeadline(tmpl) {
        const headline = LS.el("div", "form-headline");
        const headlineLeft = LS.el("div");
        const h1 = LS.el("h1");

        if (tmpl.brand && tmpl.name.toLowerCase().includes(tmpl.brand.toLowerCase())) {
            const parts = tmpl.name.split(new RegExp(`(${tmpl.brand})`, "i"));
            for (const part of parts) {
                if (part.toLowerCase() === tmpl.brand.toLowerCase()) {
                    h1.appendChild(LS.el("em", null, part));
                } else {
                    h1.appendChild(document.createTextNode(part));
                }
            }
        } else {
            h1.textContent = tmpl.name;
        }
        headlineLeft.appendChild(h1);

        const sub = LS.el("div", "sub",
            `${tmpl.folder} · ${tmpl.post_count} post${tmpl.post_count === 1 ? "" : "s"} · ${LS.dollars(tmpl.base_price_cents)}`);
        headlineLeft.appendChild(sub);
        headline.appendChild(headlineLeft);

        const pill = LS.el("span", "template-pill");
        if (tmpl.is_starred) pill.appendChild(LS.el("span", "pill-star", "★"));
        pill.appendChild(document.createTextNode(" From Template"));
        headline.appendChild(pill);

        return headline;
    }

    function buildSectionDivider(num, label) {
        const div = LS.el("div", "section-divider");
        div.appendChild(LS.el("div", "section-divider-num", num));
        div.appendChild(LS.el("div", "section-divider-label", label));
        div.appendChild(LS.el("div", "section-divider-line"));
        return div;
    }

    function buildField(name, label, type, value, options) {
        const field = LS.el("div", "field");
        field.appendChild(LS.el("label", null, label));

        let input;
        if (type === "textarea") {
            input = LS.el("textarea");
            input.value = value;
        } else if (type === "select") {
            input = LS.el("select");
            for (const opt of options || []) {
                const o = LS.el("option", null, opt.label);
                o.value = opt.value;
                if (opt.value === value) o.selected = true;
                input.appendChild(o);
            }
        } else if (type === "money") {
            const wrap = LS.el("div", "field-prefix");
            wrap.appendChild(LS.el("span", "prefix", "$"));
            input = LS.el("input");
            input.type = "text";
            input.value = LS.dollarsPlain(value);
            input.dataset.cents = "true";
            wrap.appendChild(input);
            field.appendChild(wrap);
            input.name = name;
            return field;
        } else {
            input = LS.el("input");
            input.type = type;
            input.value = value;
        }
        input.name = name;
        field.appendChild(input);
        return field;
    }

    function buildDetailsSection(tmpl) {
        const section = LS.el("div", "section");
        section.appendChild(buildSectionDivider("1", "Listing Details"));

        const group = LS.el("div", "field-group");
        group.appendChild(buildField("title", "Title", "text", tmpl.title));
        group.appendChild(buildField("description", "Description", "textarea", tmpl.description));

        // Brand / Model / Year / Finish row
        const row3 = LS.el("div", "field-row cols-4");
        row3.appendChild(buildField("brand", "Brand (Make)", "text", tmpl.brand || ""));
        row3.appendChild(buildField("model", "Model", "text", tmpl.model || ""));
        row3.appendChild(buildField("year", "Year", "text", tmpl.year || ""));
        row3.appendChild(buildField("finish", "Finish/Color", "text", tmpl.finish || ""));
        group.appendChild(row3);

        // Platform-source hint for the above row
        const platformHint1 = LS.el("div");
        platformHint1.style.fontSize = "11px";
        platformHint1.style.color = "var(--ink-3)";
        platformHint1.style.marginTop = "-8px";
        platformHint1.style.marginBottom = "8px";
        platformHint1.innerHTML = `<span style="color: var(--gold-bright);">●</span> Reverb fields · <span style="color: var(--gold-bright); opacity: 0.5;">●</span> eBay (once connected)`;
        group.appendChild(platformHint1);

        // Category dropdown (replaces the free-text reverb_category fields)
        const categories = LS.state.categories || [];
        const catRow = LS.el("div", "field-row cols-1");
        const catFieldOptions = [{ value: "", label: "(no category)" }];
        for (const cat of categories) {
            catFieldOptions.push({ value: String(cat.id), label: cat.name });
        }
        catRow.appendChild(buildField(
            "category_id", "Category", "select",
            tmpl.category_id != null ? String(tmpl.category_id) : "",
            catFieldOptions,
        ));
        group.appendChild(catRow);

        // Help text showing what the category maps to
        const catHelp = LS.el("div");
        catHelp.style.fontSize = "11px";
        catHelp.style.color = "var(--ink-3)";
        catHelp.style.marginTop = "-8px";
        catHelp.style.marginBottom = "8px";
        catHelp.style.fontStyle = "italic";

        const currentCat = LS.getCategoryById ? LS.getCategoryById(tmpl.category_id) : null;
        if (currentCat && currentCat.reverb_category_full_name) {
            catHelp.innerHTML = `Maps to Reverb: <span style="color: var(--gold-bright); font-family: var(--font-mono);">${LS.escapeHTML(currentCat.reverb_category_full_name)}</span>`;
        } else if (categories.length === 0) {
            catHelp.innerHTML = `No categories yet. Use "+ New Category" in the sidebar to create one with its Reverb taxonomy mapping.`;
        } else {
            catHelp.textContent = "Picking a category auto-applies the right Reverb taxonomy UUIDs at post time.";
        }
        group.appendChild(catHelp);

        // Condition / Price / Quantity / Weight row
        const row4 = LS.el("div", "field-row cols-4");
        row4.appendChild(buildField("condition", "Condition", "select", tmpl.condition, [
            { value: "brand_new", label: "Brand New" },
            { value: "mint", label: "Mint" },
            { value: "excellent", label: "Excellent" },
            { value: "very_good", label: "Very Good" },
            { value: "good", label: "Good" },
            { value: "fair", label: "Fair" },
            { value: "poor", label: "Poor" },
            { value: "b_stock", label: "B-Stock" },
            { value: "non_functioning", label: "Non Functioning" },
        ]));
        row4.appendChild(buildField("base_price_cents", "Base Price", "money", tmpl.base_price_cents));
        row4.appendChild(buildField("quantity", "Quantity", "text", String(tmpl.quantity)));
        row4.appendChild(buildField("weight_oz", "Weight (oz)", "text", String(tmpl.weight_oz)));
        group.appendChild(row4);

        // Reverb shipping row
        const shipType = tmpl.reverb_shipping_type || "";
        const shipRow = LS.el("div", "field-row cols-2");
        shipRow.appendChild(buildField("reverb_shipping_type", "Reverb Shipping", "select", shipType, [
            { value: "", label: "(not configured - falls back to profile)" },
            { value: "free", label: "Free domestic shipping" },
            { value: "flat", label: "Flat domestic rate" },
        ]));
        // The flat-rate amount input is always rendered, just hidden when not flat
        const flatField = buildField(
            "reverb_shipping_flat_cents", "Flat Rate Amount", "money",
            tmpl.reverb_shipping_flat_cents || 0,
        );
        flatField.id = "shipping-flat-field";
        flatField.style.visibility = shipType === "flat" ? "visible" : "hidden";
        shipRow.appendChild(flatField);
        group.appendChild(shipRow);

        // Wire visibility toggle on the shipping type select
        // We need to defer this until after the DOM is attached, so we do it
        // via a small inline script approach using setTimeout(0)
        setTimeout(() => {
            const shipTypeSelect = document.querySelector('[name="reverb_shipping_type"]');
            const flatFieldEl = document.getElementById("shipping-flat-field");
            if (shipTypeSelect && flatFieldEl) {
                shipTypeSelect.addEventListener("change", () => {
                    flatFieldEl.style.visibility = shipTypeSelect.value === "flat" ? "visible" : "hidden";
                });
            }
        }, 0);

        const shipHelp = LS.el("div");
        shipHelp.style.fontSize = "11px";
        shipHelp.style.color = "var(--ink-3)";
        shipHelp.style.marginTop = "-8px";
        shipHelp.style.marginBottom = "8px";
        shipHelp.style.fontStyle = "italic";
        shipHelp.textContent = "US continental shipping only. International shipping uses your Reverb default profile.";
        group.appendChild(shipHelp);

        section.appendChild(group);
        return section;
    }

    function buildPhotosSection(tmpl) {
        const section = LS.el("div", "section");
        section.appendChild(buildSectionDivider("2", "Photos"));

        const photosRow = LS.el("div", "photos-row");

        if (tmpl.photos && tmpl.photos.length > 0) {
            // Sort by sort_order so primary (0) comes first
            const sorted = [...tmpl.photos].sort((a, b) => a.sort_order - b.sort_order);
            sorted.forEach((photo, idx) => {
                const tile = LS.el("div", "photo-tile" + (idx === 0 ? " primary" : ""));
                tile.title = photo.source_path;

                const imgEl = LS.el("img");
                imgEl.src = `/api/nas/thumbnail?path=${encodeURIComponent(photo.source_path)}`;
                imgEl.style.width = "100%";
                imgEl.style.height = "100%";
                imgEl.style.objectFit = "cover";
                imgEl.loading = "lazy";
                imgEl.onerror = () => {
                    imgEl.style.display = "none";
                    tile.insertBefore(LS.el("div", "photo-tile-placeholder", "(missing)"), tile.firstChild);
                };
                tile.appendChild(imgEl);

                // Remove button
                const removeBtn = LS.el("button");
                removeBtn.textContent = "×";
                removeBtn.title = "Remove photo";
                Object.assign(removeBtn.style, {
                    position: "absolute", top: "4px", right: "4px",
                    width: "20px", height: "20px", borderRadius: "50%",
                    background: "rgba(0,0,0,0.65)",
                    border: "1px solid rgba(255,255,255,0.2)",
                    color: "white", cursor: "pointer", fontSize: "14px",
                    lineHeight: "1", padding: "0", zIndex: "2",
                });
                removeBtn.addEventListener("click", async (e) => {
                    e.stopPropagation();
                    if (!confirm("Remove this photo from the listing?")) return;
                    try {
                        await LS.api("DELETE",
                            `/api/templates/${tmpl.id}/photos/${photo.id}`);
                        await LS.selectTemplate(tmpl.id);
                    } catch (err) {
                        alert(`Failed to remove photo: ${err.message}`);
                    }
                });
                tile.appendChild(removeBtn);

                photosRow.appendChild(tile);
            });
        }

        const addBtn = LS.el("div", "photo-add");
        addBtn.appendChild(LS.el("span", null, "+"));
        addBtn.appendChild(LS.el("span", null, "Add from NAS"));
        addBtn.addEventListener("click", () => {
            if (LS.openPicker) LS.openPicker();
        });
        photosRow.appendChild(addBtn);

        section.appendChild(photosRow);

        const source = LS.el("div", "photo-source");
        if (tmpl.photos && tmpl.photos.length > 0) {
            const primary = [...tmpl.photos].sort((a, b) => a.sort_order - b.sort_order)[0];
            source.innerHTML = `${tmpl.photos.length} photo${tmpl.photos.length === 1 ? "" : "s"} · Primary: <span class="path">${LS.escapeHTML(primary.source_path)}</span>`;
        } else {
            source.innerHTML = `<span class="path">No photos attached yet. Click + to browse the NAS.</span>`;
        }
        section.appendChild(source);

        return section;
    }

    function buildPlatformsSection(tmpl) {
        const section = LS.el("div", "section");
        section.appendChild(buildSectionDivider("3", "Cross-post to"));

        const platforms = LS.el("div", "platforms");
        for (const p of LS.constants.ALL_PLATFORMS) {
            platforms.appendChild(buildPlatformRow(p, tmpl));
        }
        section.appendChild(platforms);
        return section;
    }

    function buildPlatformRow(platform, tmpl) {
        const row = LS.el("div", "platform-row");
        const enabled = LS.state.enabledPlatforms.has(platform);
        if (enabled) row.classList.add("enabled");

        const check = LS.el("div", "check" + (enabled ? " checked" : ""));
        check.addEventListener("click", () => {
            if (LS.state.enabledPlatforms.has(platform)) {
                LS.state.enabledPlatforms.delete(platform);
            } else {
                LS.state.enabledPlatforms.add(platform);
            }
            markDirty();
            renderForm();
        });
        row.appendChild(check);

        const info = LS.el("div", "platform-info");
        info.appendChild(LS.el("div", `platform-logo ${platform}`, LS.platformLogoText(platform)));

        const meta = LS.el("div", "platform-meta");
        meta.appendChild(LS.el("div", "platform-name", LS.platformDisplay(platform)));

        let statusText, statusClass = "platform-status";
        if (platform === "facebook") {
            statusText = "Copy-paste package · manual post required";
            statusClass += " warn";
        } else {
            const conn = LS.state.connectionStatus[platform];
            if (conn && conn.is_connected) {
                statusText = "Auto-post via API";
            } else {
                statusText = "Not connected · configure in Settings";
                statusClass += " warn";
            }
        }
        meta.appendChild(LS.el("div", statusClass, statusText));
        info.appendChild(meta);
        row.appendChild(info);

        const override = tmpl.platform_overrides[platform] || {};
        const platformPriceCents = override.price_cents || tmpl.base_price_cents;

        const priceWrap = LS.el("div", "platform-price-wrap");
        priceWrap.appendChild(LS.el("span", "prefix", "$"));
        const priceInput = LS.el("input", "platform-price-input");
        priceInput.type = "text";
        priceInput.value = LS.dollarsPlain(platformPriceCents);
        priceInput.dataset.platform = platform;
        priceInput.disabled = !enabled;
        priceInput.addEventListener("input", () => {
            updatePostSummary();
            markDirty();
        });
        priceWrap.appendChild(priceInput);
        row.appendChild(priceWrap);

        const feeDiv = LS.el("div", "platform-fee");
        feeDiv.dataset.platform = platform;
        updateFeeDisplay(feeDiv, platform, platformPriceCents);
        row.appendChild(feeDiv);

        return row;
    }

    function updateFeeDisplay(feeDiv, platform, priceCents) {
        const fee = LS.state.feeStructures[platform];
        if (!fee || priceCents <= 0) {
            feeDiv.textContent = "—";
            return;
        }
        const percentageCut = Math.floor(priceCents * fee.percentage_bps / 10000);
        const totalFee = percentageCut + fee.flat_cents + (fee.listing_cents || 0);
        const net = priceCents - totalFee;
        feeDiv.innerHTML = `fee ~${LS.dollars(totalFee)} · net <strong>${LS.dollars(net)}</strong>`;
    }

    function buildActionBar() {
        const bar = LS.el("div", "action-bar");

        const left = LS.el("div", "left");
        const saveBtn = LS.el("button", "btn-ghost");
        saveBtn.id = "btn-save";
        saveBtn.textContent = "Save changes to template";
        saveBtn.addEventListener("click", saveTemplate);
        left.appendChild(saveBtn);

        // Test action: create a draft on Reverb (doesn't publish - safe to test)
        const reverbDraftBtn = LS.el("button", "btn-ghost");
        reverbDraftBtn.id = "btn-reverb-draft";
        reverbDraftBtn.textContent = "Post Reverb Draft";
        reverbDraftBtn.title = "Create a draft listing on Reverb (not published - you can review and publish or delete it on Reverb's site)";
        reverbDraftBtn.style.marginLeft = "12px";
        reverbDraftBtn.addEventListener("click", postReverbDraft);
        left.appendChild(reverbDraftBtn);

        bar.appendChild(left);

        const right = LS.el("div", "right");
        const summary = LS.el("span", "summary-text");
        summary.id = "post-summary";
        summary.textContent = "—";
        right.appendChild(summary);

        const postBtn = LS.el("button", "btn-post");
        postBtn.id = "btn-post";
        postBtn.textContent = "Post Listing";
        postBtn.addEventListener("click", LS.postListing);
        right.appendChild(postBtn);
        bar.appendChild(right);

        return bar;
    }

    function markDirty() {
        if (LS.state.formDirty) return;
        LS.state.formDirty = true;
        const btn = LS.$("btn-save");
        if (btn) {
            btn.textContent = "Save changes *";
            btn.classList.remove("saved");
        }
    }

    function markClean() {
        LS.state.formDirty = false;
        const btn = LS.$("btn-save");
        if (btn) {
            btn.textContent = "Saved ✓";
            btn.classList.add("saved");
            setTimeout(() => {
                if (!LS.state.formDirty && btn) {
                    btn.textContent = "Save changes to template";
                    btn.classList.remove("saved");
                }
            }, 2000);
        }
    }

    function updatePostSummary() {
        const summary = LS.$("post-summary");
        if (!summary) return;
        const enabledCount = LS.state.enabledPlatforms.size;
        let totalNet = 0;
        for (const p of LS.state.enabledPlatforms) {
            const input = document.querySelector(`.platform-price-input[data-platform="${p}"]`);
            const feeDiv = document.querySelector(`.platform-fee[data-platform="${p}"]`);
            if (!input || !feeDiv) continue;
            const priceCents = LS.parseDollars(input.value);
            updateFeeDisplay(feeDiv, p, priceCents);
            const fee = LS.state.feeStructures[p];
            if (!fee || priceCents <= 0) continue;
            const percentageCut = Math.floor(priceCents * fee.percentage_bps / 10000);
            const totalFee = percentageCut + fee.flat_cents + (fee.listing_cents || 0);
            totalNet += priceCents - totalFee;
        }
        summary.innerHTML = `Posting to <strong>${enabledCount}</strong> platform${enabledCount === 1 ? "" : "s"} · est. net <strong>${LS.dollars(totalNet)}</strong>`;

        const btn = LS.$("btn-post");
        if (btn) btn.disabled = enabledCount === 0;
    }

    function collectFormData() {
        const form = {};
        document.querySelectorAll("[name]").forEach(elt => {
            const name = elt.name;
            let value = elt.value;
            if (elt.dataset.cents === "true") {
                value = LS.parseDollars(value);
            } else if (name === "quantity") {
                value = parseInt(value, 10) || 1;
            } else if (name === "weight_oz") {
                value = parseFloat(value) || 0;
            } else if (name === "category_id") {
                // empty string in the select means "no category"
                value = value === "" ? null : parseInt(value, 10);
            } else if (name === "reverb_shipping_type") {
                // empty select value means "no shipping configured" - send null
                value = value === "" ? null : value;
            }
            form[name] = value;
        });

        const overrides = {};
        document.querySelectorAll(".platform-price-input").forEach(input => {
            const p = input.dataset.platform;
            const cents = LS.parseDollars(input.value);
            if (cents !== LS.state.currentTemplate.base_price_cents) {
                overrides[p] = { price_cents: cents };
            }
        });
        form.platform_overrides = overrides;
        form.default_platforms = Array.from(LS.state.enabledPlatforms);

        return form;
    }

    async function saveTemplate() {
        if (!LS.state.currentTemplate) return;
        const btn = LS.$("btn-save");
        btn.textContent = "Saving…";
        btn.classList.add("saving");

        try {
            const payload = collectFormData();
            const updated = await LS.api("PATCH", `/api/templates/${LS.state.currentTemplate.id}`, payload);
            LS.state.currentTemplate = updated;
            markClean();
            await LS.loadTemplates();
        } catch (err) {
            alert("Save failed: " + err.message);
            btn.textContent = "Save changes *";
            btn.classList.remove("saving");
        }
    }

    async function postReverbDraft() {
        if (!LS.state.currentTemplate) return;

        // Save any unsaved edits first so what gets posted matches the form
        if (LS.state.formDirty) {
            await saveTemplate();
        }

        const btn = LS.$("btn-reverb-draft");
        btn.disabled = true;
        btn.textContent = "Creating draft…";

        try {
            // Backend decides whether to auto-upload photos based on whether
            // a photo host (ImgBB) is configured in Settings. If no host is
            // set up, the draft is created without photos and the result
            // modal falls back to the manual "drag photos into Reverb" flow.
            const result = await LS.api(
                "POST",
                `/api/templates/${LS.state.currentTemplate.id}/post-to-reverb`,
                {},
            );

            showReverbDraftResult(result);
        } catch (err) {
            alert(`Reverb draft creation failed:\n\n${err.message}`);
        } finally {
            btn.disabled = false;
            btn.textContent = "Post Reverb Draft";
        }
    }

    function showReverbDraftResult(result) {
        const backdrop = LS.el("div", "modal-backdrop");
        const card = LS.el("div", "modal-card");
        card.style.maxWidth = "560px";

        const h2 = LS.el("h2");
        h2.innerHTML = `Reverb draft <em>created</em>`;
        card.appendChild(h2);

        // Reverb sometimes returns state as {"slug": "draft", "description": "Draft"}
        // and sometimes as a plain string. Extract the readable form.
        let stateLabel = "draft";
        if (typeof result.state === "string") {
            stateLabel = result.state;
        } else if (result.state && typeof result.state === "object") {
            stateLabel = result.state.slug || result.state.description || "draft";
        }

        const info = LS.el("div", "modal-sub");
        info.innerHTML = `Listing ID: <span style="font-family: var(--font-mono); color: var(--gold-bright);">${result.listing_id}</span> · State: <strong>${stateLabel}</strong>`;
        card.appendChild(info);

        // Photo-handling next step depends on whether a host was configured.
        // Host configured → photos were auto-uploaded (with possible partials).
        // No host        → draft has no photos; fall back to manual drag-drop.
        const photoResults = result.photo_results || {};
        const hostConfigured = !!photoResults.host_configured;
        const uploaded = photoResults.uploaded || 0;
        const failed = photoResults.failed || 0;
        const errors = photoResults.errors || [];

        const nextStep = LS.el("div");
        const stepBorderColor = hostConfigured && failed === 0 && uploaded > 0
            ? "var(--moss-bright)" : "var(--gold)";
        Object.assign(nextStep.style, {
            marginTop: "16px",
            padding: "14px 16px",
            background: "var(--bg-input)",
            border: `1px solid ${stepBorderColor}`,
            borderRadius: "4px",
            fontSize: "13px",
            lineHeight: "1.5",
        });

        if (hostConfigured && uploaded > 0 && failed === 0) {
            // Happy path: everything uploaded automatically via the host
            renderPhotoHostHappyPath(nextStep, result, uploaded, photoResults.host_display_name);
        } else if (hostConfigured) {
            // Partial or total failure on the host side. Some may have uploaded;
            // surface what worked and what didn't, plus the manual fallback.
            renderPhotoHostPartial(nextStep, result, photoResults);
        } else {
            // No host configured: the legacy manual drag-and-drop workflow.
            renderManualDragDrop(nextStep, result);
        }
        card.appendChild(nextStep);

        const note = LS.el("div");
        note.style.marginTop = "16px";
        note.style.fontSize = "12px";
        note.style.color = "var(--ink-3)";
        note.style.lineHeight = "1.5";
        note.textContent = "Draft listings don't go live until you publish them on Reverb. To delete this test draft, log into Reverb's Seller Hub.";
        card.appendChild(note);

        const footer = LS.el("div", "modal-footer-bar");
        const closeBtn = LS.el("button", "btn-update-now", "Done");
        closeBtn.addEventListener("click", () => backdrop.remove());
        footer.appendChild(closeBtn);
        card.appendChild(footer);

        backdrop.appendChild(card);
        backdrop.addEventListener("click", e => {
            if (e.target === backdrop) backdrop.remove();
        });
        document.body.appendChild(backdrop);
    }

    function renderPhotoHostHappyPath(container, result, uploaded, hostName) {
        container.innerHTML = `
            <div style="font-weight: 600; color: var(--moss-bright); margin-bottom: 6px;">
                ✓ ${uploaded} photo${uploaded === 1 ? "" : "s"} uploaded via ${hostName || "image host"}
            </div>
            <div style="color: var(--ink-2); margin-bottom: 10px;">
                Reverb is fetching them now. Open the draft to confirm and publish.
            </div>
        `;
        if (result.url) {
            container.appendChild(buildOpenDraftButton(result.url, "→ Open Draft on Reverb"));
        }
    }

    function renderPhotoHostPartial(container, result, photoResults) {
        const uploaded = photoResults.uploaded || 0;
        const failed = photoResults.failed || 0;
        const errors = photoResults.errors || [];
        const hostName = photoResults.host_display_name || "image host";

        const headline = uploaded > 0
            ? `Photo upload partial: ${uploaded} succeeded, ${failed} failed`
            : `Photo upload failed (${failed} ${failed === 1 ? "photo" : "photos"})`;

        const headlineEl = LS.el("div");
        headlineEl.style.fontWeight = "600";
        headlineEl.style.color = "var(--gold-bright)";
        headlineEl.style.marginBottom = "6px";
        headlineEl.textContent = headline;
        container.appendChild(headlineEl);

        const explainer = LS.el("div");
        explainer.style.color = "var(--ink-2)";
        explainer.style.marginBottom = "10px";
        explainer.innerHTML = uploaded > 0
            ? `The draft has ${uploaded} photo${uploaded === 1 ? "" : "s"} attached. Open it to add the rest by hand.`
            : `Couldn't upload any photos to ${hostName}. Open the draft and add photos manually.`;
        container.appendChild(explainer);

        if (errors.length > 0) {
            const details = LS.el("details");
            details.style.marginBottom = "10px";
            const summary = LS.el("summary");
            summary.style.cursor = "pointer";
            summary.style.fontSize = "12px";
            summary.style.color = "var(--ink-3)";
            summary.textContent = `Show ${errors.length} error${errors.length === 1 ? "" : "s"}`;
            details.appendChild(summary);

            const list = LS.el("ul");
            list.style.marginTop = "8px";
            list.style.paddingLeft = "20px";
            list.style.fontSize = "11px";
            list.style.color = "var(--rust-bright)";
            list.style.fontFamily = "var(--font-mono)";
            for (const errLine of errors) {
                const li = LS.el("li");
                li.style.marginBottom = "4px";
                li.textContent = errLine;
                list.appendChild(li);
            }
            details.appendChild(list);
            container.appendChild(details);
        }

        if (result.url) {
            container.appendChild(buildOpenDraftPlusFolderButton(result.url));
        }
    }

    function renderManualDragDrop(container, result) {
        container.innerHTML = `
            <div style="font-weight: 600; color: var(--gold-bright); margin-bottom: 6px;">Next: add photos on Reverb</div>
            <div style="color: var(--ink-2); margin-bottom: 10px;">
                The draft is ready with all the listing details. To auto-upload photos,
                connect an image host in <strong>Settings → Reverb photo hosting</strong>.
                Otherwise open the draft below and drag photos in from the Explorer window.
            </div>
        `;
        if (result.url) {
            container.appendChild(buildOpenDraftPlusFolderButton(result.url));
        }
    }

    function buildOpenDraftButton(url, label) {
        const btn = LS.el("button");
        btn.textContent = label;
        Object.assign(btn.style, {
            display: "inline-block",
            padding: "8px 14px",
            background: "var(--gold-bright)",
            color: "var(--bg-deep)",
            border: "none",
            borderRadius: "4px",
            fontWeight: "600",
            fontSize: "13px",
            cursor: "pointer",
        });
        btn.addEventListener("click", () => window.open(url, "_blank"));
        return btn;
    }

    function buildOpenDraftPlusFolderButton(url) {
        const wrap = LS.el("div");
        const btn = LS.el("button");
        btn.textContent = "→ Open Draft + Photos Folder";
        btn.title = "Opens the draft on Reverb AND the photos folder in Explorer for drag-and-drop";
        Object.assign(btn.style, {
            display: "inline-block",
            padding: "8px 14px",
            background: "var(--gold-bright)",
            color: "var(--bg-deep)",
            border: "none",
            borderRadius: "4px",
            fontWeight: "600",
            fontSize: "13px",
            cursor: "pointer",
        });
        btn.addEventListener("click", async () => {
            window.open(url, "_blank");
            try {
                await LS.api(
                    "POST",
                    `/api/templates/${LS.state.currentTemplate.id}/open-photo-folder`,
                );
            } catch (err) {
                console.warn("Couldn't open photo folder:", err);
                const notice = LS.el("div");
                notice.style.marginTop = "8px";
                notice.style.fontSize = "11px";
                notice.style.color = "var(--rust-bright)";
                notice.textContent = `Couldn't open photo folder: ${err.message}`;
                wrap.appendChild(notice);
            }
        });
        wrap.appendChild(btn);

        // Backup plain link in case the button can't open the folder
        const fallback = LS.el("div");
        fallback.style.marginTop = "8px";
        fallback.style.fontSize = "11px";
        fallback.innerHTML = `<a href="${url}" target="_blank" style="color: var(--ink-3);">or open just the draft →</a>`;
        wrap.appendChild(fallback);

        return wrap;
    }

    LS.postListing = async function () {
        if (!LS.state.currentTemplate || LS.state.enabledPlatforms.size === 0) return;

        const btn = LS.$("btn-post");
        btn.disabled = true;
        btn.textContent = "Posting…";

        const overrides = {};
        document.querySelectorAll(".platform-price-input").forEach(input => {
            if (input.disabled) return;
            const p = input.dataset.platform;
            const cents = LS.parseDollars(input.value);
            overrides[p] = { price_cents: cents };
        });

        try {
            const response = await LS.api("POST", "/api/post", {
                template_id: LS.state.currentTemplate.id,
                platforms: Array.from(LS.state.enabledPlatforms),
                overrides: overrides,
            });
            if (LS.showPostResults) LS.showPostResults(response);
            await LS.loadTemplates();
        } catch (err) {
            alert("Posting failed: " + err.message);
        } finally {
            btn.disabled = false;
            btn.textContent = "Post Listing";
        }
    };
})();

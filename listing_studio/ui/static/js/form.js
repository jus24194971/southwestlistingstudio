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

        const row3 = LS.el("div", "field-row cols-3");
        row3.appendChild(buildField("brand", "Brand", "text", tmpl.brand || ""));
        row3.appendChild(buildField("year", "Year", "text", ""));
        row3.appendChild(buildField("condition", "Condition", "select", tmpl.condition, [
            { value: "new", label: "New" },
            { value: "new_old_stock", label: "New (Old Stock)" },
            { value: "used_excellent", label: "Used – Excellent" },
            { value: "used_good", label: "Used – Good" },
            { value: "used_fair", label: "Used – Fair" },
            { value: "for_parts", label: "For Parts" },
        ]));
        group.appendChild(row3);

        const row4 = LS.el("div", "field-row cols-4");
        row4.appendChild(buildField("base_price_cents", "Base Price", "money", tmpl.base_price_cents));
        row4.appendChild(buildField("quantity", "Quantity", "text", String(tmpl.quantity)));
        row4.appendChild(buildField("weight_oz", "Weight (oz)", "text", String(tmpl.weight_oz)));
        row4.appendChild(buildField("shipping_method", "Shipping", "select", tmpl.shipping_method, [
            { value: "usps_first_class", label: "USPS First Class" },
            { value: "usps_priority", label: "USPS Priority" },
            { value: "ups_ground", label: "UPS Ground" },
        ]));
        group.appendChild(row4);

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

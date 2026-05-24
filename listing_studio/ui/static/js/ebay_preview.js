/**
 * In-app eBay listing preview + publish confirmation.
 *
 * Seller Hub doesn't render unpublished Inventory API offers, so we build
 * our own. The preview pulls the live inventory_item + offer from eBay via
 * /api/templates/{id}/ebay-preview and renders the data the way eBay would
 * - title, photo grid, price + condition, item specifics, description.
 *
 * From the preview, the user can publish (POST /publish-to-ebay), which
 * converts the unpublished offer into a live listing and returns the
 * listing ID + standard eBay listing URL.
 */
(function () {
    "use strict";

    const RECENT_PUBLISH_KEY = "ls.ebay.recentPublishes";

    function fmtPrice(price) {
        if (!price) return "—";
        const cur = price.currency || "USD";
        const val = price.value !== undefined ? price.value : price;
        return `$${val} ${cur}`;
    }

    function chip(label, value, opts) {
        const c = LS.el("div");
        Object.assign(c.style, {
            display: "inline-flex",
            alignItems: "center",
            gap: "6px",
            padding: "4px 10px",
            background: (opts && opts.bg) || "var(--bg-input)",
            border: "1px solid " + ((opts && opts.border) || "var(--ink-3)"),
            borderRadius: "999px",
            fontSize: "12px",
            color: (opts && opts.color) || "var(--ink-2)",
            marginRight: "6px",
            marginBottom: "6px",
            fontFamily: "var(--font-mono)",
        });
        c.innerHTML = `<span style="color: var(--ink-3); font-family: var(--font-sans);">${label}:</span> ${LS.escapeHTML(String(value || "—"))}`;
        return c;
    }

    /**
     * Show the eBay preview modal for a template. Fetches fresh data from
     * eBay every time it's opened.
     */
    LS.showEbayPreviewModal = async function (templateId) {
        const backdrop = LS.el("div", "modal-backdrop");
        const card = LS.el("div", "modal-card");
        card.style.maxWidth = "780px";
        card.style.maxHeight = "85vh";
        card.style.overflowY = "auto";

        const closeX = LS.el("button", "modal-close");
        closeX.textContent = "✕";
        closeX.addEventListener("click", () => backdrop.remove());
        card.appendChild(closeX);

        const h2 = LS.el("h2");
        h2.innerHTML = `eBay <em>preview</em>`;
        card.appendChild(h2);

        const status = LS.el("div", "modal-sub");
        status.textContent = "Loading from eBay…";
        card.appendChild(status);

        const body = LS.el("div");
        body.style.marginTop = "16px";
        card.appendChild(body);

        backdrop.appendChild(card);
        document.body.appendChild(backdrop);

        let preview;
        try {
            const r = await fetch(`/api/templates/${templateId}/ebay-preview`);
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            preview = await r.json();
        } catch (err) {
            status.style.color = "var(--rust-bright)";
            status.textContent = `Couldn't load eBay preview: ${err.message}`;
            return;
        }

        renderPreview(body, status, preview, templateId);
    };

    function renderPreview(body, status, preview, templateId) {
        const ebay = preview.ebay || {};
        const inv = ebay.inventory || {};
        const product = inv.product || {};
        const offer = ebay.offer || {};
        const errors = ebay.errors || [];
        const local = preview.local || {};
        const isLive = offer.status === "PUBLISHED";

        // Header summary
        status.innerHTML = `SKU: <span style="font-family: var(--font-mono); color: var(--gold-bright);">${LS.escapeHTML(preview.sku)}</span>`
                        + (offer.offerId ? ` · Offer ID: <span style="font-family: var(--font-mono); color: var(--gold-bright);">${LS.escapeHTML(offer.offerId)}</span>` : "")
                        + ` · Status: <span style="color: ${isLive ? 'var(--moss-bright)' : 'var(--gold-bright)'};">${LS.escapeHTML(offer.status || "(no offer)")}</span>`;

        body.innerHTML = "";

        if (errors.length > 0 && !inv.sku) {
            const errBox = LS.el("div");
            Object.assign(errBox.style, {
                padding: "12px 14px",
                background: "var(--bg-input)",
                border: "1px solid var(--gold)",
                borderRadius: "4px",
                color: "var(--gold-bright)",
                fontSize: "13px",
                marginBottom: "16px",
            });
            errBox.innerHTML = `<strong>eBay didn't return inventory data:</strong><br>${errors.map(e => "• " + LS.escapeHTML(e)).join("<br>")}<br><br>The offer may still exist (status above). If both inventory and offer are missing, click <em>Post eBay Draft</em> first.`;
            body.appendChild(errBox);
        }

        // ---- Title ----
        const title = product.title || local.title || local.name || "(no title)";
        const titleEl = LS.el("h3");
        Object.assign(titleEl.style, {
            margin: "0 0 12px 0",
            fontSize: "20px",
            lineHeight: "1.3",
            color: "var(--ink-1)",
        });
        titleEl.textContent = title;
        body.appendChild(titleEl);

        // ---- Photo grid ----
        const photos = product.imageUrls || [];
        if (photos.length > 0) {
            const grid = LS.el("div");
            Object.assign(grid.style, {
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
                gap: "8px",
                marginBottom: "16px",
            });
            for (const url of photos) {
                const img = LS.el("img");
                img.src = url;
                Object.assign(img.style, {
                    width: "100%",
                    aspectRatio: "1",
                    objectFit: "cover",
                    borderRadius: "4px",
                    border: "1px solid var(--ink-3)",
                });
                img.alt = "eBay listing photo";
                grid.appendChild(img);
            }
            body.appendChild(grid);
        } else {
            const noPhoto = LS.el("div");
            Object.assign(noPhoto.style, {
                padding: "20px",
                textAlign: "center",
                background: "var(--bg-input)",
                border: "1px dashed var(--ink-3)",
                borderRadius: "4px",
                color: "var(--ink-3)",
                fontSize: "13px",
                marginBottom: "16px",
            });
            noPhoto.textContent = "No photos in inventory_item.";
            body.appendChild(noPhoto);
        }

        // ---- Price + condition + category row ----
        const meta = LS.el("div");
        meta.style.marginBottom = "16px";
        const price = offer.pricingSummary ? offer.pricingSummary.price : null;
        meta.appendChild(chip("Price", fmtPrice(price), {color: "var(--gold-bright)"}));
        meta.appendChild(chip("Condition", inv.condition || "—"));
        meta.appendChild(chip("Qty",
            (inv.availability && inv.availability.shipToLocationAvailability)
                ? (inv.availability.shipToLocationAvailability.quantity || "—")
                : (offer.availableQuantity || "—")
        ));
        meta.appendChild(chip("Category", offer.categoryId || "—"));
        meta.appendChild(chip("Format", offer.format || "FIXED_PRICE"));
        meta.appendChild(chip("Listing duration", offer.listingDuration || "GTC"));
        body.appendChild(meta);

        // ---- Item specifics ----
        const aspects = product.aspects || {};
        const aspectKeys = Object.keys(aspects);
        if (aspectKeys.length > 0) {
            const aspHeader = LS.el("div");
            Object.assign(aspHeader.style, {
                fontWeight: "600",
                fontSize: "13px",
                color: "var(--ink-2)",
                marginBottom: "6px",
            });
            aspHeader.textContent = "Item specifics";
            body.appendChild(aspHeader);

            const aspTable = LS.el("div");
            Object.assign(aspTable.style, {
                display: "grid",
                gridTemplateColumns: "auto 1fr",
                gap: "4px 14px",
                marginBottom: "16px",
                fontSize: "12px",
                fontFamily: "var(--font-mono)",
                padding: "10px 14px",
                background: "var(--bg-input)",
                borderRadius: "4px",
            });
            for (const k of aspectKeys) {
                const kEl = LS.el("div");
                kEl.style.color = "var(--ink-3)";
                kEl.textContent = k;
                aspTable.appendChild(kEl);

                const vEl = LS.el("div");
                vEl.style.color = "var(--ink-1)";
                vEl.textContent = Array.isArray(aspects[k]) ? aspects[k].join(", ") : String(aspects[k]);
                aspTable.appendChild(vEl);
            }
            body.appendChild(aspTable);
        }

        // ---- Description ----
        const descHtml = offer.listingDescription || product.description || "";
        if (descHtml) {
            const descHeader = LS.el("div");
            Object.assign(descHeader.style, {
                fontWeight: "600",
                fontSize: "13px",
                color: "var(--ink-2)",
                marginBottom: "6px",
            });
            descHeader.textContent = "Description";
            body.appendChild(descHeader);

            const descBox = LS.el("div");
            Object.assign(descBox.style, {
                padding: "14px 16px",
                background: "var(--bg-input)",
                border: "1px solid var(--ink-3)",
                borderRadius: "4px",
                fontSize: "13px",
                lineHeight: "1.5",
                color: "var(--ink-1)",
                marginBottom: "16px",
                maxHeight: "240px",
                overflowY: "auto",
            });
            // The description from eBay is already escaped HTML wrapped in
            // <p>/<br> tags from our own builder, so injecting as innerHTML
            // is safe here - we control the producer side.
            descBox.innerHTML = descHtml;
            body.appendChild(descBox);
        }

        // ---- Policies + location ----
        if (offer.listingPolicies || offer.merchantLocationKey) {
            const lp = offer.listingPolicies || {};
            const polRow = LS.el("div");
            polRow.style.marginBottom = "16px";
            if (lp.fulfillmentPolicyId) polRow.appendChild(chip("Fulfillment", lp.fulfillmentPolicyId));
            if (lp.paymentPolicyId) polRow.appendChild(chip("Payment", lp.paymentPolicyId));
            if (lp.returnPolicyId) polRow.appendChild(chip("Returns", lp.returnPolicyId));
            if (offer.merchantLocationKey) polRow.appendChild(chip("Location", offer.merchantLocationKey));
            body.appendChild(polRow);
        }

        // ---- Action footer ----
        const footer = LS.el("div");
        Object.assign(footer.style, {
            position: "sticky",
            bottom: "0",
            display: "flex",
            justifyContent: "space-between",
            gap: "10px",
            paddingTop: "14px",
            marginTop: "8px",
            borderTop: "1px solid var(--ink-3)",
            background: "var(--bg-deep)",
        });

        const closeBtn = LS.el("button", "btn-update-now", "Close");
        closeBtn.style.background = "transparent";
        closeBtn.style.color = "var(--ink-2)";
        closeBtn.style.border = "1px solid var(--ink-3)";
        closeBtn.addEventListener("click", () => {
            body.parentElement.parentElement.remove();
        });
        footer.appendChild(closeBtn);

        const right = LS.el("div");
        right.style.display = "flex";
        right.style.gap = "10px";

        if (isLive) {
            const openLive = LS.el("button", "btn-update-now");
            openLive.textContent = "→ View live listing";
            openLive.style.background = "var(--moss-bright)";
            openLive.style.color = "var(--bg-deep)";
            openLive.addEventListener("click", () => {
                const lid = (offer.listing && offer.listing.listingId) || (offer.listingId);
                window.open(lid ? `https://www.ebay.com/itm/${lid}` : "https://www.ebay.com/sh/lst/active", "_blank");
            });
            right.appendChild(openLive);
        } else if (offer.offerId) {
            const publishBtn = LS.el("button", "btn-update-now");
            publishBtn.textContent = "📤 Publish to eBay";
            publishBtn.style.background = "var(--gold-bright)";
            publishBtn.style.color = "var(--bg-deep)";
            publishBtn.addEventListener("click", () => {
                LS.confirmPublishToEbay(templateId, offer.offerId);
            });
            right.appendChild(publishBtn);
        }

        footer.appendChild(right);
        body.appendChild(footer);
    }

    /**
     * Publish-to-eBay confirmation modal. Two-step so Dad can't fat-finger
     * a publish: shows a clear "this will go LIVE on eBay" warning with
     * the listing details summary, requires explicit confirm.
     */
    LS.confirmPublishToEbay = async function (templateId, knownOfferId) {
        const backdrop = LS.el("div", "modal-backdrop");
        const card = LS.el("div", "modal-card");
        card.style.maxWidth = "520px";

        const closeX = LS.el("button", "modal-close");
        closeX.textContent = "✕";
        closeX.addEventListener("click", () => backdrop.remove());
        card.appendChild(closeX);

        const h2 = LS.el("h2");
        h2.innerHTML = `Publish to <em>eBay</em>?`;
        card.appendChild(h2);

        const warn = LS.el("div");
        Object.assign(warn.style, {
            marginTop: "12px",
            padding: "14px 16px",
            background: "var(--bg-input)",
            border: "1px solid var(--gold)",
            borderRadius: "4px",
            fontSize: "13px",
            lineHeight: "1.55",
            color: "var(--ink-1)",
        });
        warn.innerHTML = `
            <div style="font-weight: 600; color: var(--gold-bright); margin-bottom: 6px;">
                This will create a live eBay listing.
            </div>
            <div style="color: var(--ink-2);">
                Once published, the item is visible to buyers and counts toward your insertion fee allowance. You can end the listing in Seller Hub if you need to take it back, but the listing fee may still apply.
            </div>
        `;
        card.appendChild(warn);

        const footer = LS.el("div", "modal-footer-bar");
        footer.style.marginTop = "16px";

        const cancel = LS.el("button", "btn-update-now", "Cancel");
        cancel.style.background = "transparent";
        cancel.style.color = "var(--ink-2)";
        cancel.style.border = "1px solid var(--ink-3)";
        cancel.addEventListener("click", () => backdrop.remove());
        footer.appendChild(cancel);

        const go = LS.el("button", "btn-update-now");
        go.textContent = "Yes — publish now";
        go.style.background = "var(--gold-bright)";
        go.style.color = "var(--bg-deep)";
        go.addEventListener("click", async () => {
            go.disabled = true;
            go.textContent = "Publishing…";
            try {
                const r = await fetch(`/api/templates/${templateId}/publish-to-ebay`, {
                    method: "POST",
                });
                const data = await r.json();
                if (!r.ok) {
                    throw new Error(data.detail || `HTTP ${r.status}`);
                }
                backdrop.remove();
                showPublishedModal(data);
            } catch (err) {
                go.disabled = false;
                go.textContent = "Yes — publish now";
                let errEl = card.querySelector(".publish-err");
                if (!errEl) {
                    errEl = LS.el("div", "publish-err");
                    Object.assign(errEl.style, {
                        marginTop: "12px",
                        padding: "10px 12px",
                        background: "var(--bg-input)",
                        border: "1px solid var(--rust-bright)",
                        borderRadius: "4px",
                        color: "var(--rust-bright)",
                        fontSize: "12px",
                        fontFamily: "var(--font-mono)",
                        whiteSpace: "pre-wrap",
                    });
                    card.insertBefore(errEl, footer);
                }
                errEl.textContent = "Publish failed: " + err.message;
            }
        });
        footer.appendChild(go);

        card.appendChild(footer);
        backdrop.appendChild(card);
        document.body.appendChild(backdrop);
    };

    function showPublishedModal(data) {
        const backdrop = LS.el("div", "modal-backdrop");
        const card = LS.el("div", "modal-card");
        card.style.maxWidth = "520px";

        const closeX = LS.el("button", "modal-close");
        closeX.textContent = "✕";
        closeX.addEventListener("click", () => backdrop.remove());
        card.appendChild(closeX);

        const h2 = LS.el("h2");
        h2.innerHTML = data.already_published
            ? `Already <em>live</em>`
            : `Published to <em>eBay</em>`;
        card.appendChild(h2);

        const sub = LS.el("div", "modal-sub");
        sub.innerHTML = `Listing ID: <span style="font-family: var(--font-mono); color: var(--gold-bright);">${LS.escapeHTML(data.listing_id || "—")}</span>`;
        card.appendChild(sub);

        const okBox = LS.el("div");
        Object.assign(okBox.style, {
            marginTop: "16px",
            padding: "14px 16px",
            background: "var(--bg-input)",
            border: "1px solid var(--moss-bright)",
            borderRadius: "4px",
            color: "var(--ink-1)",
            fontSize: "13px",
            lineHeight: "1.5",
        });
        okBox.innerHTML = `
            <div style="font-weight: 600; color: var(--moss-bright); margin-bottom: 6px;">
                ✓ Your listing is live on eBay.
            </div>
            <div style="color: var(--ink-2);">
                Click below to open the listing page and verify everything renders correctly.
            </div>
        `;
        card.appendChild(okBox);

        const footer = LS.el("div", "modal-footer-bar");
        footer.style.marginTop = "16px";

        const close = LS.el("button", "btn-update-now", "Done");
        close.style.background = "transparent";
        close.style.color = "var(--ink-2)";
        close.style.border = "1px solid var(--ink-3)";
        close.addEventListener("click", () => backdrop.remove());
        footer.appendChild(close);

        const open = LS.el("button", "btn-update-now");
        open.textContent = "→ Open live listing";
        open.style.background = "var(--moss-bright)";
        open.style.color = "var(--bg-deep)";
        open.addEventListener("click", () => {
            window.open(data.url || "https://www.ebay.com/sh/lst/active", "_blank");
        });
        footer.appendChild(open);

        card.appendChild(footer);
        backdrop.appendChild(card);
        document.body.appendChild(backdrop);

        // Stash the recent publish for any future activity feed.
        try {
            const recent = JSON.parse(localStorage.getItem(RECENT_PUBLISH_KEY) || "[]");
            recent.unshift({listing_id: data.listing_id, url: data.url, at: Date.now()});
            localStorage.setItem(RECENT_PUBLISH_KEY, JSON.stringify(recent.slice(0, 20)));
        } catch (e) { /* ignore */ }
    }
})();

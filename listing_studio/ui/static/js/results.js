/**
 * Post results modal - shown after the user hits Post Listing.
 */

(function () {
    "use strict";

    LS.showPostResults = function (response) {
        const backdrop = LS.el("div", "modal-backdrop");
        const card = LS.el("div", "modal-card");

        const successCount = response.results.filter(r => r.status === "success").length;
        const failedCount = response.results.filter(r => r.status === "failed").length;
        const manualCount = response.results.filter(r => r.status === "manual").length;

        const h2 = LS.el("h2");
        if (successCount > 0) {
            h2.innerHTML = `Live on <em>${successCount} platform${successCount === 1 ? "" : "s"}</em>`;
        } else if (manualCount > 0 && failedCount === 0) {
            h2.innerHTML = `Ready for <em>manual post</em>`;
        } else {
            h2.innerHTML = `<em>${failedCount} platform${failedCount === 1 ? "" : "s"} failed</em>`;
        }
        card.appendChild(h2);

        card.appendChild(LS.el("div", "modal-sub",
            `Posted to ${response.results.length} platform${response.results.length === 1 ? "" : "s"} in ${(response.total_elapsed_ms / 1000).toFixed(1)}s`));

        for (const result of response.results) {
            const rcard = LS.el("div", `result-card ${result.status}`);

            rcard.appendChild(LS.el("div", `platform-logo ${result.platform}`, LS.platformLogoText(result.platform)));

            const info = LS.el("div");
            const name = LS.el("div");
            name.style.fontWeight = "600";
            name.style.color = "var(--ink)";
            name.appendChild(document.createTextNode(LS.platformDisplay(result.platform)));
            name.appendChild(LS.el("span", `result-status-pill ${result.status}`, result.status));
            info.appendChild(name);

            const detail = LS.el("div", "result-detail");
            if (result.status === "success" && result.external_listing_url) {
                const link = LS.el("a", null, result.external_listing_url);
                link.href = result.external_listing_url;
                detail.appendChild(link);
            } else if (result.error_message) {
                detail.textContent = result.error_message;
            } else if (result.status === "manual") {
                detail.textContent = "Copy-paste package ready";
            }
            info.appendChild(detail);
            rcard.appendChild(info);

            rcard.appendChild(LS.el("div", "result-price", LS.dollars(result.price_cents)));
            card.appendChild(rcard);
        }

        if (response.facebook_package) {
            const fbNote = LS.el("div", "modal-sub");
            fbNote.style.marginTop = "16px";
            fbNote.style.fontStyle = "italic";
            fbNote.textContent = "Facebook copy-paste package will appear here once that feature is implemented.";
            card.appendChild(fbNote);
        }

        const footer = LS.el("div", "modal-footer-bar");
        const closeBtn = LS.el("button", "btn-ghost", "Done");
        closeBtn.addEventListener("click", () => backdrop.remove());
        footer.appendChild(closeBtn);
        card.appendChild(footer);

        backdrop.appendChild(card);
        backdrop.addEventListener("click", e => {
            if (e.target === backdrop) backdrop.remove();
        });
        document.body.appendChild(backdrop);
    };
})();

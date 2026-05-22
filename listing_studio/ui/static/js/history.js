/**
 * History view - list of recent post attempts grouped by date.
 *
 * Fetches recent posts from the backend (we'll add the endpoint) and groups them
 * by day. Each item is expandable to show per-platform results.
 */

(function () {
    "use strict";

    LS.loadAndRenderHistory = async function () {
        const container = LS.$("history-view");
        // Find or create the container content
        let inner = LS.$("history-container");
        if (!inner) {
            inner = LS.el("div", "history-container");
            inner.id = "history-container";
            container.innerHTML = "";
            container.appendChild(inner);
        }
        inner.innerHTML = `<div class="empty-loading">Loading history…</div>`;

        try {
            const items = await LS.api("GET", "/api/posts/history");
            LS.state.historyItems = items;
            renderHistory();
        } catch (err) {
            inner.innerHTML = `<div class="empty-loading">Failed to load: ${err.message}</div>`;
        }
    };

    function renderHistory() {
        const inner = LS.$("history-container");
        inner.innerHTML = "";

        // Header
        const header = LS.el("div", "page-header");
        const headerLeft = LS.el("div");
        const h1 = LS.el("h1");
        h1.innerHTML = `Posting <em>History</em>`;
        headerLeft.appendChild(h1);
        headerLeft.appendChild(LS.el("p", null,
            "Recent listings posted across all platforms. Click an entry to see the per-platform results."));
        header.appendChild(headerLeft);

        const backBtn = LS.el("button", "tool-btn", "← Back to Library");
        backBtn.addEventListener("click", () => LS.showView("library"));
        header.appendChild(backBtn);
        inner.appendChild(header);

        if (!LS.state.historyItems || LS.state.historyItems.length === 0) {
            const empty = LS.el("div", "history-empty");
            empty.appendChild(LS.el("div", "icon", "📋"));
            const h3 = LS.el("h3", null, "No history yet");
            empty.appendChild(h3);
            empty.appendChild(LS.el("p", null,
                "Once you start posting listings, the history of all attempts (successful and failed) will appear here."));
            inner.appendChild(empty);
            return;
        }

        // Group by date
        const groups = groupByDate(LS.state.historyItems);
        for (const group of groups) {
            inner.appendChild(buildGroup(group));
        }
    }

    function groupByDate(items) {
        const groups = new Map();
        for (const item of items) {
            const date = new Date(item.started_at);
            const key = `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
            if (!groups.has(key)) {
                groups.set(key, { date: item.started_at, items: [] });
            }
            groups.get(key).items.push(item);
        }
        return Array.from(groups.values()).sort((a, b) =>
            new Date(b.date).getTime() - new Date(a.date).getTime()
        );
    }

    function buildGroup(group) {
        const div = LS.el("div", "history-group");

        const header = LS.el("div", "history-group-header");
        header.appendChild(LS.el("strong", null, LS.formatDate(group.date)));
        header.appendChild(LS.el("span", null, `${group.items.length} item${group.items.length === 1 ? "" : "s"}`));
        div.appendChild(header);

        for (const item of group.items) {
            div.appendChild(buildHistoryItem(item));
        }

        return div;
    }

    function buildHistoryItem(item) {
        const card = LS.el("div", "history-item");

        const header = LS.el("div", "history-item-header");

        const template = LS.el("div", "history-template");
        template.appendChild(LS.el("div", "history-template-name", item.template_name));
        const platformCounts = countByStatus(item.results);
        const metaText = [
            `${item.results.length} platform${item.results.length === 1 ? "" : "s"}`,
            platformCounts.success > 0 ? `${platformCounts.success} live` : null,
            platformCounts.failed > 0 ? `${platformCounts.failed} failed` : null,
            platformCounts.manual > 0 ? `${platformCounts.manual} manual` : null,
        ].filter(Boolean).join(" · ");
        template.appendChild(LS.el("div", "history-template-meta", metaText));
        header.appendChild(template);

        const strip = LS.el("div", "history-platform-strip");
        for (const result of item.results) {
            const dot = LS.el("div", `history-platform-dot ${result.platform} status-${result.status}`,
                LS.platformLogoText(result.platform));
            dot.title = `${LS.platformDisplay(result.platform)}: ${result.status}`;
            strip.appendChild(dot);
        }
        header.appendChild(strip);

        header.appendChild(LS.el("div", "history-time", LS.formatTime(item.started_at)));

        header.addEventListener("click", () => {
            card.classList.toggle("expanded");
        });
        card.appendChild(header);

        // Detail (expanded)
        const detail = LS.el("div", "history-item-detail");
        for (const result of item.results) {
            const row = LS.el("div", "history-result-row");
            row.appendChild(LS.el("div", `history-result-logo ${result.platform}`,
                LS.platformLogoText(result.platform)));

            const info = LS.el("div", "history-result-info");
            info.appendChild(LS.el("div", "history-result-platform", LS.platformDisplay(result.platform)));
            const meta = LS.el("div", "history-result-meta");
            if (result.status === "success" && result.external_listing_url) {
                const link = LS.el("a", null, result.external_listing_url);
                link.href = result.external_listing_url;
                meta.appendChild(link);
            } else if (result.status === "failed") {
                meta.classList.add("error");
                meta.textContent = result.error_message || "Failed";
            } else if (result.status === "manual") {
                meta.textContent = "Copy-paste package generated";
            } else {
                meta.textContent = result.status;
            }
            info.appendChild(meta);
            row.appendChild(info);

            row.appendChild(LS.el("div", "history-result-price", LS.dollars(result.price_cents)));
            detail.appendChild(row);
        }
        card.appendChild(detail);

        return card;
    }

    function countByStatus(results) {
        const out = { success: 0, failed: 0, manual: 0 };
        for (const r of results) {
            if (out[r.status] !== undefined) out[r.status]++;
        }
        return out;
    }
})();

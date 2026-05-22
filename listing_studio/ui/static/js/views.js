/**
 * View switching - library, settings, history.
 *
 * Updates the visible view and the toolbar's "active" state. Each view's
 * "show" handler does its own data loading and rendering.
 */

(function () {
    "use strict";

    LS.showView = async function (view) {
        LS.state.currentView = view;

        const views = {
            library: LS.$("library-view"),
            settings: LS.$("settings-view"),
            history: LS.$("history-view"),
        };

        for (const [name, el] of Object.entries(views)) {
            if (el) el.style.display = (name === view) ? "" : "none";
        }

        // Update toolbar active state
        const btnSettings = LS.$("btn-settings");
        const btnHistory = LS.$("btn-history");
        if (btnSettings) btnSettings.classList.toggle("active", view === "settings");
        if (btnHistory) btnHistory.classList.toggle("active", view === "history");

        // Per-view load
        if (view === "settings" && LS.loadAndRenderSettings) {
            await LS.loadAndRenderSettings();
        } else if (view === "history" && LS.loadAndRenderHistory) {
            await LS.loadAndRenderHistory();
        }
    };
})();

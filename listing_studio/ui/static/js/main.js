/**
 * Main app boot - the script tag at the bottom of index.html loads this last.
 *
 * Wires up the toolbar buttons, then fetches initial data and renders the library.
 */

(function () {
    "use strict";

    async function boot() {
        wireToolbar();
        wireSearch();

        try {
            const health = await LS.api("GET", "/api/health");
            LS.$("status-version").textContent = "v" + health.version;
            LS.setStatus("Connected", "ok");
        } catch (err) {
            LS.setStatus("Backend unavailable: " + err.message, "error");
            return;
        }

        await Promise.all([
            LS.loadTemplates(),
            loadFeeStructures(),
            LS.loadConnectionStatus(),
            LS.loadPreferences(),  // also pulls in accessibility settings
        ]);

        // Apply accessibility preferences as <body> classes so the CSS
        // overrides in base.css kick in. See settings.js for the matching
        // toggles that update these.
        LS.applyAccessibilityPrefs();

        // Check for updates in the background. Non-blocking - if it fails or
        // takes a while, the UI is already responsive.
        if (LS.checkForUpdates) {
            LS.checkForUpdates();
        }
    }

    // Reads the font_scale + high_contrast prefs from LS.state.preferences
    // and applies them as classes on the body. Called once at boot and
    // again whenever the user toggles them in Settings.
    LS.applyAccessibilityPrefs = function () {
        const prefs = LS.state.preferences || {};
        const body = document.body;

        // Font scale - mutually exclusive options ("normal" = no class)
        body.classList.remove("font-scale-large", "font-scale-xlarge");
        if (prefs.font_scale === "large") body.classList.add("font-scale-large");
        if (prefs.font_scale === "xlarge") body.classList.add("font-scale-xlarge");

        // High contrast - boolean toggle
        body.classList.toggle("high-contrast", !!prefs.high_contrast);
    };

    async function loadFeeStructures() {
        LS.state.feeStructures = await LS.api("GET", "/api/fees");
    }

    function wireToolbar() {
        LS.$("btn-help").addEventListener("click", () => LS.showView("help"));
        LS.$("btn-history").addEventListener("click", () => LS.showView("history"));
        LS.$("btn-settings").addEventListener("click", () => LS.showView("settings"));
        // Clicking the brand block (logo + product name) always returns to the
        // Library view. Gives Dad a universal escape hatch even if a future
        // view forgets its "← Back to Library" button.
        const brand = document.querySelector(".brand");
        if (brand) {
            brand.addEventListener("click", () => LS.showView("library"));
            brand.setAttribute("title", "Click to return to the Library");
        }
        // Note: the "New Template" / "New Category" buttons are rendered by
        // library.js into the sidebar footer and wire their own click handlers.
        // We used to have a static btn-new-template here too, but it's been
        // replaced - don't reach for it (the element is gone).
    }

    function wireSearch() {
        LS.$("template-search").addEventListener("input", (event) => {
            LS.state.searchQuery = event.target.value;
            LS.renderLibrary();
        });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }
})();

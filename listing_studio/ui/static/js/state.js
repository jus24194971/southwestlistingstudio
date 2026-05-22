/**
 * Listing Studio - global namespace and shared state.
 *
 * Each .js file under /static/js/ attaches functions to the LS namespace.
 * The shared mutable state lives at LS.state.
 *
 * This is plain JavaScript - no modules, no bundler. Each file is loaded
 * via a <script> tag in index.html, in dependency order.
 */

window.LS = window.LS || {};

LS.state = {
    // Library
    templatesByFolder: {},
    selectedTemplateId: null,
    currentTemplate: null,
    formDirty: false,
    searchQuery: "",

    // Form
    enabledPlatforms: new Set(),

    // Cached metadata
    feeStructures: {},
    connectionStatus: {},
    preferences: {},

    // View routing
    currentView: "library", // "library" | "settings" | "history"

    // History
    historyItems: [],

    // Photo picker (open modal state)
    picker: {
        open: false,
        selectedThumbs: [],         // ordered list of selected thumb IDs
        tags: ["kluson", "tuners", "vintage"], // demo tags
        currentFolder: "KLU-VTG-NIC-2023",
    },
};

LS.constants = {
    ALL_PLATFORMS: ["reverb", "ebay", "etsy", "squarespace", "facebook"],
    AUTO_POST_PLATFORMS: ["reverb", "ebay", "etsy", "squarespace"],
};

/**
 * Settings view - platform connections, default platforms, posting preferences.
 */

(function () {
    "use strict";

    LS.loadAndRenderSettings = async function () {
        const container = LS.$("settings-container");
        container.innerHTML = `<div class="empty-loading">Loading settings…</div>`;

        try {
            await Promise.all([
                LS.loadConnectionStatus(),
                LS.loadPreferences(),
            ]);
            renderSettings();
        } catch (err) {
            container.innerHTML = `<div class="empty-loading">Failed to load settings: ${err.message}</div>`;
        }
    };

    LS.loadConnectionStatus = async function () {
        const statuses = await LS.api("GET", "/api/settings/platforms");
        for (const s of statuses) {
            LS.state.connectionStatus[s.platform] = s;
        }
    };

    LS.loadPreferences = async function () {
        LS.state.preferences = await LS.api("GET", "/api/settings/preferences");
    };

    function renderSettings() {
        const container = LS.$("settings-container");
        container.innerHTML = "";

        // Header
        const header = LS.el("div", "page-header");
        const headerLeft = LS.el("div");
        const h1 = LS.el("h1");
        h1.innerHTML = `Platform <em>Connections</em>`;
        headerLeft.appendChild(h1);
        headerLeft.appendChild(LS.el("p", null,
            "Connect each marketplace once. Tokens refresh automatically afterward, except Etsy (90-day reconnect) and Facebook (manual post each time)."));
        header.appendChild(headerLeft);

        const backBtn = LS.el("button", "tool-btn", "← Back to Library");
        backBtn.addEventListener("click", () => LS.showView("library"));
        header.appendChild(backBtn);
        container.appendChild(header);

        // Platforms section
        const platformsBlock = LS.el("div", "section-block");
        platformsBlock.appendChild(buildSectionTitle("Auto-posting platforms"));
        for (const platform of LS.constants.ALL_PLATFORMS) {
            platformsBlock.appendChild(buildPlatformCard(platform));
        }
        container.appendChild(platformsBlock);

        // Default platforms section
        const defaultsBlock = LS.el("div", "section-block");
        defaultsBlock.appendChild(buildSectionTitle("Default platforms for new listings"));
        defaultsBlock.appendChild(LS.el("div", "section-help",
            "Which platforms get checked by default when you start a new listing. You can always override per listing."));

        const pillRow = LS.el("div", "platform-defaults");
        const defaultPlatforms = new Set(LS.state.preferences.default_platforms || []);

        for (const p of LS.constants.ALL_PLATFORMS) {
            if (p === "facebook") continue;
            const pill = LS.el("div", "platform-pill" + (defaultPlatforms.has(p) ? " active" : ""));
            pill.appendChild(LS.el("div", `platform-pill-logo ${p}`, LS.platformLogoText(p)));
            pill.appendChild(LS.el("span", "platform-pill-name", LS.platformDisplay(p)));
            pill.addEventListener("click", async () => {
                if (defaultPlatforms.has(p)) {
                    defaultPlatforms.delete(p);
                } else {
                    defaultPlatforms.add(p);
                }
                await updatePreference("default_platforms", Array.from(defaultPlatforms));
                renderSettings();
            });
            pillRow.appendChild(pill);
        }
        defaultsBlock.appendChild(pillRow);
        container.appendChild(defaultsBlock);

        // Preferences section
        const prefsBlock = LS.el("div", "section-block");
        prefsBlock.appendChild(buildSectionTitle("Posting preferences"));

        prefsBlock.appendChild(buildToggleRow(
            "post_parallel",
            "Post in parallel",
            "Send to all selected platforms simultaneously (faster). Disable to post one at a time with manual confirmation between."
        ));
        prefsBlock.appendChild(buildToggleRow(
            "post_best_effort",
            "Best-effort on failure",
            "If one platform fails, keep posting to the others. Disable to require all-or-nothing."
        ));
        prefsBlock.appendChild(buildNumberRow(
            "stale_price_warning_days",
            "Stale price warning threshold",
            "Show a warning when reposting a template that hasn't been used in this many days.",
            "days"
        ));
        prefsBlock.appendChild(buildToggleRow(
            "auto_copy_fb_description",
            "Auto-copy Facebook description",
            "When you click 'Open Marketplace' on the Facebook handoff, automatically copy the description so you can immediately paste it."
        ));
        prefsBlock.appendChild(buildToggleRow(
            "photo_background_removal",
            "Photo background removal (beta)",
            "Use AI to automatically remove backgrounds from product photos before posting (slower; off by default)."
        ));
        container.appendChild(prefsBlock);
    }

    function buildSectionTitle(text) {
        return LS.el("div", "section-title-line", text);
    }

    function buildPlatformCard(platform) {
        const conn = LS.state.connectionStatus[platform] || { is_connected: false };
        const isConnected = conn.is_connected;
        const isFacebook = platform === "facebook";

        const card = LS.el("div", "platform-card" + (isConnected ? " connected" : ""));
        const body = LS.el("div", "platform-card-body");

        body.appendChild(LS.el("div", `pc-logo ${platform}`, LS.platformLogoText(platform)));

        const info = LS.el("div", "pc-info");
        const name = LS.el("div", "pc-name");
        name.appendChild(document.createTextNode(LS.platformDisplay(platform)));

        let pillClass, pillText;
        if (isFacebook) {
            pillClass = "pc-status-pill manual";
            pillText = "Manual Mode";
        } else if (isConnected) {
            pillClass = "pc-status-pill connected";
            pillText = "Connected";
        } else {
            pillClass = "pc-status-pill disconnected";
            pillText = "Not Connected";
        }
        name.appendChild(LS.el("span", pillClass, pillText));
        info.appendChild(name);

        const detail = LS.el("div", "pc-detail");
        if (isFacebook) {
            detail.innerHTML = "Generates copy-paste package · no automated posting (FB doesn't allow it)";
        } else if (isConnected) {
            detail.innerHTML = conn.account_label
                ? `Account: <strong>${LS.escapeHTML(conn.account_label)}</strong>`
                : "Connected (no account label available)";
        } else {
            detail.textContent = `Click Connect to set up your ${LS.platformDisplay(platform)} account.`;
        }
        info.appendChild(detail);
        body.appendChild(info);

        const actions = LS.el("div", "pc-actions");
        if (isFacebook) {
            const infoBtn = LS.el("button", "btn-secondary-sm", "Why?");
            infoBtn.addEventListener("click", () => {
                alert("Facebook Marketplace doesn't offer a public API for third-party posting. We instead generate a 'copy-paste package' (formatted title, price, description, photos resized) that you can quickly paste into Facebook's posting form. We considered browser automation but it risks account ban.");
            });
            actions.appendChild(infoBtn);
        } else if (isConnected) {
            const testBtn = LS.el("button", "btn-secondary-sm", "Test");
            testBtn.addEventListener("click", async () => {
                testBtn.textContent = "Testing…";
                testBtn.disabled = true;
                try {
                    const result = await LS.api("POST", `/api/settings/platforms/${platform}/test`);
                    if (result.ok) {
                        alert(`✓ Connection works\n\nAccount: ${result.account_label || "(unnamed)"}`);
                    } else {
                        alert(`✗ Test failed\n\n${result.error || "Unknown error"}`);
                    }
                } catch (err) {
                    alert(`Test failed: ${err.message}`);
                } finally {
                    testBtn.textContent = "Test";
                    testBtn.disabled = false;
                }
            });
            actions.appendChild(testBtn);

            const disconnectBtn = LS.el("button", "btn-danger-sm", "Disconnect");
            disconnectBtn.addEventListener("click", async () => {
                if (!confirm(`Disconnect ${LS.platformDisplay(platform)}?`)) return;
                try {
                    await LS.api("POST", `/api/settings/platforms/${platform}/disconnect`);
                    await LS.loadConnectionStatus();
                    renderSettings();
                } catch (err) {
                    alert("Disconnect failed: " + err.message);
                }
            });
            actions.appendChild(disconnectBtn);
        } else {
            const connectBtn = LS.el("button", "btn-connect", "Connect");
            connectBtn.addEventListener("click", () => {
                const config = API_KEY_PLATFORMS[platform];
                if (config) {
                    openApiKeyConnectModal(platform, config);
                } else {
                    alert(`${LS.platformDisplay(platform)} OAuth: not yet implemented. Squarespace and Reverb are priority.`);
                }
            });
            actions.appendChild(connectBtn);
        }
        body.appendChild(actions);

        card.appendChild(body);
        return card;
    }

    function buildToggleRow(prefKey, label, helpText) {
        const row = LS.el("div", "pref-row");
        const info = LS.el("div", "pref-info");
        info.appendChild(LS.el("div", "pref-label", label));
        info.appendChild(LS.el("div", "pref-help", helpText));
        row.appendChild(info);

        const control = LS.el("div", "pref-control");
        const toggle = LS.el("div", "toggle" + (LS.state.preferences[prefKey] ? " on" : ""));
        toggle.addEventListener("click", async () => {
            const newValue = !LS.state.preferences[prefKey];
            toggle.classList.toggle("on", newValue);
            await updatePreference(prefKey, newValue);
        });
        control.appendChild(toggle);
        row.appendChild(control);

        return row;
    }

    function buildNumberRow(prefKey, label, helpText, suffix) {
        const row = LS.el("div", "pref-row");
        const info = LS.el("div", "pref-info");
        info.appendChild(LS.el("div", "pref-label", label));
        info.appendChild(LS.el("div", "pref-help", helpText));
        row.appendChild(info);

        const control = LS.el("div", "pref-control");
        const input = LS.el("input", "pref-number");
        input.type = "text";
        input.value = String(LS.state.preferences[prefKey] ?? "");

        let saveTimeout = null;
        input.addEventListener("input", () => {
            clearTimeout(saveTimeout);
            const num = parseInt(input.value, 10);
            if (!isNaN(num)) {
                saveTimeout = setTimeout(() => updatePreference(prefKey, num), 600);
            }
        });
        control.appendChild(input);
        control.appendChild(LS.el("span", "pref-suffix", suffix));
        row.appendChild(control);

        return row;
    }

    async function updatePreference(key, value) {
        try {
            LS.state.preferences = await LS.api("PATCH", "/api/settings/preferences", { [key]: value });
        } catch (err) {
            alert(`Failed to save preference '${key}': ${err.message}`);
        }
    }

    // ----------------------------------------------------------------------
    // Generic API key connect modal
    // ----------------------------------------------------------------------

    /**
     * Per-platform configuration for the API key connect modal. To add a new
     * API-key platform, just add an entry here and ensure the backend has
     * /api/settings/platforms/{name}/connect routed.
     */
    const API_KEY_PLATFORMS = {
        squarespace: {
            label: "Squarespace",
            credentialName: "API Key",
            placeholder: "Paste your Squarespace API key…",
            helpHtml: `Generate the key in Squarespace at <span class="kbd">Settings → Advanced → Developer API Keys</span> with these permissions:<br>
                <span class="kbd">• Products: Read &amp; Write<br>
                • Inventory: Read &amp; Write<br>
                • Orders: Read</span>`,
        },
        reverb: {
            label: "Reverb",
            credentialName: "Personal Access Token",
            placeholder: "Paste your Reverb personal access token…",
            helpHtml: `Generate the token at <span class="kbd">My Profile → API &amp; Integrations → Generate new token</span> with these scopes:<br>
                <span class="kbd">• public<br>
                • read_listings, write_listings<br>
                • read_orders<br>
                • read_profile</span>`,
        },
    };

    function openApiKeyConnectModal(platform, config) {
        const backdrop = LS.el("div", "modal-backdrop");
        backdrop.id = `${platform}-connect-backdrop`;

        const card = LS.el("div", "modal-card");
        card.style.maxWidth = "560px";

        const h2 = LS.el("h2");
        h2.innerHTML = `Connect <em>${LS.escapeHTML(config.label)}</em>`;
        card.appendChild(h2);

        card.appendChild(LS.el("div", "modal-sub",
            `Paste your ${config.label} ${config.credentialName.toLowerCase()} below. We'll validate it and store it securely in Windows Credential Manager.`));

        // Help text with platform-specific instructions
        const help = LS.el("div");
        help.style.fontSize = "12px";
        help.style.color = "var(--ink-3)";
        help.style.lineHeight = "1.5";
        help.style.marginBottom = "16px";
        help.innerHTML = config.helpHtml.replaceAll(
            'class="kbd"',
            'style="color: var(--gold-bright); font-family: var(--font-mono); font-size: 11px;"',
        );
        card.appendChild(help);

        // Input field
        const fieldLabel = LS.el("label");
        fieldLabel.style.display = "block";
        fieldLabel.style.fontSize = "11px";
        fieldLabel.style.color = "var(--ink-3)";
        fieldLabel.style.textTransform = "uppercase";
        fieldLabel.style.letterSpacing = "0.08em";
        fieldLabel.style.marginBottom = "5px";
        fieldLabel.textContent = config.credentialName;
        card.appendChild(fieldLabel);

        const input = LS.el("input");
        input.type = "password";
        input.placeholder = config.placeholder;
        input.style.width = "100%";
        input.style.background = "var(--bg-input)";
        input.style.border = "1px solid var(--line)";
        input.style.borderRadius = "4px";
        input.style.padding = "10px 12px";
        input.style.color = "var(--ink)";
        input.style.fontFamily = "var(--font-mono)";
        input.style.fontSize = "13px";
        card.appendChild(input);

        // Status line
        const status = LS.el("div");
        status.style.minHeight = "18px";
        status.style.marginTop = "10px";
        status.style.fontSize = "12px";
        status.style.fontFamily = "var(--font-mono)";
        card.appendChild(status);

        // Action buttons
        const footer = LS.el("div", "modal-footer-bar");
        const cancelBtn = LS.el("button", "btn-ghost", "Cancel");
        cancelBtn.addEventListener("click", () => backdrop.remove());
        footer.appendChild(cancelBtn);

        const connectBtn = LS.el("button", "btn-update-now", "Test & Save");
        connectBtn.addEventListener("click", async () => {
            const apiKey = input.value.trim();
            if (!apiKey) {
                status.style.color = "var(--rust-bright)";
                status.textContent = "Paste a key first.";
                return;
            }

            connectBtn.disabled = true;
            cancelBtn.disabled = true;
            status.style.color = "var(--ink-3)";
            status.textContent = `Validating with ${config.label}…`;

            try {
                const result = await LS.api("POST",
                    `/api/settings/platforms/${platform}/connect`,
                    { api_key: apiKey });

                status.style.color = "var(--moss-bright)";
                status.textContent = `✓ Connected to ${result.account_label || "(unnamed)"}`;

                setTimeout(() => {
                    backdrop.remove();
                    LS.loadAndRenderSettings();
                }, 800);
            } catch (err) {
                status.style.color = "var(--rust-bright)";
                status.textContent = err.message || "Failed";
                connectBtn.disabled = false;
                cancelBtn.disabled = false;
            }
        });
        footer.appendChild(connectBtn);
        card.appendChild(footer);

        backdrop.appendChild(card);
        backdrop.addEventListener("click", e => {
            if (e.target === backdrop) backdrop.remove();
        });
        document.body.appendChild(backdrop);

        setTimeout(() => input.focus(), 50);
    }
})();

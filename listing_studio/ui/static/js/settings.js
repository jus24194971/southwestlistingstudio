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
                LS.loadPhotoHostStatus(),
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

    LS.loadPhotoHostStatus = async function () {
        // Stored in its own state slot since it's not a platform. Shape:
        //   {connected: bool, service_name: "imgbb"|null, display_name: "ImgBB"|null}
        LS.state.photoHostStatus = await LS.api("GET", "/api/settings/photo-host");
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

        // Image hosting section. Reverb's API requires photos as public URLs,
        // not binary uploads, so we host them externally and pass URLs to
        // Reverb. Without a host configured, drafts get created photoless and
        // Dad drags photos into the Reverb web UI by hand.
        container.appendChild(buildPhotoHostBlock());

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

        // Listing tail boilerplate (appended to every Reverb description)
        container.appendChild(buildListingTailBlock());

        // Updates section
        container.appendChild(buildUpdatesBlock());
    }

    /**
     * Block where Dad can paste his "About us / Owner's Notes" boilerplate that
     * gets appended to every Reverb listing description automatically. Saved as
     * the `reverb_listing_tail` preference.
     */
    function buildListingTailBlock() {
        const block = LS.el("div", "section-block");
        block.appendChild(buildSectionTitle("Reverb listing boilerplate"));

        const intro = LS.el("div", "pref-help");
        intro.style.padding = "0 0 8px 0";
        intro.style.fontSize = "12px";
        intro.style.lineHeight = "1.5";
        intro.innerHTML = `This text gets appended to the bottom of every Reverb listing description automatically. Use it for shop policies, shipping info, the "About Southwest Acoustic Products" paragraph - anything you'd paste into every listing anyway.`;
        block.appendChild(intro);

        const textarea = LS.el("textarea");
        textarea.id = "reverb-tail-textarea";
        textarea.style.width = "100%";
        textarea.style.minHeight = "180px";
        textarea.style.background = "var(--bg-input)";
        textarea.style.border = "1px solid var(--line)";
        textarea.style.borderRadius = "4px";
        textarea.style.padding = "10px 12px";
        textarea.style.color = "var(--ink)";
        textarea.style.fontFamily = "var(--font-body)";
        textarea.style.fontSize = "13px";
        textarea.style.lineHeight = "1.5";
        textarea.style.resize = "vertical";
        textarea.value = LS.state.preferences.reverb_listing_tail || "";
        textarea.placeholder = "At Southwest Acoustic Products, all of our products are tested and brought back to new standards...";
        block.appendChild(textarea);

        const status = LS.el("div");
        status.id = "reverb-tail-status";
        status.style.marginTop = "6px";
        status.style.fontSize = "11px";
        status.style.color = "var(--ink-3)";
        status.style.minHeight = "16px";
        status.textContent = LS.state.preferences.reverb_listing_tail
            ? `${LS.state.preferences.reverb_listing_tail.length} characters saved`
            : "Empty - no boilerplate will be appended";
        block.appendChild(status);

        // Debounced auto-save 800ms after the user stops typing
        let saveTimer = null;
        textarea.addEventListener("input", () => {
            clearTimeout(saveTimer);
            status.textContent = "Saving…";
            status.style.color = "var(--ink-3)";
            saveTimer = setTimeout(async () => {
                try {
                    await updatePreference("reverb_listing_tail", textarea.value);
                    status.style.color = "var(--moss-bright)";
                    status.textContent = `✓ Saved (${textarea.value.length} characters)`;
                } catch (err) {
                    status.style.color = "var(--rust-bright)";
                    status.textContent = `Save failed: ${err.message}`;
                }
            }, 800);
        });

        return block;
    }

    /**
     * Updates section: shows current version and a manual "Check for updates"
     * button. Uses the existing update banner/install flow from updates.js
     * if an update is found, so we don't duplicate the install logic.
     */
    function buildUpdatesBlock() {
        const block = LS.el("div", "section-block");
        block.appendChild(buildSectionTitle("Updates"));

        const row = LS.el("div", "pref-row");

        const info = LS.el("div", "pref-info");
        info.appendChild(LS.el("div", "pref-label", "Check for updates"));

        const helpText = LS.el("div", "pref-help");
        helpText.id = "update-check-status";
        helpText.textContent = "Click to see if a newer version is available on GitHub.";
        info.appendChild(helpText);
        row.appendChild(info);

        const control = LS.el("div", "pref-control");
        const btn = LS.el("button", "btn-secondary-sm", "Check Now");
        btn.id = "btn-check-updates";
        btn.addEventListener("click", () => handleCheckForUpdates(btn, helpText));
        control.appendChild(btn);
        row.appendChild(control);

        block.appendChild(row);

        return block;
    }

    async function handleCheckForUpdates(btn, statusEl) {
        btn.disabled = true;
        btn.textContent = "Checking…";
        statusEl.style.color = "var(--ink-3)";
        statusEl.textContent = "Talking to GitHub…";

        try {
            // force=true bypasses the 6-hour cache so the user gets a real check
            const result = await LS.api("GET", "/api/updates/check?force=true");

            if (!result.is_packaged) {
                statusEl.style.color = "var(--ink-3)";
                statusEl.textContent = "Updates only check in installed builds. You're running from source right now.";
            } else if (result.update_available && result.release) {
                statusEl.style.color = "var(--moss-bright)";
                statusEl.innerHTML = `Update available: <strong>${LS.escapeHTML(result.release.tag_name)}</strong>. Look for the banner at the top of the window to install.`;
                // Trigger the existing update banner flow
                if (LS.checkForUpdates) {
                    // Clear the cached check result so checkForUpdates re-renders the banner
                    LS.checkForUpdates();
                }
            } else {
                statusEl.style.color = "var(--moss-bright)";
                statusEl.textContent = `✓ You're on the latest version (v${result.current_version}).`;
            }
        } catch (err) {
            statusEl.style.color = "var(--rust-bright)";
            statusEl.textContent = `Check failed: ${err.message}`;
        } finally {
            btn.disabled = false;
            btn.textContent = "Check Now";
        }
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

    // ----------------------------------------------------------------------
    // Image hosting section
    // ----------------------------------------------------------------------

    /**
     * Photo-host config card. Behaves like a platform card but talks to the
     * /api/settings/photo-host/* endpoints. Only one host (ImgBB) for now;
     * if/when we add Cloudinary etc, this turns into a list keyed by
     * status.service_name.
     */
    function buildPhotoHostBlock() {
        const block = LS.el("div", "section-block");
        block.appendChild(buildSectionTitle("Reverb photo hosting"));
        block.appendChild(LS.el("div", "section-help",
            "Reverb requires public URLs for photos, not binary uploads. " +
            "Connect an image host and we'll auto-upload your NAS photos to it, " +
            "then pass the URLs to Reverb when creating a draft. " +
            "Without a host, drafts are created with no photos and you'll drag them in by hand."));

        block.appendChild(buildPhotoHostCard());
        return block;
    }

    function buildPhotoHostCard() {
        const status = LS.state.photoHostStatus || { connected: false };
        const isConnected = !!status.connected;

        const card = LS.el("div", "platform-card" + (isConnected ? " connected" : ""));
        const body = LS.el("div", "platform-card-body");

        body.appendChild(LS.el("div", "pc-logo imgbb", "IB"));

        const info = LS.el("div", "pc-info");
        const name = LS.el("div", "pc-name");
        name.appendChild(document.createTextNode("ImgBB"));

        const pill = LS.el("span",
            "pc-status-pill " + (isConnected ? "connected" : "disconnected"),
            isConnected ? "Connected" : "Not Connected");
        name.appendChild(pill);
        info.appendChild(name);

        const detail = LS.el("div", "pc-detail");
        if (isConnected) {
            detail.innerHTML = "Auto-uploads photos to ImgBB before posting to Reverb.";
        } else {
            detail.innerHTML = `Free at <span style="color: var(--gold-bright);">imgbb.com</span>. Generate a key under your account's API page and paste it here.`;
        }
        info.appendChild(detail);
        body.appendChild(info);

        const actions = LS.el("div", "pc-actions");
        if (isConnected) {
            const testBtn = LS.el("button", "btn-secondary-sm", "Test");
            testBtn.addEventListener("click", async () => {
                testBtn.textContent = "Testing…";
                testBtn.disabled = true;
                try {
                    const result = await LS.api("POST", "/api/settings/photo-host/test");
                    if (result.ok) {
                        alert(`✓ ImgBB connection works\n\n${result.account_label || ""}`);
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
                if (!confirm("Disconnect ImgBB? Future Reverb drafts won't auto-include photos until you connect another host.")) return;
                try {
                    await LS.api("POST", "/api/settings/photo-host/disconnect");
                    await LS.loadPhotoHostStatus();
                    renderSettings();
                } catch (err) {
                    alert("Disconnect failed: " + err.message);
                }
            });
            actions.appendChild(disconnectBtn);
        } else {
            const connectBtn = LS.el("button", "btn-connect", "Connect");
            connectBtn.addEventListener("click", () => openPhotoHostConnectModal());
            actions.appendChild(connectBtn);
        }
        body.appendChild(actions);

        card.appendChild(body);
        return card;
    }

    /**
     * Modal for entering the ImgBB API key. Closely mirrors openApiKeyConnectModal
     * but talks to /api/settings/photo-host/imgbb/connect and refreshes the
     * photo-host status rather than the platform list.
     */
    function openPhotoHostConnectModal() {
        const backdrop = LS.el("div", "modal-backdrop");
        backdrop.id = "imgbb-connect-backdrop";

        const card = LS.el("div", "modal-card");
        card.style.maxWidth = "560px";

        const h2 = LS.el("h2");
        h2.innerHTML = `Connect <em>ImgBB</em>`;
        card.appendChild(h2);

        card.appendChild(LS.el("div", "modal-sub",
            "Paste your ImgBB API key below. We'll validate it with a tiny test upload and store it securely in Windows Credential Manager."));

        const help = LS.el("div");
        help.style.fontSize = "12px";
        help.style.color = "var(--ink-3)";
        help.style.lineHeight = "1.5";
        help.style.marginBottom = "16px";
        help.innerHTML = `Get a key at <span style="color: var(--gold-bright); font-family: var(--font-mono); font-size: 11px;">imgbb.com → Your account → API</span>. The free tier is enough for the photo volume here. Photos uploaded to ImgBB are accessible by anyone with the URL.`;
        card.appendChild(help);

        const fieldLabel = LS.el("label");
        fieldLabel.style.display = "block";
        fieldLabel.style.fontSize = "11px";
        fieldLabel.style.color = "var(--ink-3)";
        fieldLabel.style.textTransform = "uppercase";
        fieldLabel.style.letterSpacing = "0.08em";
        fieldLabel.style.marginBottom = "5px";
        fieldLabel.textContent = "API Key";
        card.appendChild(fieldLabel);

        const input = LS.el("input");
        input.type = "password";
        input.placeholder = "Paste your ImgBB API key…";
        input.style.width = "100%";
        input.style.background = "var(--bg-input)";
        input.style.border = "1px solid var(--line)";
        input.style.borderRadius = "4px";
        input.style.padding = "10px 12px";
        input.style.color = "var(--ink)";
        input.style.fontFamily = "var(--font-mono)";
        input.style.fontSize = "13px";
        card.appendChild(input);

        const status = LS.el("div");
        status.style.minHeight = "18px";
        status.style.marginTop = "10px";
        status.style.fontSize = "12px";
        status.style.fontFamily = "var(--font-mono)";
        card.appendChild(status);

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
            status.textContent = "Validating with ImgBB…";

            try {
                const result = await LS.api("POST",
                    "/api/settings/photo-host/imgbb/connect",
                    { api_key: apiKey });

                status.style.color = "var(--moss-bright)";
                status.textContent = `✓ Connected (${result.account_label || "ImgBB"})`;

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

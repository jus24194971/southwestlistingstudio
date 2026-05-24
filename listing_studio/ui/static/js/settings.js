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

        // Accessibility section - intentionally first so it's findable
        container.appendChild(buildAccessibilityBlock());

        // Backup & Transfer section
        container.appendChild(buildBackupBlock());

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
                // eBay has its own 3-field + OAuth flow modal; everything else
                // (Reverb, Squarespace) uses the single-API-key path.
                if (platform === "ebay") {
                    openEbayConnectModal();
                    return;
                }
                const config = API_KEY_PLATFORMS[platform];
                if (config) {
                    openApiKeyConnectModal(platform, config);
                } else {
                    alert(`${LS.platformDisplay(platform)} OAuth: not yet implemented.`);
                }
            });
            actions.appendChild(connectBtn);
        }
        body.appendChild(actions);

        card.appendChild(body);
        return card;
    }

    // ----------------------------------------------------------------------
    // Accessibility section (added v0.5.3)
    //
    // Two controls that materially change app legibility for Dad:
    //   - Font size: applied as a CSS zoom on <body>
    //   - High contrast: swaps in a brighter palette via .high-contrast class
    // Both persist as preferences; main.js re-applies them on every boot.
    // ----------------------------------------------------------------------

    function buildAccessibilityBlock() {
        const block = LS.el("div", "section-block");
        block.appendChild(buildSectionTitle("Accessibility"));
        block.appendChild(LS.el("div", "section-help",
            "Adjust how text and colors render. Both settings save automatically and apply across the whole app."));

        // Font size selector - radio-style buttons for click-to-set
        const row1 = LS.el("div", "pref-row");
        const info1 = LS.el("div", "pref-info");
        info1.appendChild(LS.el("div", "pref-label", "Text size"));
        info1.appendChild(LS.el("div", "pref-help",
            "Larger sizes scale every screen up. Use Extra Large if standard text strains your eyes."));
        row1.appendChild(info1);

        const sizeControl = LS.el("div", "pref-control");
        sizeControl.style.display = "flex";
        sizeControl.style.gap = "6px";
        const current = LS.state.preferences.font_scale || "normal";
        for (const opt of [
            { value: "normal", label: "Normal" },
            { value: "large", label: "Large" },
            { value: "xlarge", label: "Extra Large" },
        ]) {
            const btn = LS.el("button");
            btn.textContent = opt.label;
            const isActive = opt.value === current;
            Object.assign(btn.style, {
                padding: "6px 12px",
                fontSize: "12px",
                background: isActive ? "var(--gold-bright)" : "transparent",
                color: isActive ? "var(--bg-deep)" : "var(--ink-2)",
                border: "1px solid " + (isActive ? "var(--gold-bright)" : "var(--line)"),
                borderRadius: "4px",
                cursor: "pointer",
                fontWeight: isActive ? "600" : "400",
            });
            btn.addEventListener("click", async () => {
                await updatePreference("font_scale", opt.value);
                LS.applyAccessibilityPrefs();
                renderSettings();  // re-render to update active state
            });
            sizeControl.appendChild(btn);
        }
        row1.appendChild(sizeControl);
        block.appendChild(row1);

        // High contrast toggle
        block.appendChild(buildToggleRow(
            "high_contrast",
            "High contrast colors",
            "Switches to a brighter palette with whites and stronger gold for better legibility in low-light conditions or for low-vision users.",
        ));

        // Apply the prefs immediately when high_contrast is toggled. The
        // existing buildToggleRow handler saves to the DB but doesn't
        // re-apply CSS classes; hook that here by listening to the toggle.
        // Simplest path: just observe the toggle after the row is built.
        const toggleEl = block.querySelector(".pref-row:last-child .toggle");
        if (toggleEl) {
            toggleEl.addEventListener("click", () => {
                // Slight delay so the preferences round-trip completes first
                setTimeout(() => LS.applyAccessibilityPrefs(), 50);
            });
        }

        return block;
    }

    // ----------------------------------------------------------------------
    // Backup & Transfer section (added v0.5.3)
    //
    // Export: downloads a .sals file (ZIP) with all your templates,
    //   categories, mappings, tags, preferences. API keys are opt-in via
    //   the include-credentials checkbox.
    // Import: uploads a .sals file. This is DESTRUCTIVE - replaces current
    //   data. The UI confirms before triggering.
    // ----------------------------------------------------------------------

    function buildBackupBlock() {
        const block = LS.el("div", "section-block");
        block.appendChild(buildSectionTitle("Backup & Transfer"));
        block.appendChild(LS.el("div", "section-help",
            "Save a copy of all your templates, categories, and settings as a .sals file. Use this to move your setup to a new computer or just to keep a safety backup."));

        // -- Export row --
        const exportRow = LS.el("div", "pref-row");
        const exportInfo = LS.el("div", "pref-info");
        exportInfo.appendChild(LS.el("div", "pref-label", "Export backup"));
        exportInfo.appendChild(LS.el("div", "pref-help",
            "Downloads a .sals file containing all your data. Photos are not included (they stay on the NAS); paths are preserved so re-importing on the same NAS reattaches them automatically."));
        exportRow.appendChild(exportInfo);

        const exportControl = LS.el("div", "pref-control");
        const exportBtn = LS.el("button", "btn-update-now", "Export…");
        exportBtn.addEventListener("click", () => openExportModal());
        exportControl.appendChild(exportBtn);
        exportRow.appendChild(exportControl);
        block.appendChild(exportRow);

        // -- Import row --
        const importRow = LS.el("div", "pref-row");
        const importInfo = LS.el("div", "pref-info");
        importInfo.appendChild(LS.el("div", "pref-label", "Import backup"));
        const importHelp = LS.el("div", "pref-help");
        importHelp.innerHTML = "Restore from a previously-exported .sals file. <strong>This replaces all your current data</strong> - we'll auto-export the current state as a safety backup before proceeding.";
        importInfo.appendChild(importHelp);
        importRow.appendChild(importInfo);

        const importControl = LS.el("div", "pref-control");
        const importBtn = LS.el("button", "btn-secondary-sm", "Import…");
        importBtn.addEventListener("click", () => openImportModal());
        importControl.appendChild(importBtn);
        importRow.appendChild(importControl);
        block.appendChild(importRow);

        return block;
    }

    /**
     * Export modal - asks whether to include credentials in the .sals file,
     * with a clear security warning, then triggers the download.
     */
    function openExportModal() {
        const backdrop = LS.el("div", "modal-backdrop");
        const card = LS.el("div", "modal-card");
        card.style.maxWidth = "560px";

        const h2 = LS.el("h2");
        h2.innerHTML = `Export <em>backup</em>`;
        card.appendChild(h2);

        card.appendChild(LS.el("div", "modal-sub",
            "Choose what to include in the .sals file. Templates, categories, mappings, tags, and preferences are always included."));

        // Credentials checkbox + warning
        const credsRow = LS.el("div");
        Object.assign(credsRow.style, {
            marginTop: "16px",
            padding: "14px 16px",
            background: "var(--bg-input)",
            border: "1px solid var(--gold)",
            borderRadius: "4px",
        });

        const checkboxLabel = LS.el("label");
        checkboxLabel.style.display = "flex";
        checkboxLabel.style.alignItems = "flex-start";
        checkboxLabel.style.gap = "10px";
        checkboxLabel.style.cursor = "pointer";

        const checkbox = LS.el("input");
        checkbox.type = "checkbox";
        checkbox.style.marginTop = "3px";
        checkboxLabel.appendChild(checkbox);

        const labelText = LS.el("div");
        labelText.style.flex = "1";
        labelText.innerHTML = `
            <div style="font-weight: 600; color: var(--gold-bright); margin-bottom: 4px;">Include API keys (optional)</div>
            <div style="color: var(--ink-2); font-size: 13px; line-height: 1.5;">
                Includes your Reverb token, eBay credentials, Squarespace key, and ImgBB key in the backup. Convenient for moving to a new computer.
                <br><br>
                <strong style="color: var(--rust-bright);">⚠ Security:</strong> The file is not encrypted. Treat it like a password — store it somewhere only you have access to.
            </div>
        `;
        checkboxLabel.appendChild(labelText);
        credsRow.appendChild(checkboxLabel);
        card.appendChild(credsRow);

        // Footer
        const footer = LS.el("div", "modal-footer-bar");
        footer.style.marginTop = "20px";

        const cancelBtn = LS.el("button", "btn-ghost", "Cancel");
        cancelBtn.addEventListener("click", () => backdrop.remove());
        footer.appendChild(cancelBtn);

        const downloadBtn = LS.el("button", "btn-update-now", "Download .sals file");
        downloadBtn.addEventListener("click", async () => {
            downloadBtn.disabled = true;
            downloadBtn.textContent = "Generating…";
            // Use a real anchor click so the browser handles the download
            // dialog (Save As) rather than just navigating to the URL.
            const url = `/api/backup/export?include_credentials=${checkbox.checked ? "true" : "false"}`;
            const a = document.createElement("a");
            a.href = url;
            // The Content-Disposition header sets the filename; just trigger
            // the download. We can't easily detect when the browser finishes,
            // so close the modal after a short delay.
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => backdrop.remove(), 600);
        });
        footer.appendChild(downloadBtn);
        card.appendChild(footer);

        backdrop.appendChild(card);
        backdrop.addEventListener("click", e => {
            if (e.target === backdrop) backdrop.remove();
        });
        LS.attachModalCloseButton(card, backdrop);
        document.body.appendChild(backdrop);
    }

    /**
     * Import modal - confirms the destructive action, optionally takes a
     * safety backup of current state first, then uploads the chosen .sals.
     */
    function openImportModal() {
        const backdrop = LS.el("div", "modal-backdrop");
        const card = LS.el("div", "modal-card");
        card.style.maxWidth = "560px";

        const h2 = LS.el("h2");
        h2.innerHTML = `Import <em>backup</em>`;
        card.appendChild(h2);

        card.appendChild(LS.el("div", "modal-sub",
            "Restore a .sals file. This will replace your current templates, categories, mappings, tags, and preferences."));

        // Warning callout
        const warn = LS.el("div");
        Object.assign(warn.style, {
            marginTop: "16px",
            padding: "14px 16px",
            background: "var(--bg-input)",
            border: "1px solid var(--rust)",
            borderRadius: "4px",
            fontSize: "13px",
            lineHeight: "1.5",
            color: "var(--ink-2)",
        });
        warn.innerHTML = `
            <div style="font-weight: 600; color: var(--rust-bright); margin-bottom: 6px;">⚠ This replaces all current data</div>
            <div>Before importing, we'll automatically download a safety backup of your current state — if anything goes wrong, you can re-import that to roll back.</div>
        `;
        card.appendChild(warn);

        // File picker
        const fileLabel = LS.el("label");
        fileLabel.style.display = "block";
        fileLabel.style.marginTop = "16px";
        fileLabel.style.fontSize = "11px";
        fileLabel.style.color = "var(--ink-3)";
        fileLabel.style.textTransform = "uppercase";
        fileLabel.style.letterSpacing = "0.08em";
        fileLabel.style.marginBottom = "5px";
        fileLabel.textContent = "Choose .sals file";
        card.appendChild(fileLabel);

        const fileInput = LS.el("input");
        fileInput.type = "file";
        fileInput.accept = ".sals,application/zip,application/octet-stream";
        fileInput.style.cssText = "width: 100%; background: var(--bg-input); border: 1px solid var(--line); border-radius: 4px; padding: 8px; color: var(--ink); font-size: 13px;";
        card.appendChild(fileInput);

        const status = LS.el("div");
        status.style.minHeight = "20px";
        status.style.marginTop = "12px";
        status.style.fontSize = "12px";
        status.style.fontFamily = "var(--font-mono)";
        card.appendChild(status);

        // Footer
        const footer = LS.el("div", "modal-footer-bar");
        footer.style.marginTop = "20px";

        const cancelBtn = LS.el("button", "btn-ghost", "Cancel");
        cancelBtn.addEventListener("click", () => backdrop.remove());
        footer.appendChild(cancelBtn);

        const importBtn = LS.el("button", "btn-update-now", "Import (replaces current data)");
        importBtn.addEventListener("click", async () => {
            const file = fileInput.files && fileInput.files[0];
            if (!file) {
                status.style.color = "var(--rust-bright)";
                status.textContent = "Choose a file first.";
                return;
            }

            // Step 1: trigger a safety backup download. We just open the
            // export URL; the browser saves it with the filename header.
            status.style.color = "var(--ink-3)";
            status.textContent = "Saving safety backup of current state…";
            const safetyA = document.createElement("a");
            safetyA.href = "/api/backup/export?include_credentials=false";
            document.body.appendChild(safetyA);
            safetyA.click();
            document.body.removeChild(safetyA);

            // Brief pause so the safety backup download starts before we
            // mutate the DB. Not strictly required (export reads, import
            // writes - different transactions) but feels safer.
            await new Promise(r => setTimeout(r, 800));

            // Step 2: read the chosen file and POST it
            importBtn.disabled = true;
            cancelBtn.disabled = true;
            status.textContent = "Importing…";
            try {
                const buffer = await file.arrayBuffer();
                const response = await fetch("/api/backup/import", {
                    method: "POST",
                    headers: { "Content-Type": "application/octet-stream" },
                    body: buffer,
                });
                if (!response.ok) {
                    const text = await response.text();
                    throw new Error(`HTTP ${response.status}: ${text}`);
                }
                const result = await response.json();

                status.style.color = "var(--moss-bright)";
                const counts = result.counts || {};
                const summary = Object.entries(counts)
                    .map(([k, v]) => `${v} ${k}`)
                    .join(", ");
                status.textContent = `✓ Restored: ${summary}`;

                if (result.warnings && result.warnings.length > 0) {
                    const w = LS.el("div");
                    w.style.marginTop = "10px";
                    w.style.fontSize = "11px";
                    w.style.color = "var(--gold-bright)";
                    w.innerHTML = `<strong>${result.warnings.length} warning(s):</strong><br>` +
                        result.warnings.map(LS.escapeHTML).join("<br>");
                    card.insertBefore(w, footer);
                }

                // Reload the templates list so the new ones show
                if (LS.loadTemplates) await LS.loadTemplates();

                setTimeout(() => {
                    backdrop.remove();
                    LS.loadAndRenderSettings();
                }, 2000);
            } catch (err) {
                status.style.color = "var(--rust-bright)";
                status.textContent = `Import failed: ${err.message}`;
                importBtn.disabled = false;
                cancelBtn.disabled = false;
            }
        });
        footer.appendChild(importBtn);
        card.appendChild(footer);

        backdrop.appendChild(card);
        backdrop.addEventListener("click", e => {
            if (e.target === backdrop) backdrop.remove();
        });
        LS.attachModalCloseButton(card, backdrop);
        document.body.appendChild(backdrop);
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
        LS.attachModalCloseButton(card, backdrop);
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
        LS.attachModalCloseButton(card, backdrop);
        document.body.appendChild(backdrop);

        setTimeout(() => input.focus(), 50);
    }

    // ----------------------------------------------------------------------
    // eBay-specific connect modal
    //
    // eBay needs three fields up front (client_id, client_secret, ru_name)
    // and a follow-up OAuth dance to authorize Dad's actual seller account.
    // Step 1: Save & validate the three fields against eBay's app-token
    //         endpoint. On success, the modal transforms to show step 2.
    // Step 2: Click "Authorize Seller Account" - browser opens to eBay's
    //         consent screen. Modal polls the oauth-status endpoint until
    //         a user token shows up (or the user gives up and closes the
    //         modal).
    // ----------------------------------------------------------------------

    function openEbayConnectModal() {
        const backdrop = LS.el("div", "modal-backdrop");
        backdrop.id = "ebay-connect-backdrop";

        const card = LS.el("div", "modal-card");
        card.style.maxWidth = "600px";
        card.style.maxHeight = "85vh";
        card.style.overflowY = "auto";

        const h2 = LS.el("h2");
        h2.innerHTML = `Connect <em>eBay</em>`;
        card.appendChild(h2);

        card.appendChild(LS.el("div", "modal-sub",
            "eBay has two steps: app credentials (from your developer dashboard) and seller account authorization (a browser-based OAuth flow). The whole process takes about a minute."));

        // ---- Step 1: app credentials ----

        const step1 = LS.el("div");
        step1.style.marginTop = "20px";
        step1.style.paddingTop = "16px";
        step1.style.borderTop = "1px solid var(--line)";

        const step1Heading = LS.el("div");
        step1Heading.style.fontSize = "13px";
        step1Heading.style.fontWeight = "600";
        step1Heading.style.color = "var(--gold-bright)";
        step1Heading.style.marginBottom = "8px";
        step1Heading.textContent = "Step 1: App credentials";
        step1.appendChild(step1Heading);

        const help = LS.el("div");
        help.style.fontSize = "12px";
        help.style.color = "var(--ink-3)";
        help.style.lineHeight = "1.5";
        help.style.marginBottom = "16px";
        help.innerHTML = `Get all three values from <span style="color: var(--gold-bright); font-family: var(--font-mono); font-size: 11px;">developer.ebay.com → My Account → Application Keys</span> (Production column). The RuName is also there, listed as "Redirect URL settings."`;
        step1.appendChild(help);

        function buildFieldLabel(text) {
            const l = LS.el("label");
            l.style.display = "block";
            l.style.fontSize = "11px";
            l.style.color = "var(--ink-3)";
            l.style.textTransform = "uppercase";
            l.style.letterSpacing = "0.08em";
            l.style.marginBottom = "5px";
            l.style.marginTop = "12px";
            l.textContent = text;
            return l;
        }

        function buildFieldInput(placeholder, isSecret) {
            const i = LS.el("input");
            i.type = isSecret ? "password" : "text";
            i.placeholder = placeholder;
            i.style.cssText = "width: 100%; background: var(--bg-input); border: 1px solid var(--line); border-radius: 4px; padding: 10px 12px; color: var(--ink); font-family: var(--font-mono); font-size: 12px;";
            return i;
        }

        step1.appendChild(buildFieldLabel("Client ID (App ID)"));
        const clientIdInput = buildFieldInput("e.g. SouthwesAc-Listings-PRD-...", false);
        step1.appendChild(clientIdInput);

        step1.appendChild(buildFieldLabel("Client Secret (Cert ID)"));
        const clientSecretInput = buildFieldInput("Long secret string starting with PRD-...", true);
        step1.appendChild(clientSecretInput);

        step1.appendChild(buildFieldLabel("RuName (Redirect User Name)"));
        const ruNameInput = buildFieldInput("e.g. SouthwesAc-Listings-PRD-XXXXXXXXX-XXXXXXXX", false);
        step1.appendChild(ruNameInput);

        const ruNameHelp = LS.el("div");
        ruNameHelp.style.fontSize = "11px";
        ruNameHelp.style.color = "var(--ink-3)";
        ruNameHelp.style.marginTop = "6px";
        ruNameHelp.style.lineHeight = "1.5";
        ruNameHelp.innerHTML = `Set the RuName's redirect URL in eBay's dashboard to <code style="background: var(--bg-input); padding: 2px 5px; border-radius: 3px; color: var(--gold-bright);">http://localhost:8731/api/ebay/oauth/callback</code>`;
        step1.appendChild(ruNameHelp);

        // Step 1 status + action
        const step1Status = LS.el("div");
        step1Status.style.minHeight = "18px";
        step1Status.style.marginTop = "14px";
        step1Status.style.fontSize = "12px";
        step1Status.style.fontFamily = "var(--font-mono)";
        step1.appendChild(step1Status);

        const step1Footer = LS.el("div");
        step1Footer.style.display = "flex";
        step1Footer.style.gap = "8px";
        step1Footer.style.marginTop = "10px";

        const validateBtn = LS.el("button", "btn-update-now", "Validate & Save Step 1");
        step1Footer.appendChild(validateBtn);
        step1.appendChild(step1Footer);

        card.appendChild(step1);

        // ---- Step 2 (hidden until step 1 succeeds) ----

        const step2 = LS.el("div");
        step2.style.marginTop = "20px";
        step2.style.paddingTop = "16px";
        step2.style.borderTop = "1px solid var(--line)";
        step2.style.display = "none";  // Revealed on step 1 success

        const step2Heading = LS.el("div");
        step2Heading.style.fontSize = "13px";
        step2Heading.style.fontWeight = "600";
        step2Heading.style.color = "var(--gold-bright)";
        step2Heading.style.marginBottom = "8px";
        step2Heading.textContent = "Step 2: Authorize the seller account";
        step2.appendChild(step2Heading);

        const step2Help = LS.el("div");
        step2Help.style.fontSize = "12px";
        step2Help.style.color = "var(--ink-3)";
        step2Help.style.lineHeight = "1.5";
        step2Help.style.marginBottom = "12px";
        step2Help.innerHTML = "Clicking the button below opens your default browser to eBay's consent page. Log in as the seller (Dad's eBay account) and approve the permissions. When you come back to this modal, the seller token will be saved automatically.";
        step2.appendChild(step2Help);

        const authorizeBtn = LS.el("button", "btn-update-now", "→ Authorize Seller Account");
        step2.appendChild(authorizeBtn);

        const step2Status = LS.el("div");
        step2Status.style.minHeight = "20px";
        step2Status.style.marginTop = "14px";
        step2Status.style.fontSize = "12px";
        step2Status.style.fontFamily = "var(--font-mono)";
        step2.appendChild(step2Status);

        card.appendChild(step2);

        // ---- Footer ----

        const footer = LS.el("div", "modal-footer-bar");
        footer.style.marginTop = "24px";
        const cancelBtn = LS.el("button", "btn-ghost", "Cancel");
        cancelBtn.addEventListener("click", () => {
            stopPolling();
            backdrop.remove();
        });
        footer.appendChild(cancelBtn);

        const doneBtn = LS.el("button", "btn-update-now", "Done");
        doneBtn.style.display = "none";  // Revealed when step 2 completes
        doneBtn.addEventListener("click", () => {
            stopPolling();
            backdrop.remove();
            LS.loadAndRenderSettings();
        });
        footer.appendChild(doneBtn);

        card.appendChild(footer);

        backdrop.appendChild(card);
        backdrop.addEventListener("click", e => {
            if (e.target === backdrop) {
                stopPolling();
                backdrop.remove();
            }
        });
        // × in the corner also stops the OAuth poll before removing the modal
        LS.attachModalCloseButton(card, backdrop, () => { stopPolling(); });
        document.body.appendChild(backdrop);

        // ---- Step 1 behavior ----

        validateBtn.addEventListener("click", async () => {
            const clientId = clientIdInput.value.trim();
            const clientSecret = clientSecretInput.value.trim();
            const ruName = ruNameInput.value.trim();
            if (!clientId || !clientSecret || !ruName) {
                step1Status.style.color = "var(--rust-bright)";
                step1Status.textContent = "All three fields are required.";
                return;
            }
            validateBtn.disabled = true;
            step1Status.style.color = "var(--ink-3)";
            step1Status.textContent = "Validating with eBay…";
            try {
                const result = await LS.api("POST", "/api/settings/platforms/ebay/connect", {
                    client_id: clientId,
                    client_secret: clientSecret,
                    ru_name: ruName,
                });
                step1Status.style.color = "var(--moss-bright)";
                step1Status.textContent = `✓ App credentials accepted (${result.account_label})`;
                // Reveal step 2
                step2.style.display = "";
                validateBtn.disabled = true;
                validateBtn.textContent = "✓ Saved";
                // Lock the inputs so user can't muck with them
                clientIdInput.disabled = true;
                clientSecretInput.disabled = true;
                ruNameInput.disabled = true;
            } catch (err) {
                step1Status.style.color = "var(--rust-bright)";
                step1Status.textContent = err.message || "Validation failed";
                validateBtn.disabled = false;
            }
        });

        // ---- Step 2 behavior ----

        let pollTimer = null;
        function stopPolling() {
            if (pollTimer) {
                clearInterval(pollTimer);
                pollTimer = null;
            }
        }

        authorizeBtn.addEventListener("click", async () => {
            authorizeBtn.disabled = true;
            step2Status.style.color = "var(--ink-3)";
            step2Status.textContent = "Opening browser…";
            try {
                const result = await LS.api("GET", "/api/ebay/oauth/start");
                if (!result.opened) {
                    step2Status.innerHTML = `Browser didn't open automatically. <a href="${result.url}" target="_blank" style="color: var(--gold-bright);">Click here to open eBay manually</a>.`;
                } else {
                    step2Status.textContent = "Browser opened. Approve in eBay, then come back here…";
                }
                // Start polling for the callback to complete. eBay's consent
                // flow can take 20-60s depending on whether Dad has to log in.
                pollTimer = setInterval(checkOauthStatus, 2000);
            } catch (err) {
                step2Status.style.color = "var(--rust-bright)";
                step2Status.textContent = err.message || "Failed to start OAuth";
                authorizeBtn.disabled = false;
            }
        });

        async function checkOauthStatus() {
            try {
                const s = await LS.api("GET", "/api/settings/platforms/ebay/oauth-status");
                if (s.has_user_token) {
                    stopPolling();
                    step2Status.style.color = "var(--moss-bright)";
                    step2Status.textContent = `✓ Connected to eBay as ${s.account_label || "(unnamed)"}`;
                    authorizeBtn.style.display = "none";
                    doneBtn.style.display = "";
                    cancelBtn.style.display = "none";
                }
            } catch (err) {
                // Soft-fail; we just keep polling. The user can cancel.
                console.warn("eBay OAuth status poll failed:", err);
            }
        }

        setTimeout(() => clientIdInput.focus(), 50);
    }
})();

/**
 * Auto-update UI.
 *
 * On boot, asks the backend whether an update is available. If yes, shows a
 * banner above the view container. If the user clicks "Update Now", we kick
 * off the install via the API and poll progress until done, then call the
 * restart endpoint - the app re-launches into the new version.
 *
 * Skipped silently in dev mode (when is_packaged is false) - we don't want
 * to nag during development.
 */

(function () {
    "use strict";

    LS.checkForUpdates = async function () {
        try {
            const result = await LS.api("GET", "/api/updates/check");

            if (!result.is_packaged) {
                // Running from source - skip update UI entirely
                return;
            }
            if (!result.update_available || !result.release) {
                return;
            }

            renderUpdateBanner(result.release, result.current_version);
        } catch (err) {
            // Update check failures are non-fatal - log and continue
            console.warn("Update check failed:", err);
        }
    };

    function renderUpdateBanner(release, currentVersion) {
        // Don't render twice
        const existing = document.getElementById("update-banner");
        if (existing) return;

        const banner = LS.el("div", "update-banner");
        banner.id = "update-banner";

        banner.appendChild(LS.el("div", "update-banner-icon", "↑"));

        const msg = LS.el("div", "update-banner-msg");
        const title = LS.el("div", "update-banner-title");
        title.innerHTML = `Update available: <em>${LS.escapeHTML(release.tag_name)}</em>`;
        msg.appendChild(title);

        const sizeMB = (release.download_size / 1024 / 1024).toFixed(1);
        const sub = LS.el("div", "update-banner-sub",
            `You're on v${currentVersion} · ${sizeMB} MB download`);
        msg.appendChild(sub);
        banner.appendChild(msg);

        const actions = LS.el("div", "update-banner-actions");

        const laterBtn = LS.el("button", "btn-update-later", "Later");
        laterBtn.addEventListener("click", () => {
            banner.remove();
            // We'll get re-prompted on next launch
        });
        actions.appendChild(laterBtn);

        const updateBtn = LS.el("button", "btn-update-now", "Update Now");
        updateBtn.addEventListener("click", () => {
            banner.remove();
            startInstall(release);
        });
        actions.appendChild(updateBtn);

        banner.appendChild(actions);

        // Insert between toolbar and view container
        const viewContainer = LS.$("view-container");
        viewContainer.parentElement.insertBefore(banner, viewContainer);
    }

    function startInstall(release) {
        // Show progress dialog
        const backdrop = LS.el("div", "modal-backdrop");
        backdrop.id = "update-backdrop";
        const dialog = LS.el("div", "update-dialog");
        backdrop.appendChild(dialog);
        document.body.appendChild(backdrop);

        renderInstallDialog(dialog, release, { step: "starting" });

        // Kick off install
        LS.api("POST", "/api/updates/install", {}).then(() => {
            renderInstallDialog(dialog, release, { step: "downloading", bytes_done: 0, bytes_total: release.download_size });
            pollInstallProgress(dialog, release);
        }).catch(err => {
            renderInstallDialog(dialog, release, { step: "error", error: err.message });
        });
    }

    function pollInstallProgress(dialog, release) {
        const poll = async () => {
            try {
                const state = await LS.api("GET", "/api/updates/progress");

                if (state.error) {
                    renderInstallDialog(dialog, release, { step: "error", error: state.error });
                    return;
                }

                if (state.completed_install_root && !state.in_progress) {
                    renderInstallDialog(dialog, release, { step: "ready_to_restart" });
                    return;
                }

                if (state.in_progress) {
                    renderInstallDialog(dialog, release, {
                        step: "downloading",
                        bytes_done: state.bytes_done,
                        bytes_total: state.bytes_total,
                    });
                }

                // Continue polling
                setTimeout(poll, 250);
            } catch (err) {
                renderInstallDialog(dialog, release, { step: "error", error: err.message });
            }
        };
        poll();
    }

    async function doRestart(dialog, release) {
        renderInstallDialog(dialog, release, { step: "restarting" });
        try {
            await LS.api("POST", "/api/updates/restart");
            // We won't get here - the app is exiting and the new one is starting
        } catch (err) {
            renderInstallDialog(dialog, release, { step: "error", error: err.message });
        }
    }

    function renderInstallDialog(dialog, release, state) {
        dialog.innerHTML = "";

        const h2 = LS.el("h2");
        if (state.step === "error") {
            h2.innerHTML = `<em>Update failed</em>`;
        } else if (state.step === "ready_to_restart") {
            h2.innerHTML = `Ready to restart on <em>${LS.escapeHTML(release.tag_name)}</em>`;
        } else if (state.step === "restarting") {
            h2.innerHTML = `Restarting…`;
        } else {
            h2.innerHTML = `Installing <em>${LS.escapeHTML(release.tag_name)}</em>`;
        }
        dialog.appendChild(h2);

        if (state.step === "starting" || state.step === "downloading") {
            const stepLabel = LS.el("div", "step", state.step === "starting" ? "Starting download…" : "Downloading…");
            dialog.appendChild(stepLabel);

            const bar = LS.el("div", "progress-bar");
            const fill = LS.el("div", "progress-bar-fill");
            const pct = state.bytes_total > 0 ? (state.bytes_done / state.bytes_total) * 100 : 0;
            fill.style.width = pct + "%";
            bar.appendChild(fill);
            dialog.appendChild(bar);

            const stats = LS.el("div", "progress-stats");
            const left = LS.el("div");
            if (state.bytes_total > 0) {
                const doneMB = (state.bytes_done / 1024 / 1024).toFixed(1);
                const totalMB = (state.bytes_total / 1024 / 1024).toFixed(1);
                left.innerHTML = `<strong>${doneMB}</strong> / ${totalMB} MB`;
            }
            stats.appendChild(left);
            stats.appendChild(LS.el("div", null, `${pct.toFixed(0)}%`));
            dialog.appendChild(stats);
        }

        if (state.step === "ready_to_restart") {
            dialog.appendChild(LS.el("div", "step", "Download complete"));
            dialog.appendChild(LS.el("p", null, "The update is installed. Click Restart to switch to the new version. The app will close and reopen automatically (5-10 seconds)."));

            if (release.body) {
                const notes = LS.el("div", "notes", release.body);
                dialog.appendChild(notes);
            }

            const actions = LS.el("div", "actions");
            const restartBtn = LS.el("button", "btn-update-now", "Restart Now");
            restartBtn.addEventListener("click", () => doRestart(dialog, release));
            actions.appendChild(restartBtn);

            const laterBtn = LS.el("button", "btn-update-later", "Restart Later");
            laterBtn.addEventListener("click", () => {
                document.getElementById("update-backdrop").remove();
                // Next launch will be on the new version automatically (current.txt set)
            });
            actions.appendChild(laterBtn);

            dialog.appendChild(actions);
        }

        if (state.step === "restarting") {
            dialog.appendChild(LS.el("div", "step", "Restarting"));
            dialog.appendChild(LS.el("p", null, "Closing this version and starting the new one…"));
        }

        if (state.step === "error") {
            dialog.appendChild(LS.el("div", "step", "Error"));
            const errBox = LS.el("div", "notes");
            errBox.style.color = "var(--rust-bright)";
            errBox.textContent = state.error || "Unknown error";
            dialog.appendChild(errBox);
            dialog.appendChild(LS.el("p", null, "Your existing version is unaffected. Try again later, or contact support if the problem persists."));

            const actions = LS.el("div", "actions");
            const closeBtn = LS.el("button", "btn-update-later", "Close");
            closeBtn.addEventListener("click", () => {
                document.getElementById("update-backdrop").remove();
            });
            actions.appendChild(closeBtn);
            dialog.appendChild(actions);
        }
    }
})();

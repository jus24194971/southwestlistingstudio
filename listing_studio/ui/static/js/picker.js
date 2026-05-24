/**
 * Photo picker modal - real NAS browser.
 *
 * Talks to /api/nas/* endpoints to browse Dad's network drive. Folders and
 * photos render together; clicking a folder navigates into it, clicking a
 * photo selects it.
 *
 * Selection model:
 *   - First selected = primary (becomes the cover/first photo on listings)
 *   - Subsequent selections numbered in pick order
 *   - Selection state lives in LS.state.picker.selectedPaths (array of full
 *     filesystem paths)
 *
 * The picker is single-modal-instance: opening clears any previous state
 * (selections, current folder) so each invocation starts fresh.
 */

(function () {
    "use strict";

    // ----------------------------------------------------------------------
    // Open / close
    // ----------------------------------------------------------------------

    LS.openPicker = function () {
        LS.state.picker.open = true;
        LS.state.picker.selectedPaths = [];
        LS.state.picker.currentFolder = null;  // null = at root selector
        LS.state.picker.currentListing = null;
        LS.state.picker.breadcrumb = [];
        LS.state.picker.tags = ["kluson", "tuners", "vintage"]; // TODO: from template
        loadRootsAndRender();
    };

    function closePicker() {
        LS.state.picker.open = false;
        const existing = document.getElementById("picker-backdrop");
        if (existing) existing.remove();
    }

    // ----------------------------------------------------------------------
    // Data loading
    // ----------------------------------------------------------------------

    async function loadRootsAndRender() {
        try {
            const roots = await LS.api("GET", "/api/nas/roots");
            LS.state.picker.roots = roots;
            renderPicker();
        } catch (err) {
            renderError(`Couldn't load NAS roots: ${err.message}`);
        }
    }

    async function navigateToFolder(path, rootLabel) {
        renderPicker(true); // show loading state
        try {
            const listing = await LS.api("GET",
                `/api/nas/list?path=${encodeURIComponent(path)}`);
            LS.state.picker.currentFolder = path;
            LS.state.picker.currentListing = listing;

            // Build breadcrumb from path components relative to root
            const root = LS.state.picker.roots.find(r =>
                path === r.path || path.startsWith(r.path + "\\"));
            if (root) {
                const relative = path.substring(root.path.length).split(/[\\\/]/).filter(Boolean);
                LS.state.picker.breadcrumb = [
                    { label: root.label, path: root.path },
                    ...relative.map((part, i) => ({
                        label: part,
                        path: root.path + "\\" + relative.slice(0, i + 1).join("\\"),
                    })),
                ];
            } else {
                LS.state.picker.breadcrumb = [{ label: "(folder)", path: path }];
            }

            renderPicker();
        } catch (err) {
            renderError(`Couldn't list folder: ${err.message}`);
        }
    }

    function backToRoots() {
        LS.state.picker.currentFolder = null;
        LS.state.picker.currentListing = null;
        LS.state.picker.breadcrumb = [];
        renderPicker();
    }

    // ----------------------------------------------------------------------
    // Rendering
    // ----------------------------------------------------------------------

    function renderPicker(loading) {
        const existing = document.getElementById("picker-backdrop");
        if (existing) existing.remove();

        const backdrop = LS.el("div", "modal-backdrop");
        backdrop.id = "picker-backdrop";
        backdrop.style.zIndex = "100";

        const modal = LS.el("div", "picker-modal");
        modal.appendChild(buildHeader());
        modal.appendChild(buildBody(loading));
        modal.appendChild(buildSelectedRail());
        modal.appendChild(buildFooter());
        backdrop.appendChild(modal);

        backdrop.addEventListener("click", e => {
            if (e.target === backdrop) closePicker();
        });
        document.body.appendChild(backdrop);
    }

    function renderError(message) {
        const existing = document.getElementById("picker-backdrop");
        if (existing) existing.remove();

        const backdrop = LS.el("div", "modal-backdrop");
        backdrop.id = "picker-backdrop";
        const card = LS.el("div", "modal-card");
        card.appendChild(LS.el("h2", null, "NAS Browser Error"));
        const errBox = LS.el("div", "modal-sub");
        errBox.style.color = "var(--rust-bright)";
        errBox.textContent = message;
        card.appendChild(errBox);
        const footer = LS.el("div", "modal-footer-bar");
        const closeBtn = LS.el("button", "btn-ghost", "Close");
        closeBtn.addEventListener("click", closePicker);
        footer.appendChild(closeBtn);
        card.appendChild(footer);
        backdrop.appendChild(card);
        document.body.appendChild(backdrop);
    }

    // ----------------------------------------------------------------------
    // Header
    // ----------------------------------------------------------------------

    function buildHeader() {
        const header = LS.el("div", "picker-header");

        const titleBlock = LS.el("div", "picker-title-block");
        titleBlock.appendChild(LS.el("div", "picker-icon", "📁"));
        const titleText = LS.el("div");
        titleText.appendChild(LS.el("div", "picker-title-h", "Add Photos from NAS"));
        titleText.appendChild(LS.el("div", "picker-title-sub", "Browse Dad's photo library"));
        titleBlock.appendChild(titleText);
        header.appendChild(titleBlock);

        // Breadcrumb path bar
        const pathBar = LS.el("div", "picker-path-bar");
        if (LS.state.picker.breadcrumb && LS.state.picker.breadcrumb.length > 0) {
            const rootsBtn = LS.el("span", "path-segment", "📂 Roots");
            rootsBtn.addEventListener("click", backToRoots);
            pathBar.appendChild(rootsBtn);

            LS.state.picker.breadcrumb.forEach((crumb, idx) => {
                pathBar.appendChild(LS.el("span", "path-sep", "›"));
                const isLast = idx === LS.state.picker.breadcrumb.length - 1;
                const seg = LS.el("span",
                    "path-segment" + (isLast ? " current" : ""),
                    crumb.label);
                if (!isLast) {
                    seg.addEventListener("click", () => navigateToFolder(crumb.path));
                }
                pathBar.appendChild(seg);
            });
        } else {
            pathBar.appendChild(LS.el("span", "path-segment current", "📂 Select a root to browse"));
        }
        header.appendChild(pathBar);

        const closeBtn = LS.el("button", "picker-close", "×");
        closeBtn.addEventListener("click", closePicker);
        header.appendChild(closeBtn);

        return header;
    }

    // ----------------------------------------------------------------------
    // Body
    // ----------------------------------------------------------------------

    function buildBody(loading) {
        const body = LS.el("div", "picker-body");

        // No sidebar in the real picker - breadcrumb handles navigation.
        // Use a smaller sidebar showing pinned + recent folders eventually.
        body.appendChild(buildSidebar());
        body.appendChild(buildGallery(loading));
        return body;
    }

    function buildSidebar() {
        const sidebar = LS.el("aside", "picker-sidebar");

        // Roots section - always shown so user can switch roots from anywhere
        const rootsSection = LS.el("div", "picker-section");
        rootsSection.appendChild(LS.el("div", "picker-section-label", "NAS Roots"));

        const roots = LS.state.picker.roots || [];
        const currentRootPath = LS.state.picker.breadcrumb && LS.state.picker.breadcrumb.length > 0
            ? LS.state.picker.breadcrumb[0].path : null;

        for (const root of roots) {
            const item = LS.el("div", "pin-item" + (root.path === currentRootPath ? " active" : ""));
            item.appendChild(LS.el("div", "pin-icon", root.exists ? "📂" : "⚠"));
            item.appendChild(LS.el("div", "pin-name", root.label));
            if (!root.exists) {
                item.title = "This root path is not currently reachable";
                item.style.opacity = "0.5";
            }
            item.addEventListener("click", () => {
                if (root.exists) navigateToFolder(root.path);
            });
            rootsSection.appendChild(item);
        }
        sidebar.appendChild(rootsSection);

        // Local-computer fallback. Always available - useful even when the
        // NAS is reachable (Dad sometimes has a one-off photo on his desktop).
        // When no NAS root is reachable, this is the primary path; see the
        // banner in buildRootChooser.
        const localSection = LS.el("div", "picker-section");
        localSection.appendChild(LS.el("div", "picker-section-label", "From this computer"));
        const localItem = LS.el("div", "pin-item");
        localItem.appendChild(LS.el("div", "pin-icon", "💻"));
        localItem.appendChild(LS.el("div", "pin-name", "Pick photos…"));
        localItem.style.cursor = "pointer";
        localItem.addEventListener("click", pickLocalAndStage);
        localSection.appendChild(localItem);
        sidebar.appendChild(localSection);

        // Selected count
        const selectedSection = LS.el("div", "picker-section");
        selectedSection.appendChild(LS.el("div", "picker-section-label", "Current Selection"));
        const count = LS.state.picker.selectedPaths.length;
        const countDisplay = LS.el("div", "pin-item");
        countDisplay.style.cursor = "default";
        countDisplay.style.pointerEvents = "none";
        countDisplay.appendChild(LS.el("div", "pin-icon", "✓"));
        countDisplay.appendChild(LS.el("div", "pin-name",
            `${count} photo${count === 1 ? "" : "s"}`));
        selectedSection.appendChild(countDisplay);
        sidebar.appendChild(selectedSection);

        return sidebar;
    }

    /**
     * Open the OS native file dialog (via the FastAPI bridge), merge any
     * picked paths into the picker's selection state, then re-render so they
     * show up in the rail. From the user's perspective this is identical to
     * having ticked photos in the NAS browser - the same "Add N photos"
     * button completes the attach to the template.
     */
    async function pickLocalAndStage() {
        try {
            const result = await LS.api("POST", "/api/photos/pick-local");
            const paths = result.paths || [];
            if (paths.length === 0) {
                // User cancelled or picked nothing - no-op, no alarm
                return;
            }
            for (const p of paths) {
                if (!LS.state.picker.selectedPaths.includes(p)) {
                    LS.state.picker.selectedPaths.push(p);
                }
            }
            // Re-render to update the rail and the sidebar count
            renderPicker();
        } catch (err) {
            alert(`Couldn't open the local picker:\n\n${err.message}`);
        }
    }

    // ----------------------------------------------------------------------
    // Gallery (folders + photos)
    // ----------------------------------------------------------------------

    function buildGallery(loading) {
        const gallery = LS.el("section", "picker-gallery");

        const toolbar = LS.el("div", "gallery-toolbar");
        const stat = LS.el("div", "gallery-stat");

        if (loading) {
            stat.textContent = "Loading…";
        } else if (LS.state.picker.currentListing) {
            const l = LS.state.picker.currentListing;
            stat.innerHTML = `<strong>${l.folders.length}</strong> folders · <strong>${l.images.length}</strong> photos`;
        } else {
            stat.innerHTML = "Choose a NAS root from the sidebar to begin";
        }
        toolbar.appendChild(stat);
        gallery.appendChild(toolbar);

        const body = LS.el("div", "gallery-body");

        if (loading) {
            body.appendChild(LS.el("div", "empty-loading", "Loading…"));
        } else if (!LS.state.picker.currentListing) {
            body.appendChild(buildRootChooser());
        } else {
            const grid = LS.el("div", "thumbs-grid");

            // Folders first
            for (const folder of LS.state.picker.currentListing.folders) {
                grid.appendChild(buildFolderTile(folder));
            }
            // Then photos
            for (const image of LS.state.picker.currentListing.images) {
                grid.appendChild(buildPhotoTile(image));
            }

            if (LS.state.picker.currentListing.folders.length === 0 &&
                LS.state.picker.currentListing.images.length === 0) {
                grid.appendChild(LS.el("div", "empty-loading", "This folder is empty."));
            }

            body.appendChild(grid);
        }

        gallery.appendChild(body);
        return gallery;
    }

    function buildRootChooser() {
        const wrap = LS.el("div");
        wrap.style.padding = "20px";

        const roots = LS.state.picker.roots || [];
        const anyReachable = roots.some(r => r.exists);

        // Failover banner: if no NAS root is reachable, lead with the local-
        // picker option rather than making Dad puzzle over why the NAS tiles
        // are all greyed out.
        if (!anyReachable) {
            wrap.appendChild(buildNasUnreachableBanner());
        }

        const heading = LS.el("h3");
        heading.style.fontFamily = "var(--font-display)";
        heading.style.fontStyle = "italic";
        heading.style.fontSize = "20px";
        heading.style.color = "var(--gold-bright)";
        heading.style.marginBottom = "16px";
        heading.textContent = anyReachable
            ? "Choose a starting folder"
            : "NAS folders (currently unreachable)";
        wrap.appendChild(heading);

        const grid = LS.el("div", "thumbs-grid");

        for (const root of roots) {
            const tile = LS.el("div", "thumb");
            tile.style.cursor = root.exists ? "pointer" : "not-allowed";
            tile.style.opacity = root.exists ? "1" : "0.5";

            const img = LS.el("div", "thumb-img");
            img.style.background = root.exists ? "var(--bg-input)" : "var(--bg-panel-2)";
            img.style.display = "grid";
            img.style.placeItems = "center";
            img.style.fontSize = "48px";
            img.textContent = root.exists ? "📂" : "⚠";
            tile.appendChild(img);

            const meta = LS.el("div", "thumb-meta");
            meta.appendChild(LS.el("div", "thumb-name", root.label));
            meta.appendChild(LS.el("div", "thumb-detail",
                root.exists ? "Click to browse" : "Not reachable"));
            tile.appendChild(meta);

            if (root.exists) {
                tile.addEventListener("click", () => navigateToFolder(root.path));
            }
            grid.appendChild(tile);
        }

        wrap.appendChild(grid);
        return wrap;
    }

    /**
     * Big visible "NAS unreachable, here's how to pick from your computer
     * instead" banner shown when none of the configured roots resolve.
     */
    function buildNasUnreachableBanner() {
        const banner = LS.el("div");
        Object.assign(banner.style, {
            marginBottom: "20px",
            padding: "16px 18px",
            background: "var(--bg-input)",
            border: "1px solid var(--gold)",
            borderRadius: "6px",
            fontSize: "13px",
            lineHeight: "1.5",
        });

        const title = LS.el("div");
        title.style.fontWeight = "600";
        title.style.color = "var(--gold-bright)";
        title.style.marginBottom = "6px";
        title.style.fontSize = "14px";
        title.textContent = "⚠ NAS not reachable";
        banner.appendChild(title);

        const body = LS.el("div");
        body.style.color = "var(--ink-2)";
        body.style.marginBottom = "12px";
        body.innerHTML = `The configured NAS roots aren't responding (Z: drive offline, VPN disconnected, etc.). You can still attach photos from this computer's local storage — they'll work just like NAS photos.`;
        banner.appendChild(body);

        const btn = LS.el("button");
        btn.textContent = "📁 Pick photos from this computer";
        Object.assign(btn.style, {
            padding: "8px 14px",
            background: "var(--gold-bright)",
            color: "var(--bg-deep)",
            border: "none",
            borderRadius: "4px",
            fontWeight: "600",
            fontSize: "13px",
            cursor: "pointer",
        });
        btn.addEventListener("click", pickLocalAndStage);
        banner.appendChild(btn);

        return banner;
    }

    function buildFolderTile(folder) {
        const tile = LS.el("div", "thumb");
        tile.style.cursor = "pointer";

        const img = LS.el("div", "thumb-img");
        img.style.background = "var(--bg-input)";
        img.style.display = "grid";
        img.style.placeItems = "center";
        img.style.fontSize = "48px";
        img.style.color = "var(--gold)";
        img.textContent = "📁";
        tile.appendChild(img);

        const meta = LS.el("div", "thumb-meta");
        meta.appendChild(LS.el("div", "thumb-name", folder.name));
        meta.appendChild(LS.el("div", "thumb-detail", "Folder"));
        tile.appendChild(meta);

        tile.addEventListener("click", () => navigateToFolder(folder.path));
        return tile;
    }

    function buildPhotoTile(photo) {
        const selectedIdx = LS.state.picker.selectedPaths.indexOf(photo.path);
        const isSelected = selectedIdx >= 0;
        const isPrimary = selectedIdx === 0;

        const tile = LS.el("div", "thumb" + (isSelected ? " selected" : "") + (isPrimary ? " primary" : ""));
        tile.dataset.path = photo.path;

        const img = LS.el("div", "thumb-img");
        const imgEl = LS.el("img");
        imgEl.src = `/api/nas/thumbnail?path=${encodeURIComponent(photo.path)}`;
        imgEl.style.width = "100%";
        imgEl.style.height = "100%";
        imgEl.style.objectFit = "cover";
        imgEl.loading = "lazy";
        imgEl.onerror = () => {
            // If thumbnail generation failed, show a placeholder
            imgEl.style.display = "none";
            const ph = LS.el("div");
            ph.style.color = "var(--ink-4)";
            ph.style.fontSize = "24px";
            ph.textContent = "🖼";
            imgEl.parentElement.appendChild(ph);
        };
        img.appendChild(imgEl);

        if (isSelected) {
            img.insertAdjacentHTML("beforeend", `<div class="check-overlay">✓</div>`);
            if (isPrimary) {
                img.insertAdjacentHTML("beforeend", `<div class="primary-badge">PRIMARY</div>`);
            }
            img.insertAdjacentHTML("beforeend", `<div class="order-badge">${selectedIdx + 1}</div>`);
        }
        tile.appendChild(img);

        const meta = LS.el("div", "thumb-meta");
        meta.appendChild(LS.el("div", "thumb-name", photo.name));
        const sizeMB = (photo.size_bytes / 1024 / 1024).toFixed(1);
        meta.appendChild(LS.el("div", "thumb-detail", `${sizeMB} MB`));
        tile.appendChild(meta);

        tile.addEventListener("click", () => {
            const idx = LS.state.picker.selectedPaths.indexOf(photo.path);
            if (idx >= 0) {
                LS.state.picker.selectedPaths.splice(idx, 1);
            } else {
                LS.state.picker.selectedPaths.push(photo.path);
            }
            renderPicker();
        });

        return tile;
    }

    // ----------------------------------------------------------------------
    // Selected rail
    // ----------------------------------------------------------------------

    function buildSelectedRail() {
        const rail = LS.el("div", "selected-rail");

        const label = LS.el("div", "rail-label");
        label.appendChild(LS.el("span", null, "Selected"));
        label.appendChild(LS.el("strong", null,
            `${LS.state.picker.selectedPaths.length} photo${LS.state.picker.selectedPaths.length === 1 ? "" : "s"}`));
        rail.appendChild(label);

        const items = LS.el("div", "rail-items");
        if (LS.state.picker.selectedPaths.length === 0) {
            items.appendChild(LS.el("div", "rail-empty",
                "Click a photo above to select it · first selection becomes primary"));
        } else {
            LS.state.picker.selectedPaths.forEach((path, idx) => {
                const filename = path.split(/[\\\/]/).pop();

                const item = LS.el("div", "rail-item" + (idx === 0 ? " primary" : ""));

                const imgDiv = LS.el("div", "rail-img");
                const thumb = LS.el("img");
                thumb.src = `/api/nas/thumbnail?path=${encodeURIComponent(path)}`;
                thumb.style.width = "100%";
                thumb.style.height = "100%";
                thumb.style.objectFit = "cover";
                imgDiv.appendChild(thumb);
                item.appendChild(imgDiv);

                const info = LS.el("div", "rail-info");
                info.appendChild(LS.el("div", "rail-name", filename));
                if (idx === 0) info.appendChild(LS.el("span", "rail-primary-tag", "PRIMARY"));
                item.appendChild(info);

                const removeBtn = LS.el("button", "rail-remove", "×");
                removeBtn.addEventListener("click", e => {
                    e.stopPropagation();
                    LS.state.picker.selectedPaths = LS.state.picker.selectedPaths.filter(x => x !== path);
                    renderPicker();
                });
                item.appendChild(removeBtn);

                items.appendChild(item);
            });
        }
        rail.appendChild(items);
        return rail;
    }

    // ----------------------------------------------------------------------
    // Footer (tags + actions)
    // ----------------------------------------------------------------------

    function buildFooter() {
        const footer = LS.el("div", "picker-footer");

        const tagArea = LS.el("div", "tag-area");
        tagArea.appendChild(LS.el("span", "tag-label", "Tag selection:"));

        for (const tag of LS.state.picker.tags) {
            const chip = LS.el("span", "tag-chip");
            chip.appendChild(document.createTextNode(tag));
            const x = LS.el("button", "tag-chip-x", "×");
            x.addEventListener("click", () => {
                LS.state.picker.tags = LS.state.picker.tags.filter(t => t !== tag);
                renderPicker();
            });
            chip.appendChild(x);
            tagArea.appendChild(chip);
        }

        const addTag = LS.el("button", "tag-add", "+ add tag");
        addTag.addEventListener("click", () => {
            const newTag = prompt("New tag:");
            if (newTag && newTag.trim()) {
                LS.state.picker.tags.push(newTag.trim().toLowerCase());
                renderPicker();
            }
        });
        tagArea.appendChild(addTag);
        footer.appendChild(tagArea);

        const actions = LS.el("div", "picker-footer-actions");

        const cancelBtn = LS.el("button", "btn-ghost", "Cancel");
        cancelBtn.addEventListener("click", closePicker);
        actions.appendChild(cancelBtn);

        const count = LS.state.picker.selectedPaths.length;
        const addBtn = LS.el("button", "btn-picker-primary",
            count === 0 ? "Add photos" : `Add ${count} photo${count === 1 ? "" : "s"}`);
        addBtn.disabled = count === 0;
        addBtn.addEventListener("click", async () => {
            if (!LS.state.currentTemplate) {
                alert("No template selected — open a template first, then add photos.");
                return;
            }

            const templateId = LS.state.currentTemplate.id;
            addBtn.disabled = true;
            addBtn.textContent = "Saving…";

            try {
                const result = await LS.api(
                    "POST",
                    `/api/templates/${templateId}/photos`,
                    {
                        paths: LS.state.picker.selectedPaths,
                        tags: LS.state.picker.tags,
                    }
                );

                // Refresh the form so new photos appear
                closePicker();
                if (LS.selectTemplate) {
                    await LS.selectTemplate(templateId);
                }

                // Subtle success indicator - flash a status message
                if (LS.setStatus) {
                    const skipped = result.skipped_count > 0
                        ? ` (${result.skipped_count} already attached)`
                        : "";
                    LS.setStatus(`✓ Added ${result.added_count} photo${result.added_count === 1 ? "" : "s"}${skipped}`, "ok");
                    setTimeout(() => LS.setStatus("Ready", "ok"), 4000);
                }
            } catch (err) {
                alert(`Failed to add photos: ${err.message}`);
                addBtn.disabled = false;
                addBtn.textContent = count === 0 ? "Add photos" : `Add ${count} photo${count === 1 ? "" : "s"}`;
            }
        });
        actions.appendChild(addBtn);
        footer.appendChild(actions);
        return footer;
    }
})();

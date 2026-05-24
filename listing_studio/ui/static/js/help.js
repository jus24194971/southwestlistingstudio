/**
 * Help view - in-app guide for using Listing Studio.
 *
 * Structure: an array of {id, icon, title, subtitle, content} sections.
 * TOC on the left, content pane on the right. The active section is
 * tracked in LS.state.helpActiveSection so a re-entry to the view
 * remembers where the user was.
 *
 * Content is written in plain English for the actual user (Dad). When
 * adding a new feature elsewhere in the app, add a section here too.
 */

(function () {
    "use strict";

    LS.state.helpActiveSection = LS.state.helpActiveSection || "getting-started";

    // ----------------------------------------------------------------------
    // The content. Adding a section is just adding an object to this array.
    // The `content` field is HTML; keep it self-contained (no external
    // dependencies) and use the .help-* classes from help.css for styling.
    // ----------------------------------------------------------------------

    const SECTIONS = [
        {
            id: "getting-started",
            icon: "✦",
            title: "Getting Started",
            subtitle: "What this app does and how a typical session flows",
            content: `
                <p>Listing Studio is a one-stop tool for posting guitar parts to <strong>Reverb</strong>, <strong>eBay</strong>, and <strong>Squarespace</strong> from a single template. It also generates a copy-paste package for <strong>Facebook Marketplace</strong> since Facebook doesn't allow API posting.</p>

                <h2>The big picture</h2>
                <ol class="help-steps">
                    <li><strong>Connect each marketplace once</strong> in Settings. Tokens get stored securely in Windows Credential Manager - no plain-text files.</li>
                    <li><strong>Create a Category</strong> per product type (Tuners, Pickups, Bridges, etc.). Each Category gets mapped to the correct taxonomy on every platform once, then reused.</li>
                    <li><strong>Create a Template</strong> per product - title, description, price, photos. Pick the Category it belongs to.</li>
                    <li><strong>Hit "Post Reverb Draft"</strong> (and eventually eBay/Squarespace once those flows finish). The app builds the listing, uploads photos via ImgBB, and creates the draft for you to review and publish.</li>
                </ol>

                <h2>What the toolbar buttons do</h2>
                <ul>
                    <li><strong>Help</strong> - you're looking at it. Click any section in the sidebar to read about that feature.</li>
                    <li><strong>History</strong> - every posting attempt the app has made, with success/failure status and links to the actual listings.</li>
                    <li><strong>Settings</strong> - where you connect Reverb, Squarespace, eBay, and ImgBB. Also where you set your default boilerplate text and posting preferences.</li>
                </ul>

                <div class="help-callout tip">
                    <span class="help-callout-label">Tip</span>
                    The status bar at the bottom of the window always shows whether the app is connected to the backend and what version you're running. If something looks stuck, glance down there first.
                </div>
            `,
        },

        {
            id: "library",
            icon: "📚",
            title: "The Library",
            subtitle: "How templates are organized and how to find what you need",
            content: `
                <p>The library is the left sidebar on the main screen. It shows every template you've created, grouped by Category. Click any template to load it into the form on the right for editing or posting.</p>

                <h2>Searching</h2>
                <p>The search box at the top of the library filters templates by name, title, or description. It's instant - no need to press Enter. Clear the box to see everything again.</p>

                <h2>Categories in the sidebar</h2>
                <p>Each Category shows a header with the count of templates inside it. Click the header to collapse or expand that section. Click the small <strong>"+ New Category"</strong> button at the bottom of the sidebar to create a new one.</p>

                <h2>Starring a template</h2>
                <p>A small star icon next to a template marks it as a frequent favorite. Starred items sort to the top of their category. Click the star to toggle it on/off.</p>

                <h2>Creating a new template</h2>
                <p>The <strong>"+ New Template"</strong> button at the bottom of the sidebar opens the new-template wizard. You pick a Category first; the template's defaults pre-fill from that Category's defaults (condition, weight, shipping method). See <strong>Creating a Template</strong> for more.</p>

                <div class="help-callout">
                    <span class="help-callout-label">Note</span>
                    You can have many templates under one Category (e.g. ten different Tuner models all share the Tuners Category). Each template is one specific product; the Category is its taxonomy on the marketplaces.
                </div>
            `,
        },

        {
            id: "templates",
            icon: "📝",
            title: "Creating a Template",
            subtitle: "What every field does and how they map to each marketplace",
            content: `
                <p>A template is one product. All its fields - title, description, price, condition - get used when posting to any marketplace. You can also override specific fields per platform if (say) you want a longer description on eBay than Reverb.</p>

                <h2>The required fields</h2>
                <ul>
                    <li><strong>Name</strong> - your internal short name, never shown on a marketplace. Use what makes sense to you ("Kluson Vintage Nickel 6-in-line").</li>
                    <li><strong>Title</strong> - what buyers see at the top of the listing. Aim for 60-80 characters with the brand and model up front.</li>
                    <li><strong>Description</strong> - the body of the listing. Markdown-style formatting works (bullets, bold).</li>
                    <li><strong>Brand and Model</strong> - Reverb requires both. eBay uses them in their structured fields.</li>
                    <li><strong>Condition</strong> - "New Old Stock," "Excellent," "Very Good," etc. Each marketplace has slightly different condition names; the app translates yours to whatever Reverb/eBay expects.</li>
                    <li><strong>Price</strong> - in dollars. The app converts to cents internally.</li>
                    <li><strong>Quantity</strong> - how many you have available.</li>
                </ul>

                <h2>Category assignment</h2>
                <p>Pick a Category from the dropdown. The Category handles the taxonomy mapping (which Reverb UUID, which eBay category ID, which Squarespace store page) so you don't have to think about it per template. If you haven't created the right Category yet, click <strong>"+ New Category"</strong> in the sidebar first.</p>

                <h2>Photos</h2>
                <p>Click <strong>"Add Photos"</strong> in the form. See <strong>Adding Photos</strong> for the full picker walkthrough. The first photo you pick becomes the listing's cover photo on every marketplace.</p>

                <h2>Reverb-specific fields</h2>
                <p>A few fields only matter for Reverb:</p>
                <ul>
                    <li><strong>Year</strong> and <strong>Finish</strong> - Reverb shows these prominently in instrument listings.</li>
                    <li><strong>Reverb shipping</strong> - "Free domestic" or "Flat rate $X." Set on each template; falls back to a Reverb shipping profile if you don't set it here.</li>
                </ul>

                <h2>Saving</h2>
                <p>The form auto-saves edits 800ms after you stop typing. The "Save changes" button at the top right flashes when there are unsaved edits; once you stop typing, it relaxes back to indicating everything's saved.</p>

                <div class="help-callout tip">
                    <span class="help-callout-label">Tip</span>
                    To duplicate a template (useful for similar products), open the original, copy its name to a new template, then tweak the differences. The Category dropdown will pre-fill defaults from the Category each time.
                </div>
            `,
        },

        {
            id: "photos",
            icon: "🖼",
            title: "Adding Photos",
            subtitle: "NAS picker, local fallback, and how photos flow into listings",
            content: `
                <p>Photos can come from two places: the NAS (the network drive at <code>Z:\\</code>) or your local computer. The app handles both the same way once they're attached.</p>

                <h2>Opening the picker</h2>
                <p>Click <strong>Add Photos</strong> on a template form. The picker modal opens with the NAS browser if the NAS is reachable. If not, it switches to a local-file fallback mode (more below).</p>

                <h2>The NAS browser</h2>
                <ol class="help-steps">
                    <li>Pick a starting root from the sidebar - <strong>Guitar Pictures</strong> or <strong>Guitar Parts</strong>.</li>
                    <li>Click folders to navigate into them. The breadcrumb at the top shows where you are; click any breadcrumb segment to jump back up.</li>
                    <li>Click photo tiles to select them. The first one you pick becomes the <strong>primary</strong> (cover) photo; subsequent picks get numbered in order.</li>
                    <li>Click <strong>"Add N photos"</strong> at the bottom right to attach the selected photos to the template.</li>
                </ol>

                <h2>The local fallback</h2>
                <p>If the NAS isn't reachable (Z: drive offline, VPN dropped, working from a different network), the picker shows a yellow banner: <strong>"⚠ NAS not reachable"</strong>. Click <strong>"📁 Pick photos from this computer"</strong> to open the OS native file dialog instead. Selected photos appear in the same selection rail as NAS picks would.</p>

                <p>You can also pick local photos even when the NAS works fine - the sidebar always has a <strong>"From this computer"</strong> section with a Pick photos... button. Useful when Dad has a one-off photo on his desktop.</p>

                <h2>What happens to photos during posting</h2>
                <p>When you post to Reverb, the app does this for each photo:</p>
                <ol>
                    <li>Reads the file from the NAS (or local disk)</li>
                    <li>Rotates it correctly based on EXIF orientation (so phone shots don't show up sideways)</li>
                    <li>Resizes large photos down to 2048px on the long edge (avoids upload timeouts)</li>
                    <li>Re-encodes as JPEG at quality 88 (a good balance of file size and visual quality)</li>
                    <li>Uploads the normalized version to ImgBB (or whichever image host you have configured)</li>
                    <li>Passes the resulting URL to Reverb, which fetches and stores the photo on their CDN</li>
                </ol>

                <div class="help-callout warn">
                    <span class="help-callout-label">Note</span>
                    If <strong>no</strong> image host is configured in Settings, the app skips photo upload entirely. The Reverb draft gets created without photos, and you'll need to drag them into Reverb's web UI by hand. See <strong>Image Hosting</strong> for setup.
                </div>

                <h2>Reordering, removing</h2>
                <p>In the template form, each attached photo shows in a row. Click the small <strong>×</strong> to remove a photo. Drag photos to reorder them (the first one is always the cover).</p>
            `,
        },

        {
            id: "categories",
            icon: "🗂",
            title: "Categories",
            subtitle: "How one Category maps to every marketplace",
            content: `
                <p>Categories are the bridge between your mental organization (you think "Tuners") and each marketplace's required taxonomy (Reverb wants a UUID, eBay wants a numeric ID, Squarespace wants a store page). Set up the mapping once per Category and reuse it across every template in that bucket.</p>

                <h2>Creating a Category</h2>
                <ol class="help-steps">
                    <li>Click <strong>"+ New Category"</strong> in the library sidebar.</li>
                    <li>Type a <strong>name</strong> (e.g. "Tuners," "Acoustic Guitars," "Bridges").</li>
                    <li>In the <strong>Reverb</strong> section, type a search like "tuner" - results appear from Reverb's taxonomy. Click <strong>Set Primary</strong> on the right leaf category. Add subcategories with <strong>+ Sub</strong> if needed (Reverb allows up to 2 subs).</li>
                    <li>In the <strong>eBay</strong> section, do the same - search and pick a leaf category. eBay only allows listings on leaves; the app will warn you with a red "non-leaf" tag if you try to pick a parent.</li>
                    <li>In the <strong>Squarespace</strong> section, pick a store page from the dropdown.</li>
                    <li>Optionally set defaults (condition, weight, shipping method) that pre-fill any new template created under this Category.</li>
                    <li>Click <strong>Create Category</strong>.</li>
                </ol>

                <h2>The suggestion engine</h2>
                <p>When you pick a category on one platform, the app may suggest a matching category on another. Three sources, ordered by reliability:</p>

                <h3>✦ Shipped (highest confidence)</h3>
                <p>The app ships with a small set of hand-curated Reverb↔eBay mappings for common parts. When you pick Reverb's "Tuning Heads," the eBay suggestion box pre-fills with "Tuning Pegs" - one click to accept.</p>

                <h3>↺ Learned</h3>
                <p>Every Category you save with mappings on two or more platforms gets remembered. The next Category that picks the same Reverb leaf gets the same eBay leaf suggested at full confidence. The system gets smarter as you use it.</p>

                <h3>✱ Fuzzy match</h3>
                <p>If no direct mapping exists yet, the app does a name-based search against the target platform's taxonomy. Lower confidence; verify before accepting. After you confirm, the pairing is recorded as "learned" and becomes high-confidence going forward.</p>

                <h2>Recently used</h2>
                <p>Above each platform's search results in the Category editor, you'll see a row of pills showing the categories you've used most recently on that platform. Click any pill to apply it. Saves scrolling/searching for your frequent buckets.</p>

                <h2>Editing or deleting a Category</h2>
                <p>Click any Category header in the library sidebar to open it for editing. The Delete button only appears if no templates are currently using it - move or delete the templates first if you need to remove a Category.</p>
            `,
        },

        {
            id: "posting",
            icon: "📤",
            title: "Posting to Reverb",
            subtitle: "What happens when you click \"Post Reverb Draft\"",
            content: `
                <p>The <strong>Post Reverb Draft</strong> button on the template form sends everything Reverb needs to create a draft listing. <em>"Draft"</em> means: created on Reverb but not visible to buyers yet. You review it in Reverb's Seller Hub and publish when you're ready.</p>

                <h2>What happens, step by step</h2>
                <ol class="help-steps">
                    <li>The app saves any pending edits to the template first (so what gets posted matches what's on screen).</li>
                    <li>If you have ImgBB connected: each photo gets normalized (rotated, resized, JPEG-encoded) and uploaded. The resulting public URLs go into the Reverb payload.</li>
                    <li>The app reads the Category mapping and constructs the Reverb payload: title, description, condition, price, shipping config, category UUIDs, and photo URLs.</li>
                    <li>The Reverb API creates the draft and returns the listing ID + a URL to view it.</li>
                    <li>The result modal opens with an "Open Draft" button to take you to Reverb's web UI to review.</li>
                </ol>

                <h2>The result modal</h2>
                <p>Depending on the outcome, you'll see one of three callouts:</p>
                <ul>
                    <li><strong>Green</strong> - everything worked. "✓ N photos uploaded via ImgBB" with an Open Draft button.</li>
                    <li><strong>Yellow / partial</strong> - the draft was created but some photos failed. The modal shows which ones (expandable error list) and offers to open the photo folder for manual drag-and-drop on Reverb.</li>
                    <li><strong>Manual mode</strong> - no image host configured. The draft was created without photos; the modal opens both the Reverb draft AND the photo folder in Explorer so you can drag them in.</li>
                </ul>

                <h2>About the "draft" state</h2>
                <p>A Reverb draft is <strong>not</strong> visible to buyers and doesn't cost you any listing fees. You can edit it freely on Reverb before publishing. To delete a test draft, log into Reverb's Seller Hub - draft listings are managed in the same place as live listings.</p>

                <div class="help-callout tip">
                    <span class="help-callout-label">Why drafts?</span>
                    Until we've validated every platform's posting flow end-to-end, draft-only is the safe default - no fake test listings going live by accident. Once we trust the pipeline, we may add a "Publish immediately" toggle.
                </div>

                <h2>Listing tail / boilerplate</h2>
                <p>If you've set <strong>Reverb listing boilerplate</strong> in Settings (the textarea under "Reverb listing boilerplate"), that text gets appended to every Reverb description automatically. Useful for shop policies, the "About Southwest Acoustic Products" paragraph, shipping notes - anything you'd paste into every listing anyway.</p>
            `,
        },

        {
            id: "settings",
            icon: "⚙",
            title: "Settings & Connecting Accounts",
            subtitle: "Where credentials live and how to add each marketplace",
            content: `
                <p>The Settings screen is where every marketplace (and the image host) gets connected. Tokens are stored in <strong>Windows Credential Manager</strong> - never in plain text on disk.</p>

                <h2>Connecting Reverb</h2>
                <ol class="help-steps">
                    <li>On Reverb's website: <strong>My Profile → API &amp; Integrations → Generate new token</strong></li>
                    <li>Scopes needed: <code>public</code>, <code>read_listings</code>, <code>write_listings</code>, <code>read_orders</code>, <code>read_profile</code></li>
                    <li>Copy the token (long string starting with letters/numbers).</li>
                    <li>In the app: Settings → Reverb card → <strong>Connect</strong> → paste the token → <strong>Test &amp; Save</strong>. You should see a green "✓ Connected to [your shop name]".</li>
                </ol>

                <h2>Connecting Squarespace</h2>
                <ol class="help-steps">
                    <li>On Squarespace: <strong>Settings → Advanced → Developer API Keys</strong> → create a new key</li>
                    <li>Permissions: <strong>Products R/W, Inventory R/W, Orders R</strong></li>
                    <li>Copy the key, paste it into the app's Settings → Squarespace card.</li>
                </ol>

                <h2>Connecting eBay</h2>
                <p>eBay is the most complex because it has two credential types. App credentials (from your developer account) let the app read eBay's category taxonomy. User credentials (from your seller account) let the app actually post listings.</p>
                <ol class="help-steps">
                    <li>Get your <strong>client_id</strong> and <strong>client_secret</strong> from <strong>developer.ebay.com → My Account → Application Keys</strong> (use Production column).</li>
                    <li>Get your <strong>RuName</strong> from the same area - it's a redirect identifier eBay uses for the OAuth flow.</li>
                    <li>In the app: Settings → eBay card → <strong>Connect</strong> → paste all three.</li>
                    <li>After the app credentials validate, click <strong>Authorize Seller Account</strong> - your browser opens to eBay's consent screen.</li>
                    <li>Log in as Dad's eBay seller account, approve the permissions, and the browser sends you back. The app picks up the seller token automatically.</li>
                </ol>

                <h2>Connecting ImgBB (recommended for Reverb photos)</h2>
                <p>See the <strong>Image Hosting</strong> section for the why and the step-by-step.</p>

                <h2>Other preferences</h2>
                <ul>
                    <li><strong>Default platforms</strong> - which platforms get checked by default when starting a new listing.</li>
                    <li><strong>Post in parallel</strong> - send to all selected platforms at once (faster) vs. one at a time.</li>
                    <li><strong>Best-effort on failure</strong> - if one platform fails, keep going on the others.</li>
                    <li><strong>Stale price warning</strong> - get a heads-up if you're reposting a template that hasn't been used in a long time.</li>
                    <li><strong>Reverb listing boilerplate</strong> - boilerplate text that auto-appends to every Reverb description.</li>
                </ul>

                <h2>Disconnecting</h2>
                <p>Every connected platform has a <strong>Disconnect</strong> button. Removes the stored credentials. Tokens never get re-created automatically - you'd have to reconnect manually if needed.</p>
            `,
        },

        {
            id: "image-host",
            icon: "☁",
            title: "Image Hosting (ImgBB)",
            subtitle: "Why Reverb photos need an external host",
            content: `
                <p>Reverb's API doesn't accept binary photo uploads. The only working way to attach photos to a Reverb listing via the API is to give Reverb <strong>publicly fetchable URLs</strong> - Reverb's servers download the images themselves.</p>

                <p>That's why the app needs an image host. We use ImgBB as the default because it's free, has no real volume limits at our scale, and is dead simple to set up.</p>

                <h2>Setting up an ImgBB account</h2>
                <ol class="help-steps">
                    <li>Go to <code>imgbb.com</code> and click <strong>Sign Up</strong>. Just email + password - no credit card.</li>
                    <li>Verify your email.</li>
                    <li>Visit <code>api.imgbb.com</code> while logged in. Click the button to generate your API key.</li>
                    <li>Copy the key (long alphanumeric string).</li>
                    <li>In the app: Settings → <strong>Reverb photo hosting</strong> → <strong>Connect</strong> → paste the key → <strong>Test &amp; Save</strong>.</li>
                </ol>

                <h2>What happens at post time</h2>
                <p>With ImgBB connected, every Reverb post automatically uploads its photos to ImgBB first, then passes the URLs to Reverb. You'll see a green callout in the result modal: "✓ N photos uploaded via ImgBB."</p>

                <h2>Without ImgBB</h2>
                <p>If no image host is configured, Reverb drafts are created with <strong>no photos</strong>. The result modal opens the draft on Reverb AND the photo folder in Windows Explorer, so you can drag the photos into Reverb's web UI manually. Works, but more clicks per listing.</p>

                <h2>Privacy</h2>
                <div class="help-callout warn">
                    <span class="help-callout-label">Heads up</span>
                    ImgBB images are accessible to anyone with the URL. For Southwest Acoustics product photos (which end up on public Reverb listings anyway), this is fine. If we ever need stricter privacy (e.g. for confidential drafts), we can swap in Cloudinary or Backblaze B2 later - the photo-host interface is designed to support multiple providers.
                </div>

                <h2>Costs</h2>
                <p>Free tier handles way more than Dad's volume. ImgBB caps at 32 MB per image (the app normalizes well under that) and the upload rate limits are generous enough to be a non-issue.</p>
            `,
        },

        {
            id: "updates",
            icon: "⬆",
            title: "Updates",
            subtitle: "How the app updates itself when a new version ships",
            content: `
                <p>When a new version of Listing Studio is released, the app checks for it automatically and shows a banner at the top of the window. Click the banner to install - the update downloads in the background, then the app restarts on the new version.</p>

                <h2>Automatic update flow</h2>
                <ol>
                    <li>App opens and quietly checks GitHub for the latest release (every 6 hours).</li>
                    <li>If a newer version exists, a yellow banner appears at the top: "Update available: v0.X.Y."</li>
                    <li>Click <strong>Install Now</strong>. The download takes about 30 seconds. Files get replaced in-place.</li>
                    <li>The app restarts automatically. Your data (templates, settings, credentials) is preserved.</li>
                </ol>

                <h2>Manual check</h2>
                <p>Settings → scroll down to <strong>Updates</strong> → click <strong>Check Now</strong>. Useful if Justin tells you a new version just shipped and you don't want to wait for the next automatic check.</p>

                <div class="help-callout">
                    <span class="help-callout-label">Note</span>
                    Updates only apply to the installed (packaged) version. If you're running from source code (which doesn't happen on your machine, only on Justin's dev setup), the check still runs but reports "you're running from source, no update needed."
                </div>

                <h2>What changes between versions</h2>
                <p>Each release has a changelog visible on the GitHub Releases page. Major updates may add new features (eBay support, etc.); patches usually fix small bugs. If a release adds new fields to existing data, the app's schema migration runs automatically on next start - no manual cleanup needed.</p>
            `,
        },

        {
            id: "troubleshooting",
            icon: "🔧",
            title: "Troubleshooting",
            subtitle: "Common errors and what to do about them",
            content: `
                <p>Most errors the app shows are written in plain English. If something doesn't make sense, screenshot it and send it to Justin; the log file at <code>%LOCALAPPDATA%\\ListingStudio\\logs\\</code> usually has the full story for him to dig into.</p>

                <h2>Connection errors</h2>

                <div class="help-qa">
                    <div class="help-qa-q">Settings says "Reverb rejected the token"</div>
                    <div class="help-qa-a">The token you pasted didn't match what Reverb has on file. Common causes: extra whitespace in the paste, the token was revoked from Reverb's side, or the token has the wrong scopes. Generate a fresh token and try again, making sure all the scopes listed in the Connect modal are checked.</div>
                </div>

                <div class="help-qa">
                    <div class="help-qa-q">"Reverb not connected" but I just connected it</div>
                    <div class="help-qa-a">The app caches the Reverb taxonomy in memory; if Reverb was connected mid-session the cache may not have picked it up yet. Close and reopen the app - the cache reloads on startup.</div>
                </div>

                <div class="help-qa">
                    <div class="help-qa-q">eBay says "App credentials missing" when searching the taxonomy</div>
                    <div class="help-qa-a">You haven't pasted your eBay client_id and client_secret yet. Settings → eBay card → Connect → fill in all three fields. The seller-account OAuth dance is a separate step that you do AFTER the app credentials validate.</div>
                </div>

                <h2>Posting errors</h2>

                <div class="help-qa">
                    <div class="help-qa-q">"Reverb validation error" with a list of complaints</div>
                    <div class="help-qa-a">Reverb rejected the listing because some field is wrong or missing. Common causes: condition isn't set, the Category doesn't have a Reverb UUID assigned, shipping isn't configured, or the title is too long. The error message lists which specific fields Reverb complained about - fix them on the template and try again.</div>
                </div>

                <div class="help-qa">
                    <div class="help-qa-q">"No Reverb category set" error when posting</div>
                    <div class="help-qa-a">The template's Category doesn't have a Reverb taxonomy UUID assigned yet. Open the Category for editing and pick a Reverb category in the search there. Save, then re-try posting.</div>
                </div>

                <div class="help-qa">
                    <div class="help-qa-q">Photos failed to upload but the draft was created</div>
                    <div class="help-qa-a">The yellow callout will list which photos failed and why. Common causes: the NAS file is missing (someone moved it after picking), the file's corrupted, or ImgBB hit a rate limit. Click "Open Draft + Photos Folder" and drag the missing photos in by hand - the draft is otherwise fine.</div>
                </div>

                <h2>NAS / photo errors</h2>

                <div class="help-qa">
                    <div class="help-qa-q">The NAS picker shows "NAS not reachable"</div>
                    <div class="help-qa-a">The Z: drive isn't mounted right now - usually means the network connection to Dad's NAS dropped or the VPN disconnected. You can still pick photos from your local computer with the "Pick photos from this computer" button. Once the NAS is back online, future picks can use the NAS again.</div>
                </div>

                <div class="help-qa">
                    <div class="help-qa-q">Photos look rotated wrong on Reverb</div>
                    <div class="help-qa-a">Shouldn't happen - the app applies EXIF rotation before uploading. If it does, screenshot the Reverb listing and send to Justin; the photo's EXIF data might be unusual.</div>
                </div>

                <h2>App errors</h2>

                <div class="help-qa">
                    <div class="help-qa-q">"Backend unavailable" on the status bar</div>
                    <div class="help-qa-a">The embedded FastAPI server didn't start or crashed. Usually happens if another copy of Listing Studio is already running on the same port (8731). Check the Windows taskbar / system tray, close any extra instances, and reopen.</div>
                </div>

                <div class="help-qa">
                    <div class="help-qa-q">The window opens to a blank gray screen</div>
                    <div class="help-qa-a">The backend probably crashed during startup. Look in <code>%LOCALAPPDATA%\\ListingStudio\\logs\\</code> for the most recent log file and send it to Justin. If the issue is a corrupted database, deleting <code>%LOCALAPPDATA%\\ListingStudio\\listing_studio.db</code> resets everything (you'd lose templates - back it up first if you have important data).</div>
                </div>

                <h2>Still stuck?</h2>
                <p>Open <strong>History</strong> from the toolbar to see what the app has been doing. If a recent post shows as failed, the error message there usually points to the underlying issue. If all else fails, capture a screenshot of what's happening + the log file and send to Justin.</p>
            `,
        },
    ];

    // ----------------------------------------------------------------------
    // Rendering
    // ----------------------------------------------------------------------

    LS.renderHelp = function () {
        const container = LS.$("help-view");
        container.innerHTML = "";

        // Page-level header that matches Settings/History so the "← Back to
        // Library" button is in the same place across every top-level view.
        // The two-pane help layout lives below this header.
        const pageHeader = LS.el("div", "page-header help-page-header");
        const headerLeft = LS.el("div");
        const h1 = LS.el("h1");
        h1.innerHTML = `User <em>Guide</em>`;
        headerLeft.appendChild(h1);
        headerLeft.appendChild(LS.el("p", null,
            "Plain-English help for everything in Listing Studio. Pick a topic from the sidebar."));
        pageHeader.appendChild(headerLeft);

        const backBtn = LS.el("button", "tool-btn", "← Back to Library");
        backBtn.addEventListener("click", () => LS.showView("library"));
        pageHeader.appendChild(backBtn);
        container.appendChild(pageHeader);

        // Two-pane body wrapper - holds the sidebar + content side by side
        // below the page header.
        const body = LS.el("div", "help-body");

        // Sidebar
        const sidebar = LS.el("aside", "help-sidebar");
        const header = LS.el("div", "help-sidebar-header");
        const title = LS.el("div", "help-sidebar-title", "Help");
        const sub = LS.el("div", "help-sidebar-sub", "User guide & FAQ");
        header.appendChild(title);
        header.appendChild(sub);
        sidebar.appendChild(header);

        const toc = LS.el("ul", "help-toc");
        for (const section of SECTIONS) {
            const item = LS.el("li", "help-toc-item");
            if (section.id === LS.state.helpActiveSection) {
                item.classList.add("active");
            }
            const icon = LS.el("span", "help-toc-icon", section.icon);
            item.appendChild(icon);
            item.appendChild(document.createTextNode(section.title));
            item.addEventListener("click", () => {
                LS.state.helpActiveSection = section.id;
                LS.renderHelp();
            });
            toc.appendChild(item);
        }
        sidebar.appendChild(toc);
        body.appendChild(sidebar);

        // Content pane
        const content = LS.el("div", "help-content");
        const active = SECTIONS.find(s => s.id === LS.state.helpActiveSection) || SECTIONS[0];

        const sectionH1 = LS.el("h1", null, active.title);
        content.appendChild(sectionH1);
        if (active.subtitle) {
            const subtitle = LS.el("div", "help-section-sub", active.subtitle);
            content.appendChild(subtitle);
        }

        // The content is HTML; trust it (it's our own content, not user-supplied)
        const contentBody = LS.el("div");
        contentBody.innerHTML = active.content;
        content.appendChild(contentBody);

        body.appendChild(content);
        container.appendChild(body);
    };
})();

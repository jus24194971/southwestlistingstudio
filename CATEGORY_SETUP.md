# Category setup playbook

This is the tomorrow-morning playbook for getting Dad's listing categories
mapped across **Reverb, eBay, and Squarespace** in one sitting. Print it,
keep it open in a tab, whatever — it walks step-by-step from "fresh app"
to "every Category mapped on every platform."

## Before you start — credentials checklist

You'll need three sets of credentials. Gather them up front so you're not
context-switching mid-setup:

| Platform | What you need | Where to find it |
|---|---|---|
| **Reverb** | Personal access token | reverb.com → My Profile → API & Integrations → Generate new token. Scopes: `public`, `read_listings`, `write_listings`, `read_orders`, `read_profile` |
| **Squarespace** | API key | squarespace.com → site Settings → Advanced → Developer API Keys. Permissions: Products R/W, Inventory R/W, Orders R |
| **eBay** | App credentials: `client_id` + `client_secret` (sometimes labeled "App ID" and "Cert ID" in the developer dashboard) | developer.ebay.com → My Account → Application Keys. Use the **Production** column. |
| **ImgBB** (optional) | API key | imgbb.com → account → API. Already covered in v0.3.0 — see the main README. |

⚠️ **eBay's `client_secret` is shown once at creation time only.** If you've
forgotten it, regenerate from the eBay developer dashboard. The user OAuth
flow (for posting listings) is a separate dance that we'll get to later;
for tonight's category-mapping work, app credentials alone are enough.

## Step 0 — start the app

```powershell
cd C:\Users\jus24\OneDrive\Documents\GitHub\southwestlistingstudio
.\.venv\Scripts\python.exe -m listing_studio
```

On first launch with v0.4.0, the database picks up two new tables
(`category_mappings`, `category_usage`) and the seed JSON loads — but with
**null eBay IDs as placeholders** until we verify them in Step 4.

## Step 1 — connect all three platforms

Settings → Auto-posting platforms → Connect each:

1. **Reverb** → paste the token → click Test & Save → expect a green "✓
   Connected to <Dad's shop name>"
2. **Squarespace** → paste the API key → expect "✓ Connected to <site
   title>"
3. **eBay** (new in v0.4.0) → modal asks for `client_id` and `client_secret`
   → expect "✓ Connected to eBay (app-only)"

If any platform fails the test, the error message is plain English — paste
it back to Claude Code and we'll fix.

## Step 2 — verify taxonomy search works on each platform

Before mapping categories, confirm each platform's taxonomy is searchable:

1. Click **+ New Category** in the library sidebar to open the editor
2. In the Reverb section, type "tuner" — you should see a list of matching
   results within 1-2 seconds. If you see "Reverb not connected", revisit
   Step 1.
3. In the eBay section, type "tuner" — same thing, but with eBay's full
   breadcrumb path visible under each match. **Watch for the red "non-leaf"
   tag** on mid-tree results; we can only list on leaves.
4. In the Squarespace section, the dropdown should be populated with your
   store pages (if you have any products yet). If empty, that's fine —
   Squarespace's API only knows about pages with products on them. You can
   still type the page ID manually once you have one.

Close the editor without saving.

## Step 3 — first category: the suggestion-engine smoke test

Pick a simple Dad category to start. **Tuning Heads** is a good first one:

1. **+ New Category** → name it "Tuning Heads"
2. In the Reverb section, search "tuning heads" → pick the leaf result
   (Set Primary)
3. Watch the **eBay section** below. A green callout should appear:
   "Suggested eBay match: Tuning Pegs (<id>)" with a "Use this" button.

   - If the callout appears with a real eBay ID → the shipped seed worked,
     click Use this and you're done.
   - If the callout appears with the marker "Fuzzy match" → the seed JSON
     didn't have a verified ID for this pair yet (expected for v0.4.0). The
     fuzzy fallback used the Reverb category name to search eBay's tree
     and pick the closest leaf. Verify it's right, then click Use this. The
     pairing gets recorded — next category that picks this Reverb leaf
     will get the eBay match as a learned mapping (not fuzzy).
4. Squarespace: pick the matching store page from the dropdown (or "(no
   page assigned)" if Squarespace isn't ready yet).
5. **Save**.

## Step 4 — verify all 18 seed mappings against live eBay taxonomy

Open [listing_studio/data/seed_category_mappings.json](listing_studio/data/seed_category_mappings.json).
Each entry has an `ebay_id: null` placeholder. For each one, find the
verified eBay leaf ID by searching the taxonomy in the category editor and
note it down. Common Southwest Acoustics categories to verify:

| Category | Expected Reverb path | Expected eBay path |
|---|---|---|
| Tuning Heads / Tuning Pegs | Parts > Guitar Parts > Tuning Heads | MI&G > Guitars & Basses > Parts & Accessories > Tuning Pegs |
| Pickups | Parts > Guitar Parts > Pickups | MI&G > Guitars & Basses > Parts & Accessories > Pickups |
| Bridges | Parts > Guitar Parts > Bridges | MI&G > Guitars & Basses > Parts & Accessories > Bridges & Saddles |
| Necks | Parts > Guitar Parts > Necks | MI&G > Guitars & Basses > Parts & Accessories > Necks |
| Bodies | Parts > Guitar Parts > Bodies | MI&G > Guitars & Basses > Parts & Accessories > Bodies |
| Strings | Accessories > Strings | MI&G > Guitars & Basses > Parts & Accessories > Strings |
| Knobs | Parts > Guitar Parts > Knobs | MI&G > Guitars & Basses > Parts & Accessories > Knobs, Jacks, Switches |
| Pickguards | Parts > Guitar Parts > Pickguards | MI&G > Guitars & Basses > Parts & Accessories > Pickguards |
| Cases & Gig Bags | Accessories > Cases & Gig Bags | MI&G > Guitars & Basses > Parts & Accessories > Cases & Gig Bags |
| Straps | Accessories > Straps | MI&G > Guitars & Basses > Parts & Accessories > Straps |
| Acoustic Guitars | Acoustic Guitars | MI&G > Guitars & Basses > Acoustic Guitars |
| Electric Guitars | Electric Guitars | MI&G > Guitars & Basses > Electric Guitars |
| Bass Guitars | Bass Guitars | MI&G > Guitars & Basses > Bass Guitars |
| Effects Pedals | Effects and Pedals | MI&G > Guitars & Basses > Effects Pedals |
| Amp Tubes | Parts > Amp Parts > Tubes | (verify - eBay's tube category may be in Vintage section) |
| Picks | Accessories > Picks | MI&G > Guitars & Basses > Parts & Accessories > Picks |
| Capos | Accessories > Capos | MI&G > Guitars & Basses > Parts & Accessories > Capos |

Once you have the real IDs, paste them into Claude Code and we'll do a
one-shot pass to update the seed JSON + reload it.

## Step 5 — create the remaining Dad categories

For each category Dad sells, repeat Step 3. Watch the suggestion engine
get smarter as you go:

- First Tuners category: fuzzy match suggests an eBay leaf (you verify).
- Second tuner-adjacent category: shipped seed (or now-learned mapping)
  suggests an eBay leaf at full confidence.
- Third onwards: instant suggestions on every save.

The **Recent** pills above each search will populate with your last 6
picks per platform, making subsequent setups even faster.

## Step 6 — verify with a test listing

Once 3-5 categories are set up:

1. Library → pick a template that uses one of the mapped categories
2. Attach a photo (NAS or local picker)
3. Click "Post Reverb Draft" → the listing should be created with
   photos uploaded via ImgBB → confirm by opening the draft on Reverb
4. (eBay and Squarespace listing flows are not yet wired — that's the
   next milestone. Tomorrow's goal is correct category mapping; actual
   cross-posting comes after.)

## Troubleshooting

- **"eBay rejected the app credentials"** → re-paste the client_secret;
  it's case-sensitive and easily corrupted by clipboard managers
- **"Squarespace returned no store pages"** → expected if the store has no
  products yet, or if Dad created products under "drafts" rather than
  published pages. Type the page ID manually until products exist.
- **"Reverb not connected" inside the category editor even though the
  Settings page says connected** → restart the app. The taxonomy cache is
  per-process; if Reverb was connected mid-session there's a brief race.
- **Suggestion callout never appears** → check that the source platform's
  category is actually saved on the Category (not just hovering in the
  search results). Suggestions key off the saved selection.

## After tomorrow's session

When categories are mapped, the next milestone is **eBay listing creation**
(Inventory item → Offer → Publish), then **Squarespace product creation
with the right store page**. Both build on the foundation we'll have
verified during the session.

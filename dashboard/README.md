# Dino Slayer dashboard

Single file: `index.html`. No build step, no framework. MapLibre GL JS from CDN.

## Run it

Serve from the **repo root** (the page reads `../dataset/web/`, and browsers block
`file://` fetch):

```
python -m http.server
```

Then open <http://localhost:8000/dashboard/>.

## Data it reads

| File | What |
|---|---|
| `../dataset/web/dipi.geojson` | 1,448 settlement points + attributes |
| `../dataset/web/sabah_districts.geojson` | 25 GADM district polygons (`NAME_2`) |
| `../dataset/web/sabah_divisions.geojson` | 5 official divisions, pre-dissolved |

`sabah_divisions.geojson` is generated once, offline, by unioning the district
polygons per division. Regenerate it only if the district file changes.

Nothing in the page modifies, imputes or invents a data value.

## Optional: Google imagery (off by default, cannot bill you by accident)

Street View + Places photos in the drill-down's Local Context section. **Nothing
is requested unless you deliberately switch it on**, and the key never enters
this repo.

**Turn it on**

1. Google Cloud console → enable **Street View Static API** and **Places API (New)**
2. Create a **browser key**, restrict it by HTTP referrer to `localhost:8000/*`
   (and your demo host), and restrict it to only those two APIs
3. Set a billing budget alert — belt and braces
4. Open <http://localhost:8000/dashboard/?setup=1>, paste the key, Save
5. A **"Google imagery"** toggle now appears in the sidebar under LAYERS. It
   starts **OFF**. Turn it on when you want it.

**Turn it off:** flick the same toggle, or hit `?setup=1` → Clear key.

**What stops it costing money**

| Guard | Effect |
|---|---|
| Key lives in `localStorage` | Never committed, never in page source, cannot leak via git |
| Toggle defaults OFF even with a key | A saved key alone bills nothing |
| Lazy per settlement | Fires only when a drill-down panel opens, for that one point — never for all 1,448, never at boot |
| Per-settlement cache | Re-opening the same settlement costs nothing |
| Hard session cap | 50 calls, then it refuses and says so. Reload resets |
| Free metadata pre-check | Street View metadata is free; the billable image is only requested where imagery actually exists |
| Live counter | The sidebar shows billable calls used and remaining |

Every Google result carries *"Context only — not scoring evidence. Absence of
imagery is not evidence that a place lacks facilities."* Google content is never
used as DIPI evidence.

## Optional: the simulator's video clip

The Experience Simulator ships with a **CSS mock player** that needs no asset —
it stalls and spins according to the computed buffering maths.

To use a real clip instead, do **both** steps:

1. Put the file at exactly `dashboard/media/sample_clip.mp4`
2. In `index.html`, change `let CLIP_URL = null;` to
   `let CLIP_URL = "media/sample_clip.mp4";`

Step 2 is a deliberate manual switch rather than an automatic probe: probing for
a file that is not there logs a 404 console error, and the acceptance checklist
requires a clean console. The same computed pauses drive the real clip once it
is enabled — nothing else changes.

| Requirement | Value |
|---|---|
| Path / name | `dashboard/media/sample_clip.mp4` (exact — nothing else is looked for) |
| Container / codec | MP4, H.264 video, AAC or no audio |
| Length | **≤ 10 seconds** (the player models exactly 10 s of content) |
| Resolution | 1280×720 or smaller, 16:9 |
| Size | keep under ~2 MB so first load stays under 3 s |
| Licence | royalty-free, bundled locally |

It is muted and never embedded from an external host — no YouTube, no iframe.
The overlay label *"Simulated preview — visualisation of estimated experience,
not a live network test."* stays on screen whether the clip is real or mocked.

If the file is absent the page logs nothing and shows the mock. That is the
supported default, not a failure state.

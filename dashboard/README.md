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
| `../dataset/web/facilities.geojson` | 606 OSM schools and health points |

Terrain is derived at load from the `elevation_m` already in `dipi.geojson`: distance to
the nearest of the 59 OSM towns, the metres of drop to it, and elevation percentile within
the district. The agent and `export_training_table.py` compute the same three values with
the same haversine and the same rounding, and all three were checked to agree on all 1,448
settlements. Terrain is context and never enters DIPI.

The optional **Terrain relief** layer streams NASA SRTM hillshade tiles from AWS Terrain
Tiles. It is off by default and requests nothing until switched on, so the opening reveal
never waits on a third-party host.

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
3. Set a billing budget alert, belt and braces
4. Open <http://localhost:8000/dashboard/?setup=1>, paste the key, Save
5. A **"Google imagery"** toggle now appears in the sidebar under LAYERS. It
   starts **OFF**. Turn it on when you want it.

**Turn it off:** flick the same toggle, or hit `?setup=1` → Clear key.

**What stops it costing money**

| Guard | Effect |
|---|---|
| Key lives in `localStorage` | Never committed, never in page source, cannot leak via git |
| Toggle defaults OFF even with a key | A saved key alone bills nothing |
| Lazy per settlement | Fires only when a drill-down panel opens, for that one point, never for all 1,448, never at boot |
| Per-settlement cache | Re-opening the same settlement costs nothing |
| Hard session cap | 50 calls, then it refuses and says so. Reload resets |
| Free metadata pre-check | Street View metadata is free; the billable image is only requested where imagery actually exists |
| Live counter | The sidebar shows billable calls used and remaining |

Every Google result carries *"Context only, not scoring evidence. Absence of
imagery is not evidence that a place lacks facilities."* Google content is never
used as DIPI evidence.

## The simulator's video clips

Five clips ship with the page, one per quality tier, in
`public/videostimulation/`. Selecting a tier plays the real thing, so a judge
sees the difference between 360p and 4K rather than only the stalling.

| Tier | File | Resolution | Size |
|---|---|---|---|
| 360p | `video360p.mp4` | 640×360 | 0.54 MB |
| 480p | `video480p.mp4` | 854×480 | 2.80 MB |
| 720p | `video720p.mp4` | 1280×720 | 7.83 MB |
| 1080p | `video1080p.mp4` | 1920×1080 | 16.79 MB |
| 4K | `video4k.mp4` | 3840×2160 | 27.25 MB |

All five are H.264 with AAC audio. `video360p.mp4` is re-encoded from the 480p
source rather than shot separately.

**Nothing is fetched until a tier is actually selected.** Every clip carries
`preload="none"`, because 55 MB at boot would blow the three second opening
reveal. Opening a settlement plays 720p by default.

**Sound starts muted, deliberately.** Chrome blocks autoplay with audio until
the user has interacted with the page, and a blocked video freezes on frame one,
which reads as a broken simulation. Muted first means it always plays. The
speaker button in the top right corner unmutes, and that preference then sticks
across tier switches and settlements. Closing the panel pauses and rewinds the
clip, so nothing keeps playing behind a panel you have dismissed.

The same computed pauses drive the real clips: below 1.0× the link speed, each
2 s of video takes 2/ratio seconds to arrive, and the player stalls for the
difference. The caption *"Simulated preview, visualisation of estimated
experience, not a live network test."* sits under the player and never
disappears. Nothing is embedded from an external host, no YouTube, no iframe.

To swap a clip, replace the file at the same path. Keep it at or under 10
seconds, the player models exactly 10 s of content.

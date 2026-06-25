#!/usr/bin/env python3
"""d3_geo_plot_demo.py — minimal, readable example of building a Geoplot figure.

It shows the whole public surface of d3_geo_plot_embed:

  * path_layer()    — a line trajectory with per-point tooltip data
  * polygon_layer() — a filled region
  * embed()         — bake layers into the HTML template (online build)
  * download_offline_assets() + embed(offline=...) — a self-contained build

(For tabular input there is also layer_from_dataframe(df, ...), and online
figures can verify the CDN basemap via the ATLAS_SRI block in the template —
see d3_geo_plot_assets/README.md. Neither is needed here.)

Usage:
    python d3_geo_plot_demo.py                            # ./d3_geo_plot.html -> ./d3_geo_plot_demo.html
    python d3_geo_plot_demo.py d3_geo_plot.html out.html  # explicit template / output

Standard library only. Writes an online figure always, and an offline,
fully self-contained figure when the offline assets are available.
"""
import math
import os
import sys

# Import the sibling helper regardless of the current working directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from d3_geo_plot_embed import (path_layer, polygon_layer, embed,
                               download_offline_assets, ASSET_DIR_DEFAULT)

# A handful of airports (lon, lat) and routes between them. The routes include a
# few antimeridian and near-polar crossings to exercise the projection.
AIRPORTS = {
    "New York":      (-73.78,  40.64),
    "London":        ( -0.46,  51.47),
    "San Francisco": (-122.38, 37.62),
    "Tokyo":         (139.78,  35.55),
    "Sydney":        (151.18, -33.95),
    "Singapore":     (103.99,   1.36),
    "Sao Paulo":     (-46.47, -23.43),
    "Johannesburg":  ( 28.23, -26.13),
    "Los Angeles":   (-118.41, 33.94),
    "Dubai":         ( 55.36,  25.25),
    "Paris":         (  2.55,  49.01),
    "Santiago":      (-70.79, -33.39),
    "Auckland":      (174.79, -37.01),
}
ROUTES = [
    ("New York",      "London"),
    ("San Francisco", "Tokyo"),
    ("Sydney",        "Singapore"),
    ("Sao Paulo",     "Johannesburg"),
    ("Los Angeles",   "Sydney"),      # crosses the antimeridian
    ("Dubai",         "New York"),
    ("Tokyo",         "Paris"),        # near-polar
    ("Santiago",      "Auckland"),     # crosses the antimeridian
]

# Cycled per-trajectory styling.
PALETTE = ["#c1572e", "#2f6f8f", "#5a8f4e", "#8a5fa3", "#b08a2e", "#3d7a7a"]
STYLES  = ("solid", "dash", "dot", "long-dash", "long-dash-dot")


def great_circle(lon1, lat1, lon2, lat2, n=64):
    """Sample the great-circle path between two points (slerp on the sphere).
    Returns n+1 [lon, lat] pairs."""
    f1, l1, f2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    d = 2 * math.asin(math.sqrt(
        math.sin((f2 - f1) / 2) ** 2 +
        math.cos(f1) * math.cos(f2) * math.sin((l2 - l1) / 2) ** 2))
    if d == 0:
        return [[lon1, lat1], [lon2, lat2]]
    pts = []
    for i in range(n + 1):
        f = i / n
        a, b = math.sin((1 - f) * d) / math.sin(d), math.sin(f * d) / math.sin(d)
        x = a * math.cos(f1) * math.cos(l1) + b * math.cos(f2) * math.cos(l2)
        y = a * math.cos(f1) * math.sin(l1) + b * math.cos(f2) * math.sin(l2)
        z = a * math.sin(f1) + b * math.sin(f2)
        pts.append([round(math.degrees(math.atan2(y, x)), 4),
                    round(math.degrees(math.atan2(z, math.hypot(x, y))), 4)])
    return pts


def build_layers():
    """Build the demo's trajectory + polygon layers."""
    layers = []
    for i, (origin, dest) in enumerate(ROUTES):
        coords = great_circle(*AIRPORTS[origin], *AIRPORTS[dest])
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        # Any extra keyword becomes a per-point field shown in the hover tooltip.
        progress_pct = [round(j / (len(coords) - 1) * 100) for j in range(len(coords))]
        layers.append(path_layer(
            lons, lats,
            name=f"{origin} \u2192 {dest}",
            color=PALETTE[i % len(PALETTE)],
            width=1.6,
            line_style=STYLES[i % len(STYLES)],
            progress_pct=progress_pct,
        ))

    # A filled region: polygon_layer takes a fill opacity and a winding direction
    # (ccw here) so d3-geo fills the enclosed area rather than the rest of the globe.
    ring = [(-45, 40), (-15, 45), (-10, 60), (-50, 58)]
    layers.append(polygon_layer(
        [p[0] for p in ring], [p[1] for p in ring],
        name="N. Atlantic watch area",
        color="#37506b", width=1.2, fill_opacity=0.15, winding="ccw",
    ))
    return layers


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    template = sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "d3_geo_plot.html")
    out      = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, "d3_geo_plot_demo.html")

    layers = build_layers()
    config = {"type": "equirectangular", "showLegend": True}

    # 1) Online figure — small file; fetches d3/topojson/atlas from a CDN on open.
    embed(template, layers, out, config=config)
    print(f"online  -> {out}  ({len(layers)} layers)")

    # 2) Offline figure — fully self-contained (opens with no network). Populate
    #    the assets folder once (needs internet); thereafter it embeds from disk.
    assets_dir  = os.path.join(here, ASSET_DIR_DEFAULT)
    offline_out = os.path.join(here, "d3_geo_plot_demo_offline.html")
    try:
        download_offline_assets(assets_dir)   # no-op once the four files are present
        embed(template, layers, offline_out, config=config, offline=assets_dir)
        print(f"offline -> {offline_out}  (self-contained)")
    except Exception as e:                     # offline with assets not yet downloaded
        print(f"offline -> skipped ({e.__class__.__name__}: {e})")
        print("           populate the assets once with internet:")
        print(f"           python -c \"import d3_geo_plot_embed as c; "
              f"c.download_offline_assets('{ASSET_DIR_DEFAULT}')\"")


if __name__ == "__main__":
    main()

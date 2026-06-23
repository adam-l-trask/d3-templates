"""cartoplot_embed.py — embed trajectory layers into a Cartoplot HTML file.

The Cartoplot HTML has an empty data block:

    <script type="application/json" id="cartoplot-data"></script>

This helper writes JSON into that block, producing a self-contained HTML figure.
You never hand-write the JSON — pass arrays or a DataFrame and it builds the spec.

Quick start
-----------
    from cartoplot_embed import path_layer, embed

    layers = [
        path_layer(lons, lats, name="Flight 123",
                   color="#c1572e", width=1.6,
                   time=timestamps, altitude=altitudes),  # extra fields -> tooltips
    ]
    embed("cartoplot.html", layers, "cartoplot_flight.html")

From a pandas DataFrame
-----------------------
    from cartoplot_embed import layer_from_dataframe, embed
    layer = layer_from_dataframe(df, lon="lon", lat="lat", name="Track A")
    embed("cartoplot.html", [layer], "out.html")

Schema (scoped to trajectory layers; wrapped in an object so config can be
added later without breaking existing files):

    { "layers": [
        { "type": "path",                      # "path" (line) or "polygon" (filled)
          "name": "Flight 123",
          "coordinates": [[lon, lat], ...],    # NOTE: [lon, lat] order
          "winding": "ccw",                    # polygons only: "ccw" (default) |
                                               # "cw" — declares your vertex order
                                               # so d3 fills the enclosed region
          "style": {"color": "#c1572e", "width": 1.6, "opacity": 1,
                    "markers": false, "fillOpacity": 0.25,
                    "dash": "dash"},   # solid|dash|dot|long-dash|long-dash-dot
          "data": {"time": [...], "altitude": [...]} }   # columnar, parallel to coords
    ] }
"""
import json
import os
import re
import urllib.request


_LINE_STYLES = ("solid", "dash", "dot", "long-dash", "long-dash-dot")


def path_layer(lons, lats, name=None, color=None, width=None, opacity=None,
               markers=False, line_style="solid", polygon=False, **point_fields):
    """Build one layer from parallel lon/lat sequences.

    Any extra keyword arrays (e.g. time=..., altitude=..., speed=...) are stored
    per-point and shown in the hover tooltip. They must match the point count.

    `line_style` is one of "solid" (default), "dash", "dot", "long-dash" or
    "long-dash-dot"; the dash pattern scales with the line width.
    """
    if line_style not in _LINE_STYLES:
        raise ValueError(f"line_style must be one of {_LINE_STYLES}")
    lons = [float(x) for x in lons]
    lats = [float(y) for y in lats]
    if len(lons) != len(lats):
        raise ValueError("lons and lats must be the same length")

    layer = {
        "type": "polygon" if polygon else "path",
        "coordinates": [[x, y] for x, y in zip(lons, lats)],
    }
    if name is not None:
        layer["name"] = name

    style = {}
    if color is not None:   style["color"] = color
    if width is not None:   style["width"] = width
    if opacity is not None: style["opacity"] = opacity
    if markers:             style["markers"] = True
    if line_style != "solid": style["dash"] = line_style
    if style:
        layer["style"] = style

    if point_fields:
        data = {}
        for key, values in point_fields.items():
            values = list(values)
            if len(values) != len(lons):
                raise ValueError(f"point field '{key}' has {len(values)} values, "
                                 f"expected {len(lons)}")
            data[key] = values
        layer["data"] = data

    return layer


def polygon_layer(lons, lats, name=None, color=None, width=None, opacity=None,
                  fill_opacity=None, markers=False, line_style="solid",
                  winding="ccw", **point_fields):
    """Build a filled polygon layer from a ring of lon/lat vertices.

    Like path_layer, but the layer is type "polygon" and its interior is filled.
    `fill_opacity` (0..1) controls the fill alpha. Extra keyword arrays become
    per-vertex tooltip data.

    `winding` ("ccw" default, or "cw") declares the order of your vertices.
    Cartoplot orients the ring for d3-geo accordingly so the region your ring
    *encloses* is the one that fills — a "cw" ring is used as-is, a "ccw" ring is
    reversed internally. Declare the winding your vertices are actually in; "ccw"
    is the default because that matches standard GeoJSON exterior rings. (If you
    ever want the complementary region filled instead — e.g. an area larger than
    a hemisphere — declare the opposite of your true winding.)
    """
    if winding not in ("cw", "ccw"):
        raise ValueError("winding must be 'cw' or 'ccw'")
    layer = path_layer(lons, lats, name=name, color=color, width=width,
                       opacity=opacity, markers=markers, line_style=line_style,
                       polygon=True, **point_fields)
    layer["winding"] = winding
    if fill_opacity is not None:
        layer.setdefault("style", {})["fillOpacity"] = fill_opacity
    return layer


def layer_from_dataframe(df, lon="lon", lat="lat", name=None, color=None,
                         width=None, line_style="solid", extra=None, polygon=False):
    """Build a layer from a pandas DataFrame.

    Every column other than the lon/lat columns becomes per-point tooltip data,
    unless `extra` is given to restrict which columns to include.
    """
    cols = extra if extra is not None else [c for c in df.columns if c not in (lon, lat)]
    return path_layer(df[lon], df[lat], name=name, color=color, width=width,
                      line_style=line_style, polygon=polygon, **{c: df[c] for c in cols})


_BLOCK = re.compile(
    r'(<script type="application/json" id="cartoplot-data">)(.*?)(</script>)', re.S)

# ---------------------------------------------------------------------------
# Offline support
#
# Online, the template loads d3 + topojson from a CDN and fetches the world-atlas
# vectors at runtime. For an offline (fully self-contained) figure we inline the
# two libraries and embed the atlas TopoJSON straight into the HTML, so the file
# opens with no network at all. The assets live in a folder you populate once
# (download_offline_assets, which needs internet) or fill in by hand.
# ---------------------------------------------------------------------------
ASSET_DIR_DEFAULT = "cartoplot_assets"

# logical name -> (local filename, CDN url). The JS versions must match the
# template's CDN <script> tags so the offline build behaves identically.
OFFLINE_ASSETS = {
    "d3":         ("d3.min.js",         "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"),
    "topojson":   ("topojson.min.js",   "https://cdnjs.cloudflare.com/ajax/libs/topojson/3.0.2/topojson.min.js"),
    "atlas-110m": ("countries-110m.json","https://cdn.jsdelivr.net/npm/world-atlas@2/countries-110m.json"),
    "atlas-50m":  ("countries-50m.json", "https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json"),
}

_LIBS_BLOCK = re.compile(r"<!-- cartoplot:libs.*?-->.*?<!-- /cartoplot:libs -->", re.S)


def download_offline_assets(dest_dir=ASSET_DIR_DEFAULT, overwrite=False):
    """Download the four offline assets (d3, topojson, both atlas resolutions)
    into `dest_dir`, creating it if needed. Run this ONCE on a machine with
    internet; afterwards `embed(..., offline=True)` works with no network.

    Returns the directory. Set overwrite=True to re-fetch existing files.
    """
    os.makedirs(dest_dir, exist_ok=True)
    for _name, (fn, url) in OFFLINE_ASSETS.items():
        dest = os.path.join(dest_dir, fn)
        if os.path.exists(dest) and not overwrite:
            continue
        req = urllib.request.Request(url, headers={"User-Agent": "cartoplot-offline/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        with open(dest, "wb") as f:
            f.write(data)
    return dest_dir


def _read_asset(assets_dir, filename):
    path = os.path.join(assets_dir, filename)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Offline asset missing: {path}\n"
            f"Run download_offline_assets({assets_dir!r}) on a machine with internet, "
            f"or place the file there yourself (see OFFLINE_ASSETS for the source URL).")
    with open(path, encoding="utf-8") as f:
        return f.read()


def _inline_libraries(html, assets_dir):
    """Replace the CDN <script src> block with inline <script> bundles."""
    d3_js = _read_asset(assets_dir, OFFLINE_ASSETS["d3"][0])
    topo_js = _read_asset(assets_dir, OFFLINE_ASSETS["topojson"][0])
    # A literal </script> inside library text would close the tag early; neutralise it.
    esc = lambda js: js.replace("</script>", r"<\/script>")
    inline = ("<!-- cartoplot:libs (inlined for offline use) -->\n"
              "<script>" + esc(d3_js) + "</script>\n"
              "<script>" + esc(topo_js) + "</script>\n"
              "<!-- /cartoplot:libs -->")
    if not _LIBS_BLOCK.search(html):
        raise ValueError("libs marker block not found — template too old for offline embedding.")
    return _LIBS_BLOCK.sub(lambda m: inline, html, count=1)


def _embed_atlas(html, assets_dir):
    """Fill the per-resolution atlas <script type=application/json> blocks."""
    for res in ("110m", "50m"):
        raw = _read_asset(assets_dir, OFFLINE_ASSETS[f"atlas-{res}"][0])
        # '<' can only appear inside JSON string values here; escaping keeps the
        # JSON valid (JSON.parse turns \u003c back into '<') and tag-safe.
        payload = raw.replace("<", r"\u003c")
        blk = re.compile(
            r'(<script type="application/json" id="cartoplot-atlas-' + res + r'">)(.*?)(</script>)', re.S)
        if not blk.search(html):
            raise ValueError(f"atlas block for {res} not found — template too old for offline embedding.")
        html = blk.sub(lambda m: m.group(1) + payload + m.group(3), html, count=1)
    return html


def embed(template_path, layers, out_path=None, config=None,
          offline=False, assets_dir=ASSET_DIR_DEFAULT):
    """Inject `layers` into the Cartoplot template and write `out_path`.

    If out_path is omitted, the template is overwritten in place.

    `config` (optional dict) sets the figure's opening state — any of:
    type, res, rotate, bounds, showBorders, showGraticule, graticuleStep,
    plotAspect, plotSize, color, showLegend, theme ("light"|"dark"). Only the
    keys you pass are applied; everything else falls back to the figure's
    defaults. Passing theme="dark" without an explicit `color` also switches the
    basemap to the dark palette (trajectory colours are never changed).

    `offline` makes the output fully self-contained (no network at view time) by
    inlining d3 + topojson and embedding the world-atlas vectors. Pass True to
    use `assets_dir` (default "cartoplot_assets"), or pass a path string to use a
    specific folder. Populate that folder once with download_offline_assets().
    """
    with open(template_path, encoding="utf-8") as f:
        html = f.read()
    if not _BLOCK.search(html):
        raise ValueError("Could not find the <script id=\"cartoplot-data\"> block "
                         "in the template — is this a Cartoplot HTML file?")
    spec = {"layers": list(layers)}
    if config:
        spec["config"] = config
    # Compact JSON; escape '<' so an embedded string can never close the tag.
    payload = json.dumps(spec, separators=(",", ":")).replace("<", r"\u003c")
    html = _BLOCK.sub(lambda m: m.group(1) + payload + m.group(3), html, count=1)

    if offline:
        adir = offline if isinstance(offline, str) else assets_dir
        html = _inline_libraries(html, adir)
        html = _embed_atlas(html, adir)

    out_path = out_path or template_path
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


if __name__ == "__main__":
    # Tiny demo: a great-circle-ish flight path NYC -> London with altitude.
    import math
    lons, lats, alt, t = [], [], [], []
    for k in range(25):
        f = k / 24
        lons.append(-73.8 + (-0.1 - (-73.8)) * f)
        lats.append(40.6 + (51.5 - 40.6) * f + 6 * math.sin(math.pi * f))  # arc-ish
        alt.append(round(11000 * math.sin(math.pi * f)))
        t.append(f"T+{int(f*7*60)}min")
    demo = path_layer(lons, lats, name="NYC -> LHR", color="#c1572e", width=1.8,
                      time=t, altitude=alt)
    embed("cartoplot.html", [demo], "cartoplot_demo.html")
    print("wrote cartoplot_demo.html")

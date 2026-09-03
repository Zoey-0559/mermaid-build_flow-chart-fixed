#!/usr/bin/env python3
"""build_flow.py — one-shot Flow Chart Style flowchart builder.

Take a PLAIN Mermaid ``flowchart``, attach the Flow Chart house style
automatically (init directive + node classes + auto-numbered ``linkStyle`` +
tinted group frames), validate it, and render SVG (and optionally PNG).

You write a normal flowchart and, optionally, drop lightweight hints:

    flowchart TD
      A["開始"]                        %% @pillGray
      B["接收並解析輸入"]
      C{"資訊是否充足？"}
      A --> B
      B --> C
      C -->|"充足"| D["依規劃執行"]      %% @success
      C -->|"不足"| A                   %% @danger
      subgraph g1["分析階段"]           %% @group blue
        B
        C
      end

Hints (every one optional — sensible defaults are inferred):
  node line   ``%% @pillGray|pillOrange|cardDefault|cardSegmented|decision``
              (or write ``:::class`` yourself, or leave it blank)
  edge line   ``%% @default|success|info|danger|muted``
  subgraph    ``%% @group blue|yellow``

Inference when a node has no hint and no ``:::class``:
  * ``{...}`` shape          -> decision
  * ``([...])`` pill, no outgoing edge -> pillOrange, else pillGray
  * no incoming edge         -> pillGray   (start)
  * no outgoing edge         -> pillOrange (result)
  * otherwise                -> cardDefault

``linkStyle`` indices are assigned from edge order in the file, so you never
count them by hand. Re-running on an already-built file is safe: the generated
block is stripped and rebuilt.

Usage:
  build_flow.py INPUT.mmd [-o OUT.svg] [--png] [--stdout] [--check]
                [--styled OUT.styled.mmd] [--config flow-chart.mermaid.json]
                [--no-validate]

Only the Python 3 standard library is required. Rendering prefers ``mmdc``
(https://github.com/mermaid-js/mermaid-cli) when it is on PATH — correct fonts,
SVG + PNG — and otherwise falls back to the Kroki web service (needs network;
SVG always, PNG only if a headless Chrome/Chromium is found).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter, OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.environ.get(
    "FLOW_CHART_CONFIG",
    os.path.join(os.environ.get("CLAUDE_PLUGIN_ROOT", HERE), "flow-chart.mermaid.json")
    if os.environ.get("CLAUDE_PLUGIN_ROOT")
    else os.path.join(HERE, "flow-chart.mermaid.json"),
)

GEN_START = "%% >>> flow-chart-style (generated — do not edit below) >>>"
GEN_END = "%% <<< flow-chart-style <<<"

NODE_CLASSES = ("pillGray", "pillOrange", "cardDefault", "cardSegmented", "decision")
ARROW_ORDER = ("default", "success", "info", "danger", "muted")

GROUP_STYLE = {
    "blue": "fill:#EAF4F6,stroke:#79CFDD,stroke-width:2px,color:#003D56",
    "yellow": "fill:#FFF3E0,stroke:#F69800,stroke-width:2px,color:#A34900",
}

# Used verbatim when flow-chart.mermaid.json cannot be read.
FALLBACK_CLASSDEF = {
    "pillGray": "fill:#D9DDE0,stroke:#000000,stroke-width:2px,color:#000000",
    "pillOrange": "fill:#FFEAC7,stroke:#F69800,stroke-width:2px,color:#A34900",
    "cardDefault": "fill:#FFFFFF,stroke:#C0C6CB,stroke-width:2px,color:#000000",
    "cardSegmented": "fill:#FFFFFF,stroke:#C0C6CB,stroke-width:2px,color:#000000",
    "decision": "fill:#D4F3F6,stroke:#144F66,stroke-width:2px,color:#003D56",
}
FALLBACK_ARROW = {
    "default": "stroke:#000000,color:#000000,stroke-width:2px",
    "success": "stroke:#00A513,color:#00A513,stroke-width:2px",
    "info": "stroke:#009DDB,color:#009DDB,stroke-width:2px",
    "danger": "stroke:#FF0033,color:#FF0033,stroke-width:2px",
    "muted": "stroke:#9F9F9F,color:#9F9F9F,stroke-width:2px,stroke-dasharray:8 4",
}
FALLBACK_INIT = (
    '%%{init: {"theme":"base","fontFamily":"roboto, Noto Sans, PingFang TC, '
    'Sans-Serif, Microsoft JhengHei","themeVariables":{"fontFamily":"roboto, '
    'Noto Sans, PingFang TC, Sans-Serif, Microsoft JhengHei","background":'
    '"#F7F7F7","edgeLabelBackground":"#FFFFFF","lineColor":"#000000",'
    '"primaryColor":"#FFFFFF","primaryBorderColor":"#C0C6CB","primaryTextColor":'
    '"#000000"},"themeCSS":".node polygon,.node circle,.node rect,.node path,'
    '.node .outer-path{filter:none} .cluster rect{filter:none}","flowchart":'
    '{"curve":"basis","nodeSpacing":40,"rankSpacing":55,"htmlLabels":false,'
    '"padding":12}}}%%'
)

KROKI = "https://kroki.io/mermaid/"


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
class Style:
    def __init__(self, init, classdef, arrow):
        self.init = init
        self.classdef = classdef
        self.arrow = arrow


def load_style(config_path):
    classdef = dict(FALLBACK_CLASSDEF)
    arrow = dict(FALLBACK_ARROW)
    init = FALLBACK_INIT
    try:
        with open(config_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (OSError, ValueError) as exc:
        print("note: using built-in style (could not read %s: %s)"
              % (config_path, exc), file=sys.stderr)
        return Style(init, classdef, arrow)

    base = {k: v for k, v in cfg.items()
            if not k.startswith("x-") and k not in ("$schema", "//")}
    if base:
        init = "%%{init: " + json.dumps(base, ensure_ascii=False,
                                        separators=(",", ":")) + "}%%"
    x = cfg.get("x-flowChartStyle", {})
    for name, spec in (x.get("nodeClasses") or {}).items():
        if isinstance(spec, dict) and spec.get("classDef"):
            classdef[name] = spec["classDef"]
    for name, spec in (x.get("arrowClasses") or {}).items():
        if isinstance(spec, dict) and spec.get("linkStyle"):
            arrow[name] = spec["linkStyle"]
    return Style(init, classdef, arrow)


# --------------------------------------------------------------------------- #
# parsing helpers
# --------------------------------------------------------------------------- #
# id + opening bracket + inner text + closing bracket.  Longer alternatives
# first so `([` wins over `(`.
NODE_RE = re.compile(
    r"\b([A-Za-z0-9_]+)"
    r"(\(\[|\[\(|\(\(|\{\{|\[|\(|\{)"
    r"(\s*\"[^\"]*\"\s*|\s*'[^']*'\s*|[^\]\)\}]*?)"
    r"(\]\)|\)\]|\)\)|\}\}|\]|\)|\})"
)

ARROW_RE = re.compile(r"(-\.->|-->|==>|---)(?:\|[^|]*\|)?")
_INLINE_LABEL_RE = re.compile(r"--\s+(\"[^\"]*\"|'[^']*'|[^-|>][^|>]*?)\s+-->")
_SHAPE_RE = re.compile(
    r"\s*(?:\(\[|\[\(|\(\(|\{\{|\[|\(|\{)[^\[\](){}]*(?:\]\)|\)\]|\)\)|\}\}|\]|\)|\})"
)


def split_hint(line):
    """(code, hint_words) — strip a trailing ``%% ...`` that sits outside quotes.

    ``hint_words`` is ``['pillGray']`` or ``['group', 'blue']`` when the comment
    is ``%% @word`` / ``%% @word word``; otherwise ``[]``.  The comment (hint or
    not) is always removed from ``code``.
    """
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
            continue
        if ch == "%" and line[i:i + 2] == "%%":
            code = line[:i].rstrip()
            m = re.match(r"@([A-Za-z]+)(?:\s+([A-Za-z]+))?", line[i + 2:].strip())
            words = [w for w in (m.group(1), m.group(2)) if w] if m else []
            return code, words
    return line, []


def normalize_labels(line):
    """`A -- "x" --> B`  ->  `A -->|"x"| B` so one arrow regex covers both."""
    return _INLINE_LABEL_RE.sub(lambda m: "-->|%s|" % m.group(1), line)


def strip_shapes(part):
    prev = None
    while prev != part:
        prev = part
        part = _SHAPE_RE.sub("", part)
    return part


def ids_in(part):
    part = re.sub(r":::[A-Za-z0-9_]+", "", part)   # drop any class operator
    return re.findall(r"[A-Za-z0-9_]+", strip_shapes(part))


# --------------------------------------------------------------------------- #
# strip a previous build / hand-written style so re-runs are idempotent
# --------------------------------------------------------------------------- #
def strip_preamble(text):
    out = []
    skip_init = skip_gen = False
    for ln in text.splitlines():
        if skip_gen:
            if GEN_END in ln:
                skip_gen = False
            continue
        if GEN_START in ln:
            skip_gen = True
            continue
        if skip_init:
            if "}%%" in ln:
                skip_init = False
            continue
        if "%%{init" in ln:
            if "}%%" not in ln:
                skip_init = True
            continue
        s = ln.strip()
        if re.match(r"classDef\s+(?:%s)\b" % "|".join(NODE_CLASSES), s):
            continue
        if re.match(r"linkStyle\s", s):
            continue
        if re.match(r"style\s+\w+\s+fill:#(?:EAF4F6|FFF3E0)", s, re.I):
            continue
        out.append(ln)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def recover_style(raw, style):
    """Read semantics back out of an already-styled diagram so a rebuild keeps
    them even without ``%% @`` hints — handles both this script's own output and
    hand-written Flow Chart diagrams.

    Returns ``(edge_class_by_index, group_colour_by_id)``.
    """
    stroke_to_arrow = {}
    for name, body in style.arrow.items():
        m = re.search(r"stroke:\s*(#[0-9A-Fa-f]{3,8})", body)
        if m:
            stroke_to_arrow.setdefault(m.group(1).upper(), name)
    group_key = {}
    for colour, spec in GROUP_STYLE.items():
        m = re.search(r"stroke:\s*(#[0-9A-Fa-f]{3,8})", spec)
        if m:
            group_key[m.group(1).upper()] = colour

    edges, groups = {}, {}
    for ln in raw.splitlines():
        s = ln.strip()
        m = re.match(r"linkStyle\s+([\d,\s]+?)\s+(\S.*)$", s)
        if m:
            body = m.group(2)
            cm = re.search(r"stroke:\s*(#[0-9A-Fa-f]{3,8})", body)
            cls = stroke_to_arrow.get(cm.group(1).upper()) if cm else None
            if cls in (None, "default") and "dasharray" in body:
                cls = "muted"
            if cls:
                for idx in re.findall(r"\d+", m.group(1)):
                    edges[int(idx)] = cls
            continue
        m = re.match(r"style\s+([A-Za-z0-9_]+)\s+(.*fill:.*)$", s)
        if m:
            up = m.group(2).upper()
            for key, colour in group_key.items():
                if key in up:
                    groups[m.group(1)] = colour
    return edges, groups


# --------------------------------------------------------------------------- #
# the build
# --------------------------------------------------------------------------- #
class BuildResult:
    def __init__(self, text, nodes, edges, groups, missing):
        self.text = text
        self.nodes = nodes
        self.edges = edges
        self.groups = groups
        self.missing = missing


def build(raw, style):
    rec_edges, rec_groups = recover_style(raw, style)
    body_text = strip_preamble(raw)
    lines = body_text.splitlines()

    # -- pass 1: edges, shapes, explicit classes, groups ------------------- #
    edges = []                       # [{'src','dst','cls'}] in file order
    shape = {}                       # id -> 'diamond' | 'pill' | 'card'
    explicit = {}                    # id -> class  (from ::: or @hint)
    groups = OrderedDict()           # subgraph id -> 'blue' | 'yellow'
    subgraph_ids = set()
    for gid, colour in rec_groups.items():   # recovered from `style gX …` lines
        groups[gid] = colour

    for raw_line in lines:
        code, hint = split_hint(raw_line)

        sg = re.match(r"\s*subgraph\s+([A-Za-z0-9_]+)", code)
        if sg:
            subgraph_ids.add(sg.group(1))
            if hint[:1] == ["group"] and hint[1:2] and hint[1] in GROUP_STYLE:
                groups[sg.group(1)] = hint[1]
            continue  # a subgraph title is never a styled node

        for m in NODE_RE.finditer(code):
            nid, op = m.group(1), m.group(2)
            sh = "diamond" if "{" in op else ("pill" if op in ("([", "[(") else "card")
            shape.setdefault(nid, sh)
            after = code[m.end():]
            cm = re.match(r":::([A-Za-z0-9_]+)", after)
            if cm:
                explicit.setdefault(nid, cm.group(1))

        if hint[:1] and hint[0] in NODE_CLASSES:
            first = NODE_RE.search(code)
            if first:
                explicit.setdefault(first.group(1), hint[0])

        norm = normalize_labels(code)
        if ARROW_RE.search(norm):
            cls = hint[0] if (hint[:1] and hint[0] in ARROW_ORDER) else None
            segs = ARROW_RE.sub("\x00", norm).split("\x00")
            for a, b in zip(segs, segs[1:]):
                la, lb = ids_in(a), ids_in(b)
                if la and lb:
                    edges.append({"src": la[-1], "dst": lb[0], "cls": cls})

    for i, e in enumerate(edges):        # inline hint > recovered > default
        if e["cls"] is None:
            e["cls"] = rec_edges.get(i, "default")

    indeg, outdeg = Counter(), Counter()
    for e in edges:
        outdeg[e["src"]] += 1
        indeg[e["dst"]] += 1

    first_src = edges[0]["src"] if edges else None

    all_ids = (set(shape) | set(indeg) | set(outdeg) | set(explicit)) - subgraph_ids
    cls_of = {}
    for nid in all_ids:
        if nid in explicit:
            cls_of[nid] = explicit[nid]
            continue
        if shape.get(nid) == "diamond":
            cls_of[nid] = "decision"
            continue
        inc, out = indeg[nid], outdeg[nid]
        if shape.get(nid) == "pill":
            cls_of[nid] = "pillOrange" if out == 0 else "pillGray"
        elif nid == first_src:
            cls_of[nid] = "pillGray"
        elif inc == 0 and (out > 0 or nid in shape):
            cls_of[nid] = "pillGray"
        elif out == 0 and inc > 0:
            cls_of[nid] = "pillOrange"
        else:
            cls_of[nid] = "cardDefault"

    # -- pass 2: rewrite body, attach :::class once per id ---------------- #
    applied = set()

    def inject(line):
        def repl(m):
            nid = m.group(1)
            end = m.end()
            if line[end:end + 3] == ":::":
                applied.add(nid)
                return m.group(0)
            if nid in applied:
                return m.group(0)
            applied.add(nid)
            c = cls_of.get(nid)
            return m.group(0) + (":::" + c if c else "")
        return NODE_RE.sub(repl, line)

    new_body = []
    for raw_line in lines:
        code, _ = split_hint(raw_line)
        if not code.strip() and raw_line.strip():
            continue  # line was only a hint comment
        if re.match(r"\s*subgraph\b", code):
            new_body.append(code)      # keep the title untouched
        else:
            new_body.append(inject(code))

    # ids that never got a bracket decl but still need a class
    missing = sorted(
        nid for nid in all_ids
        if nid not in applied and cls_of.get(nid)
    )

    # -- assemble -------------------------------------------------------- #
    gen = [GEN_START]
    for name in NODE_CLASSES:
        gen.append("classDef %-13s %s" % (name, style.classdef[name]))
    for gid, colour in groups.items():
        gen.append("style %s %s" % (gid, GROUP_STYLE[colour]))
    for nid in missing:
        gen.append("%s:::%s" % (nid, cls_of[nid]))
    buckets = OrderedDict()
    for i, e in enumerate(edges):
        buckets.setdefault(e["cls"], []).append(i)
    for cls in ARROW_ORDER:
        if cls in buckets:
            gen.append("linkStyle %s %s"
                       % (",".join(str(i) for i in buckets[cls]), style.arrow[cls]))
    gen.append(GEN_END)

    out = "\n".join([style.init, ""] + new_body + ["", ""] + gen) + "\n"
    return BuildResult(out, cls_of, edges, groups, missing)


# --------------------------------------------------------------------------- #
# validate / render
# --------------------------------------------------------------------------- #
_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def kroki(text, fmt, tries=6):
    """POST the diagram to Kroki; return the rendered bytes.

    Prefers the ``curl`` binary (its request signature sails past Kroki's
    Cloudflare edge, which 403s a bare ``urllib`` User-Agent), and falls
    back to ``urllib`` when curl is absent.
    """
    url = KROKI + fmt
    curl = shutil.which("curl")
    last = ""
    for n in range(tries):
        if curl:
            try:
                proc = subprocess.run(
                    [curl, "-sS", "-A", _UA, "--max-time", "60", "-X", "POST",
                     "-H", "Content-Type: text/plain", "--data-binary", "@-",
                     "-w", "\n%{http_code}", url],
                    input=text.encode("utf-8"), capture_output=True, timeout=90)
            except subprocess.TimeoutExpired:
                last = "curl timed out"
                time.sleep(2 + n)
                continue
            out = proc.stdout
            nl = out.rfind(b"\n")
            body, code = (out[:nl], out[nl + 1:].decode().strip()) if nl >= 0 else (out, "")
            if code == "200":
                return body
            last = "HTTP %s: %s" % (code, body[:300].decode("utf-8", "replace"))
            if code.startswith("4") and code != "429":
                raise RuntimeError("Kroki %s" % last)   # 4xx = bad diagram
        else:
            try:
                req = urllib.request.Request(
                    url, data=text.encode("utf-8"),
                    headers={"Content-Type": "text/plain", "User-Agent": _UA},
                    method="POST")
                with urllib.request.urlopen(req, timeout=45) as resp:
                    return resp.read()
            except urllib.error.HTTPError as exc:
                raise RuntimeError("Kroki %s: %s" % (
                    exc.code, exc.read().decode("utf-8", "replace")[:300]))
            except urllib.error.URLError as exc:
                last = str(exc)
        time.sleep(2 + n)
    raise RuntimeError("Kroki request failed after %d tries (%s)" % (tries, last))


def validate(text):
    mmdc = shutil.which("mmdc")
    if mmdc:
        with tempfile.NamedTemporaryFile("w", suffix=".mmd", delete=False,
                                         encoding="utf-8") as tf:
            tf.write(text)
            src = tf.name
        dst = src + ".svg"
        try:
            r = subprocess.run([mmdc, "-i", src, "-o", dst],
                               capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                raise RuntimeError((r.stderr or r.stdout).strip()[:600])
        finally:
            for p in (src, dst):
                try:
                    os.unlink(p)
                except OSError:
                    pass
        return "mmdc"
    kroki(text, "svg")
    return "kroki"


_SHADOW_RE = re.compile(r"filter\s*:\s*drop-shadow\((?:[^()]|\([^()]*\))*\)")


def find_chrome():
    for env in ("PUPPETEER_EXECUTABLE_PATH", "CHROME_PATH", "CHROME"):
        p = os.environ.get(env)
        if p and os.path.exists(p):
            return p
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    for p in ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
              "/Applications/Chromium.app/Contents/MacOS/Chromium"):
        if os.path.exists(p):
            return p
    return None


def rasterize(chrome, svg_path, png_path):
    with open(svg_path, encoding="utf-8") as fh:
        svg = fh.read()
    m = re.search(r'<svg[^>]*?\bwidth="([\d.]+)"[^>]*?\bheight="([\d.]+)"', svg)
    w = int(float(m.group(1))) + 8 if m else 2000
    h = int(float(m.group(2))) + 8 if m else 6000
    html = tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                       encoding="utf-8")
    html.write("<!doctype html><meta charset=utf-8>"
               "<style>*{margin:0}html,body{background:#fff}"
               "svg{display:block}</style>" + svg)
    html.close()
    try:
        subprocess.run([chrome, "--headless", "--disable-gpu", "--hide-scrollbars",
                        "--default-background-color=FFFFFFFF",
                        "--force-device-scale-factor=2",
                        "--window-size=%d,%d" % (w, h),
                        "--screenshot=" + png_path, "file://" + html.name],
                       capture_output=True, text=True, timeout=120)
    finally:
        try:
            os.unlink(html.name)
        except OSError:
            pass
    return os.path.exists(png_path)


def render(text, styled_path, out_svg, want_png, config_path):
    mmdc = shutil.which("mmdc")
    if mmdc:
        cmd = [mmdc, "-i", styled_path, "-o", out_svg, "-b", "#F7F7F7"]
        if os.path.isfile(config_path):
            cmd += ["--configFile", config_path]
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
        print("rendered (mmdc) ->", out_svg)
        if want_png:
            png = os.path.splitext(out_svg)[0] + ".png"
            cmd = [mmdc, "-i", styled_path, "-o", png, "-b", "#F7F7F7", "-w", "2048"]
            if os.path.isfile(config_path):
                cmd += ["--configFile", config_path]
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
            print("rendered (mmdc) ->", png)
        return

    svg = kroki(text, "svg").decode("utf-8")
    svg = _SHADOW_RE.sub("filter:none", svg)          # strip Kroki's shadow bug
    with open(out_svg, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print("rendered (kroki) ->", out_svg)
    if want_png:
        chrome = find_chrome()
        png_ok = False
        if chrome:
            try:
                png_ok = rasterize(chrome, out_svg, os.path.splitext(out_svg)[0] + ".png")
            except subprocess.TimeoutExpired:
                png_ok = False
        if png_ok:
            print("rendered (chrome) ->", os.path.splitext(out_svg)[0] + ".png")
        else:
            print("note: PNG skipped — install @mermaid-js/mermaid-cli (mmdc) "
                  "or a headless Chrome for PNG output.")


# --------------------------------------------------------------------------- #
# cli
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="build_flow.py",
        description="Apply Flow Chart Style to a plain Mermaid flowchart and render it.")
    ap.add_argument("input", help="plain flowchart .mmd (styling hints optional)")
    ap.add_argument("-o", "--out", help="SVG output path (default: <input>.svg)")
    ap.add_argument("--styled", help="styled .mmd output path "
                                     "(default: <input>.styled.mmd)")
    ap.add_argument("--png", action="store_true", help="also write a PNG preview")
    ap.add_argument("--config", default=DEFAULT_CONFIG,
                    help="flow-chart.mermaid.json (default: next to this script)")
    ap.add_argument("--no-validate", action="store_true",
                    help="skip the pre-render validation")
    ap.add_argument("--stdout", action="store_true",
                    help="print the styled .mmd and exit (no files, no render)")
    ap.add_argument("--check", action="store_true",
                    help="build + validate only; write nothing")
    args = ap.parse_args(argv)

    try:
        with open(args.input, encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        ap.error(str(exc))

    style = load_style(args.config)
    result = build(raw, style)

    if args.stdout:
        sys.stdout.write(result.text)
        return 0

    if not args.no_validate:
        try:
            how = validate(result.text)
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            print("VALIDATION FAILED:\n" + str(exc), file=sys.stderr)
            print("(use --no-validate to skip this check)", file=sys.stderr)
            return 1
        print("validated via %s" % how)

    ngrp = (" · groups: "
            + ", ".join("%s=%s" % (k, v) for k, v in result.groups.items())
            ) if result.groups else ""
    cls_count = Counter(result.nodes.values())
    print("nodes: %d (%s) · edges: %d%s"
          % (len(result.nodes),
             ", ".join("%s×%d" % (k, cls_count[k]) for k in NODE_CLASSES if cls_count[k]),
             len(result.edges), ngrp))

    if args.check:
        return 0

    stem = os.path.splitext(args.input)[0]
    styled_path = args.styled or (stem + ".styled.mmd")
    out_svg = args.out or (stem + ".svg")
    with open(styled_path, "w", encoding="utf-8") as fh:
        fh.write(result.text)
    print("styled  ->", styled_path)

    try:
        render(result.text, styled_path, out_svg, args.png, args.config)
    except (RuntimeError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", None) or exc
        print("RENDER FAILED:\n%s" % str(detail).strip()[:600], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

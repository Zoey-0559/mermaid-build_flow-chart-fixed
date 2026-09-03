---
name: flow-chart-style
description: >-
  Build a Mermaid flowchart in the "Flow Chart" house visual style — pill /
  rounded-card / diamond nodes, five semantic arrow colours (default black,
  success green, info blue, danger red, muted grey dashed), tinted group frames
  (blue #79CFDD / yellow #F69800), white edge-label backgrounds, no shadows,
  basis curves. USE THIS SKILL when the user asks for a flowchart "in Flow Chart
  style", references flow-chart.mermaid.json / flow_chart_style, wants the house /
  branded flow-diagram look, or says 套用 Flow Chart 樣式 / 流程圖樣式 /
  流程圖配色 / 用這個樣式畫流程圖. Self-contained: ships build_flow.py (a plain
  flowchart in, a fully-styled + validated + rendered SVG/PNG out — auto node
  classes, auto-numbered linkStyle, auto group frames), a portable Mermaid
  config (mmdc --configFile), a copy-paste style block, and render.sh.
---

# Flow Chart Style

House style for **Mermaid flowcharts**. Give it a plain `flowchart` and it
attaches a fixed visual language (colours, node shapes, arrow semantics, group
frames) for you.

This skill is **self-contained** — it does not depend on any other skill.
Invoke it as `/flow-chart-style` (note: it is *not* the global `/mermaid-skill`;
that is a different, general-purpose diagram skill). It also triggers on
phrases like "Flow Chart style" / "套用 Flow Chart 樣式".

## The fast path — `build_flow.py`

Write a **plain** `flowchart` (no `%%{init}%%`, no `classDef`, no `linkStyle`).
Add optional one-word hints as trailing `%% @…` comments; everything else is
inferred.

```
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
```

```bash
python3 build_flow.py diagram.mmd            # -> diagram.styled.mmd + diagram.svg
python3 build_flow.py diagram.mmd --png      # also a PNG preview
python3 build_flow.py diagram.mmd --stdout   # print styled .mmd only, no render
python3 build_flow.py diagram.mmd --check    # build + validate, write nothing
```

What it does: injects the init directive (from `flow-chart.mermaid.json`, the
single source of truth), assigns a `:::class` to every node, appends the
`classDef` block, **auto-numbers `linkStyle` by edge order**, emits `style gX …`
for tagged subgraphs, validates via `mmdc` or Kroki, then renders — `mmdc` if it
is on `PATH` (correct fonts, SVG + PNG), else Kroki SVG with the shadow-strip
fix. Re-running on an already-built file is safe.

### Hints (all optional)

| Where | Hint | Effect |
| --- | --- | --- |
| node line | `%% @pillGray` `@pillOrange` `@cardDefault` `@cardSegmented` `@decision` | force that node class (or just write `:::class` yourself) |
| edge line | `%% @default` `@success` `@info` `@danger` `@muted` | that arrow class for every edge on the line |
| `subgraph` line | `%% @group blue` / `%% @group yellow` | tinted group frame |

### Inference when a node has no hint and no `:::class`

- `{ … }` shape → `decision`
- `([ … ])` pill with no outgoing edge → `pillOrange`, otherwise `pillGray`
- source of the first edge, or any node with no incoming edge → `pillGray` (start)
- no outgoing edge → `pillOrange` (result)
- otherwise → `cardDefault`

### Still your job

Text wrapping (≤ 20 chars/line, CJK = 1, Latin ≈ 1; insert `<br/>` manually;
break parenthetical notes onto their own line) and choosing `TD` vs `LR` so
labels don't cross nodes. `build_flow.py` does not reflow text or move nodes.

## Manual path (no Python, or fine-tuning the output)

1. Author the `flowchart` normally.
2. Apply the style — pick one:
   - **mmdc:** `mmdc --configFile flow-chart.mermaid.json -i diagram.mmd -o diagram.svg`
     (the `%%{init}%%` header is then optional).
   - **Kroki / mermaid.live:** paste `x-flowChartStyle.initDirective` (one line) as
     the first line of the `.mmd`.
3. Shape every node and add `:::class` (see table below).
4. Paste `x-flowChartStyle.styleBlock` at the **end**, then set `linkStyle`
   **per edge, by appearance order (0-based)**. **Never `linkStyle default`** —
   it forces every arrowhead to one colour. Comma lists are fine: `linkStyle 0,2,3 …`.
5. Group frames: `subgraph gX["標題"] … end`, then `style gX fill:#EAF4F6,stroke:#79CFDD,…`
   (blue) or `style gX fill:#FFF3E0,stroke:#F69800,…` (yellow). Fill lighter than members.
6. Validate:
   `curl -sS -X POST -H 'Content-Type: text/plain' --data-binary @diagram.mmd https://kroki.io/mermaid/svg -o /tmp/_v.svg` → expect HTTP 200.
7. Export: `./render.sh diagram` (Kroki + shadow-strip; PNG when Chrome + Pillow
   are present) or `mmdc --configFile flow-chart.mermaid.json -i diagram.mmd -o diagram.svg`.
   Deliverable is **SVG**; PNG is preview only.

## Node classes

| Class | Shape syntax | `classDef` | Use |
| --- | --- | --- | --- |
| `pillGray` | `(["…"])` | `fill:#D9DDE0,stroke:#000000,stroke-width:2px,color:#000000` | start / neutral endpoint |
| `pillOrange` | `(["…"])` | `fill:#FFEAC7,stroke:#F69800,stroke-width:2px,color:#A34900` | result node / highlighted step |
| `cardDefault` | `("…")` | `fill:#FFFFFF,stroke:#C0C6CB,stroke-width:2px,color:#000000` | normal process |
| `cardSegmented` | `("…")` | same as cardDefault | multi-field / parallel step |
| `decision` | `{"…"}` | `fill:#D4F3F6,stroke:#144F66,stroke-width:2px,color:#003D56` | branch / decision |

## Arrow classes (`linkStyle <index> …`)

| Class | `linkStyle` body | Use |
| --- | --- | --- |
| default | `stroke:#000000,color:#000000,stroke-width:2px` | main path |
| success | `stroke:#00A513,color:#00A513,stroke-width:2px` | condition met / passed / normal completion |
| info | `stroke:#009DDB,color:#009DDB,stroke-width:2px` | informational / secondary / external ref |
| danger | `stroke:#FF0033,color:#FF0033,stroke-width:2px` | error / exception / abort / condition failed |
| muted | `stroke:#9F9F9F,color:#9F9F9F,stroke-width:2px,stroke-dasharray:8 4` | skippable / backtrack / weak link (dashed) |

## Files

| File | Purpose |
| --- | --- |
| `build_flow.py` | **The fast path.** Plain flowchart → styled + validated + rendered. Stdlib only; `mmdc` or Kroki for rendering. |
| `flow-chart.mermaid.json` | **Source of truth.** Top level = a valid Mermaid config for `mmdc --configFile`. `x-flowChartStyle` = copy-paste material (`initDirective`, `styleBlock`, `nodeClasses`, `arrowClasses`, `groupStyles`, `rules`, `postProcess`, `render`). |
| `render.sh` | `./render.sh <name|path>` → Kroki SVG → strip Kroki's shadow bug → (if Chrome + Pillow) a trimmed PNG. |
| `templates/flow_template.mmd` | Blank starter for `build_flow.py` (plain) + the manual style block. |
| `examples/flow_sample.mmd` | Worked example (5 arrow types + 2 groups), hand-styled. |
| `examples/flow_pipeline.mmd` | Larger hand-styled example (subgraph state store + dotted data edges). |
| `examples/requirement_flow.mmd` | Plain input for `build_flow.py` — `python3 build_flow.py examples/requirement_flow.mmd`. |

## Rules

- **Arrowhead colour = line colour** only if the edge has an explicit
  `linkStyle <index> stroke:…`. Style black edges too. No `linkStyle default`.
- `linkStyle` index = order the edge appears in the file, 0-based (`build_flow.py`
  handles this; re-number by hand only on the manual path).
- A node with **no outgoing edge** → `pillOrange` (it is a result).
- Edge-label background is `#FFFFFF`; label colour follows the stroke.
- Group frame: blue `#79CFDD` on `#EAF4F6`, or yellow `#F69800` on `#FFF3E0`;
  fill lighter than its members.

## Known limitations

- **Kroki font metrics:** Kroki's server has no CJK/Latin fonts, so it sizes
  nodes slightly narrow and the last glyph of a label can clip by ~1 char.
  `flowchart.htmlLabels:false` + `padding:12` (already in the config) fixes edge
  labels; keep node labels short and `<br/>`-wrapped. Local `mmdc` and
  mermaid.live render correctly.
- **Shadows:** Kroki's SVG rasteriser (resvg) mis-applies Mermaid's
  `[data-look="neo"]` `filter:drop-shadow` rule. `render.sh` and `build_flow.py`
  strip it. `mmdc` / real browsers are unaffected.
- `build_flow.py` covers the common flowchart subset (`flowchart`, `[] () ([]) {}`
  shapes, `-->` / `-->|label|` / `-- label -->` / `-.->` / `==>`, `subgraph`).
  Exotic syntax may need the manual path.
- No fixed node sizes; no true orthogonal routing with rounded corners; no inner
  divider for `cardSegmented`; arrow-marker size not configurable.

`flow-chart.mermaid.json` holds the exact strings — read it first and prefer them.

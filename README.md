# Mermaid + flow-chart-style 使用方式
與 mermaid.ai 生成並行，套用 Flow 繪製規範，讓圖面美觀與一致

---

**來源檔**：`flow-chart.mermaid.json`
**Skill 指令**: `/flow-chart-style`
**輸出檔**：`SVG` `PNG` `mmd` `styled`  
**備註**：運行 Mermaid 加入繪製設定檔

---

### 方式 1：用 JSON config 手動套樣式
與 `/mermaid-skill` 併用**：先讓 mermaid-skill 產生 `.mmd`，一併附上 `flow-chart.mermaid.json`，Prompt 交代：
  > 請用 `mmdc --configFile flow-chart.mermaid.json` 套用樣式

### 方式 2：安裝 `flow-chart-style` skill
**安裝後輸入即運行**：
```/flow-chart-style```
（也會被「Flow Chart style」「flow_chart_style」「套用 Flow Chart 樣式」「流程圖配色」等語句觸發。）


---


## 若無選用任一套用樣式
- 運行 mermaid-kill 僅會生成無 mermaid 預設版


---


**flow-chart-style（Mermaid）**
- 無法對應：固定節點尺寸、精確 40px 間距 / 零重疊保證、正交折線 + 24px 圓角轉角（現用 `curve:basis`；要正交改 `curve:step` 但無圓角）、`cardSegmented` 內部分隔線、箭頭 marker 固定 12px
- `build_flow.py` 覆蓋常見子集（`flowchart`、`[] () ([]) {}` 形狀、`-->` / `-->|label|` / `-- label -->` / `-.->` / `==>`、`subgraph`）；特殊語法需走手動路線

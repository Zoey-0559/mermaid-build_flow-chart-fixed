#### 兩套工具，對應兩種情境：
1. `flowchart-change-style`
> 過 Mermaid，直接依設計 token 重畫成 SVG。
[https://github.com/Zoey-0559/flow-chart_change-style](https://github.com/Zoey-0559/flow-chart_change-style)

2. `flow-chart-style`
> Mermaid 套用樣式直接生成，本身有主題／樣式選項限制，將視覺語言改寫成符合 Mermaid 生成規範的 config／skill；

#### 效率排序（快 → 慢）
1. Mermaid 預設：直接產出
2. 生成即美化（`flow-chart-style skill`）：一次生成就帶樣式
3. 二次繪製（`flowchart-change-style skill`）：讀圖 → 判斷列節點與邊、判語意 → 依 token 重畫 SVG → 延伸版面 → 檢查內容是否零重疊
4. Browser JSON ＆ skill 二次改圖


---

# Mermaid + flow-chart-style 使用方式
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

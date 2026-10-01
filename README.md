# ISO 27001:2022 運作流程｜系統與網路安全（動畫教學簡報）

Q 版 Allan Lo 講師 × 助教阿拉蕾的雙人動畫課程，以控制屬性「運作流程（Operational capabilities）＝ System and network security」為主軸，涵蓋：

| 控制措施 | 名稱 | 備註 |
|---|---|---|
| 8.9 | 組態管理 Configuration management | 2022 新增 |
| 8.20 | 網路安全 Networks security | 舊版 A.13.1.1 |
| 8.21 | 網路服務之安全 Security of network services | 舊版 A.13.1.2 |
| 8.22 | 網路之區隔 Segregation of networks | 舊版 A.13.1.3 |
| 8.23 | 網頁過濾 Web filtering | 2022 新增 |
| 6.7 | 遠端工作 Remote working | 舊版 A.6.2.2 |

課程分三道菜：**ISMS 作業重點 → 稽核查核重點 → 常見缺失**，穿插兩個管理案例（產線停工兩天、「暫時」的防火牆規則）、不符合事項寫法範例、修正 vs. 矯正措施，以及隨堂小測驗。全長約 14 分鐘，22 個段落。

## 檔案

| 路徑 | 內容 |
|---|---|
| `video/系統與網路安全.mp4` | 成品影片（1280×720，含旁白） |
| `presentation/index.html` | 互動播放器：可暫停、拖曳進度、跳段落、調速、字幕開關、全螢幕 |
| `presentation/audio/narration.mp3` | 旁白音軌（台灣口音神經語音：講師男聲、助教女聲） |
| `presentation/lesson.js` | 由腳本產生的時間軸（請勿手改） |
| `src/lesson.json` | **講稿來源**：每句台詞、說話者、表情 |
| `docs/講稿.md` | 逐字稿（含各段落起始時間） |
| `tools/build_audio.py` | 講稿 → 語音、時間軸、逐字稿 |
| `tools/render_video.cjs` | 播放器 → MP4 |

## 使用方式

**直接上課**：用瀏覽器開啟 `presentation/index.html`（建議用本機伺服器，例如 `npx serve presentation`），按「開始上課」。

快捷鍵：空白鍵 播放/暫停、← → 倒轉/快轉 5 秒、`[` `]` 上/下一段、F 全螢幕、C 字幕。網址加上 `#s14` 這類錨點可直接跳到該段。

## 修改講稿後重新產生

```bash
pip install edge-tts                 # 語音合成（需 ffmpeg）
python3 tools/build_audio.py         # 只重做有改動的句子，並更新 lesson.js、講稿.md

npm i -D playwright                  # 錄影用
node tools/render_video.cjs          # 輸出 video/系統與網路安全.mp4
node tools/render_video.cjs --shots 30,120,400   # 只截圖檢查版面（build/shots/）
```

- 台詞在 `src/lesson.json`：`w` 為說話者（`A` 講師、`R` 助教），`t` 為字幕文字，`s`（選填）為 TTS 實際唸法，`e` 為表情（`happy`、`cheer`、`think`、`idea`、`surprised`、`oops`、`wink`）。條號如 `8.20` 會自動唸成「八點二十」。
- 畫面元素在 `presentation/index.html` 各 `<section data-id="sXX">` 中，`data-at="n"` 表示第 n 句台詞開始時出現，`data-p` 為該句進度比例、`data-fx` 為進場效果、`data-hl` 為哪幾句時高亮。台詞增減時請一併調整對應的 `data-at`。
- 語音：講師 `zh-TW-YunJheNeural`、助教 `zh-TW-HsiaoYuNeural`，可在 `src/lesson.json` 的 `voices` 調整語速與音高。

## 說明

- 管理案例為「改編自輔導實務常見狀況」的教學情境，非特定組織的真實事件；NCR 範例中的設備、日期、規則編號皆為示意。
- 助教「阿拉蕾」為原創 Q 版造型（耳機麥克風、大圓眼鏡、薄荷綠制服），未沿用既有漫畫角色的設計，可放心用於課程。
- 講師造型為通用 Q 版西裝講師，可在 `index.html` 中 `#cA` 的 SVG 調整髮型、眼鏡、領帶顏色。

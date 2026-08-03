# Media Inventory

更新时间：2026-07-30
探测工具：`ffprobe`、`sips`

## 视频

| 文件 | 时长 | 分辨率 | FPS | 视频 | 音频 | 字幕 | 大小 |
|---|---:|---:|---:|---|---|---|---:|
| `格物智评_LabTrace_初赛Demo.mp4` | 02:42.61 | 1280×720 | 30 | H.264 | AAC 16 kHz 单声道 | 默认 `mov_text` 简体中文 | 3.01 MiB |

配音使用 `zh-CN-XiaoxiaoNeural` 暖声神经语音，分 11 个场景独立生成，合成语速为 `-3%`；每页按真实语音时长重排，未用 `atempo` 做机械拉伸。字幕时间来自每段音频的实际时长。完整视频已通过音视频解码、响度、字幕轨和 11 个关键画面检查。

## 独立字幕

| 文件 | 格式 | 大小 |
|---|---|---:|
| `格物智评_LabTrace_Demo.zh-CN.srt` | SubRip / UTF-8 | 2.34 KiB |

## 核心截图与报告页

| 文件 | 尺寸 | 大小 |
|---|---:|---:|
| `assets/labtrace-word-native-result.png` | 1275×717 | 375.1 KiB |
| `assets/labtrace-word-native-result-full.png` | 1275×4285 | 1.63 MiB |
| `assets/labtrace-word-native-delivery.png` | 1275×717 | 391.8 KiB |
| `assets/labtrace-word-native-delivery-full.png` | 1275×4529 | 1.67 MiB |
| `assets/labtrace-word-native-home.png` | 1275×1919 | 756.0 KiB |
| `assets/labtrace-home-v2.png` | 1275×717 | 78.3 KiB |
| `assets/labtrace-allergen-result-v2.png` | 1275×717 | 76.6 KiB |
| `assets/labtrace-game-result-v2.png` | 1275×717 | 76.4 KiB |
| `assets/labtrace-diagnosis-v2.png` | 1275×717 | 53.9 KiB |
| `assets/report-allergen-cover.png` | 1547×2002 | 194.0 KiB |
| `assets/report-allergen-evidence.png` | 1547×2002 | 192.6 KiB |
| `assets/report-game-cover.png` | 1547×2002 | 191.9 KiB |
| `assets/report-game-evidence.png` | 1547×2002 | 228.4 KiB |

`word-native-*` 来自 2026-07-30 生产环境 MiniMax-M3 真实运行：检测并分析 1 张合成截图，生成 5 条 Word 原生批注，其中 1 条锚定图片；教师终审将 75 分调整为 77 分并写回评语。旧版截图保留用于版本对照，正式 PPT/PDF 与视频以 `word-native-*`、`v2` 和 `report-*` 资产为证据。

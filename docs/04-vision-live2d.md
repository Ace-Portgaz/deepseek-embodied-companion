# 全身 Live2D、视觉跟随与点击互动

## 导入模型

当前适配用户提供的 DeepSeek-chan 原版全身模型。感谢 [@Kamiya_Ryoko](https://vgen.co/KAMIYA) 的插画／PSD 与发布，以及霓虹猫_NeonNeko 的 Live2D 绑定。原包条款禁止重新上传完整模型，所以仓库只提供适配代码和导入工具。

取得原作者资源后，在仓库根目录执行：

```bash
python scripts/import-character-assets.py /absolute/path/DeepSeek-chan.zip
# 核对导入清单，再追加 --apply；默认不写文件。
```

工具查找 `.model3.json`，保留其目录内模型、贴图、表情、动作和许可文本，不导入 PSD、可执行文件或第三方应用源码。模型放入忽略的 `rem-phone-system/vendor/rem/RemBody/assets/rem-bust-v4/models/deepseek-chan-user/`，生成全身 `catalog.json`，并校验所引用资源路径。多模型压缩包需用 `--model` 指定入口。

另外在 `rem-phone-system/vendor/rem/RemBody/assets/rem-bust-v4/preview/vendor/` 准备：

- 从 [Live2D 官方](https://www.live2d.com/download/cubism-sdk/download-web/) 获得 `live2dcubismcore.min.js`，遵守其许可。
- PixiJS 6.5.10 的 `pixi-6.5.10.min.js`、pixi-live2d-display 0.4.0 的 `pixi-live2d-display-0.4.0.min.js`；文件名以 `preview/runtime.js` 为准。

再生成作者动作与部位映射，并准备视觉依赖：

```bash
node scripts/build-character-interaction.cjs
python rem-phone-system/scripts/fetch-visual-dependencies.py
python rem-phone-system/scripts/fetch-vision-notices.py
python rem-phone-system/scripts/stage-vision-dependencies.py
```

生成器从实际 Cubism 网格、部件父链和 CDI 名称推导部位，枚举 Exp3 / Animation 文件，写入本地 `interaction.json`；不会修改原始 moc 或纹理。其他作者的模型需调整参数名、动作名与部件映射，不能保证直接套用。

MediaPipe Tasks 0.10.35 的库、Face Landmarker 和 Gesture Recognizer 在本地下载、记录来源和 hash，再提取 ARM64 JNI、Java 库与任务模型。保留其原始许可；历史 `prepare-visual-assets.py` 是旧包整包导入入口，当前不要运行它覆盖源码。

## 作者表情与动作

原模型包含 23 份表情／外观 JSON 和 8 份 motion3，但原 model3 未全部列入播放清单。现在用 sidecar 补齐：待机、抚胸手、竖食指、狗尾草的出场／回收和长演出，配合脸红、爱心眼、流泪、屑屑眼等表情与配件切换。

`motion-clip.js` 处理直线、Bezier、阶跃和反向阶跃曲线；`author-interaction.js` 负责待机、表情叠加和手势回收。头部、眼神和口型参数保留实时输入优先级，防止动作覆盖说话或跟随。手动表情一般保持 8 秒，配件可保持开关状态。

长按顶部“大肥鱼” → “表情与动作（本地预览）”，可直接试脸红、爱心眼、抚胸手和“全部恢复”。模型里的“表情文件”也包含外观开关，23 个文件不等于 23 种情绪。

## 摄像头和本地观察

Camera2 通常取得 640×480 YUV，按传感器方向转正。Face Landmarker 优先 GPU，失败回退 CPU；手势使用 CPU，繁忙时丢弃过时帧。`ObservationPolicy` 负责阈值、迟滞、冷却；`visual-follow.js` 平滑控制眼睛和头部。

| 事件 | 判断与反馈 |
| --- | --- |
| ARRIVED / LEFT | 脸进入或持续丢失；注视与回正 |
| NOD / SHAKE | 多帧点头／摇头；头部或表情回应 |
| WAVE | 张开手掌的平移／手腕摆动；微笑与作者手势 |
| APPROACH / RETREAT | 脸框相对尺度变化；靠近时可脸红 |

距离是相对变化，不是厘米测距。当前仅前台、亮屏且观察开关打开时持续运行；退后台、熄屏或硬件检查会释放摄像头。原始帧不落盘、不上传；云端只接收近期事件。后摄像头目前用于维护检查。

## 点击形象

点击使用模型变形后的三角网格与渲染顺序，结合画布及贴图透明度排除透明空白，识别 head / face / hand / body / legs / tail（腿和脚合并为 legs）。头发属于 head；不能用整个矩形框代替部位判断。

短点击小于 650 ms、移动不超过 14 px；长按和拖动不触发。Java `TouchPolicy` 再校验白名单、8 秒冷却、前台状态及对话忙碌状态；忙碌时丢弃，不排队。点击语音可在维护菜单关闭。

本地先做表情与动作，再发送明确的屏幕触摸文本，让 DeepSeek 回应实际点击部位；不启动麦克风、不伪造语音识别。合成播放的 RMS 能量驱动嘴型，不是逐音素口型。

## 渲染兼容与验收

大尺寸纹理根据设备 `MAX_TEXTURE_SIZE` 在 GPU 上传前缩放，保留原文件；Multiply / Screen Color 兼容修复解决脸部黑块。全身 framing 固定为完整模型范围。

真机分别检查全身比例、脸部颜色、眼神方向、五类动作、表情预览、头发／尾巴点击对应回复、透明背景无误触，以及熄屏／恢复。离线测试用合成曲线和网格验证算法；原作者全部动作的资源校验与实际效果需本地模型和真机完成。

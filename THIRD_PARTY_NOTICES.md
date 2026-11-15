# 第三方来源与许可范围

这是公开的工程整理仓库。当前没有给整个仓库授予统一开源许可证；公开可见不等于所有文件都可在任意条件下再分发。各第三方文件沿用其原始许可。项目自有代码的统一许可尚待维护者选择，使用或再分发时请确认相应授权。

| 项目 | 本工程用途 | 许可说明 |
| --- | --- | --- |
| [xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server) | ESP32 协议服务与 Provider 基础 | 上游 MIT；装配时复制上游 LICENSE |
| [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) | 原设备固件与协议参考 | 不随仓库分发固件 |
| [LineageOS](https://github.com/LineageOS) / AOSP / Linux | Android 基线、设备树、内核 | 多种许可，完整源码与补丁使用需遵循各目录声明 |
| [MediaPipe](https://github.com/google-ai-edge/mediapipe) | 面部和手势推理 | Apache-2.0；下载并保留原 LICENSE，新增日志工厂为本项目适配 |
| [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) | 参考音色推理与权重 | 源码、模型及其依赖分别遵守各自声明；不分发权重 |
| [Genie-TTS](https://github.com/High-Logic/Genie-TTS) | ONNX 转换、中文与日语 G2P | MIT；摘取的前端位于 `rem-voice/service/vendor_genie/`，保留 LICENSE |
| [pyopenjtalk-plus](https://github.com/tsukumijima/pyopenjtalk-plus) | 日语前端和词典接口 | 见上游及词典各自声明 |
| [Demucs](https://github.com/facebookresearch/demucs) / [faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 本地参考音频准备 | 使用上游发行包；不分发模型与素材 |

Live2D Cubism Core、Cubism Web Framework、PixiJS、pixi-live2d-display，以及资源包来源中的 live2d-agent-kit / psd2live，保留了随原资源取得的许可与来源说明：

- [角色技术资源许可目录](rem-phone-system/vendor/rem/RemBody/assets/character-licenses)
- [Genie 摘取前端许可](rem-voice/service/vendor_genie/LICENSE)

该目录的第三方说明按收到的内容保留，其中相对链接指向各上游项目目录，而非本仓库。它们不授予角色美术、名称、原始录音、声优表演或第三方用户模型的使用权。公开版本移除了相应资产与样本。下载脚本只补齐用户主动选择的外部依赖，使用者需审阅其许可。

## 当前模型与声音鸣谢

感谢 **[@Kamiya_Ryoko](https://vgen.co/KAMIYA)** 提供／发布大肥鱼 **DeepSeek-chan** 模型。

- 插画与 PSD 分层：**Kamiya Ryoko（神宫凉子）**。
- Live2D 绑定：**霓虹猫_NeonNeko**。
- 原包使用说明允许按其条款使用模型、调整追踪／表情设置，并要求保留署名；禁止重新上传完整模型。本仓库仅发布适配代码，模型和 PSD 由使用者从原作者渠道取得。

感谢 **[AI Hobbyist 资源库](https://res.acgnai.top/)** 提供本项目使用的声音素材来源。原素材、参考音频、训练集、微调权重与生成试听不在本仓库；具体素材权利与使用条件由其原作者和来源说明确定。

中文推理还使用 [G2pM](https://github.com/kakaobrain/g2pM)、[pypinyin](https://github.com/mozillazg/python-pinyin)、[jieba](https://github.com/fxsjy/jieba) 和 [HFL 中文 RoBERTa](https://huggingface.co/hfl/chinese-roberta-wwm-ext-large)。依赖和权重分别遵循其上游许可。`vendor_genie/Chinese` 保留上游声明；本工程增加中文语气词归一化和空分句保护。训练与导出脚本不授予声音素材或模型权重的再分发权。

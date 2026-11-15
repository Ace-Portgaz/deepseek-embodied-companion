# GPT-SoVITS → Genie-TTS：参考音色接入

## 方案与结果

使用 [GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) v2ProPlus 的短参考音频条件合成，再转换到 [Genie-TTS](https://github.com/High-Logic/Genie-TTS) ONNX 路线用于 CPU 云端。**没有在本工程训练一套雷姆专用权重**；听感来自预训练权重和参考音频条件。这也不是官方原声录音直接拼接。

使用者已确认本地试听自然、手机播放音色满意、嘴型正常。手机关闭电脑后仍可用；ESP32 音色没有在此步骤中切换。

## 1. 准备自己的参考录音

选择单人、清晰、少混响、无背景音乐的日语素材，准确转写。工程参考片段约 3.8 秒、32 kHz 单声道；实际长度要求以所选上游版本为准。原始视频、拆分人声、参考录音及文本配对没有公开。

必要时使用 [Demucs](https://github.com/facebookresearch/demucs) 分离人声，使用 [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 辅助转写，再人工核对。转写模型、词典也需要单独准备，`transcribe_reference.py` 不会自动提供它们。不要把分离失败、BGM 残留或错误转写直接归因于 TTS 模型。

复制 `rem-voice/reference-config.example.json` 到忽略的 `rem-voice/reference/reference-config.json`，填写音频绝对路径和一致的日语文本。确保拥有使用和发布相关声音的权利；仓库不分发角色录音与生成试听。

## 2. 本地 GPU 试听

官方源码固定到 `20250606v2pro`，提交 `d7c2210da8c013e81a94bfc7b811a477c99fd506`：

```bash
git clone https://github.com/RVC-Boss/GPT-SoVITS.git rem-voice/GPT-SoVITS-v2Pro
git -C rem-voice/GPT-SoVITS-v2Pro checkout d7c2210da8c013e81a94bfc7b811a477c99fd506
python scripts/fetch-voice-weights.py
```

权重清单固定到 Hugging Face `lj1995/GPT-SoVITS` 的 `8f8857563c040d542de108a2c18b0425abd6c9c5`。下载器按 LFS SHA-256 或 Git blob SHA-1 与文件大小校验，下载到已忽略的上游目录。

独立 venv，实测 Python 3.12、PyTorch 2.6.0 + CUDA 12.6、RTX 4060 Laptop 8 GB。按机器与驱动选择匹配 Torch，随后安装 `requirements-trial.txt`，使用 `constraints.txt` 和 `requirements-without-torch.lock` 核对版本；FFmpeg 需另行安装。完整锁文件是实测依赖记录，不表示跨平台通用。

```bash
python rem-voice/synthesize_trial.py --text 'こんにちは。今日もお話ししましょう。'
```

脚本默认拒绝没有 GPU 的试听，防止误用低配 CPU 长时间阻塞。它使用离线 Hugging Face 模式，因此要先备齐模型、语言资源和词典。接受音色后再进入云端步骤。

## 3. ONNX 转换与参考特征

取得 Genie-TTS 源码放到 `rem-voice/Genie-TTS/`。`genie-source.json` 保留本次源码 ZIP 的 SHA-256；当时使用 master 归档，**没有保存可验证的 Git commit**，因此不能把当前 master 当作同一份转换器。若旧归档不可得，需要对新版本重新验证转换和试听。

Genie 运行资源使用 Hugging Face `High-Logic/Genie`，固定 revision `52b17272e0b7032415e85ad37b551db2386b1810`，包括 `GenieData/chinese-hubert-base/` 与 `GenieData/speaker_encoder.onnx`。这些是外部依赖，需要按 Genie 的目录说明下载到 `rem-voice/GenieData/`，不会随仓库发布。

准备好转换依赖与上游模板后依次运行：

```bash
python rem-voice/convert_genie.py
python rem-voice/benchmark_genie.py
python rem-voice/materialize_genie.py
```

第一个脚本导出模型；第二个载入自备参考音频，计算 `reference-features.npz` 并进行 CPU 试听；第三个把外部 FP16 存储权重展开为运行需要的 FP32 文件，避免服务器启动时通过大型 protobuf 复制权重。三者顺序不能调换。

云端只带固定参考特征和运行模型，不需要一直驻留 HuBERT、说话人编码器与 prompt encoder。`service/rem_genie.py` 使用直接文件加载、有限线程和生成长度控制。输出目录为 `models/rem-ja-genie-runtime-v1/`，更新参考音频后必须重新生成特征与运行产物。

## 4. 云端服务

云端目录建议为：

```text
/opt/rem-voice/venv/
/opt/rem-voice/releases/rem-ja-genie-v1/service/
/opt/rem-voice/releases/rem-ja-genie-v1/models/
/opt/rem-voice/current -> releases/rem-ja-genie-v1
```

传输自有模型和 `service/`，在独立 venv 安装 `service/requirements.txt`。日语前端词典必须在启动前离线备好：systemd 的 `PrivateNetwork=yes` 禁止语音进程自行联网下载。保留 vendor_genie MIT 许可。

安装 `service/rem-voice.service` 后启用服务。它使用已有 `rem` 用户，Unix socket 权限 0600，无公网监听，限制 CPU 150%、内存 2300 MiB、swap 128 MiB。主服务与语音服务的内存上限相加接近 4 GB，需观察实际可用内存，不适合并发多人使用。

确认私有 socket 能完成短句后，为 `rem-cloud.service` 添加 drop-in：

```ini
[Service]
Environment=REM_PHONE_TTS=genie
```

执行 `systemctl daemon-reload` 并重启主服务。移除此变量并重启即可回退火山音色，无需更改手机。更换发布目录后可回切 `current` 指向的上一版，模型与参考特征必须成套。

## 5. 边界与性能

单次最多 160 字，按不超过 45 字分段，最长 30 秒 PCM，推理超时预算 25 秒；一次只处理一个推理。发生超时、忙碌或无效音频时主服务回退 Vivi，仍使用同一轮字符额度。手机网络超时与合成超时接近，慢请求可能仍需用户重试；这不是低延迟流式 TTS。

| 环境 | 代表结果 |
| --- | --- |
| 本地 GPU 热机 | 5.6–6 秒语音约 2.05–2.58 秒生成；首次加载约 26 秒 |
| 原 PyTorch 本地 CPU，2 线程 | 约 22–25 秒，内存约 4.2–5.4 GiB |
| 优化后本地 ONNX，2 线程 | 约 4.55–5.09 秒，峰值 RSS 约 1764 MiB |
| 实际 2 核 4 GB 云主机 | 4.76–5.04 秒语音约 9.21–10.71 秒，峰值进程 RSS 约 2072 MiB |
| 一次实际鉴权文本对话 | 24 字回复、3.62 秒音频，DeepSeek 加音色总计约 9.05 秒 |

以上是本次样本，不是普遍性能承诺。ONNX 降低内存占用，但云主机 CPU 与本地桌面性能不同；不要直接用本地速度估算云端对话延迟。

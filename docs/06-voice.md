# 中文 GPT-SoVITS 微调与云端音色

## 当前方案

当前为**中文素材微调 GPT-SoVITS v2ProPlus，再转换成 Genie ONNX 在 CPU 云端推理**。它不是仅把日语参考语音的语言参数改成中文。使用者已确认花火中文试听自然，手机上的声音和嘴型一致。素材来源鸣谢 [AI Hobbyist 资源库](https://res.acgnai.top/)；原素材、训练集、参考片段与权重不公开。

本次从 612 个候选片段、约 67.72 分钟中筛出 240 个训练片段、约 22.9 分钟，另留 12 个片段验收；SoVITS 8 个 epoch、GPT 10 个 epoch。这是一次实际训练配置，不是任何声音的固定最优参数。手机使用此音色，ESP32 仍走火山 TTS。

## 1. 准备环境与素材

[GPT-SoVITS](https://github.com/RVC-Boss/GPT-SoVITS) 固定到提交 `d7c2210da8c013e81a94bfc7b811a477c99fd506`（20250606v2pro）：

```bash
git clone https://github.com/RVC-Boss/GPT-SoVITS.git rem-voice/GPT-SoVITS-v2Pro
git -C rem-voice/GPT-SoVITS-v2Pro checkout d7c2210da8c013e81a94bfc7b811a477c99fd506
python scripts/fetch-voice-weights.py
```

权重清单固定 `lj1995/GPT-SoVITS` revision `8f8857563c040d542de108a2c18b0425abd6c9c5`，下载后按清单检查大小和 hash。中文训练还依赖 `chinese-roberta-wwm-ext-large`、`chinese-hubert-base`、说话人编码器及 v2ProPlus 预训练权重；核对清单和上游要求，缺失时先补齐。

使用独立 venv；实测 Python 3.12、PyTorch 2.6.0 + CUDA 12.6、RTX 4060 Laptop 8 GB。安装适配机器的 Torch 与 FFmpeg，再核对 `requirements-trial.txt`、`constraints.txt` 和实测锁文件。锁文件不是跨平台兼容保证；训练脚本使用当前解释器，并开启离线模型模式。

选择单人、清晰的普通话素材，去除 BGM、重叠说话和不完整音节；逐句核对转写、声调、噪声和时长。准备目录：

```text
rem-voice/datasets/dafeiyu-zh-sparkle-v1/
  wavs/            32 kHz 单声道 WAV，唯一文件名
  train.list       每行：音频绝对路径|speaker|ZH|准确转写
  manifest.json    train 与 heldout 数组；每项含 file（音频绝对路径）和 sha256
```

训练集和验收集必须分离，`train.list` 只能列训练集。manifest 的 hash 针对规范化后的 WAV。素材切分、转写与筛选需要本地完成，仓库没有预制数据集或训练数据清单。`train_mandarin.py` 会校验训练文件 hash、集合不重叠及特征完整性。

## 2. 训练与 GPU 试听

```bash
python rem-voice/train_mandarin.py all \
  --name dafeiyu-zh-sparkle-v1 \
  --dataset /absolute/path/to/dafeiyu-zh-sparkle-v1
```

也可分别运行 `prepare`、`train`。脚本先生成文本/BERT、HuBERT、说话人和语义特征，逐项校验后训练；输出位于忽略的 `rem-voice/training/`。不会自动部署。

复制 `reference-config.example.json` 到本地 `rem-voice/reference/reference-config.json`，填写清晰、准确转写的中文参考录音，保留 `"language":"all_zh"`。本次选用约 6.5 秒参考音频。显式指定新训练的两份权重试听，避免误用预训练版本：

```bash
python rem-voice/synthesize_trial.py \
  --reference /absolute/path/reference-config.json \
  --gpt-weights /absolute/path/selected-gpt.ckpt \
  --sovits-weights /absolute/path/selected-sovits.pth \
  --text-language all_zh --text '你好呀，我是大肥鱼。你刚才朝我挥手啦。'
```

验收日常短句、自我介绍、疑问句、数字与语气词，比较未参与训练的句子；确认发音、音色和停顿后再转换。试听脚本拒绝无 GPU 的意外慢推理；输出也不进入 Git。

## 3. ONNX、中文 BERT 与参考特征

取得 [Genie-TTS](https://github.com/High-Logic/Genie-TTS) 放到 `rem-voice/Genie-TTS/`。`genie-source.json` 记录所用 master ZIP 的 SHA-256，但当时没有保存可验证 Git commit，不能将当前 master 视为同一版本。更换转换器需重新校验和试听。

Genie 参考编码资源来自 `High-Logic/Genie` revision `52b17272e0b7032415e85ad37b551db2386b1810`，自行准备 `GenieData/chinese-hubert-base/` 与 `GenieData/speaker_encoder.onnx`。顺序如下：

```bash
python rem-voice/convert_genie.py \
  --gpt /absolute/path/selected-gpt.ckpt \
  --sovits /absolute/path/selected-sovits.pth \
  --output rem-voice/models/dafeiyu-zh-sparkle-v1
python rem-voice/export_chinese_bert.py
python rem-voice/prepare_chinese_reference.py \
  --model-dir rem-voice/models/dafeiyu-zh-sparkle-v1 \
  --reference /absolute/path/reference-config.json
python rem-voice/materialize_genie.py \
  --source rem-voice/models/dafeiyu-zh-sparkle-v1 \
  --output rem-voice/models/dafeiyu-zh-sparkle-runtime-v1 \
  --bert-dir rem-voice/models/chinese-bert-cpu-v1 \
  --profile dafeiyu-zh-sparkle-v1
python rem-voice/benchmark_sparkle_cpu.py
```

中文 BERT 使用正确的倒数第三层，导出并量化为 q8，检查与 FP32 的一致性；推理端严格验证字与音素对齐，不用全零特征掩盖错误。参考编码器在离线阶段运行，服务器只加载固定特征和运行模型。外部 FP16 权重提前展开为 FP32 文件，减少启动时复制峰值。换声音或参考录音后需成套重新生成。

## 4. 云端部署

云主机实测为 Ubuntu 24.04、2 核 4 GB，无 GPU。目录建议：

```text
/opt/rem-voice/venv/
/opt/rem-voice/releases/dafeiyu-zh-sparkle-v1/service/
/opt/rem-voice/releases/dafeiyu-zh-sparkle-v1/models/
/opt/rem-voice/current -> releases/dafeiyu-zh-sparkle-v1
```

用加密连接上传自有运行模型和 `service/`，在独立 venv 安装 `service/requirements.txt`；启动前准备好中文 G2pM、分词、BERT 和兼容日语前端所需离线资源。模型与生成 manifest 一同校验，不把原录音或 API 密钥放进语音 worker。

安装 `service/rem-voice.service`，使用已有 `rem` 用户，Unix socket 权限 0600，无公网监听，`PrivateNetwork=yes`；CPU 150%、内存 2800 MiB、swap 128 MiB。4 GB 机器同时还有对话主服务，要检查实际总内存和负载；此部署面向单用户，不适合多人并发。

为主服务 `rem-cloud.service` 增加 drop-in，确保两服务 profile 一致：

```ini
[Service]
Environment=REM_PHONE_TTS=genie
Environment=REM_VOICE_PROFILE=dafeiyu-zh-sparkle-v1
```

语音单元已设置 `REM_VOICE_LANGUAGE=zh` 及相同 profile。执行 `systemctl daemon-reload` 后启用／重启服务，先检查私有 socket，再测手机短句。回滚时可切回上一组完整产物；移除 `REM_PHONE_TTS=genie` 并重启主服务可恢复火山声音，手机无需重刷。

## 5. 运行边界

回复最多 160 字，中文按标点和不超过 45 字分段。提前 EOS 才有最多三次有界重试，始终共享 25 秒推理截止时间；失败、忙碌或无效音频会回退火山 Vivi。回退可能产生明显不同声线，应核对实际 engine，不把它误判为训练权重被替换。

中文前端规范部分语气词和英文缩写，空分句安全处理；ASR 最终空帧不应覆盖此前有效识别。整轮最多 30 秒 PCM，一次处理一个推理，字符额度按同一轮预留。DeepSeek 费用和服务器费用另计，语音字数上限不是全部服务费用封顶。

一次中文整链路实测约 21.6 秒，仅为当时样本；云端 CPU、句长、模型调用与回退都会影响延迟。当前不是完整流式低延迟语音，操作后需等待本轮完成。

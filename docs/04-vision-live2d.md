# Live2D、前置摄像头与视觉反馈

## 准备资源

工程使用用户提供的 `Rem_Expressive_Bust_v5_1_Gyro.zip`，角色美术、网格、纹理、模型和 SDK 二进制不在公开仓库。拥有可用资源时，按自己的许可准备；换一个 Live2D 模型还需适配参数名、坐标和动作映射，不是改文件名即可。

公开源码保留渲染与桥接逻辑。原资源包包含 `android-assets/`、`android/`、`licenses/`；当前 Java / JS 已包含后续视觉与语音改动，因此不要用旧资源包的源码覆盖它们。可用下面的补齐工具，只导入缺少的二进制资产和模型 JSON：

```bash
python scripts/import-character-assets.py /absolute/path/Rem_Expressive_Bust_v5_1_Gyro.zip
# 检查待导入列表后，在同一命令追加 --apply。
python rem-phone-system/scripts/fetch-visual-dependencies.py
python rem-phone-system/scripts/fetch-vision-notices.py
python rem-phone-system/scripts/stage-vision-dependencies.py
```

下载工具取得 MediaPipe Tasks 0.10.35、Face Landmarker / Gesture Recognizer 及依赖，在 `tools/vision-dependencies/` 记录来源和 hash。`stage-vision-dependencies.py` 提取 ARM64 JNI、Java 库与任务模型，并替换统计日志工厂以使用空实现；不改模型或 JNI 算法。请保留下载的原始许可。历史 `prepare-visual-assets.py` 是早期整包导入工具，不适合覆盖当前最新源码。

## 本地处理链

`FrontCameraSource` 用 Camera2 获取 YUV 帧，常用 640×480；按传感器方向转正，再转入视觉引擎。Face Landmarker 优先 GPU，失败回退 CPU。手势识别单独使用 CPU，繁忙时丢弃过时帧，避免堆积和拖慢表情刷新。

`ObservationEngine` 给出脸位置、姿态、手势和时序样本。纯 Java 的 `ObservationPolicy` 负责阈值、迟滞、冷却和事件判断；WebView 桥将结果交给 `visual-follow.js`，平滑地更新眼睛和头部参数。

| 事件 | 本地意义 | 角色反馈 |
| --- | --- | --- |
| ARRIVED / LEFT | 检测到脸进入 / 持续丢失 | 注视、等待、回正 |
| NOD / SHAKE | 多帧俯仰 / 左右摆动 | 头部或表情回应 |
| WAVE | 张开手掌并有摆动轨迹 | 微笑、歪头、字幕 |
| APPROACH / RETREAT | 脸框相对大小变化 | 表情与字幕反馈 |

靠近/远离是相对尺度，不是厘米测距。挥手修复同时考虑手掌平移和手腕摆动，仍受光线、遮挡和完整手掌是否入镜影响。半身模型没有手臂挥动参数，因此识别到挥手不代表模型也能抬手挥动。

## 眼神和嘴型的协调

视觉跟随保持坐标方向、限幅和回正；正常眨眼与表情仍保留。说话时根据播放 PCM 的 RMS 能量更新开口幅度，不是逐音素口型。测试保证视觉更新不抹掉说话时的嘴型。

`RemMotionSensor` 与资源包中的陀螺仪效果可存在，但观察开启时眼神应由视觉目标控制，避免两个控制源反复抢参数。

## 摄像头生命周期

观察开启 + Activity 前台 + 屏幕可用时保持前摄像头运行。退出前台、熄屏或进入维护检查会释放资源；用户可以暂停观察。原始帧不写磁盘、不上传。后置摄像头目前是维护检查入口，非持续场景识别。

云端只在对话请求中收到最近 15 秒内最多 8 个事件，服务端额外拒绝超过 30 秒的事件。事件用于语言回应，不构成用户授权，也不代表对衣服、物品或身份有视觉理解。

## 验收

手机竖直放稳，测试左右/上下移动、点头、摇头、挥手、靠近/离开；然后测试熄屏、恢复和维护相机启停。已经由使用者确认眼睛方向正确、点头/摇头/距离变化可见、挥手修正版能识别。自动化测试覆盖状态和参数逻辑，真实光线与脸部识别仍需真机验证。

开源候选包括 [MediaPipe](https://github.com/google-ai-edge/mediapipe)、[OpenSeeFace](https://github.com/emilianavt/OpenSeeFace) 和 [MediaMTX](https://github.com/bluenviron/mediamtx)。当前实现使用 MediaPipe；后两者没有部署到这台手机。

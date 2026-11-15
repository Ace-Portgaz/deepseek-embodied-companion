# 手机对话、性格与记忆

## 凭据登记

手机只持有自己独立的设备凭据，不持有 DeepSeek / 火山 API 密钥。服务端 `credentials.json` 的 `phone_devices` 结构为：

```json
{
  "phone-EXAMPLE1234": {
    "token_sha256": "REPLACE_WITH_SHA256_OF_A_NEW_RANDOM_DEVICE_TOKEN"
  }
}
```

使用 `secrets.token_urlsafe(32)` 生成随机 token，服务端只登记 SHA-256。将手机身份在 `settings.json` 的 `memory_identity_aliases` 中指向已有 ESP32 对应的记忆身份。关联必须由管理员确定，不能相信客户端自行传来的身份字段。

构建前编辑 `rem-phone-system/vendor/rem/RemBody/src/com/rem/body/voice/CloudEndpoint.java` 的 `HOST` 为自有服务端地址。公开版为 `rem.example.com`，不能直接连接。客户端和登记接收器共同引用这一白名单，避免让设备凭据发送到任意地址。

本机生成的手机配置包含 `url`、`device`、`token`，`url` 形如 `https://rem.example.com/rem-phone/v1`。通过已授权的 ADB shell 将 Base64 JSON 传给 `com.rem.body.voice.ProvisionReceiver`；Manifest 要求 `android.permission.DUMP`，普通应用不能广播登记。Base64 只是传输编码，**不是加密**；不要将配置贴到终端记录、Issue 或 Git 提交里。

手机写入 `MODE_PRIVATE` 的 `cloud-device.json`，应用禁止备份。撤销时删除服务端登记记录并重启加载配置，遗失设备应使用新凭据重新登记。

## API

所有接口要求 `X-Rem-Device` 与 `Authorization: Bearer …`。

| 接口 | 方法 | 用途 |
| --- | --- | --- |
| `/rem-phone/v1/status` | GET | 配置就绪、语种、音色标识 |
| `/rem-phone/v1/turn` | POST | 一轮语音或文本对话，携带近期动作 |
| `/rem-phone/v1/personality` | GET / POST | 读取或保存手机对话的附加性格风格 |

非敏感的请求形状示例：

```json
{
  "id": "EXAMPLE-REQUEST-0001",
  "text": "私は今、何をしましたか？",
  "events": [{"event": "WAVE", "age_ms": 1200}]
}
```

实际手机使用 `audio`：Base64 的 16 kHz、单声道、16 bit PCM，最长 15 秒；`text` 和 `audio` 二选一。服务端拒绝照片、任意身份覆盖和非白名单事件。每设备并发一轮，轮间最短 2 秒；相同 request id 的最近结果缓存 90 秒，防止短暂重试重复调用模型。

链路是录音 → 火山日语识别 → DeepSeek → 日语回复（最多 160 字）→ 合成 → 手机 AudioTrack 播放。模型和服务不是即时响应，按钮结束录音后应等待；不要连续点击制造多个请求。

## 性格与记忆如何调整

基础人设在 `rem-cloud/prompts/rem_ja.txt`，设定温柔、朋友关系、使用日语。手机 `personality` 接口接受 `{"style":"希望的说话风格"}`，最多 2000 字，保存到服务端 `data/personality.json`，下一轮生效，不需要刷手机。

附加性格接口目前作用于手机对话；要改变 ESP32 端基础人设，需同步修改基础 prompt 并部署。不要把手机附加风格接口理解成已经自动修改全部终端。

`RemMemory` 持久保存有限偏好和事件摘要：最多 12 条偏好、32 条事件，检索时选相关摘要。它不保存完整逐字对话，也不是无限记忆。别名让新手机读取同一份服务端记忆，不复制一个容易分叉的新文件。迁移测试已覆盖身份映射、重启后读取和未知设备隔离。

## 动作进入对话

最初仅附加英文事件名时，回复会忽略挥手。改为明确的日语描述、事件时间，并在当前轮提示中优先解释最近的挥手/点头/摇头。真机测试问题「私は今、何をしましたか？」已回答挥手。

视觉事件仅为可能误判的观察，不是命令、同意或身份依据。模型应接受用户纠正，不应由未观察到的数据推断衣服、物品或身份。

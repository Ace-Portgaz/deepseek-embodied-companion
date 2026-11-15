# ESP32 与云端部署

## 环境和上游

首次设备为立创实战派 ESP32-S3，屏幕、麦克风、扬声器已集成。实测固件属于小智 2.2.2 系列，保留了已有固件，修改服务器配置。后续手机接口复用了同一云服务。

云端实测 Ubuntu 24.04、2 vCPU / 4 GB、60 GB SSD，无 GPU。购买时套餐为 188 元/年，5 Mbps、每月 500 GB；这是历史记录，采购时应核对实时价格和续费规则。

服务适配基于 [xiaozhi-esp32-server](https://github.com/xinnan-tech/xiaozhi-esp32-server)，固定提交 `4b1a54a41c28112bc06b1ab605d2ba723f678ad3`。先在仓库根目录准备上游：

```bash
mkdir -p upstream
git clone https://github.com/xinnan-tech/xiaozhi-esp32-server.git upstream/xiaozhi-esp32-server
git -C upstream/xiaozhi-esp32-server checkout 4b1a54a41c28112bc06b1ab605d2ba723f678ad3
python rem-cloud/prepare.py
```

`prepare.py` 会确认提交和工作区干净，复制服务端并装配适配器；不会启动服务或调用计费接口。升级上游时必须重新检查补丁位置。

## 填写本机私密配置

```bash
python rem-cloud/setup_app.py
```

窗口写入 `rem-cloud/.private/`。也可按 `settings.example.json` 格式在本机私密目录手工配置，凭据字段为 `deepseek_api_key`、`volc_asr_api_key`、`volc_tts_api_key`。`with_device_secrets()` 生成稳定的设备初始化密钥和服务鉴权密钥，不要每次部署重新生成。

`public_host` 只填域名或公网 IPv4，不带协议；`device_id` 填自有 ESP32 MAC。选择账号实际支持的 DeepSeek 模型和支持中文的火山音色。示例中的模型名是工程所用配置，并非保证所有账号都可用。

```bash
python rem-cloud/prepare.py --runtime
```

会生成 `runtime/settings.json`、`runtime/credentials.json`、`runtime/caddy.env`。这些全部含部署私密信息，不提交 Git；用 SSH 加密传输到自有服务器。

## 原生 systemd 部署

将 `rem-cloud/build/`、`rem-cloud/deploy/`、`rem-cloud/runtime/` 放到 `/opt/rem-cloud/` 对应目录。以管理员在服务器执行：

```bash
sudo apt-get update
sudo bash /opt/rem-cloud/deploy/bootstrap-native.sh
sudo bash /opt/rem-cloud/deploy/activate-native.sh
sudo systemctl status rem-cloud --no-pager
```

先审阅脚本：它们会安装依赖、建立 `rem` 系统账号并启用服务。凭据通过 systemd `LoadCredential` 读取，持久数据在 `/var/lib/rem-cloud/data/`。启用前给 runtime 文件设置严格的目录与文件权限；不要把它们放在 Web 静态目录。

`deploy/Caddyfile.cloud` 提供网关模板，但证书路径、环境变量、设备初始化路由必须适配自有部署。当前入口只支持合法设备凭据；不要为了排错关闭鉴权。Docker 文件作为备选保留，本工程最终运行的是原生 systemd。

域名可以指向服务器；GitHub 仓库或 GitHub Pages 不能充当此 WSS / ASR / 模型后端。工程实际曾使用公网 IP 短期 TLS 证书，复现时需自行确认 CA 支持、证书链和续期任务，不要通过关闭证书校验替代配置。

## 每日额度

`speech_budget.py` 使用持久账本。工程启用的日常额度为两设备合计 **每天 1000 个合成字符、600 秒识别**，按 UTC+8 日期切换。首次启用前，将 `rem-cloud/speech-budget.example.json` 作为新账本放到 `/var/lib/rem-cloud/data/speech-test-budget.json`，归属 `rem` 用户、权限 0600。示例日期会在第一次请求按 UTC+8 更新；已有账本不得覆盖。没有设置 `REM_TEST_BUDGET_FILE` 时不执行此限额，提供的 systemd 单元已设置它；测试额度与日常额度是不同模式。

部署后应保留账本并在重启、更新和备份恢复时保留累计值。超额暂停，次日恢复。DeepSeek 的费用由 API 账号另行计算；此语音上限不是所有云服务费用的总封顶。克隆失败回退火山时，同一轮只预留一次字符额度。

## ESP32 接入与回滚

1. 读取芯片、Flash 大小、固件版本、NVS 分区和 MAC，完整备份 Flash 与 NVS 到私密目录。
2. 用自有设备信息准备 OTA / WSS 配置，先检查服务端 TLS 与未授权请求拒绝。
3. 只修改所需服务器地址并回读校验，再重启设备。
4. 短句验证收音、中文识别和播放；异常时恢复备份中的配置。

旧版固件曾因清除兼容字段而反复重启。**不要直接删除旧 `mqtt` / `httpConfig` 相关字段**；字段存在与是否实际走旧服务是两个问题，应结合串口日志和服务器请求确认。本仓库的 `deploy/prepare_device.py` 是配置生成辅助，不是适用于任意开发板的自动刷写器。原始备份与具体设备 NVS 不公开。

ESP32 当前仍使用原唤醒方式与火山中文音色；本次 Genie 音色只接入手机端。

管理员可在账本中设置 `one_day_extra: {"date":"YYYY-MM-DD","characters":1000}`，只对指定日期增加合成额度，不改变次日常规上限或已用计数。若当天已经暂停，确认新的有效额度后再解除 `paused`。手机对话遇到限额返回 429 并显示明确提示；不要删除账本绕过限制。

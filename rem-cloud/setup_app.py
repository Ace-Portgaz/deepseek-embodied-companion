"""Local configuration window. Saves only on this computer; tests are explicit."""
import json
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import ttk
import urllib.error
import urllib.request
from cloud_config import ROOT, load_private, private_write, with_device_secrets, validate


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def test_deepseek(settings, credentials):
    if not credentials.get("deepseek_api_key"):
        return "请先填写并保存 DeepSeek API 密钥。"
    payload = {"model": settings["deepseek_model"], "stream": False,
               "thinking": {"type": "disabled"}, "max_tokens": 160,
               "messages": [{"role": "system", "content": (ROOT / "prompts/dafeiyu_zh.txt").read_text(encoding="utf-8")},
                            {"role": "user", "content": "今天有点累，请简短地回复我。"}]}
    request = urllib.request.Request("https://api.deepseek.com/chat/completions",
                                     data=json.dumps(payload).encode(), method="POST",
                                     headers={"Authorization": "Bearer " + credentials["deepseek_api_key"],
                                              "Content-Type": "application/json"})
    start = time.monotonic()
    try:
        with urllib.request.build_opener(NoRedirect).open(request, timeout=45) as response:
            data = json.load(response)
        answer = data["choices"][0]["message"]["content"]
        return f"DeepSeek 已连接，完整回答用时 {time.monotonic() - start:.1f} 秒（不含语音）。\n\n{answer}"
    except urllib.error.HTTPError as error:
        return f"DeepSeek 返回 HTTP {error.code}。请检查密钥、余额和模型权限。"
    except Exception:
        return "连接未完成。请检查网络及配置；密钥和请求内容未写入日志。"


def main():
    settings, credentials = load_private()
    window = tk.Tk()
    window.title("大肥鱼 · 云端连接设置")
    window.geometry("760x740")
    frame = ttk.Frame(window, padding=22)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="大肥鱼的连接设置", font=("Microsoft YaHei UI", 18)).pack(anchor="w")
    ttk.Label(frame, text="密钥只保存到这台电脑；不需要发到聊天中。保存不会调用付费接口。\n配置文件采用本地明文保存，请勿分享 .private 或 runtime 文件夹。",
              wraplength=700).pack(anchor="w", pady=(8, 14))
    fields = {}
    labels = [("deepseek_api_key", "DeepSeek API 密钥", True),
              ("volc_asr_api_key", "火山语音识别 API Key", True),
              ("volc_tts_api_key", "火山声音合成 API Key", True),
              ("tts_speaker", "中文音色 ID（尚未选定可留空）", False),
              ("public_host", "云端域名或公网 IP（尚未配置可留空）", False),
              ("device_id", "开发板设备 ID / MAC（稍后核对）", False)]
    for key, label, secret in labels:
        state = "（已有保存，留空保留）" if secret and credentials.get(key) else ""
        ttk.Label(frame, text=label + state).pack(anchor="w", pady=(5, 2))
        variable = tk.StringVar(value="" if secret else settings.get(key, ""))
        fields[key] = variable
        ttk.Entry(frame, textvariable=variable, show="●" if secret else "", width=80).pack(fill="x")
    voice_kind = tk.StringVar(value=settings.get("tts_resource", "seed-tts-2.0"))
    ttk.Label(frame, text="声音类型").pack(anchor="w", pady=(8, 2))
    ttk.Combobox(frame, state="readonly", textvariable=voice_kind,
                 values=["seed-tts-2.0", "seed-icl-2.0"]).pack(anchor="w")
    ttk.Label(frame, text="seed-tts-2.0：平台音色；seed-icl-2.0：已经创建好的复刻音色。", wraplength=700).pack(anchor="w")
    status = tk.StringVar(value="可以先只保存 DeepSeek 密钥，验证中文人设。")
    output = tk.Text(frame, height=6, wrap="word", state="disabled")
    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=12)

    def save():
        nonlocal credentials
        # Keep credentials/settings saved by another setup step while this window
        # was open. An unchanged field must not overwrite newer local configuration.
        latest_settings, latest_credentials = load_private()
        credentials = latest_credentials
        for key, _, secret in labels:
            value = fields[key].get().strip()
            if secret:
                if value:
                    credentials[key] = value
            elif value != settings.get(key, ""):
                latest_settings[key] = value
        if voice_kind.get() != settings.get("tts_resource"):
            latest_settings["tts_resource"] = voice_kind.get()
        settings.clear()
        settings.update(latest_settings)
        credentials = with_device_secrets(credentials)
        private_write(ROOT / ".private/settings.json", json.dumps(settings, ensure_ascii=False, indent=2))
        private_write(ROOT / ".private/credentials.json", json.dumps(credentials, indent=2))
        status.set("已保存在本机。尚未部署到云端。")

    def test():
        save()
        test_button.configure(state="disabled")
        status.set("正在测试 DeepSeek 中文回答……")
        def work():
            result = test_deepseek(dict(settings), dict(credentials))
            def finish():
                output.configure(state="normal")
                output.delete("1.0", "end")
                output.insert("end", result)
                output.configure(state="disabled")
                test_button.configure(state="normal")
                status.set("本次文字测试结束；语音和开发板连接仍需单独验证。")
            window.after(0, finish)
        threading.Thread(target=work, daemon=True).start()

    ttk.Button(buttons, text="保存到本机", command=save).pack(side="left")
    test_button = ttk.Button(buttons, text="测试中文回答（少量 API 费用）", command=test)
    test_button.pack(side="left", padx=12)
    ttk.Label(frame, textvariable=status, wraplength=700).pack(anchor="w", pady=5)
    ttk.Label(frame, text="测试仅发送大肥鱼人设和固定句子“今天有点累”，不上传你的文件或历史聊天。", wraplength=700).pack(anchor="w")
    output.pack(fill="both", expand=True)
    window.mainloop()


if __name__ == "__main__":
    main()

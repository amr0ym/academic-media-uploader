import os
import signal
import subprocess
import threading
import time
from queue import Queue, Empty

import gradio as gr


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_MAP = {
    "Google Drive": os.path.join(ROOT_DIR, "downloaders", "gdrive.py"),
    "OneDrive": os.path.join(ROOT_DIR, "downloaders", "onedrive.py"),
    "Telegram": os.path.join(ROOT_DIR, "downloaders", "telegram.py"),
}
PRIVACY_OPTIONS = ["public", "unlisted", "private"]

_STATE = {
    "process": None,
    "lock": threading.Lock(),
}


def _append(logs, line):
    logs.append(line)
    if len(logs) > 1000:
        del logs[: len(logs) - 1000]
    return "\n".join(logs)


def _build_command_and_env(
    source_name,
    source_url,
    video_title,
    video_description,
    privacy_status,
    telegram_api_id,
    telegram_api_hash,
):
    if source_name not in SCRIPT_MAP:
        raise ValueError("اختيار السكربت غير صالح.")
    if not source_url.strip():
        raise ValueError("يرجى إدخال الرابط.")

    script_path = SCRIPT_MAP[source_name]
    env = os.environ.copy()
    cmd = ["python", script_path]

    if source_name == "Telegram":
        cmd.extend(["--telegram-post-url", source_url.strip()])
        if not telegram_api_id.strip() or not telegram_api_hash.strip():
            raise ValueError("يرجى إدخال Telegram API ID و Telegram API HASH عند اختيار Telegram.")
        env["TELEGRAM_API_ID"] = telegram_api_id.strip()
        env["TELEGRAM_API_HASH"] = telegram_api_hash.strip()
    else:
        cmd.extend(["--video-url", source_url.strip()])

    if video_title.strip():
        cmd.extend(["--video-title", video_title.strip()])
    if video_description.strip():
        cmd.extend(["--video-description", video_description.strip()])
    if privacy_status in PRIVACY_OPTIONS:
        cmd.extend(["--privacy-status", privacy_status])

    return cmd, env


def _reader_thread(stream, output_queue):
    try:
        for line in iter(stream.readline, ""):
            output_queue.put(line.rstrip("\n"))
    finally:
        stream.close()


def run_selected_script(
    source_name,
    source_url,
    video_title,
    video_description,
    privacy_status,
    telegram_api_id,
    telegram_api_hash,
):
    logs = []
    with _STATE["lock"]:
        if _STATE["process"] is not None and _STATE["process"].poll() is None:
            yield _append(logs, "يوجد تشغيل حالي بالفعل. أوقفه أولًا قبل بدء مهمة جديدة.")
            return

    try:
        cmd, env = _build_command_and_env(
            source_name=source_name,
            source_url=source_url,
            video_title=video_title,
            video_description=video_description,
            privacy_status=privacy_status,
            telegram_api_id=telegram_api_id,
            telegram_api_hash=telegram_api_hash,
        )
    except Exception as exc:
        yield _append(logs, f"خطأ في الإدخال: {exc}")
        return

    process = subprocess.Popen(
        cmd,
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
        start_new_session=True,
    )
    with _STATE["lock"]:
        _STATE["process"] = process

    yield _append(logs, f"بدأ تشغيل سكربت: {source_name}")
    yield _append(logs, "جاري التقاط سجل التنفيذ...")

    output_queue = Queue()
    reader = threading.Thread(target=_reader_thread, args=(process.stdout, output_queue), daemon=True)
    reader.start()

    while True:
        updated = False
        while True:
            try:
                line = output_queue.get_nowait()
            except Empty:
                break
            updated = True
            yield _append(logs, line)

        if process.poll() is not None:
            while True:
                try:
                    line = output_queue.get_nowait()
                except Empty:
                    break
                updated = True
                yield _append(logs, line)
            break

        if not updated:
            time.sleep(0.25)

    exit_code = process.poll()
    with _STATE["lock"]:
        if _STATE["process"] is process:
            _STATE["process"] = None

    if exit_code == 0:
        yield _append(logs, "انتهى التنفيذ بنجاح.")
    else:
        yield _append(logs, f"انتهى التنفيذ مع خطأ. رمز الخروج: {exit_code}")


def stop_selected_script(current_log):
    with _STATE["lock"]:
        process = _STATE["process"]

    if process is None or process.poll() is not None:
        base = current_log.strip() if current_log else ""
        return (base + "\n" if base else "") + "لا توجد عملية قيد التشغيل لإيقافها."

    try:
        os.killpg(process.pid, signal.SIGTERM)
        time.sleep(1.0)
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        message = "تم إرسال أمر الإيقاف للمهمة الحالية."
    except Exception as exc:
        message = f"فشل إيقاف العملية: {exc}"
    finally:
        with _STATE["lock"]:
            if _STATE["process"] is process and process.poll() is not None:
                _STATE["process"] = None

    base = current_log.strip() if current_log else ""
    return (base + "\n" if base else "") + message


def toggle_telegram_fields(source_name):
    is_telegram = source_name == "Telegram"
    return gr.update(visible=is_telegram), gr.update(visible=is_telegram)


with gr.Blocks(title="Academic Media Uploader - Colab UI") as demo:
    gr.Markdown("## Academic Media Uploader\nواجهة بسيطة لتشغيل السكربتات الحالية من داخل Colab.")

    source_name = gr.Dropdown(
        choices=["Google Drive", "OneDrive", "Telegram"],
        value="Google Drive",
        label="اختر السكربت",
    )
    source_url = gr.Textbox(label="رابط الفيديو / المنشور", placeholder="ضع الرابط هنا")
    video_title = gr.Textbox(label="عنوان الفيديو (اختياري)")
    video_description = gr.Textbox(label="وصف الفيديو (اختياري)", lines=3)
    privacy_status = gr.Dropdown(
        choices=PRIVACY_OPTIONS,
        value="unlisted",
        label="خصوصية الفيديو على YouTube",
    )

    telegram_api_id = gr.Textbox(label="Telegram API ID", visible=False)
    telegram_api_hash = gr.Textbox(label="Telegram API HASH", type="password", visible=False)

    with gr.Row():
        run_button = gr.Button("تشغيل", variant="primary")
        stop_button = gr.Button("إيقاف", variant="stop")

    log_output = gr.Textbox(label="سجل التنفيذ والأخطاء", lines=20, interactive=False)

    source_name.change(
        fn=toggle_telegram_fields,
        inputs=[source_name],
        outputs=[telegram_api_id, telegram_api_hash],
    )

    run_button.click(
        fn=run_selected_script,
        inputs=[
            source_name,
            source_url,
            video_title,
            video_description,
            privacy_status,
            telegram_api_id,
            telegram_api_hash,
        ],
        outputs=[log_output],
    )

    stop_button.click(
        fn=stop_selected_script,
        inputs=[log_output],
        outputs=[log_output],
    )


if __name__ == "__main__":
    demo.queue().launch(share=True)

import tkinter as tk
from tkinter import messagebox, filedialog
import subprocess
import os
import sys
import textwrap
from pathlib import Path

APP_NAME = "НЕЙРОХАК СТУДИЯ"
WIDTH = 720
HEIGHT = 1280

def app_dir():
    return Path(sys.executable).parent if getattr(
        sys, "frozen", False
    ) else Path(__file__).parent

BASE = app_dir()
OUTPUT = BASE / "output"
OUTPUT.mkdir(exist_ok=True)


def create_video():
    title = title_entry.get().strip()
    script = script_text.get("1.0", tk.END).strip()

    if not title or not script:
        messagebox.showwarning(
            "Ошибка",
            "Введите название и текст сценария."
        )
        return

    ffmpeg = BASE / "ffmpeg.exe"

    if not ffmpeg.exists():
        messagebox.showerror(
            "Ошибка",
            "Не найден ffmpeg.exe"
        )
        return

    output_file = OUTPUT / "neurohack_video.mp4"

    # Создаём текстовый файл для FFmpeg
    text_file = BASE / "video_text.txt"

    wrapped = "\n".join(
        textwrap.wrap(script[:350], width=28)
    )

    text_file.write_text(
        wrapped,
        encoding="utf-8"
    )

    font = "C:/Windows/Fonts/arial.ttf"

    # Подготавливаем путь для фильтра FFmpeg
    text_path = str(text_file).replace("\\", "/")
    text_path = text_path.replace(":", "\\:")

    filter_complex = (
        f"drawtext=fontfile='{font}':"
        f"textfile='{text_path}':"
        "fontcolor=white:"
        "fontsize=32:"
        "line_spacing=12:"
        "x=(w-text_w)/2:"
        "y=(h-text_h)/2"
    )

    command = [
        str(ffmpeg),
        "-y",
        "-f", "lavfi",
        "-i", f"color=c=0x080B16:s={WIDTH}x{HEIGHT}:r=25",
        "-t", "15",
        "-vf", filter_complex,
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        str(output_file)
    ]

    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        messagebox.showinfo(
            "Готово!",
            f"Видео сохранено:\n{output_file}"
        )

    except subprocess.CalledProcessError as e:
        messagebox.showerror(
            "Ошибка FFmpeg",
            e.stderr[-1500:]
        )


def open_output():
    os.startfile(OUTPUT)


root = tk.Tk()
root.title(APP_NAME)
root.geometry("700x650")
root.configure(bg="#080B16")

tk.Label(
    root,
    text="⚡ НЕЙРОХАК СТУДИЯ",
    font=("Arial", 24, "bold"),
    fg="#00D9FF",
    bg="#080B16"
).pack(pady=20)

tk.Label(
    root,
    text="Название ролика",
    fg="white",
    bg="#080B16",
    font=("Arial", 12)
).pack()

title_entry = tk.Entry(
    root,
    width=55,
    font=("Arial", 12)
)
title_entry.pack(pady=10)

tk.Label(
    root,
    text="Сценарий видео",
    fg="white",
    bg="#080B16",
    font=("Arial", 12)
).pack()

script_text = tk.Text(
    root,
    height=13,
    width=65,
    font=("Arial", 11)
)
script_text.pack(pady=10)

tk.Button(
    root,
    text="🎬 СОЗДАТЬ ВИДЕО",
    command=create_video,
    bg="#00D9FF",
    fg="black",
    font=("Arial", 14, "bold"),
    height=2
).pack(pady=15)

tk.Button(
    root,
    text="📁 ОТКРЫТЬ ГОТОВЫЕ ВИДЕО",
    command=open_output,
    bg="#8B5CF6",
    fg="white",
    font=("Arial", 11)
).pack(pady=10)

root.mainloop()

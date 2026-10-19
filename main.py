import tkinter as tk
from tkinter import messagebox
import subprocess
import os
import sys
import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

APP_NAME = "НЕЙРОХАК СТУДИЯ"
WIDTH = 720
HEIGHT = 1280

def app_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

BASE = app_dir()
OUTPUT = BASE / "output"
OUTPUT.mkdir(exist_ok=True)


def create_background(title, script):
    img = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        "#080B16"
    )

    draw = ImageDraw.Draw(img)

    font_path = "C:/Windows/Fonts/arial.ttf"

    title_font = ImageFont.truetype(
        font_path, 48
    )

    text_font = ImageFont.truetype(
        font_path, 34
    )

    small_font = ImageFont.truetype(
        font_path, 26
    )

    # Неоновая рамка
    draw.rounded_rectangle(
        (35, 180, 685, 1100),
        radius=30,
        outline="#00D9FF",
        width=5
    )

    # Название бренда
    draw.text(
        (WIDTH // 2, 80),
        "НЕЙРОХАК",
        font=title_font,
        fill="#00D9FF",
        anchor="mm"
    )

    # Заголовок ролика
    wrapped_title = textwrap.fill(
        title[:80],
        width=22
    )

    draw.multiline_text(
        (WIDTH // 2, 260),
        wrapped_title,
        font=title_font,
        fill="white",
        anchor="ma",
        align="center",
        spacing=12
    )

    # Основной текст
    wrapped_script = textwrap.fill(
        script[:450],
        width=34
    )

    draw.multiline_text(
        (WIDTH // 2, 500),
        wrapped_script,
        font=text_font,
        fill="white",
        anchor="ma",
        align="center",
        spacing=14
    )

    # Нижняя надпись
    draw.text(
        (WIDTH // 2, 1180),
        "VK • НЕЙРОХАК",
        font=small_font,
        fill="#8B5CF6",
        anchor="mm"
    )

    background = BASE / "background.png"
    img.save(background)

    return background


def create_video():
    title = title_entry.get().strip()
    script = script_text.get(
        "1.0", tk.END
    ).strip()

    if not title or not script:
        messagebox.showwarning(
            "Ошибка",
            "Введите название и сценарий."
        )
        return

    ffmpeg = BASE / "ffmpeg.exe"

    if not ffmpeg.exists():
        messagebox.showerror(
            "Ошибка",
            "Не найден ffmpeg.exe"
        )
        return

    try:
        background = create_background(
            title, script
        )

        output_file = OUTPUT / "neurohack_video.mp4"

        command = [
            str(ffmpeg),
            "-y",
            "-loop", "1",
            "-framerate", "25",
            "-i", str(background),
            "-t", "15",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            str(output_file)
        ]

        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        messagebox.showinfo(
            "Готово!",
            f"Видео создано:\n{output_file}"
        )

    except Exception as e:
        messagebox.showerror(
            "Ошибка",
            str(e)
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

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import subprocess
import threading
import datetime
import os
import sys
import re
import wave
import json
import shutil

WIDTH = 720
HEIGHT = 1280
FPS = 25

def base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

BASE = base_dir()
OUTPUT = BASE / "output"
TEMP = BASE / "temp"
VOICES = BASE / "voices"

for folder in [OUTPUT, TEMP]:
    folder.mkdir(exist_ok=True)


def resource(name):
    return BASE / name


def find_font():
    fonts = [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf"
    ]

    for font in fonts:
        if Path(font).exists():
            return font

    raise RuntimeError("Не найден подходящий шрифт")


FONT = find_font()


def split_text(text, max_chars=85):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    scenes = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) < max_chars:
            current += (" " if current else "") + sentence
        else:
            if current:
                scenes.append(current)
            current = sentence

    if current:
        scenes.append(current)

    return scenes


def wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()

        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return "\n".join(lines)


def create_scene_image(title, text, number, total, path):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        "#080B16"
    )

    draw = ImageDraw.Draw(image)

    title_font = ImageFont.truetype(FONT, 48)
    scene_font = ImageFont.truetype(FONT, 39)
    small_font = ImageFont.truetype(FONT, 25)

    # Неоновое оформление
    draw.rounded_rectangle(
        (30, 190, 690, 1090),
        radius=35,
        outline="#00D9FF",
        width=4
    )

    draw.line(
        [(50, 1120), (670, 1120)],
        fill="#8B5CF6",
        width=4
    )

    draw.text(
        (WIDTH // 2, 90),
        "НЕЙРОХАК",
        font=title_font,
        fill="#00D9FF",
        anchor="mm"
    )

    wrapped_title = wrap_text(
        draw,
        title[:90],
        title_font,
        590
    )

    draw.multiline_text(
        (WIDTH // 2, 300),
        wrapped_title,
        font=title_font,
        fill="white",
        anchor="mm",
        align="center",
        spacing=12
    )

    wrapped_scene = wrap_text(
        draw,
        text,
        scene_font,
        560
    )

    draw.multiline_text(
        (WIDTH // 2, 650),
        wrapped_scene,
        font=scene_font,
        fill="white",
        anchor="mm",
        align="center",
        spacing=15
    )

    draw.text(
        (WIDTH // 2, 1180),
        f"VK • НЕЙРОХАК  |  {number}/{total}",
        font=small_font,
        fill="#8B5CF6",
        anchor="mm"
    )

    image.save(path)


def run_command(command, input_text=None):
    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])

    return result


def audio_duration(path):
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def generate_audio(text, voice_name, output_file):
    piper = resource("piper.exe")

    models = {
        "Мужской": VOICES / "ru_RU-ruslan-medium.onnx",
        "Женский": VOICES / "ru_RU-irina-medium.onnx"
    }

    model = models[voice_name]

    if not model.exists():
        raise RuntimeError(
            f"Не найдена голосовая модель:\n{model}"
        )

    run_command([
        str(piper),
        "--model", str(model),
        "--output_file", str(output_file)
    ], input_text=text)


def create_scene_video(image, audio, output):
    duration = audio_duration(audio)

    ffmpeg = resource("ffmpeg.exe")

    run_command([
        str(ffmpeg),
        "-y",
        "-loop", "1",
        "-framerate", str(FPS),
        "-i", str(image),
        "-i", str(audio),
        "-t", str(duration),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        str(output)
    ])


def build_video():
    title = title_entry.get().strip()
    script = script_text.get("1.0", tk.END).strip()
    voice = voice_var.get()

    if not title or not script:
        messagebox.showwarning(
            "Ошибка",
            "Введите название и сценарий."
        )
        return

    create_button.config(state="disabled")
    status_var.set("Создание видео...")

    threading.Thread(
        target=process_video,
        args=(title, script, voice),
        daemon=True
    ).start()


def process_video(title, script, voice):
    try:
        scenes = split_text(script)

        if not scenes:
            raise RuntimeError("Сценарий пуст")

        timestamp = datetime.datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        workdir = TEMP / timestamp
        workdir.mkdir(exist_ok=True)

        videos = []

        for index, scene in enumerate(scenes, start=1):
            root.after(
                0,
                lambda i=index, n=len(scenes):
                status_var.set(f"Обработка сцены {i}/{n}")
            )

            image = workdir / f"scene_{index}.png"
            audio = workdir / f"audio_{index}.wav"
            video = workdir / f"video_{index}.mp4"

            create_scene_image(
                title,
                scene,
                index,
                len(scenes),
                image
            )

            generate_audio(
                scene,
                voice,
                audio
            )

            create_scene_video(
                image,
                audio,
                video
            )

            videos.append(video)

        concat_file = workdir / "concat.txt"

        concat_file.write_text(
            "\n".join(
                f"file '{video.as_posix()}'"
                for video in videos
            ),
            encoding="utf-8"
        )

        final_video = OUTPUT / f"neurohack_{timestamp}.mp4"

        run_command([
            str(resource("ffmpeg.exe")),
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(final_video)
        ])

        root.after(
            0,
            lambda: messagebox.showinfo(
                "Готово!",
                f"Видео создано:\n{final_video}"
            )
        )

        root.after(
            0,
            lambda: status_var.set("Видео готово!")
        )

    except Exception as error:
        error_text = str(error)

        root.after(
            0,
            lambda: messagebox.showerror(
                "Ошибка",
                error_text
            )
        )

        root.after(
            0,
            lambda: status_var.set("Ошибка создания видео")
        )

    finally:
        root.after(
            0,
            lambda: create_button.config(state="normal")
        )


def open_output():
    os.startfile(OUTPUT)


root = tk.Tk()
root.title("НЕЙРОХАК СТУДИЯ 2.0")
root.geometry("760x720")
root.configure(bg="#080B16")

tk.Label(
    root,
    text="⚡ НЕЙРОХАК СТУДИЯ 2.0",
    font=("Arial", 24, "bold"),
    fg="#00D9FF",
    bg="#080B16"
).pack(pady=20)

tk.Label(
    root,
    text="Название ролика",
    fg="white",
    bg="#080B16"
).pack()

title_entry = tk.Entry(
    root,
    width=65,
    font=("Arial", 12)
)
title_entry.pack(pady=10)

tk.Label(
    root,
    text="Выберите голос",
    fg="white",
    bg="#080B16"
).pack()

voice_var = tk.StringVar(value="Мужской")

voice_select = ttk.Combobox(
    root,
    textvariable=voice_var,
    values=["Мужской", "Женский"],
    state="readonly",
    width=30
)
voice_select.pack(pady=10)

tk.Label(
    root,
    text="Сценарий видео",
    fg="white",
    bg="#080B16"
).pack()

script_text = tk.Text(
    root,
    height=15,
    width=70,
    font=("Arial", 11)
)
script_text.pack(pady=10)

create_button = tk.Button(
    root,
    text="🎬 СОЗДАТЬ ВИДЕО",
    command=build_video,
    bg="#00D9FF",
    fg="black",
    font=("Arial", 14, "bold"),
    height=2
)
create_button.pack(pady=15)

tk.Button(
    root,
    text="📁 ОТКРЫТЬ ГОТОВЫЕ ВИДЕО",
    command=open_output,
    bg="#8B5CF6",
    fg="white",
    font=("Arial", 11)
).pack(pady=10)

status_var = tk.StringVar(value="Готов к работе")

tk.Label(
    root,
    textvariable=status_var,
    fg="#00D9FF",
    bg="#080B16",
    font=("Arial", 11)
).pack(pady=10)

root.mainloop()

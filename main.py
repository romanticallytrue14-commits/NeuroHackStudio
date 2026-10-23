import tkinter as tk
from tkinter import ttk, filedialog, messagebox
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
import math

WIDTH = 720
HEIGHT = 1280
FPS = 25

BG = "#080B16"
CYAN = "#00D9FF"
PURPLE = "#8B5CF6"


def base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE = base_dir()
OUTPUT = BASE / "output"
TEMP = BASE / "temp"
VOICES = BASE / "voices"
PROJECTS = BASE / "projects"

for folder in [OUTPUT, TEMP, PROJECTS]:
    folder.mkdir(exist_ok=True)


FONT = "C:/Windows/Fonts/arial.ttf"

materials = []
scene_assignments = {}
scenes = []


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


def split_text(text, max_chars=90):
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())

    result = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) < max_chars:
            current += (" " if current else "") + sentence
        else:
            if current:
                result.append(current)
            current = sentence

    if current:
        result.append(current)

    return result


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


def create_overlay(title, scene_text, number, total, path):
    image = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(image)

    title_font = ImageFont.truetype(FONT, 45)
    text_font = ImageFont.truetype(FONT, 35)
    small_font = ImageFont.truetype(FONT, 24)

    # Полупрозрачная область для текста
    draw.rounded_rectangle(
        (30, 720, 690, 1110),
        radius=30,
        fill=(8, 11, 22, 215),
        outline=CYAN,
        width=3
    )

    draw.text(
        (WIDTH // 2, 90),
        "НЕЙРОХАК",
        font=title_font,
        fill=CYAN,
        anchor="mm"
    )

    title_wrapped = wrap_text(
        draw,
        title[:80],
        title_font,
        620
    )

    draw.multiline_text(
        (WIDTH // 2, 170),
        title_wrapped,
        font=title_font,
        fill="white",
        anchor="mm",
        align="center"
    )

    scene_wrapped = wrap_text(
        draw,
        scene_text,
        text_font,
        570
    )

    draw.multiline_text(
        (WIDTH // 2, 900),
        scene_wrapped,
        font=text_font,
        fill="white",
        anchor="mm",
        align="center",
        spacing=12
    )

    draw.text(
        (WIDTH // 2, 1190),
        f"VK • НЕЙРОХАК | {number}/{total}",
        font=small_font,
        fill=PURPLE,
        anchor="mm"
    )

    image.save(path)


def audio_duration(path):
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def generate_audio(text, voice_name, output_file):
    piper = BASE / "piper.exe"

    models = {
        "Мужской": VOICES / "ru_RU-ruslan-medium.onnx",
        "Женский": VOICES / "ru_RU-irina-medium.onnx"
    }

    model = models[voice_name]

    if not piper.exists():
        raise RuntimeError("Не найден piper.exe")

    if not model.exists():
        raise RuntimeError("Не найдена голосовая модель")

    espeak_path = BASE / "espeak-ng-data"

    if not espeak_path.exists():
        raise RuntimeError("Не найдена папка espeak-ng-data")

    env = os.environ.copy()
    env["ESPEAK_DATA_PATH"] = str(espeak_path)

    result = subprocess.run(
        [
            str(piper),
            "--model", str(model),
            "--output_file", str(output_file)
        ],
        input=text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        cwd=str(BASE),
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])


def create_scene_video(background, overlay, audio, output):
    ffmpeg = BASE / "ffmpeg.exe"
    duration = audio_duration(audio)

    if background and background.lower().endswith(
        (".jpg", ".jpeg", ".png")
    ):
        command = [
            str(ffmpeg),
            "-y",
            "-loop", "1",
            "-i", background,
            "-i", str(overlay),
            "-i", str(audio),
            "-filter_complex",
            (
                "[0:v]scale=720:1280:force_original_aspect_ratio=increase,"
                "crop=720:1280[bg];"
                "[bg][1:v]overlay=0:0[v]"
            ),
            "-map", "[v]",
            "-map", "2:a",
            "-t", str(duration),
            "-r", str(FPS),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(output)
        ]

    elif background and background.lower().endswith(".mp4"):
        command = [
            str(ffmpeg),
            "-y",
            "-stream_loop", "-1",
            "-i", background,
            "-i", str(overlay),
            "-i", str(audio),
            "-filter_complex",
            (
                "[0:v]scale=720:1280:force_original_aspect_ratio=increase,"
                "crop=720:1280[bg];"
                "[bg][1:v]overlay=0:0[v]"
            ),
            "-map", "[v]",
            "-map", "2:a",
            "-t", str(duration),
            "-r", str(FPS),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(output)
        ]

    else:
        command = [
            str(ffmpeg),
            "-y",
            "-f", "lavfi",
            "-i", "color=c=0x080B16:s=720x1280:r=25",
            "-i", str(overlay),
            "-i", str(audio),
            "-filter_complex",
            "[0:v][1:v]overlay=0:0[v]",
            "-map", "[v]",
            "-map", "2:a",
            "-t", str(duration),
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            str(output)
        ]

    run_command(command)


def add_materials():
    files = filedialog.askopenfilenames(
        title="Выберите видео и изображения",
        filetypes=[
            ("Медиа", "*.mp4 *.jpg *.jpeg *.png")
        ]
    )

    for file in files:
        if file not in materials:
            materials.append(file)

    update_materials()


def update_materials():
    materials_list.delete(0, tk.END)

    for file in materials:
        materials_list.insert(
            tk.END,
            Path(file).name
        )


def prepare_scenes():
    global scenes

    script = script_text.get("1.0", tk.END).strip()

    if not script:
        messagebox.showwarning(
            "Ошибка",
            "Введите сценарий"
        )
        return

    scenes = split_text(script)

    scene_list.delete(0, tk.END)

    for index, scene in enumerate(scenes):
        scene_list.insert(
            tk.END,
            f"{index + 1}. {scene[:50]}"
        )

    status_var.set(
        f"Подготовлено сцен: {len(scenes)}"
    )


def assign_material():
    selected_scene = scene_list.curselection()
    selected_material = materials_list.curselection()

    if not selected_scene or not selected_material:
        messagebox.showwarning(
            "Ошибка",
            "Выберите сцену и материал"
        )
        return

    scene_index = selected_scene[0]
    material_index = selected_material[0]

    scene_assignments[scene_index] = materials[material_index]

    messagebox.showinfo(
        "Готово",
        "Материал назначен сцене"
    )


def build_video():
    title = title_entry.get().strip()
    script = script_text.get("1.0", tk.END).strip()
    voice = voice_var.get()
    mode = mode_var.get()

    if not title or not script:
        messagebox.showwarning(
            "Ошибка",
            "Введите название и сценарий"
        )
        return

    create_button.config(state="disabled")
    status_var.set("Начинаем создание...")

    threading.Thread(
        target=process_video,
        args=(title, script, voice, mode),
        daemon=True
    ).start()


def process_video(title, script, voice, mode):
    try:
        current_scenes = split_text(script)

        timestamp = datetime.datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        workdir = PROJECTS / timestamp
        workdir.mkdir(exist_ok=True)

        video_files = []

        for index, scene in enumerate(current_scenes):
            root.after(
                0,
                lambda i=index: status_var.set(
                    f"Создание сцены {i + 1}/{len(current_scenes)}"
                )
            )

            image = workdir / f"overlay_{index}.png"
            audio = workdir / f"audio_{index}.wav"
            video = workdir / f"scene_{index}.mp4"

            create_overlay(
                title,
                scene,
                index + 1,
                len(current_scenes),
                image
            )

            generate_audio(scene, voice, audio)

            background = None

            if mode == "Авто":
                if materials:
                    background = materials[index % len(materials)]

            else:
                background = scene_assignments.get(index)

            create_scene_video(
                background,
                image,
                audio,
                video
            )

            video_files.append(video)

        concat_file = workdir / "concat.txt"

        concat_file.write_text(
            "\n".join(
                f"file '{video.as_posix()}'"
                for video in video_files
            ),
            encoding="utf-8"
        )

        output_file = OUTPUT / f"neurohack_{timestamp}.mp4"

        run_command([
            str(BASE / "ffmpeg.exe"),
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c", "copy",
            str(output_file)
        ])

        project_info = {
            "title": title,
            "voice": voice,
            "mode": mode,
            "scenes": current_scenes
        }

        (workdir / "project.json").write_text(
            json.dumps(
                project_info,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        root.after(
            0,
            lambda: status_var.set("Видео готово!")
        )

        root.after(
            0,
            lambda: messagebox.showinfo(
                "Готово",
                f"Видео создано:\n{output_file}"
            )
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
root.title("НЕЙРОХАК СТУДИЯ 3.0")
root.geometry("950x850")
root.configure(bg=BG)

tk.Label(
    root,
    text="⚡ НЕЙРОХАК СТУДИЯ 3.0",
    font=("Arial", 24, "bold"),
    fg=CYAN,
    bg=BG
).pack(pady=12)

tk.Label(
    root,
    text="Название ролика",
    fg="white",
    bg=BG
).pack()

title_entry = tk.Entry(
    root,
    width=75,
    font=("Arial", 12)
)
title_entry.pack(pady=5)

voice_var = tk.StringVar(value="Мужской")
mode_var = tk.StringVar(value="Авто")

tk.Label(
    root,
    text="Голос",
    fg="white",
    bg=BG
).pack()

ttk.Combobox(
    root,
    textvariable=voice_var,
    values=["Мужской", "Женский"],
    state="readonly"
).pack(pady=5)

tk.Label(
    root,
    text="Режим",
    fg="white",
    bg=BG
).pack()

ttk.Combobox(
    root,
    textvariable=mode_var,
    values=["Авто", "Ручной"],
    state="readonly"
).pack(pady=5)

tk.Label(
    root,
    text="Сценарий",
    fg="white",
    bg=BG
).pack()

script_text = tk.Text(
    root,
    height=9,
    width=90
)
script_text.pack(pady=5)

tk.Button(
    root,
    text="🎬 ПОДГОТОВИТЬ СЦЕНЫ",
    command=prepare_scenes,
    bg=PURPLE,
    fg="white"
).pack(pady=5)

scene_list = tk.Listbox(
    root,
    width=90,
    height=6
)
scene_list.pack(pady=5)

tk.Button(
    root,
    text="📁 ДОБАВИТЬ ВИДЕО И ФОТО",
    command=add_materials,
    bg=CYAN
).pack(pady=5)

materials_list = tk.Listbox(
    root,
    width=90,
    height=5
)
materials_list.pack(pady=5)

tk.Button(
    root,
    text="🔗 НАЗНАЧИТЬ МАТЕРИАЛ СЦЕНЕ",
    command=assign_material,
    bg=PURPLE,
    fg="white"
).pack(pady=5)

create_button = tk.Button(
    root,
    text="🎬 СОЗДАТЬ VK КЛИП",
    command=build_video,
    bg=CYAN,
    fg="black",
    font=("Arial", 14, "bold")
)
create_button.pack(pady=12)

tk.Button(
    root,
    text="📁 ОТКРЫТЬ ГОТОВЫЕ ВИДЕО",
    command=open_output,
    bg=PURPLE,
    fg="white"
).pack()

status_var = tk.StringVar(value="Готов к работе")

tk.Label(
    root,
    textvariable=status_var,
    fg=CYAN,
    bg=BG
).pack(pady=10)

root.mainloop()

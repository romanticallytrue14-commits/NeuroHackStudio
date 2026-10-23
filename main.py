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
import uuid


# ==========================================
# НАСТРОЙКИ ПРОГРАММЫ
# ==========================================

APP_NAME = "НЕЙРОХАК СТУДИЯ 3.1"

WIDTH = 720
HEIGHT = 1280
FPS = 25

BG = "#080B16"
CYAN = "#00D9FF"
PURPLE = "#8B5CF6"
WHITE = "#FFFFFF"


def base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).parent


BASE = base_dir()

OUTPUT = BASE / "output"
PROJECTS = BASE / "projects"
VOICES = BASE / "voices"

OUTPUT.mkdir(exist_ok=True)
PROJECTS.mkdir(exist_ok=True)


FONT_PATH = "C:/Windows/Fonts/arial.ttf"

materials = []
scene_assignments = {}
scenes = []


# ==========================================
# КОПИРОВАНИЕ И ВСТАВКА
# ==========================================

def setup_clipboard(widget):

    menu = tk.Menu(
        widget,
        tearoff=0
    )

    menu.add_command(
        label="✂ Вырезать",
        command=lambda: widget.event_generate("<<Cut>>")
    )

    menu.add_command(
        label="📋 Копировать",
        command=lambda: widget.event_generate("<<Copy>>")
    )

    menu.add_command(
        label="📥 Вставить",
        command=lambda: widget.event_generate("<<Paste>>")
    )

    menu.add_separator()

    def select_all():
        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "1.0")
        else:
            widget.select_range(0, tk.END)
            widget.icursor(tk.END)

        widget.focus_set()

    menu.add_command(
        label="Выделить всё",
        command=select_all
    )

    def show_menu(event):
        widget.focus_set()

        try:
            menu.tk_popup(
                event.x_root,
                event.y_root
            )
        finally:
            menu.grab_release()

        return "break"

    widget.bind(
        "<Button-3>",
        show_menu
    )

    # Windows keycodes:
    # A = 65
    # C = 67
    # V = 86
    # X = 88
    #
    # Они не зависят от русской раскладки.

    def keyboard_handler(event):

        ctrl_pressed = bool(event.state & 0x4)

        if not ctrl_pressed:
            return None

        # Не перехватываем Alt+Ctrl.
        if event.state & 0x8:
            return None

        key = event.keycode

        if key == 65:
            select_all()
            return "break"

        if key == 67:
            widget.event_generate("<<Copy>>")
            return "break"

        if key == 86:
            widget.event_generate("<<Paste>>")
            return "break"

        if key == 88:
            widget.event_generate("<<Cut>>")
            return "break"

        return None

    widget.bind(
        "<KeyPress>",
        keyboard_handler
    )


# ==========================================
# ЗАПУСК ВНЕШНИХ ПРОГРАММ
# ==========================================

def run_command(command, input_text=None, cwd=None):

    result = subprocess.run(
        command,
        input=input_text,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        cwd=cwd,
        creationflags=subprocess.CREATE_NO_WINDOW
    )

    if result.returncode != 0:

        error = result.stderr[-3000:]

        raise RuntimeError(
            error or "Ошибка выполнения команды"
        )

    return result


# ==========================================
# РАЗДЕЛЕНИЕ ТЕКСТА НА СЦЕНЫ
# ==========================================

def split_text(text, max_chars=85):

    sentences = re.split(
        r'(?<=[.!?])\s+',
        text.strip()
    )

    result = []
    current = ""

    for sentence in sentences:

        # Длинные предложения разбиваем по словам.
        words = sentence.split()

        for word in words:

            candidate = (
                current + " " + word
            ).strip()

            if len(candidate) <= max_chars:
                current = candidate

            else:
                if current:
                    result.append(current)

                current = word

    if current:
        result.append(current)

    return result


# ==========================================
# ПЕРЕНОС ТЕКСТА
# ==========================================

def wrap_text(draw, text, font, max_width):

    words = text.split()

    lines = []
    current = ""

    for word in words:

        candidate = (
            current + " " + word
        ).strip()

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=font
        )

        text_width = bbox[2] - bbox[0]

        if text_width <= max_width:
            current = candidate

        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return "\n".join(lines)


# ==========================================
# СОЗДАНИЕ КИБЕРПАНК-ОФОРМЛЕНИЯ
# ==========================================

def create_overlay(
    title,
    scene_text,
    number,
    total,
    output_path
):

    image = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(image)

    brand_font = ImageFont.truetype(
        FONT_PATH,
        46
    )

    title_font = ImageFont.truetype(
        FONT_PATH,
        38
    )

    text_font = ImageFont.truetype(
        FONT_PATH,
        34
    )

    small_font = ImageFont.truetype(
        FONT_PATH,
        24
    )

    # Верхняя полупрозрачная панель

    draw.rounded_rectangle(
        (25, 35, 695, 235),
        radius=25,
        fill=(8, 11, 22, 220),
        outline=CYAN,
        width=3
    )

    # Бренд

    draw.text(
        (WIDTH // 2, 85),
        "НЕЙРОХАК",
        font=brand_font,
        fill=CYAN,
        anchor="mm"
    )

    # Заголовок

    wrapped_title = wrap_text(
        draw,
        title[:70],
        title_font,
        590
    )

    draw.multiline_text(
        (WIDTH // 2, 160),
        wrapped_title,
        font=title_font,
        fill=WHITE,
        anchor="mm",
        align="center",
        spacing=8
    )

    # Нижняя панель для субтитров

    draw.rounded_rectangle(
        (25, 750, 695, 1110),
        radius=30,
        fill=(8, 11, 22, 225),
        outline=CYAN,
        width=3
    )

    wrapped_text = wrap_text(
        draw,
        scene_text,
        text_font,
        570
    )

    # Подбираем размер, если текст не помещается.

    for size in range(34, 19, -2):

        test_font = ImageFont.truetype(
            FONT_PATH,
            size
        )

        candidate = wrap_text(
            draw,
            scene_text,
            test_font,
            570
        )

        bbox = draw.multiline_textbbox(
            (0, 0),
            candidate,
            font=test_font,
            spacing=10,
            align="center"
        )

        text_height = bbox[3] - bbox[1]

        if text_height <= 290:

            wrapped_text = candidate
            text_font = test_font
            break

    draw.multiline_text(
        (WIDTH // 2, 930),
        wrapped_text,
        font=text_font,
        fill=WHITE,
        anchor="mm",
        align="center",
        spacing=10
    )

    # Номер сцены

    draw.text(
        (WIDTH // 2, 1180),
        f"VK • НЕЙРОХАК  |  {number}/{total}",
        font=small_font,
        fill=PURPLE,
        anchor="mm"
    )

    image.save(output_path)


# ==========================================
# РУССКАЯ ОЗВУЧКА PIPER
# ==========================================

def generate_audio(
    text,
    voice_name,
    output_file
):

    piper = BASE / "piper.exe"

    models = {
        "Мужской":
            VOICES / "ru_RU-ruslan-medium.onnx",

        "Женский":
            VOICES / "ru_RU-irina-medium.onnx"
    }

    model = models[voice_name]

    if not piper.exists():
        raise RuntimeError(
            "Не найден piper.exe"
        )

    if not model.exists():
        raise RuntimeError(
            f"Не найдена модель голоса:\n{model}"
        )

    espeak_path = BASE / "espeak-ng-data"

    if not espeak_path.exists():
        raise RuntimeError(
            "Не найдена папка espeak-ng-data"
        )

    env = os.environ.copy()

    env["ESPEAK_DATA_PATH"] = str(
        espeak_path
    )

    result = subprocess.run(
        [
            str(piper),
            "--model",
            str(model),
            "--output_file",
            str(output_file)
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
        raise RuntimeError(
            result.stderr[-3000:]
        )


# ==========================================
# ПРОДОЛЖИТЕЛЬНОСТЬ АУДИО
# ==========================================

def audio_duration(path):

    with wave.open(
        str(path),
        "rb"
    ) as audio:

        return (
            audio.getnframes()
            / audio.getframerate()
        )


# ==========================================
# СОЗДАНИЕ ВИДЕОСЦЕНЫ
# ==========================================

def create_scene_video(
    background,
    overlay,
    audio,
    output
):

    ffmpeg = BASE / "ffmpeg.exe"

    if not ffmpeg.exists():
        raise RuntimeError(
            "Не найден ffmpeg.exe"
        )

    duration = audio_duration(audio)

    if duration <= 0:
        raise RuntimeError(
            "Озвучка имеет нулевую длительность"
        )

    command = [
        str(ffmpeg),
        "-y"
    ]

    # Выбираем источник фона.

    if background:

        extension = Path(
            background
        ).suffix.lower()

        if extension in [
            ".jpg",
            ".jpeg",
            ".png"
        ]:

            command += [
                "-loop", "1",
                "-framerate", str(FPS),
                "-i", str(background)
            ]

        elif extension == ".mp4":

            command += [
                "-stream_loop", "-1",
                "-i", str(background)
            ]

        else:

            raise RuntimeError(
                "Неподдерживаемый формат материала"
            )

    else:

        command += [
            "-f", "lavfi",
            "-i",
            (
                f"color=c=0x080B16:"
                f"s={WIDTH}x{HEIGHT}:"
                f"r={FPS}"
            )
        ]

    command += [
        "-loop", "1",
        "-framerate", str(FPS),
        "-i", str(overlay),
        "-i", str(audio)
    ]

    filter_complex = (
        "[0:v]"
        "scale=720:1280:"
        "force_original_aspect_ratio=increase,"
        "crop=720:1280,"
        "setsar=1,"
        "fps=25,"
        "format=yuv420p[bg];"
        "[bg][1:v]"
        "overlay=0:0:"
        "format=auto,"
        "format=yuv420p[v]"
    )

    command += [
        "-filter_complex",
        filter_complex,

        "-map", "[v]",
        "-map", "2:a:0",

        "-t", str(duration),

        "-r", str(FPS),

        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "26",

        "-pix_fmt", "yuv420p",

        "-c:a", "aac",
        "-b:a", "128k",

        "-ar", "44100",

        "-movflags", "+faststart",

        str(output)
    ]

    run_command(command)


# ==========================================
# ДОБАВЛЕНИЕ МАТЕРИАЛОВ
# ==========================================

def add_materials():

    files = filedialog.askopenfilenames(
        title="Выберите фотографии и видео",
        filetypes=[
            (
                "Медиафайлы",
                "*.mp4 *.jpg *.jpeg *.png"
            )
        ]
    )

    for file in files:

        if file not in materials:
            materials.append(file)

    update_materials()


def update_materials():

    materials_list.delete(
        0,
        tk.END
    )

    for file in materials:

        materials_list.insert(
            tk.END,
            Path(file).name
        )


def clear_materials():

    materials.clear()
    scene_assignments.clear()

    update_materials()

    status_var.set(
        "Материалы очищены"
    )


# ==========================================
# ПОДГОТОВКА СЦЕН
# ==========================================

def prepare_scenes():

    global scenes

    script = script_text.get(
        "1.0",
        tk.END
    ).strip()

    if not script:

        messagebox.showwarning(
            "Ошибка",
            "Введите сценарий"
        )

        return

    scenes = split_text(script)

    scene_assignments.clear()

    scene_list.delete(
        0,
        tk.END
    )

    for index, scene in enumerate(scenes):

        scene_list.insert(
            tk.END,
            f"{index + 1}. {scene[:65]}"
        )

    status_var.set(
        f"Подготовлено сцен: {len(scenes)}"
    )


# ==========================================
# РУЧНОЕ НАЗНАЧЕНИЕ МАТЕРИАЛОВ
# ==========================================

def assign_material():

    selected_scene = scene_list.curselection()

    selected_material = (
        materials_list.curselection()
    )

    if not selected_scene or not selected_material:

        messagebox.showwarning(
            "Ошибка",
            "Выберите сцену и материал"
        )

        return

    scene_index = selected_scene[0]
    material_index = selected_material[0]

    scene_assignments[scene_index] = (
        materials[material_index]
    )

    status_var.set(
        f"Материал назначен сцене {scene_index + 1}"
    )


# ==========================================
# СОЗДАНИЕ ВИДЕО
# ==========================================

def build_video():

    title = title_entry.get().strip()

    script = script_text.get(
        "1.0",
        tk.END
    ).strip()

    voice = voice_var.get()
    mode = mode_var.get()

    if not title or not script:

        messagebox.showwarning(
            "Ошибка",
            "Введите название и сценарий"
        )

        return

    current_scenes = split_text(script)

    # Передаём копии данных, чтобы изменения
    # интерфейса не влияли на текущую сборку.

    current_materials = list(materials)

    current_assignments = dict(
        scene_assignments
    )

    create_button.config(
        state="disabled"
    )

    status_var.set(
        "Создание видео..."
    )

    thread = threading.Thread(
        target=process_video,
        args=(
            title,
            current_scenes,
            voice,
            mode,
            current_materials,
            current_assignments
        ),
        daemon=True
    )

    thread.start()


def process_video(
    title,
    current_scenes,
    voice,
    mode,
    current_materials,
    current_assignments
):

    try:

        timestamp = (
            datetime.datetime.now().strftime(
                "%Y%m%d_%H%M%S"
            )
        )

        project_id = (
            timestamp + "_" + uuid.uuid4().hex[:6]
        )

        workdir = PROJECTS / project_id

        workdir.mkdir(
            exist_ok=True
        )

        video_files = []

        total = len(current_scenes)

        for index, scene in enumerate(current_scenes):

            root.after(
                0,
                lambda i=index, n=total:
                status_var.set(
                    f"Создание сцены {i + 1}/{n}"
                )
            )

            image = (
                workdir / f"overlay_{index:03d}.png"
            )

            audio = (
                workdir / f"audio_{index:03d}.wav"
            )

            video = (
                workdir / f"scene_{index:03d}.mp4"
            )

            create_overlay(
                title,
                scene,
                index + 1,
                total,
                image
            )

            generate_audio(
                scene,
                voice,
                audio
            )

            background = None

            if mode == "Авто":

                if current_materials:

                    background = current_materials[
                        index % len(current_materials)
                    ]

            else:

                background = (
                    current_assignments.get(index)
                )

            create_scene_video(
                background,
                image,
                audio,
                video
            )

            video_files.append(video)

        # ==================================
        # ОБЪЕДИНЕНИЕ СЦЕН
        # ==================================

        concat_file = (
            workdir / "concat.txt"
        )

        lines = []

        for video in video_files:

            lines.append(
                f"file '{video.name}'"
            )

        concat_file.write_text(
            "\n".join(lines),
            encoding="utf-8"
        )

        output_file = (
            OUTPUT / f"neurohack_{project_id}.mp4"
        )

        run_command(
            [
                str(BASE / "ffmpeg.exe"),

                "-y",

                "-f", "concat",
                "-safe", "0",

                "-i", "concat.txt",

                "-c", "copy",

                "-movflags", "+faststart",

                str(output_file)
            ],
            cwd=str(workdir)
        )

        # ==================================
        # СОХРАНЕНИЕ ИНФОРМАЦИИ О ПРОЕКТЕ
        # ==================================

        project_info = {
            "title": title,
            "voice": voice,
            "mode": mode,
            "scenes": current_scenes,
            "materials": current_materials,
            "assignments": current_assignments,
            "output": str(output_file)
        }

        project_file = (
            workdir / "project.json"
        )

        project_file.write_text(
            json.dumps(
                project_info,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        root.after(
            0,
            lambda: status_var.set(
                "Видео успешно создано!"
            )
        )

        root.after(
            0,
            lambda: messagebox.showinfo(
                "Готово!",
                f"Видео сохранено:\n{output_file}"
            )
        )

    except Exception as error:

        error_text = str(error)

        root.after(
            0,
            lambda: status_var.set(
                "Ошибка создания видео"
            )
        )

        root.after(
            0,
            lambda: messagebox.showerror(
                "Ошибка",
                error_text
            )
        )

    finally:

        root.after(
            0,
            lambda: create_button.config(
                state="normal"
            )
        )


# ==========================================
# ОТКРЫТИЕ ПАПОК
# ==========================================

def open_output():
    os.startfile(OUTPUT)


def open_projects():
    os.startfile(PROJECTS)


# ==========================================
# ГРАФИЧЕСКИЙ ИНТЕРФЕЙС
# ==========================================

root = tk.Tk()

root.title(APP_NAME)

root.geometry("850x650")
root.minsize(650, 480)

root.configure(bg=BG)


# ==========================================
# ЗАГОЛОВОК
# ==========================================

header = tk.Frame(
    root,
    bg=BG
)

header.pack(
    fill="x"
)

tk.Label(
    header,
    text="⚡ НЕЙРОХАК СТУДИЯ 3.1",
    font=("Arial", 21, "bold"),
    fg=CYAN,
    bg=BG
).pack(pady=12)


# ==========================================
# НИЖНЯЯ ПАНЕЛЬ
# КНОПКА ВСЕГДА ВИДНА
# ==========================================

bottom_frame = tk.Frame(
    root,
    bg=BG
)

bottom_frame.pack(
    side="bottom",
    fill="x"
)

status_var = tk.StringVar(
    value="Готов к работе"
)

create_button = tk.Button(
    bottom_frame,
    text="🎬 СОЗДАТЬ VK КЛИП",
    command=build_video,
    bg=CYAN,
    fg="black",
    font=("Arial", 13, "bold"),
    height=2
)

create_button.pack(
    fill="x",
    padx=20,
    pady=5
)

tk.Label(
    bottom_frame,
    textvariable=status_var,
    fg=CYAN,
    bg=BG,
    font=("Arial", 10)
).pack(pady=5)


# ==========================================
# ВКЛАДКИ
# ==========================================

notebook = ttk.Notebook(root)

notebook.pack(
    fill="both",
    expand=True,
    padx=15,
    pady=10
)

tab_video = tk.Frame(
    notebook,
    bg=BG
)

tab_materials = tk.Frame(
    notebook,
    bg=BG
)

tab_settings = tk.Frame(
    notebook,
    bg=BG
)

notebook.add(
    tab_video,
    text="🎬 Создание видео"
)

notebook.add(
    tab_materials,
    text="📁 Материалы"
)

notebook.add(
    tab_settings,
    text="⚙ Настройки"
)


# ==========================================
# ВКЛАДКА 1. СОЗДАНИЕ ВИДЕО
# ==========================================

tk.Label(
    tab_video,
    text="Название ролика",
    fg=WHITE,
    bg=BG
).pack(pady=(10, 2))

title_entry = tk.Entry(
    tab_video,
    font=("Arial", 12)
)

title_entry.pack(
    fill="x",
    padx=20,
    pady=5
)

setup_clipboard(title_entry)


tk.Label(
    tab_video,
    text="Сценарий видео",
    fg=WHITE,
    bg=BG
).pack(pady=5)

script_frame = tk.Frame(
    tab_video,
    bg=BG
)

script_frame.pack(
    fill="both",
    expand=True,
    padx=20,
    pady=5
)

script_scroll = tk.Scrollbar(
    script_frame
)

script_scroll.pack(
    side="right",
    fill="y"
)

script_text = tk.Text(
    script_frame,
    font=("Arial", 11),
    wrap="word",
    undo=True,
    yscrollcommand=script_scroll.set
)

script_text.pack(
    side="left",
    fill="both",
    expand=True
)

script_scroll.config(
    command=script_text.yview
)

setup_clipboard(script_text)


# ==========================================
# НАСТРОЙКИ ГОЛОСА И РЕЖИМА
# ==========================================

controls_frame = tk.Frame(
    tab_video,
    bg=BG
)

controls_frame.pack(
    fill="x",
    padx=20,
    pady=10
)

voice_var = tk.StringVar(
    value="Мужской"
)

mode_var = tk.StringVar(
    value="Авто"
)

tk.Label(
    controls_frame,
    text="Голос:",
    fg=WHITE,
    bg=BG
).pack(side="left")

ttk.Combobox(
    controls_frame,
    textvariable=voice_var,
    values=[
        "Мужской",
        "Женский"
    ],
    state="readonly",
    width=15
).pack(
    side="left",
    padx=10
)

tk.Label(
    controls_frame,
    text="Режим:",
    fg=WHITE,
    bg=BG
).pack(
    side="left",
    padx=(15, 0)
)

ttk.Combobox(
    controls_frame,
    textvariable=mode_var,
    values=[
        "Авто",
        "Ручной"
    ],
    state="readonly",
    width=15
).pack(
    side="left",
    padx=10
)


# ==========================================
# ВКЛАДКА 2. МАТЕРИАЛЫ
# ==========================================

materials_buttons = tk.Frame(
    tab_materials,
    bg=BG
)

materials_buttons.pack(
    fill="x",
    pady=10
)

tk.Button(
    materials_buttons,
    text="📁 Добавить фото и видео",
    command=add_materials,
    bg=CYAN
).pack(
    side="left",
    padx=10
)

tk.Button(
    materials_buttons,
    text="Очистить материалы",
    command=clear_materials,
    bg=PURPLE,
    fg=WHITE
).pack(
    side="left",
    padx=10
)


tk.Label(
    tab_materials,
    text="Добавленные материалы",
    fg=WHITE,
    bg=BG
).pack()

materials_list = tk.Listbox(
    tab_materials,
    height=5
)

materials_list.pack(
    fill="x",
    padx=20,
    pady=5
)


tk.Button(
    tab_materials,
    text="Подготовить сцены",
    command=prepare_scenes,
    bg=PURPLE,
    fg=WHITE
).pack(pady=5)


tk.Label(
    tab_materials,
    text="Сцены",
    fg=WHITE,
    bg=BG
).pack()

scene_list = tk.Listbox(
    tab_materials,
    height=5
)

scene_list.pack(
    fill="both",
    expand=True,
    padx=20,
    pady=5
)


tk.Button(
    tab_materials,
    text="🔗 Назначить материал сцене",
    command=assign_material,
    bg=CYAN
).pack(pady=10)


# ==========================================
# ВКЛАДКА 3. НАСТРОЙКИ
# ==========================================

tk.Label(
    tab_settings,
    text="НЕЙРОХАК СТУДИЯ 3.1",
    font=("Arial", 17, "bold"),
    fg=CYAN,
    bg=BG
).pack(pady=20)


tk.Label(
    tab_settings,
    text=(
        "Формат: 720 × 1280\n"
        "Частота: 25 FPS\n"
        "Кодек: H.264\n"
        "Озвучка: Piper TTS\n"
        "Монтаж: FFmpeg"
    ),
    fg=WHITE,
    bg=BG,
    font=("Arial", 12),
    justify="center"
).pack(pady=15)


tk.Button(
    tab_settings,
    text="📁 Открыть готовые видео",
    command=open_output,
    bg=PURPLE,
    fg=WHITE
).pack(pady=10)


tk.Button(
    tab_settings,
    text="📁 Открыть проекты",
    command=open_projects,
    bg=PURPLE,
    fg=WHITE
).pack(pady=10)


# ==========================================
# ЗАПУСК
# ==========================================

root.mainloop()

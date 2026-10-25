import os
import sys
import re
import json
import wave
import uuid
import threading
import subprocess
import traceback
import datetime

from pathlib import Path

import tkinter as tk

from tkinter import (
    ttk,
    filedialog,
    messagebox
)

from PIL import (
    Image,
    ImageDraw,
    ImageFont
)


# ==========================================
# НЕЙРОХАК СТУДИЯ 3.3
# ==========================================

VERSION = "3.3"

APP_NAME = f"НЕЙРОХАК СТУДИЯ {VERSION}"

WIDTH = 720
HEIGHT = 1280
FPS = 25

BG = "#080B16"
CYAN = "#00D9FF"
PURPLE = "#8B5CF6"
WHITE = "#FFFFFF"


# ==========================================
# ПАПКИ
# ==========================================

def get_base_dir():

    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).parent


BASE = get_base_dir()

OUTPUT = BASE / "output"
PROJECTS = BASE / "projects"
VOICES = BASE / "voices"

OUTPUT.mkdir(
    parents=True,
    exist_ok=True
)

PROJECTS.mkdir(
    parents=True,
    exist_ok=True
)

LOG_FILE = BASE / "error_log.txt"

FONT = Path(
    "C:/Windows/Fonts/arial.ttf"
)

PIPER = BASE / "piper.exe"
FFMPEG = BASE / "ffmpeg.exe"

ESPEAK = BASE / "espeak-ng-data"


# ==========================================
# ДАННЫЕ
# ==========================================

materials = []

assignments = {}

scenes = []


VOICE_MODELS = {

    "Мужской":
        "ru_RU-ruslan-medium.onnx",

    "Женский":
        "ru_RU-irina-medium.onnx"

}


# ==========================================
# ЖУРНАЛ ОШИБОК
# ==========================================

def write_log(text):

    timestamp = datetime.datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    with open(
        LOG_FILE,
        "a",
        encoding="utf-8"
    ) as file:

        file.write(
            f"\n\n[{timestamp}]\n{text}\n"
        )


def report_error(error):

    details = traceback.format_exc()

    try:
        write_log(details)
    except OSError:
        pass

    message = str(error).strip()

    if not message:
        message = repr(error)

    root.after(
        0,
        lambda text=message: messagebox.showerror(
            "Ошибка",
            text[-2500:]
        )
    )

    set_status(
        "Ошибка. Подробности в error_log.txt"
    )


# ==========================================
# ОБНОВЛЕНИЕ ИНТЕРФЕЙСА
# ==========================================

def set_status(text):

    root.after(
        0,
        lambda value=text: status_var.set(value)
    )


def show_success(text):

    root.after(
        0,
        lambda value=text: messagebox.showinfo(
            "Готово",
            value
        )
    )


def set_button_enabled(button, enabled):

    root.after(
        0,
        lambda: button.config(
            state="normal" if enabled else "disabled"
        )
    )


# ==========================================
# КОПИРОВАНИЕ И ВСТАВКА
# ==========================================

def enable_clipboard(widget):

    menu = tk.Menu(
        widget,
        tearoff=0
    )

    def select_all():

        widget.focus_set()

        if isinstance(widget, tk.Text):

            widget.tag_add(
                "sel",
                "1.0",
                "end-1c"
            )

            widget.mark_set(
                "insert",
                "1.0"
            )

        else:

            widget.select_range(
                0,
                tk.END
            )

    menu.add_command(
        label="Вырезать",
        command=lambda: widget.event_generate(
            "<<Cut>>"
        )
    )

    menu.add_command(
        label="Копировать",
        command=lambda: widget.event_generate(
            "<<Copy>>"
        )
    )

    menu.add_command(
        label="Вставить",
        command=lambda: widget.event_generate(
            "<<Paste>>"
        )
    )

    menu.add_separator()

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

    widget.bind(
        "<Button-3>",
        show_menu
    )

    def handle_keys(event):

        # Ctrl
        if not (event.state & 0x4):
            return None

        # Не перехватываем Alt+Ctrl
        if event.state & 0x8:
            return None

        key = event.keycode

        # A
        if key == 65:

            select_all()

            return "break"

        actions = {

            67: "<<Copy>>",
            86: "<<Paste>>",
            88: "<<Cut>>"

        }

        if key in actions:

            widget.event_generate(
                actions[key]
            )

            return "break"

        return None

    widget.bind(
        "<KeyPress>",
        handle_keys
    )


# ==========================================
# ЗАПУСК ВНЕШНИХ ПРОГРАММ
# ==========================================

def run_command(command, cwd=None):

    result = subprocess.run(

        command,

        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,

        cwd=cwd,

        creationflags=subprocess.CREATE_NO_WINDOW

    )

    if result.returncode != 0:

        stderr = result.stderr.decode(
            "utf-8",
            errors="replace"
        )

        stdout = result.stdout.decode(
            "utf-8",
            errors="replace"
        )

        details = stderr or stdout

        if not details.strip():

            details = (
                f"Код завершения: {result.returncode}"
            )

        raise RuntimeError(
            details[-3000:]
        )

    return result


# ==========================================
# ПРОВЕРКА КОМПОНЕНТОВ
# ==========================================

def check_components(voice):

    model = VOICES / VOICE_MODELS[voice]

    required = [

        PIPER,
        FFMPEG,
        ESPEAK,
        model,
        Path(str(model) + ".json")

    ]

    missing = [

        str(path)

        for path in required

        if not path.exists()

    ]

    if missing:

        raise RuntimeError(

            "Не найдены необходимые компоненты:\n\n"

            + "\n".join(missing)

        )

    if not FONT.exists():

        raise RuntimeError(
            "Не найден шрифт Arial"
        )

    return model


# ==========================================
# РУССКАЯ ОЗВУЧКА
# ==========================================

def generate_voice(text, voice, output_file):

    model = check_components(voice)

    env = os.environ.copy()

    env["ESPEAK_DATA_PATH"] = str(
        ESPEAK
    )

    # Передаём текст как UTF-8 bytes.
    # Это исключает преобразование через
    # системную кодировку Windows.

    input_data = (
        text.strip() + "\n"
    ).encode("utf-8")

    command = [

        str(PIPER),

        "--model",
        str(model),

        "--output_file",
        str(output_file)

    ]

    result = subprocess.run(

        command,

        input=input_data,

        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,

        cwd=str(BASE),

        env=env,

        creationflags=subprocess.CREATE_NO_WINDOW

    )

    stderr = result.stderr.decode(
        "utf-8",
        errors="replace"
    )

    stdout = result.stdout.decode(
        "utf-8",
        errors="replace"
    )

    if result.returncode != 0:

        details = stderr or stdout

        if not details.strip():

            details = (
                f"Piper завершился с кодом "
                f"{result.returncode}"
            )

        raise RuntimeError(
            "Ошибка Piper:\n\n" + details[-2500:]
        )

    if not output_file.exists():

        raise RuntimeError(

            "Piper завершился без ошибки, "
            "но WAV-файл не создан.\n\n"

            + stderr[-1500:]

        )

    if output_file.stat().st_size < 100:

        raise RuntimeError(
            "Piper создал пустой аудиофайл"
        )

    # Проверяем WAV.

    try:

        with wave.open(
            str(output_file),
            "rb"
        ) as audio:

            if audio.getnframes() == 0:

                raise RuntimeError(
                    "Аудиофайл не содержит звука"
                )

    except wave.Error as error:

        raise RuntimeError(
            f"Некорректный WAV: {error}"
        )


# ==========================================
# ПРОВЕРКА ОЗВУЧКИ
# ==========================================

def test_voice():

    voice = voice_var.get()

    test_button.config(
        state="disabled"
    )

    set_status(
        "Проверяем озвучку..."
    )

    threading.Thread(

        target=run_voice_test,

        args=(voice,),

        daemon=True

    ).start()


def run_voice_test(voice):

    try:

        timestamp = datetime.datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        output_file = OUTPUT / (
            f"test_voice_{timestamp}.wav"
        )

        text = (

            "Привет! Это Нейрохак. "

            "Проверяем автоматическую "

            "русскую озвучку."

        )

        generate_voice(
            text,
            voice,
            output_file
        )

        set_status(
            "Озвучка работает!"
        )

        show_success(

            "Проверка успешно завершена!\n\n"

            f"Файл:\n{output_file}\n\n"

            "Открой его и проверь звук."

        )

    except Exception as error:

        report_error(error)

    finally:

        set_button_enabled(
            test_button,
            True
        )


# ==========================================
# ДЛИТЕЛЬНОСТЬ АУДИО
# ==========================================

def audio_duration(path):

    with wave.open(
        str(path),
        "rb"
    ) as audio:

        frames = audio.getnframes()

        rate = audio.getframerate()

        return frames / rate


# ==========================================
# РАЗДЕЛЕНИЕ ТЕКСТА
# ==========================================

def split_script(text, limit=85):

    words = text.strip().split()

    result = []

    current = ""

    for word in words:

        candidate = (
            current + " " + word
        ).strip()

        if len(candidate) <= limit:

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

    lines = []

    current = ""

    for word in text.split():

        candidate = (
            current + " " + word
        ).strip()

        bbox = draw.textbbox(

            (0, 0),

            candidate,

            font=font

        )

        width = bbox[2] - bbox[0]

        if width <= max_width:

            current = candidate

        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return "\n".join(lines)


# ==========================================
# КИБЕРПАНК-ОФОРМЛЕНИЕ
# ==========================================

def create_overlay(
    title,
    text,
    number,
    total,
    path
):

    image = Image.new(

        "RGBA",

        (WIDTH, HEIGHT),

        (0, 0, 0, 0)

    )

    draw = ImageDraw.Draw(image)

    brand_font = ImageFont.truetype(
        str(FONT),
        45
    )

    title_font = ImageFont.truetype(
        str(FONT),
        34
    )

    small_font = ImageFont.truetype(
        str(FONT),
        23
    )

    # Верхняя панель

    draw.rounded_rectangle(

        (25, 35, 695, 240),

        radius=25,

        fill=(8, 11, 22, 225),

        outline=CYAN,

        width=3

    )

    draw.text(

        (WIDTH // 2, 90),

        "НЕЙРОХАК",

        font=brand_font,

        fill=CYAN,

        anchor="mm"

    )

    wrapped_title = wrap_text(

        draw,

        title[:65],

        title_font,

        580

    )

    draw.multiline_text(

        (WIDTH // 2, 165),

        wrapped_title,

        font=title_font,

        fill=WHITE,

        anchor="mm",

        align="center",

        spacing=8

    )

    # Панель субтитров

    draw.rounded_rectangle(

        (25, 750, 695, 1120),

        radius=30,

        fill=(8, 11, 22, 230),

        outline=CYAN,

        width=3

    )

    selected_font = None

    wrapped = ""

    for size in range(36, 17, -2):

        font = ImageFont.truetype(
            str(FONT),
            size
        )

        candidate = wrap_text(

            draw,
            text,
            font,
            570

        )

        bbox = draw.multiline_textbbox(

            (0, 0),

            candidate,

            font=font,

            spacing=10

        )

        height = bbox[3] - bbox[1]

        if height <= 280:

            selected_font = font

            wrapped = candidate

            break

    if selected_font is None:

        raise RuntimeError(
            "Слишком длинный текст сцены"
        )

    draw.multiline_text(

        (WIDTH // 2, 930),

        wrapped,

        font=selected_font,

        fill=WHITE,

        anchor="mm",

        align="center",

        spacing=10

    )

    draw.text(

        (WIDTH // 2, 1190),

        f"VK • НЕЙРОХАК | {number}/{total}",

        font=small_font,

        fill=PURPLE,

        anchor="mm"

    )

    image.save(path)


# ==========================================
# СОЗДАНИЕ ВИДЕОСЦЕНЫ
# ==========================================

def create_video_scene(
    background,
    overlay,
    audio,
    output
):

    duration = audio_duration(audio)

    if duration <= 0:

        raise RuntimeError(
            "Нулевая длительность озвучки"
        )

    command = [

        str(FFMPEG),

        "-y"

    ]

    if background:

        extension = Path(
            background
        ).suffix.lower()

        if extension in (
            ".jpg",
            ".jpeg",
            ".png"
        ):

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

    filters = (

        "[0:v]"

        "scale=720:1280:"

        "force_original_aspect_ratio=increase,"

        "crop=720:1280,"

        "setsar=1,"

        "fps=25[bg];"

        "[bg][1:v]"

        "overlay=0:0,"

        "format=yuv420p[v]"

    )

    command += [

        "-filter_complex",
        filters,

        "-map", "[v]",

        "-map", "2:a:0",

        "-t", str(duration),

        "-c:v", "libx264",

        "-preset", "ultrafast",

        "-crf", "26",

        "-pix_fmt", "yuv420p",

        "-r", str(FPS),

        "-c:a", "aac",

        "-b:a", "128k",

        "-ar", "44100",

        "-movflags", "+faststart",

        str(output)

    ]

    run_command(command)

    if not output.exists():

        raise RuntimeError(
            "FFmpeg не создал MP4"
        )

    if output.stat().st_size == 0:

        raise RuntimeError(
            "Создан пустой MP4"
        )


# ==========================================
# МАТЕРИАЛЫ
# ==========================================

def add_materials():

    files = filedialog.askopenfilenames(

        title="Выберите фото и видео",

        filetypes=[

            (
                "Медиа",
                "*.mp4 *.jpg *.jpeg *.png"
            )

        ]

    )

    for file in files:

        if file not in materials:
            materials.append(file)

    refresh_materials()


def refresh_materials():

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

    assignments.clear()

    refresh_materials()

    set_status(
        "Материалы очищены"
    )


# ==========================================
# ПОДГОТОВКА СЦЕН
# ==========================================

def prepare_scenes():

    global scenes

    text = script_text.get(
        "1.0",
        "end-1c"
    ).strip()

    if not text:

        messagebox.showwarning(
            "Ошибка",
            "Введите сценарий"
        )

        return

    scenes = split_script(text)

    assignments.clear()

    scene_list.delete(
        0,
        tk.END
    )

    for index, scene in enumerate(scenes):

        scene_list.insert(

            tk.END,

            f"{index + 1}. {scene[:60]}"

        )

    set_status(
        f"Подготовлено сцен: {len(scenes)}"
    )


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

    index = selected_scene[0]

    assignments[index] = (
        materials[selected_material[0]]
    )

    set_status(
        f"Материал назначен сцене {index + 1}"
    )


# ==========================================
# ЗАПУСК СОЗДАНИЯ ВИДЕО
# ==========================================

def start_creation():

    title = title_entry.get().strip()

    script = script_text.get(
        "1.0",
        "end-1c"
    ).strip()

    voice = voice_var.get()

    mode = mode_var.get()

    if not title or not script:

        messagebox.showwarning(

            "Ошибка",

            "Введите название и сценарий"

        )

        return

    try:

        check_components(voice)

    except Exception as error:

        messagebox.showerror(
            "Ошибка компонентов",
            str(error)
        )

        return

    current_scenes = split_script(script)

    if mode == "Ручной" and current_scenes != scenes:

        messagebox.showwarning(

            "Подготовьте сцены",

            "Перейдите во вкладку «Материалы» "
            "и нажмите «Подготовить сцены»."

        )

        return

    create_button.config(
        state="disabled"
    )

    set_status(
        "Создание видео..."
    )

    threading.Thread(

        target=process_video,

        args=(

            title,

            current_scenes,

            voice,

            mode,

            list(materials),

            dict(assignments)

        ),

        daemon=True

    ).start()


# ==========================================
# СБОРКА ВИДЕО
# ==========================================

def process_video(
    title,
    current_scenes,
    voice,
    mode,
    current_materials,
    current_assignments
):

    try:

        timestamp = datetime.datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        project_id = (
            timestamp + "_" + uuid.uuid4().hex[:6]
        )

        workdir = PROJECTS / project_id

        workdir.mkdir(
            parents=True,
            exist_ok=True
        )

        video_files = []

        total = len(current_scenes)

        for index, scene in enumerate(current_scenes):

            set_status(

                f"Создание сцены {index + 1}/{total}"

            )

            overlay = (
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

                overlay

            )

            generate_voice(

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

                background = current_assignments.get(
                    index
                )

            create_video_scene(

                background,

                overlay,

                audio,

                video

            )

            video_files.append(video)

        # ==================================
        # ОБЪЕДИНЕНИЕ СЦЕН
        # ==================================

        set_status(
            "Объединяем видео..."
        )

        concat_file = workdir / "concat.txt"

        lines = [

            f"file '{video.name}'"

            for video in video_files

        ]

        concat_file.write_text(

            "\n".join(lines),

            encoding="utf-8"

        )

        final_video = OUTPUT / (
            f"neurohack_{project_id}.mp4"
        )

        run_command(

            [

                str(FFMPEG),

                "-y",

                "-f", "concat",

                "-safe", "0",

                "-i", "concat.txt",

                "-c", "copy",

                "-movflags", "+faststart",

                str(final_video)

            ],

            cwd=str(workdir)

        )

        if not final_video.exists():

            raise RuntimeError(
                "Итоговое видео не создано"
            )

        if final_video.stat().st_size == 0:

            raise RuntimeError(
                "Итоговый MP4 пуст"
            )

        # ==================================
        # СОХРАНЕНИЕ ПРОЕКТА
        # ==================================

        project_data = {

            "title": title,

            "voice": voice,

            "mode": mode,

            "scenes": current_scenes,

            "materials": current_materials,

            "assignments": current_assignments,

            "output": str(final_video)

        }

        (workdir / "project.json").write_text(

            json.dumps(

                project_data,

                ensure_ascii=False,

                indent=2

            ),

            encoding="utf-8"

        )

        set_status(
            "Видео успешно создано!"
        )

        show_success(

            "Готово!\n\n"

            f"Видео сохранено:\n{final_video}"

        )

    except Exception as error:

        report_error(error)

    finally:

        set_button_enabled(
            create_button,
            True
        )


# ==========================================
# ОТКРЫТИЕ ПАПОК
# ==========================================

def open_output():

    os.startfile(OUTPUT)


def open_projects():

    os.startfile(PROJECTS)


def open_log():

    if not LOG_FILE.exists():

        messagebox.showinfo(

            "Журнал",

            "Ошибок пока не зарегистрировано."

        )

        return

    os.startfile(LOG_FILE)


# ==========================================
# ИНТЕРФЕЙС
# ==========================================

root = tk.Tk()

root.title(APP_NAME)

root.geometry("850x650")

root.minsize(650, 480)

root.configure(bg=BG)


# ==========================================
# ВЕРХНЯЯ ПАНЕЛЬ
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

    text="⚡ НЕЙРОХАК СТУДИЯ 3.3",

    font=("Arial", 21, "bold"),

    fg=CYAN,

    bg=BG

).pack(pady=12)


# ==========================================
# НИЖНЯЯ ПАНЕЛЬ
# ==========================================

bottom = tk.Frame(
    root,
    bg=BG
)

bottom.pack(

    side="bottom",

    fill="x"

)

status_var = tk.StringVar(
    value="Готов к работе"
)

create_button = tk.Button(

    bottom,

    text="🎬 СОЗДАТЬ VK КЛИП",

    command=start_creation,

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

    bottom,

    textvariable=status_var,

    fg=CYAN,

    bg=BG

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

tab_media = tk.Frame(
    notebook,
    bg=BG
)

tab_settings = tk.Frame(
    notebook,
    bg=BG
)

notebook.add(
    tab_video,
    text="Создание видео"
)

notebook.add(
    tab_media,
    text="Материалы"
)

notebook.add(
    tab_settings,
    text="Настройки"
)


# ==========================================
# СОЗДАНИЕ ВИДЕО
# ==========================================

tk.Label(

    tab_video,

    text="Название ролика",

    fg=WHITE,

    bg=BG

).pack(pady=5)

title_entry = tk.Entry(

    tab_video,

    font=("Arial", 12)

)

title_entry.pack(

    fill="x",

    padx=20,

    pady=5

)

enable_clipboard(title_entry)


tk.Label(

    tab_video,

    text="Сценарий видео",

    fg=WHITE,

    bg=BG

).pack(pady=5)


text_frame = tk.Frame(
    tab_video,
    bg=BG
)

text_frame.pack(

    fill="both",

    expand=True,

    padx=20

)


scrollbar = tk.Scrollbar(
    text_frame
)

scrollbar.pack(

    side="right",

    fill="y"

)


script_text = tk.Text(

    text_frame,

    font=("Arial", 11),

    wrap="word",

    undo=True,

    yscrollcommand=scrollbar.set

)

script_text.pack(

    side="left",

    fill="both",

    expand=True

)

scrollbar.config(
    command=script_text.yview
)

enable_clipboard(script_text)


# ==========================================
# ГОЛОС И РЕЖИМ
# ==========================================

controls = tk.Frame(
    tab_video,
    bg=BG
)

controls.pack(pady=10)


voice_var = tk.StringVar(
    value="Мужской"
)

mode_var = tk.StringVar(
    value="Авто"
)


tk.Label(

    controls,

    text="Голос:",

    fg=WHITE,

    bg=BG

).pack(side="left")


ttk.Combobox(

    controls,

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

    controls,

    text="Режим:",

    fg=WHITE,

    bg=BG

).pack(side="left")


ttk.Combobox(

    controls,

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
# КНОПКА ПРОВЕРКИ ГОЛОСА
# ==========================================

test_button = tk.Button(

    tab_video,

    text="🎙 ПРОВЕРИТЬ ОЗВУЧКУ",

    command=test_voice,

    bg=PURPLE,

    fg=WHITE,

    font=("Arial", 11, "bold")

)

test_button.pack(
    pady=10
)


# ==========================================
# ВКЛАДКА МАТЕРИАЛОВ
# ==========================================

media_buttons = tk.Frame(
    tab_media,
    bg=BG
)

media_buttons.pack(pady=10)


tk.Button(

    media_buttons,

    text="Добавить фото и видео",

    command=add_materials,

    bg=CYAN

).pack(

    side="left",

    padx=10

)


tk.Button(

    media_buttons,

    text="Очистить",

    command=clear_materials,

    bg=PURPLE,

    fg=WHITE

).pack(

    side="left",

    padx=10

)


tk.Label(

    tab_media,

    text="Загруженные материалы",

    fg=WHITE,

    bg=BG

).pack()


materials_list = tk.Listbox(

    tab_media,

    height=5

)

materials_list.pack(

    fill="x",

    padx=20,

    pady=5

)


tk.Button(

    tab_media,

    text="Подготовить сцены",

    command=prepare_scenes,

    bg=PURPLE,

    fg=WHITE

).pack(pady=5)


tk.Label(

    tab_media,

    text="Список сцен",

    fg=WHITE,

    bg=BG

).pack()


scene_list = tk.Listbox(

    tab_media,

    height=5

)

scene_list.pack(

    fill="both",

    expand=True,

    padx=20,

    pady=5

)


tk.Button(

    tab_media,

    text="Назначить материал сцене",

    command=assign_material,

    bg=CYAN

).pack(pady=10)


# ==========================================
# ВКЛАДКА НАСТРОЕК
# ==========================================

tk.Label(

    tab_settings,

    text="НЕЙРОХАК СТУДИЯ 3.3",

    font=("Arial", 17, "bold"),

    fg=CYAN,

    bg=BG

).pack(pady=20)


tk.Label(

    tab_settings,

    text=(

        "Разрешение: 720 × 1280\n"

        "Частота: 25 FPS\n"

        "Кодек: H.264\n"

        "Озвучка: Piper TTS\n"

        "Монтаж: FFmpeg\n"

        "Работа без платных API"

    ),

    fg=WHITE,

    bg=BG,

    font=("Arial", 12),

    justify="center"

).pack(pady=15)


tk.Button(

    tab_settings,

    text="Открыть готовые видео",

    command=open_output,

    bg=PURPLE,

    fg=WHITE

).pack(pady=5)


tk.Button(

    tab_settings,

    text="Открыть проекты",

    command=open_projects,

    bg=PURPLE,

    fg=WHITE

).pack(pady=5)


tk.Button(

    tab_settings,

    text="Открыть журнал ошибок",

    command=open_log,

    bg=PURPLE,

    fg=WHITE

).pack(pady=5)


# ==========================================
# ЗАПУСК
# ==========================================

root.mainloop()

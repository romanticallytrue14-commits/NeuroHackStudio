import os
import sys
import json
import wave
import uuid
import threading
import subprocess
import traceback
import datetime
import tkinter as tk

from pathlib import Path
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageDraw, ImageFont


# ==========================================
# НАСТРОЙКИ
# ==========================================

VERSION = "3.4"
APP_NAME = f"НЕЙРОХАК СТУДИЯ {VERSION}"

WIDTH = 720
HEIGHT = 1280
FPS = 25

BG = "#080B16"
CYAN = "#00D9FF"
PURPLE = "#8B5CF6"
WHITE = "#FFFFFF"


def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


BASE = get_base_dir()

OUTPUT = BASE / "output"
PROJECTS = BASE / "projects"
VOICES = BASE / "voices"

for folder in (OUTPUT, PROJECTS):
    folder.mkdir(parents=True, exist_ok=True)

PIPER = BASE / "piper.exe"
FFMPEG = BASE / "ffmpeg.exe"
ESPEAK = BASE / "espeak-ng-data"

FONT = Path("C:/Windows/Fonts/arial.ttf")
LOG_FILE = BASE / "error_log.txt"

VOICE_MODELS = {
    "Мужской": "ru_RU-ruslan-medium.onnx",
    "Женский": "ru_RU-irina-medium.onnx"
}

materials = []
assignments = {}
prepared_scenes = []


# ==========================================
# ИНТЕРФЕЙС И ОШИБКИ
# ==========================================

def set_status(text):
    root.after(
        0,
        lambda value=text: status_var.set(value)
    )


def show_info(text):
    root.after(
        0,
        lambda value=text: messagebox.showinfo(
            "НЕЙРОХАК",
            value
        )
    )


def set_button(button, enabled):
    root.after(
        0,
        lambda: button.config(
            state="normal" if enabled else "disabled"
        )
    )


def report_error(error):
    details = traceback.format_exc()

    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(
                "\n\n" +
                datetime.datetime.now().isoformat() +
                "\n" + details
            )
    except OSError:
        pass

    text = str(error).strip() or repr(error)

    set_status("Ошибка. Открой журнал во вкладке Настройки.")

    root.after(
        0,
        lambda value=text: messagebox.showerror(
            "Ошибка",
            value[-2500:]
        )
    )


# ==========================================
# КОПИРОВАНИЕ И ВСТАВКА
# ==========================================

def enable_clipboard(widget):

    menu = tk.Menu(widget, tearoff=0)

    def select_all():
        widget.focus_set()

        if isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "1.0")
        else:
            widget.select_range(0, tk.END)

    menu.add_command(
        label="Вырезать",
        command=lambda: widget.event_generate("<<Cut>>")
    )

    menu.add_command(
        label="Копировать",
        command=lambda: widget.event_generate("<<Copy>>")
    )

    menu.add_command(
        label="Вставить",
        command=lambda: widget.event_generate("<<Paste>>")
    )

    menu.add_separator()

    menu.add_command(
        label="Выделить всё",
        command=select_all
    )

    def popup(event):
        widget.focus_set()

        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", popup)

    def keyboard(event):
        if not event.state & 0x4:
            return None

        if event.state & 0x8:
            return None

        actions = {
            67: "<<Copy>>",
            86: "<<Paste>>",
            88: "<<Cut>>"
        }

        # Используем Windows keycode.
        # Не зависит от русского символа клавиши.

        if event.keycode == 65:
            select_all()
            return "break"

        if event.keycode in actions:
            widget.event_generate(
                actions[event.keycode]
            )
            return "break"

        return None

    widget.bind("<KeyPress>", keyboard)


# ==========================================
# ВНЕШНИЕ КОМАНДЫ
# ==========================================

def run_command(command, cwd=None, env=None, input_data=None):

    result = subprocess.run(
        command,
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
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

        details = stderr.strip() or stdout.strip()

        if not details:
            details = "Нет дополнительного вывода."

        raise RuntimeError(
            f"Команда завершилась с кодом "
            f"{result.returncode}\n\n{details[-2500:]}"
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
        Path(str(model) + ".json"),
        FONT
    ]

    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]

    if missing:
        raise RuntimeError(
            "Не найдены компоненты:\n\n" +
            "\n".join(missing)
        )

    if not (ESPEAK / "phontab").exists():
        raise RuntimeError(
            "В папке espeak-ng-data отсутствует phontab."
        )

    return model


# ==========================================
# ОЗВУЧКА
# ==========================================

def generate_voice(text, voice, output_file):

    model = check_components(voice)

    env = os.environ.copy()

    env["ESPEAK_DATA_PATH"] = str(ESPEAK)

    input_data = (
        text.strip() + "\n"
    ).encode("utf-8")

    command = [
        str(PIPER),
        "--model", str(model),
        "--output_file", str(output_file)
    ]

    run_command(
        command,
        cwd=str(BASE),
        env=env,
        input_data=input_data
    )

    if not output_file.exists():
        raise RuntimeError(
            "Piper не создал аудиофайл."
        )

    if output_file.stat().st_size < 100:
        raise RuntimeError(
            "Piper создал пустой аудиофайл."
        )

    with wave.open(str(output_file), "rb") as audio:
        if audio.getnframes() == 0:
            raise RuntimeError(
                "В аудиофайле отсутствуют звуковые данные."
            )


def test_voice():

    voice = voice_var.get()

    test_button.config(state="disabled")
    set_status("Проверяем голос...")

    def worker():
        try:
            output = OUTPUT / (
                "test_voice_" +
                uuid.uuid4().hex[:8] +
                ".wav"
            )

            generate_voice(
                "Привет! Это Нейрохак. Проверяем русский голос.",
                voice,
                output
            )

            set_status("Проверка озвучки завершена.")

            show_info(
                f"Голос создан!\n\nФайл:\n{output}"
            )

        except Exception as error:
            report_error(error)

        finally:
            set_button(test_button, True)

    threading.Thread(
        target=worker,
        daemon=True
    ).start()


# ==========================================
# РАЗДЕЛЕНИЕ ТЕКСТА
# ==========================================

def split_script(text, limit=85):

    result = []
    current = ""

    for word in text.strip().split():

        candidate = (current + " " + word).strip()

        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                result.append(current)
            current = word

    if current:
        result.append(current)

    return result


def wrap_text(draw, text, font, max_width):

    lines = []
    current = ""

    for word in text.split():

        candidate = (current + " " + word).strip()

        box = draw.textbbox(
            (0, 0),
            candidate,
            font=font
        )

        if box[2] - box[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return "\n".join(lines)


# ==========================================
# СОЗДАНИЕ КАРТИНКИ СЦЕНЫ
# ==========================================

def create_overlay(title, text, number, total, output):

    image = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(image)

    brand_font = ImageFont.truetype(str(FONT), 46)
    title_font = ImageFont.truetype(str(FONT), 34)
    small_font = ImageFont.truetype(str(FONT), 23)

    draw.rounded_rectangle(
        (25, 35, 695, 240),
        radius=25,
        fill=(8, 11, 22, 225),
        outline=CYAN,
        width=3
    )

    draw.text(
        (360, 85),
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
        (360, 165),
        wrapped_title,
        font=title_font,
        fill=WHITE,
        anchor="mm",
        align="center",
        spacing=8
    )

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

        font = ImageFont.truetype(str(FONT), size)

        candidate = wrap_text(
            draw,
            text,
            font,
            570
        )

        box = draw.multiline_textbbox(
            (0, 0),
            candidate,
            font=font,
            spacing=10
        )

        if box[3] - box[1] <= 280:
            selected_font = font
            wrapped = candidate
            break

    if selected_font is None:
        raise RuntimeError(
            "Текст сцены слишком длинный."
        )

    draw.multiline_text(
        (360, 930),
        wrapped,
        font=selected_font,
        fill=WHITE,
        anchor="mm",
        align="center",
        spacing=10
    )

    draw.text(
        (360, 1190),
        f"VK • НЕЙРОХАК | {number}/{total}",
        font=small_font,
        fill=PURPLE,
        anchor="mm"
    )

    image.save(output)


# ==========================================
# ВИДЕОСЦЕНА
# ==========================================

def audio_duration(path):

    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


def create_video_scene(background, overlay, audio, output):

    duration = audio_duration(audio)

    if duration <= 0:
        raise RuntimeError("Пустая озвучка.")

    command = [str(FFMPEG), "-y"]

    if background:

        extension = Path(background).suffix.lower()

        if extension in (".jpg", ".jpeg", ".png"):

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
                "Неподдерживаемый формат: " + extension
            )

    else:

        command += [
            "-f", "lavfi",
            "-i",
            f"color=c=0x080B16:s={WIDTH}x{HEIGHT}:r={FPS}"
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
        "-filter_complex", filters,
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

    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError(
            "FFmpeg не создал видеосцену."
        )


# ==========================================
# МАТЕРИАЛЫ
# ==========================================

def refresh_materials():

    materials_list.delete(0, tk.END)

    for file in materials:
        materials_list.insert(
            tk.END,
            Path(file).name
        )


def add_materials():

    files = filedialog.askopenfilenames(
        title="Выберите фото и видео",
        filetypes=[
            ("Медиа", "*.jpg *.jpeg *.png *.mp4")
        ]
    )

    for file in files:
        if file not in materials:
            materials.append(file)

    refresh_materials()


def clear_materials():

    materials.clear()
    assignments.clear()
    refresh_materials()

    set_status("Материалы очищены.")


def prepare_scenes():

    global prepared_scenes

    text = script_text.get("1.0", "end-1c").strip()

    if not text:
        messagebox.showwarning(
            "Ошибка",
            "Введите сценарий."
        )
        return

    prepared_scenes = split_script(text)

    assignments.clear()
    scene_list.delete(0, tk.END)

    for i, scene in enumerate(prepared_scenes):
        scene_list.insert(
            tk.END,
            f"{i + 1}. {scene[:65]}"
        )

    set_status(
        f"Подготовлено сцен: {len(prepared_scenes)}"
    )


def assign_material():

    selected_scene = scene_list.curselection()
    selected_media = materials_list.curselection()

    if not selected_scene or not selected_media:
        messagebox.showwarning(
            "Ошибка",
            "Выберите сцену и материал."
        )
        return

    index = selected_scene[0]

    assignments[index] = materials[selected_media[0]]

    set_status(
        f"Материал назначен сцене {index + 1}."
    )


# ==========================================
# СОЗДАНИЕ ВИДЕО
# ==========================================

def start_creation():

    title = title_entry.get().strip()
    script = script_text.get("1.0", "end-1c").strip()

    voice = voice_var.get()
    mode = mode_var.get()

    if not title or not script:
        messagebox.showwarning(
            "Ошибка",
            "Введите название и сценарий."
        )
        return

    current_scenes = split_script(script)

    if mode == "Ручной" and current_scenes != prepared_scenes:
        messagebox.showwarning(
            "Подготовьте сцены",
            "Откройте вкладку Материалы "
            "и нажмите Подготовить сцены."
        )
        return

    create_button.config(state="disabled")

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


def process_video(
    title,
    current_scenes,
    voice,
    mode,
    current_materials,
    current_assignments
):

    try:

        check_components(voice)

        project_id = (
            datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_" + uuid.uuid4().hex[:6]
        )

        workdir = PROJECTS / project_id
        workdir.mkdir(parents=True, exist_ok=True)

        video_files = []
        total = len(current_scenes)

        for index, scene in enumerate(current_scenes):

            set_status(
                f"Создание сцены {index + 1}/{total}"
            )

            overlay = workdir / f"overlay_{index:03d}.png"
            audio = workdir / f"audio_{index:03d}.wav"
            video = workdir / f"scene_{index:03d}.mp4"

            create_overlay(
                title,
                scene,
                index + 1,
                total,
                overlay
            )

            generate_voice(scene, voice, audio)

            background = None

            if mode == "Авто":

                if current_materials:
                    background = current_materials[
                        index % len(current_materials)
                    ]

            else:

                background = current_assignments.get(index)

            create_video_scene(
                background,
                overlay,
                audio,
                video
            )

            video_files.append(video)

        set_status("Объединение сцен...")

        concat_file = workdir / "concat.txt"

        concat_file.write_text(
            "\n".join(
                f"file '{video.name}'"
                for video in video_files
            ),
            encoding="utf-8"
        )

        final_video = OUTPUT / f"neurohack_{project_id}.mp4"

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
                "Итоговый MP4 не создан."
            )

        project_info = {
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
                project_info,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        set_status("Видео успешно создано!")

        show_info(
            f"Видео готово!\n\n{final_video}"
        )

    except Exception as error:
        report_error(error)

    finally:
        set_button(create_button, True)


# ==========================================
# ОТКРЫТИЕ ПАПОК
# ==========================================

def open_output():
    os.startfile(OUTPUT)


def open_projects():
    os.startfile(PROJECTS)


def open_log():

    if LOG_FILE.exists():
        os.startfile(LOG_FILE)
    else:
        messagebox.showinfo(
            "Журнал",
            "Ошибок пока нет."
        )


# ==========================================
# ИНТЕРФЕЙС
# ==========================================

root = tk.Tk()

root.title(APP_NAME)
root.geometry("900x650")
root.minsize(700, 500)
root.configure(bg=BG)


# ==========================================
# ЗАГОЛОВОК
# ==========================================

header = tk.Frame(root, bg=BG)
header.pack(fill="x")

tk.Label(
    header,
    text="⚡ НЕЙРОХАК СТУДИЯ 3.4",
    font=("Arial", 21, "bold"),
    fg=CYAN,
    bg=BG
).pack(pady=10)


# ==========================================
# НИЖНЯЯ ПАНЕЛЬ
# ==========================================

bottom = tk.Frame(root, bg=BG)

bottom.pack(
    side="bottom",
    fill="x"
)

status_var = tk.StringVar(value="Готов к работе")

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
).pack(pady=4)


# ==========================================
# ВКЛАДКИ
# ==========================================

notebook = ttk.Notebook(root)

notebook.pack(
    fill="both",
    expand=True,
    padx=15,
    pady=8
)

tab_video = tk.Frame(notebook, bg=BG)
tab_media = tk.Frame(notebook, bg=BG)
tab_settings = tk.Frame(notebook, bg=BG)

notebook.add(tab_video, text="Создание видео")
notebook.add(tab_media, text="Материалы")
notebook.add(tab_settings, text="Настройки")


# ==========================================
# ВКЛАДКА СОЗДАНИЯ
# ==========================================

# Верхний блок настроек.
# Он находится НАД сценарием.

settings_frame = tk.Frame(
    tab_video,
    bg=BG
)

settings_frame.pack(
    side="top",
    fill="x",
    padx=15,
    pady=8
)

voice_var = tk.StringVar(value="Мужской")
mode_var = tk.StringVar(value="Авто")

tk.Label(
    settings_frame,
    text="Голос:",
    fg=WHITE,
    bg=BG
).pack(side="left", padx=5)

ttk.Combobox(
    settings_frame,
    textvariable=voice_var,
    values=["Мужской", "Женский"],
    state="readonly",
    width=14
).pack(side="left", padx=5)

tk.Label(
    settings_frame,
    text="Режим:",
    fg=WHITE,
    bg=BG
).pack(side="left", padx=10)

ttk.Combobox(
    settings_frame,
    textvariable=mode_var,
    values=["Авто", "Ручной"],
    state="readonly",
    width=14
).pack(side="left", padx=5)

test_button = tk.Button(
    settings_frame,
    text="🎙 Проверить озвучку",
    command=test_voice,
    bg=PURPLE,
    fg=WHITE
)

test_button.pack(side="left", padx=15)


# ==========================================
# НАЗВАНИЕ РОЛИКА
# ==========================================

tk.Label(
    tab_video,
    text="Название ролика",
    fg=WHITE,
    bg=BG
).pack(pady=3)

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


# ==========================================
# СЦЕНАРИЙ
# ==========================================

tk.Label(
    tab_video,
    text="Сценарий видео",
    fg=WHITE,
    bg=BG
).pack(pady=3)

text_frame = tk.Frame(tab_video, bg=BG)

text_frame.pack(
    fill="both",
    expand=True,
    padx=20,
    pady=5
)

scrollbar = tk.Scrollbar(text_frame)

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
# ВКЛАДКА МАТЕРИАЛОВ
# ==========================================

media_buttons = tk.Frame(tab_media, bg=BG)
media_buttons.pack(pady=10)

tk.Button(
    media_buttons,
    text="Добавить фото и видео",
    command=add_materials,
    bg=CYAN
).pack(side="left", padx=10)

tk.Button(
    media_buttons,
    text="Очистить",
    command=clear_materials,
    bg=PURPLE,
    fg=WHITE
).pack(side="left", padx=10)

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
    text="НЕЙРОХАК СТУДИЯ 3.4",
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
        "Монтаж: FFmpeg"
    ),
    fg=WHITE,
    bg=BG,
    font=("Arial", 12),
    justify="center"
).pack(pady=10)

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

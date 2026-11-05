import os
import sys
import re
import json
import wave
import random
import shutil
import tempfile
import subprocess
import threading
import traceback

from difflib import SequenceMatcher
from pathlib import Path
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# НЕЙРОХАК СТУДИЯ 4.2
# ============================================================

APP_NAME = "НЕЙРОХАК СТУДИЯ 4.2"

WIDTH = 720
HEIGHT = 1280
FPS = 25

BG = "#080B16"
PANEL = "#111827"
SURFACE = "#101827"
SURFACE_2 = "#172337"
EDITOR_BG = "#0B1220"
BORDER = "#26354A"
MUTED = "#94A3B8"
CYAN = "#00D9FF"
PURPLE = "#8B5CF6"
WHITE = "#FFFFFF"
GRAY = "#94A3B8"

VOICE_MODELS = {
    "Мужской": "ru_RU-ruslan-medium.onnx",
    "Женский": "ru_RU-irina-medium.onnx"
}

VOICE_SPEEDS = {
    "Медленная": 1.20,
    "Нормальная": 1.00,
    "Быстрая": 0.90
}

SUBTITLE_SIZES = {
    "Маленькие": 40,
    "Средние": 54,
    "Крупные": 66
}

ACCENT_WORDS = {
    "нейросеть", "нейросети", "нейросетей",
    "бесплатно", "бесплатный", "бесплатная",
    "бесплатные", "искусственный", "интеллект",
    "технологии", "технология", "секрет",
    "лайфхак", "лайфхаки", "видео", "время",
    "деньги", "заработок", "заработать",
    "важно", "топ", "ии"
}

SUBTITLE_SAFE_WIDTH = 580
SUBTITLE_TOP = 690
SUBTITLE_BOTTOM = 1040


# ============================================================
# ПУТИ
# ============================================================

if getattr(sys, "frozen", False):
    BASE = Path(sys.executable).resolve().parent
else:
    BASE = Path(__file__).resolve().parent

OUTPUT = BASE / "output"
PROJECTS = BASE / "projects"
MUSIC = BASE / "music"
VOICES = BASE / "voices"
AUTOSAVE_PATH = PROJECTS / "autosave.json"

for folder in [OUTPUT, PROJECTS, MUSIC]:
    folder.mkdir(parents=True, exist_ok=True)


def find_component(name):
    candidates = [
        BASE / name,
        BASE / "piper" / name,
        BASE / "ffmpeg" / name,
        BASE / "bin" / name
    ]

    if getattr(sys, "frozen", False):
        internal = Path(getattr(sys, "_MEIPASS", BASE))
        candidates.extend([
            internal / name,
            internal / "piper" / name,
            internal / "ffmpeg" / name
        ])

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return BASE / name


FFMPEG = find_component("ffmpeg.exe")
PIPER = find_component("piper.exe")


def find_espeak():
    candidates = [
        BASE / "espeak-ng-data",
        BASE / "piper" / "espeak-ng-data"
    ]

    if getattr(sys, "frozen", False):
        internal = Path(getattr(sys, "_MEIPASS", BASE))
        candidates.append(internal / "espeak-ng-data")

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return BASE / "espeak-ng-data"


ESPEAK = find_espeak()


# ============================================================
# ЖУРНАЛ ОШИБОК
# ============================================================

def write_error(error):
    with open(
        BASE / "error_log.txt",
        "a",
        encoding="utf-8"
    ) as file:
        file.write("\n" + "=" * 60 + "\n")
        file.write(str(datetime.now()) + "\n")
        file.write(str(error) + "\n")
        file.write(traceback.format_exc())


class TaskCancelled(Exception):
    """Raised when the user cancels a background generation task."""


def open_with_default_app(path):
    """Open a file or folder with the operating system's default application."""
    target = str(Path(path).expanduser())

    if os.name == "nt" and hasattr(os, "startfile"):
        os.startfile(target)
        return

    opener = "open" if sys.platform == "darwin" else "xdg-open"

    try:
        subprocess.Popen(
            [opener, target],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except OSError as error:
        raise RuntimeError(f"Не удалось открыть: {target}\n{error}") from error


def run_command(command, input_data=None, env=None, cancel_event=None):
    command = [str(item) for item in command]

    if cancel_event and cancel_event.is_set():
        raise TaskCancelled("Задача отменена пользователем.")

    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE if input_data is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(BASE),
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )

    pending_input = input_data
    while True:
        try:
            stdout, stderr = process.communicate(
                input=pending_input,
                timeout=0.25
            )
            break
        except subprocess.TimeoutExpired:
            pending_input = None
            if cancel_event and cancel_event.is_set():
                try:
                    process.terminate()
                except OSError:
                    pass
                try:
                    process.communicate(timeout=3)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                    except OSError:
                        pass
                    process.communicate()
                raise TaskCancelled("Задача отменена пользователем.")

    if cancel_event and cancel_event.is_set():
        raise TaskCancelled("Задача отменена пользователем.")

    result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Код завершения: {result.returncode}\n"
            + error[-7000:]
        )

    return result


def check_components():
    problems = []

    if not FFMPEG.exists():
        problems.append("Не найден ffmpeg.exe")

    if not PIPER.exists():
        problems.append("Не найден piper.exe")

    if not ESPEAK.exists():
        problems.append("Не найдена папка espeak-ng-data")

    for model in VOICE_MODELS.values():
        path = VOICES / model

        if not path.exists():
            problems.append("Нет модели: " + model)

        if not Path(str(path) + ".json").exists():
            problems.append("Нет JSON модели: " + model)

    return problems


# ============================================================
# ТЕКСТ
# ============================================================

def normalize_speech_text(text):
    replacements = {
        "ChatGPT": "чат джи пи ти",
        "Windows 10": "виндовс десять",
        "Windows 11": "виндовс одиннадцать",
        "Win + Shift + S": "вин шифт эс",
        "Win + V": "вин вэ",
        "VK": "вконтакте"
    }

    for source, target in replacements.items():
        text = re.sub(
            re.escape(source),
            target,
            text,
            flags=re.IGNORECASE
        )

    text = re.sub(
        r"\bИИ\b",
        "искусственный интеллект",
        text
    )

    return text.strip()


def split_script(text, max_length=105):
    text = re.sub(r"\s+", " ", text).strip()

    if not text:
        return []

    scenes = []
    current = ""

    for word in text.split():
        candidate = (current + " " + word).strip()

        if len(candidate) > max_length and current:
            scenes.append(current)
            current = word
        else:
            current = candidate

    if current:
        scenes.append(current)

    return scenes


def russian_plural(number, one, few, many):
    remainder_10 = abs(number) % 10
    remainder_100 = abs(number) % 100
    if remainder_10 == 1 and remainder_100 != 11:
        return one
    if 2 <= remainder_10 <= 4 and not 12 <= remainder_100 <= 14:
        return few
    return many


def split_subtitles(text, max_words=5):
    words = text.split()

    return [
        " ".join(words[i:i + max_words])
        for i in range(0, len(words), max_words)
    ]


def format_srt_timestamp(seconds):
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"


def write_srt(path, captions):
    with open(path, "w", encoding="utf-8") as output:
        for index, (start, end, text) in enumerate(captions, 1):
            output.write(f"{index}\n")
            output.write(
                f"{format_srt_timestamp(start)} --> "
                f"{format_srt_timestamp(end)}\n"
            )
            output.write(text.strip() + "\n\n")


# ============================================================
# ШРИФТЫ
# ============================================================

def get_font(size, bold=True):
    fonts = Path("C:/Windows/Fonts")

    names = (
        ["arialbd.ttf", "segoeuib.ttf", "impact.ttf"]
        if bold else
        ["arial.ttf", "segoeui.ttf"]
    )

    for name in names:
        path = fonts / name

        if path.exists():
            return ImageFont.truetype(str(path), size)

    return ImageFont.load_default()


def measure_text(draw, text, font):
    if not text:
        return 0

    box = draw.textbbox(
        (0, 0),
        text,
        font=font
    )

    return box[2] - box[0]


# ============================================================
# КИБЕРПАНК-ОФОРМЛЕНИЕ
# ============================================================

def create_base_overlay(path, number):
    image = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, WIDTH, 105),
        fill=(8, 11, 22, 225)
    )

    draw.rectangle(
        (0, 101, WIDTH, 105),
        fill=(0, 217, 255, 255)
    )

    draw.text(
        (35, 25),
        "НЕЙРОХАК",
        font=get_font(43),
        fill=CYAN
    )

    draw.text(
        (570, 40),
        f"{number:02d}",
        font=get_font(30),
        fill=PURPLE
    )

    draw.rectangle(
        (0, 1190, WIDTH, HEIGHT),
        fill=(8, 11, 22, 230)
    )

    draw.text(
        (35, 1210),
        "НЕЙРОСЕТИ • ТЕХНОЛОГИИ",
        font=get_font(27),
        fill=WHITE
    )

    image.save(path)


# ============================================================
# СУБТИТРЫ 4.1.1
# ============================================================

def clean_subtitle_word(word):
    return re.sub(
        r"[^а-яёa-z0-9]",
        "",
        word.lower()
    )


def choose_accent_words(text):
    words = text.split()
    selected = set()

    for index, word in enumerate(words):
        if clean_subtitle_word(word) in ACCENT_WORDS:
            selected.add(index)

    if not selected and words:
        candidates = []

        for index, word in enumerate(words):
            clean = clean_subtitle_word(word)

            if len(clean) >= 4:
                candidates.append(
                    (len(clean), index)
                )

        if candidates:
            candidates.sort(reverse=True)
            selected.add(candidates[0][1])
        else:
            selected.add(0)

    return selected


def split_subtitle_lines(draw, text, font):
    words = text.split()

    if not words:
        return []

    lines = []
    current = []

    for word in words:
        candidate = current + [word]

        width = measure_text(
            draw,
            " ".join(candidate),
            font
        )

        if width > SUBTITLE_SAFE_WIDTH and current:
            lines.append(current)
            current = [word]
        else:
            current = candidate

    if current:
        lines.append(current)

    return lines


def calculate_subtitle_layout(text, size):
    image = Image.new(
        "RGBA",
        (WIDTH, HEIGHT)
    )

    draw = ImageDraw.Draw(image)

    requested_size = SUBTITLE_SIZES.get(size, 54)

    for font_size in range(
        requested_size,
        17,
        -2
    ):
        font = get_font(font_size)

        lines = split_subtitle_lines(
            draw,
            text,
            font
        )

        if not lines:
            return [], font, 0

        line_height = int(font_size * 1.55)
        total_height = len(lines) * line_height

        maximum_width = max(
            measure_text(
                draw,
                " ".join(line),
                font
            )
            for line in lines
        )

        if (
            maximum_width <= SUBTITLE_SAFE_WIDTH
            and total_height <= SUBTITLE_BOTTOM - SUBTITLE_TOP
            and len(lines) <= 3
        ):
            return lines, font, line_height

    font = get_font(18)
    lines = split_subtitle_lines(draw, text, font)

    return lines, font, 30


def draw_subtitle_line(
    draw,
    words,
    y,
    font,
    accent_indexes,
    global_offset,
    glow=False
):
    if not words:
        return

    space_width = measure_text(draw, " ", font)

    widths = [
        measure_text(draw, word, font)
        for word in words
    ]

    total_width = (
        sum(widths)
        + space_width * (len(words) - 1)
    )

    x = (WIDTH - total_width) / 2

    for local_index, word in enumerate(words):
        accent = (
            global_offset + local_index
        ) in accent_indexes

        if glow:
            color = (
                (0, 217, 255, 230)
                if accent else
                (139, 92, 246, 220)
            )

            draw.text(
                (round(x), y),
                word,
                font=font,
                fill=color,
                stroke_width=7,
                stroke_fill=color
            )

        else:
            color = CYAN if accent else WHITE

            draw.text(
                (round(x), y),
                word,
                font=font,
                fill=color,
                stroke_width=3,
                stroke_fill=(5, 8, 20, 255)
            )

        x += widths[local_index] + space_width


def create_subtitle_image(text, path, size):
    text = re.sub(
        r"\s+",
        " ",
        text.upper()
    ).strip()

    image = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    if not text:
        image.save(path)
        return

    lines, font, line_height = (
        calculate_subtitle_layout(text, size)
    )

    if not lines:
        image.save(path)
        return

    accent_indexes = choose_accent_words(text)

    total_height = len(lines) * line_height

    center_y = (
        SUBTITLE_TOP + SUBTITLE_BOTTOM
    ) // 2

    start_y = max(
        SUBTITLE_TOP,
        center_y - total_height // 2
    )

    glow = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0)
    )

    glow_draw = ImageDraw.Draw(glow)

    offset = 0

    for index, line in enumerate(lines):
        draw_subtitle_line(
            glow_draw,
            line,
            start_y + index * line_height,
            font,
            accent_indexes,
            offset,
            glow=True
        )

        offset += len(line)

    glow = glow.filter(
        ImageFilter.GaussianBlur(13)
    )

    image = Image.alpha_composite(image, glow)
    image = Image.alpha_composite(image, glow)

    draw = ImageDraw.Draw(image)
    offset = 0

    for index, line in enumerate(lines):
        draw_subtitle_line(
            draw,
            line,
            start_y + index * line_height,
            font,
            accent_indexes,
            offset,
            glow=False
        )

        offset += len(line)

    image.save(path)


# ============================================================
# ОЗВУЧКА PIPER
# ============================================================

def generate_voice(text, voice, speed, output_file, cancel_event=None):
    model = VOICES / VOICE_MODELS[voice]

    env = os.environ.copy()
    env["ESPEAK_DATA_PATH"] = str(ESPEAK)

    command = [
        str(PIPER),
        "--model", str(model),
        "--output_file", str(output_file),
        "--length_scale", str(VOICE_SPEEDS[speed])
    ]

    clean = normalize_speech_text(text)

    run_command(
        command,
        input_data=(clean + "\n").encode("utf-8"),
        env=env,
        cancel_event=cancel_event
    )

    if not output_file.exists():
        raise RuntimeError("Piper не создал WAV-файл.")


def audio_duration(path):
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes() / audio.getframerate()


# ============================================================
# СОЗДАНИЕ ВИДЕОСЦЕНЫ
# ============================================================

def make_scene(
    material,
    voice_file,
    output_file,
    overlay_file,
    subtitles,
    subtitles_enabled,
    cancel_event=None
):
    duration = audio_duration(voice_file) + 0.20

    command = [str(FFMPEG), "-y"]

    has_material = bool(
        material and Path(material).exists()
    )

    if has_material:
        extension = Path(material).suffix.lower()

        if extension in [".mp4", ".mov", ".mkv", ".avi"]:
            command += [
                "-stream_loop", "-1",
                "-i", str(material)
            ]
        else:
            command += [
                "-loop", "1",
                "-i", str(material)
            ]
    else:
        command += [
            "-f", "lavfi",
            "-i",
            "color=c=0x080B16:s=720x1280:r=25"
        ]

    command += [
        "-i", str(voice_file),
        "-loop", "1",
        "-i", str(overlay_file)
    ]

    for subtitle in subtitles:
        command += [
            "-loop", "1",
            "-i", str(subtitle)
        ]

    filters = [
        "[0:v]"
        "scale=720:1280:"
        "force_original_aspect_ratio=increase,"
        "crop=720:1280,"
        "setsar=1,"
        "format=yuv420p[bg]",

        "[bg][2:v]"
        "overlay=0:0:shortest=1[v0]"
    ]

    current = "v0"

    if subtitles_enabled and subtitles:
        phrase_duration = duration / len(subtitles)

        for index, subtitle in enumerate(subtitles):
            start = index * phrase_duration
            end = min(
                duration,
                (index + 1) * phrase_duration
            )

            input_index = index + 3

            subtitle_label = f"sub{index}"
            output_label = f"v{index + 1}"

            filters.append(
                f"[{input_index}:v]"
                "format=rgba,"
                "fade=t=in:st=0:d=0.22:alpha=1,"
                f"setpts=PTS-STARTPTS+{start:.3f}/TB"
                f"[{subtitle_label}]"
            )

            filters.append(
                f"[{current}][{subtitle_label}]"
                "overlay=0:0:"
                "eof_action=pass:"
                f"enable='gte(t,{start:.3f})*lt(t,{end:.3f})'"
                f"[{output_label}]"
            )

            current = output_label

    command += [
        "-filter_complex",
        ";".join(filters),

        "-map", f"[{current}]",
        "-map", "1:a:0",

        "-t", str(duration),
        "-r", str(FPS),

        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "26",
        "-pix_fmt", "yuv420p",

        "-c:a", "aac",
        "-b:a", "160k",
        "-ar", "44100",
        "-ac", "2",

        "-movflags", "+faststart",
        str(output_file)
    ]

    run_command(command, cancel_event=cancel_event)


# ============================================================
# ОБЪЕДИНЕНИЕ СЦЕН
# ============================================================

def combine_scenes(scene_files, output_file, workdir, cancel_event=None):
    concat_file = workdir / "concat.txt"

    with open(
        concat_file,
        "w",
        encoding="utf-8"
    ) as file:
        for scene in scene_files:
            file.write(f"file '{scene.name}'\n")

    run_command([
        str(FFMPEG),
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(output_file)
    ], cancel_event=cancel_event)


# ============================================================
# ФОНОВАЯ МУЗЫКА
# ============================================================

def add_background_music(
    video_file,
    music_file,
    volume,
    output_file,
    cancel_event=None
):
    if cancel_event and cancel_event.is_set():
        raise TaskCancelled("Задача отменена пользователем.")

    if not music_file:
        shutil.copy2(video_file, output_file)
        if cancel_event and cancel_event.is_set():
            raise TaskCancelled("Задача отменена пользователем.")
        return

    run_command([
        str(FFMPEG),
        "-y",
        "-i", str(video_file),
        "-stream_loop", "-1",
        "-i", str(music_file),

        "-filter_complex",
        (
            f"[1:a]volume={volume:.3f}[music];"
            "[0:a][music]"
            "amix=inputs=2:"
            "duration=first:"
            "dropout_transition=0[a]"
        ),

        "-map", "0:v:0",
        "-map", "[a]",

        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "160k",
        "-shortest",
        "-movflags", "+faststart",

        str(output_file)
    ], cancel_event=cancel_event)


# ============================================================
# ПОМОЩНИК 4.2 — БЕСПЛАТНО И БЕЗ ИНТЕРНЕТА
# ============================================================

IDEA_TOPICS = [
    "5 бесплатных нейросетей для работы",
    "3 полезных сайта для учёбы",
    "Как использовать ChatGPT",
    "Нейросети для создания изображений",
    "Бесплатные инструменты для монтажа видео",
    "Как ускорить работу на компьютере",
    "5 скрытых возможностей Windows",
    "Нейросети для написания текстов",
    "Как создавать презентации с помощью ИИ",
    "Полезные расширения для браузера",
    "Бесплатные сервисы для обработки фотографий",
    "Как защитить свои данные в интернете",
    "Лучшие бесплатные приложения для Windows",
    "Как автоматизировать повседневные задачи",
    "Нейросети для изучения английского языка",
    "Полезные функции смартфона",
    "Как создавать короткие видео",
    "Бесплатные программы для записи экрана",
    "Как быстро находить нужную информацию",
    "5 цифровых лайфхаков на каждый день"
]

HOOKS = [
    "Ты удивишься, насколько полезной может быть эта технология!",
    "Большинство людей даже не знают об этой возможности!",
    "Хочешь тратить меньше времени на повседневные задачи?",
    "Вот идея, которую стоит попробовать уже сегодня!",
    "Этот цифровой лайфхак может пригодиться каждому!"
]

BENEFITS = [
    "Начни с простой задачи и проверь результат самостоятельно.",
    "Сравни несколько бесплатных решений и выбери удобное.",
    "Не загружай личные данные в незнакомые сервисы.",
    "Перед использованием проверь ограничения бесплатной версии.",
    "Сохрани полезный результат, чтобы вернуться к нему позже."
]

CALLS_TO_ACTION = [
    "Подписывайся на Нейрохак, чтобы узнавать больше о технологиях!",
    "Сохрани этот клип и подпишись на Нейрохак!",
    "Больше полезных цифровых лайфхаков — в сообществе Нейрохак!"
]


def clean_topic(topic):
    topic = re.sub(r"\s+", " ", topic).strip()

    if not topic:
        raise ValueError("Сначала введи тему клипа.")

    return topic[:180]


def generate_script(topic, duration="30–60 секунд"):
    topic = clean_topic(topic)

    hook = random.choice(HOOKS)
    benefit = random.choice(BENEFITS)
    ending = random.choice(CALLS_TO_ACTION)

    if duration == "15–30 секунд":
        return (
            f"{hook} "
            f"Сегодня наша тема — {topic}. "
            f"{benefit} "
            f"{ending}"
        )

    if duration == "60–90 секунд":
        return (
            f"{hook} "
            f"Сегодня разбираем тему: {topic}. "
            "Первый шаг — определись, какую задачу хочешь решить. "
            "Второй шаг — найди подходящий инструмент "
            "и изучи его бесплатные возможности. "
            "Третий шаг — проверь результат на небольшом примере. "
            f"{benefit} "
            "Проверяй информацию, которую предлагают нейросети. "
            f"{ending}"
        )

    return (
        f"{hook} "
        f"Сегодня поговорим про {topic}. "
        "Для начала определи, какую задачу "
        "хочешь решить с помощью этой технологии. "
        "Затем попробуй бесплатные инструменты "
        "и сравни полученные результаты. "
        f"{benefit} "
        f"{ending}"
    )


def generate_title(topic):
    topic = clean_topic(topic)

    return random.choice([
        f"🔥 {topic} — полезный лайфхак!",
        f"⚡ {topic}: что стоит знать?",
        f"🤖 Разбираемся: {topic}",
        f"🚀 {topic} — попробуй сам!"
    ])


def generate_description(topic):
    topic = clean_topic(topic)

    return (
        f"Сегодня в НЕЙРОХАК разбираем: {topic}.\n\n"
        "Полезные технологии, нейросети и цифровые лайфхаки.\n"
        "Подписывайся, чтобы не пропустить новые ролики!\n\n"
        "#нейрохак #нейросети #технологии #лайфхаки #ии"
    )


def generate_ideas(count=10):
    count = min(max(int(count), 1), len(IDEA_TOPICS))
    return random.sample(IDEA_TOPICS, count)


# ============================================================
# ГЛАВНОЕ ОКНО
# ============================================================

class NeuroHackStudio:

    PAGE_META = {
        "create": ("Создание клипа", "Соберите вертикальное видео из сценария, озвучки и материалов."),
        "ai": ("ИИ-помощник", "Идеи, сценарии и описание для следующего ролика."),
        "materials": ("Материалы и сцены", "Управляйте исходниками и распределением по сценам."),
        "music": ("Музыкальная библиотека", "Добавьте фоновую музыку и настройте её громкость."),
        "library": ("Проекты и результаты", "Недавние клипы, сохранённые проекты и восстановление работы."),
        "settings": ("Настройки", "Параметры проекта и проверка компонентов."),
    }

    def __init__(self, root):
        self.root = root

        root.title(APP_NAME)
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = min(1240, max(850, screen_width - 80))
        window_height = min(820, max(600, screen_height - 80))
        root.geometry(f"{window_width}x{window_height}")
        root.minsize(850, 600)
        root.configure(bg=BG)
        root.option_add("*Font", ("Arial", 10))

        self.materials = []
        self.scene_assignments = {}
        self.prepared_scenes = []

        self.last_video = None
        self.last_srt = None
        self.busy = False
        self.ai_script = ""
        self.cancel_event = threading.Event()
        self.current_project_file = None
        self.is_dirty = False
        self._loading_project = False
        self._close_when_idle = False
        self._autosave_after = None
        self._preview_after = None
        self.output_video_files = []
        self.project_file_paths = []

        self.voice_var = tk.StringVar(value="Мужской")
        self.speed_var = tk.StringVar(value="Нормальная")

        self.subtitle_var = tk.BooleanVar(value=True)
        self.export_srt_var = tk.BooleanVar(value=True)
        self.subtitle_size = tk.StringVar(value="Средние")

        self.mode_var = tk.StringVar(value="Автоматически")
        self.music_var = tk.StringVar(value="Без музыки")
        self.volume_var = tk.DoubleVar(value=12)

        self.status_var = tk.StringVar(value="Готов к работе")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_percent_var = tk.StringVar(value="0%")
        self.page_title_var = tk.StringVar(value="")
        self.page_subtitle_var = tk.StringVar(value="")
        self.script_meta_var = tk.StringVar(value="0 слов · 0 сцен")
        self.preview_info_var = tk.StringVar(value="Субтитры включены")
        self.material_count_var = tk.StringVar(value="0 файлов")
        self.scene_count_var = tk.StringVar(value="0 сцен")
        self.library_video_count_var = tk.StringVar(value="0 клипов")
        self.library_project_count_var = tk.StringVar(value="0 проектов")
        self.volume_label_var = tk.StringVar(value="12%")

        self.ai_topic = tk.StringVar()
        self.ai_duration = tk.StringVar(value="30–60 секунд")

        self.setup_style()
        self.build_interface()
        self.enable_clipboard()
        self.refresh_music()
        self.refresh_library()
        self.update_script_details()

        for variable in (
            self.voice_var,
            self.speed_var,
            self.subtitle_var,
            self.export_srt_var,
            self.subtitle_size,
            self.mode_var,
            self.music_var,
            self.volume_var
        ):
            variable.trace_add("write", self.on_project_setting_changed)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after_idle(self.draw_preview)
        self.root.after(500, self.restore_autosave)

    # --------------------------------------------------------

    def setup_style(self):
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "Dark.TCombobox",
            fieldbackground=SURFACE_2,
            background=SURFACE_2,
            foreground=WHITE,
            arrowcolor=CYAN,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(8, 6),
            arrowsize=12
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", SURFACE_2), ("focus", SURFACE_2)],
            foreground=[("readonly", WHITE), ("disabled", MUTED)],
            selectbackground=[("readonly", SURFACE_2)],
            selectforeground=[("readonly", WHITE)]
        )
        style.configure(
            "Dark.TEntry",
            fieldbackground=SURFACE_2,
            foreground=WHITE,
            insertcolor=CYAN,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(9, 7)
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#202B3D",
            background=CYAN,
            bordercolor="#202B3D",
            lightcolor=CYAN,
            darkcolor=CYAN,
            thickness=8
        )
        style.configure(
            "TScrollbar",
            background=SURFACE_2,
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=MUTED
        )
        style.configure("TScale", background=SURFACE, troughcolor="#26354A")

        try:
            root_window = self.root
            root_window.option_add("*TCombobox*Listbox.background", SURFACE_2)
            root_window.option_add("*TCombobox*Listbox.foreground", WHITE)
            root_window.option_add("*TCombobox*Listbox.selectBackground", PURPLE)
            root_window.option_add("*TCombobox*Listbox.selectForeground", WHITE)
        except Exception:
            pass

    # --------------------------------------------------------

    def button(self, parent, text, command, color=PURPLE):
        foreground = BG if color == CYAN else WHITE
        active = "#69E8FF" if color == CYAN else "#7652D8"
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg=foreground,
            activebackground=active,
            activeforeground=BG if color == CYAN else WHITE,
            disabledforeground=MUTED,
            font=("Arial", 9, "bold"),
            relief="flat",
            bd=0,
            padx=12,
            pady=8,
            cursor="hand2",
            highlightthickness=0
        )

    # --------------------------------------------------------

    def label(self, parent, text, color=WHITE, font=None, bg=None, **kwargs):
        if bg is None:
            try:
                bg = parent.cget("bg")
            except Exception:
                bg = BG

        return tk.Label(
            parent,
            text=text,
            bg=bg,
            fg=color,
            font=font or ("Arial", 10),
            **kwargs
        )

    # --------------------------------------------------------

    @staticmethod
    def card(parent, **kwargs):
        return tk.Frame(
            parent,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1,
            **kwargs
        )

    # ========================================================
    # MAIN SHELL & NAVIGATION
    # ========================================================

    def build_interface(self):
        self.root.grid_columnconfigure(0, weight=0, minsize=214)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        self.sidebar = tk.Frame(self.root, bg=PANEL, width=214)
        self.sidebar.grid(row=0, column=0, rowspan=2, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(3, weight=1)

        brand = tk.Frame(self.sidebar, bg=PANEL)
        brand.pack(fill="x", padx=18, pady=(22, 18))

        mark = tk.Label(
            brand,
            text="✦",
            bg="#17263A",
            fg=CYAN,
            font=("Arial", 17, "bold"),
            width=2,
            height=1
        )
        mark.pack(side="left", padx=(0, 10))

        brand_text = tk.Frame(brand, bg=PANEL)
        brand_text.pack(side="left", fill="x", expand=True)
        self.label(
            brand_text,
            "НЕЙРОХАК",
            color=WHITE,
            font=("Arial", 11, "bold")
        ).pack(anchor="w")
        self.label(
            brand_text,
            "СТУДИЯ 4.2",
            color=MUTED,
            font=("Arial", 8, "bold")
        ).pack(anchor="w", pady=(2, 0))

        tk.Frame(self.sidebar, bg=BORDER, height=1).pack(fill="x", padx=16)
        self.label(
            self.sidebar,
            "РАБОЧЕЕ ПРОСТРАНСТВО",
            color="#64748B",
            font=("Arial", 8, "bold")
        ).pack(anchor="w", padx=19, pady=(19, 8))

        nav = tk.Frame(self.sidebar, bg=PANEL)
        nav.pack(fill="x", padx=10)
        self.nav_items = {}

        nav_entries = [
            ("create", "✦", "Создание клипа"),
            ("ai", "✧", "ИИ-помощник"),
            ("materials", "▧", "Материалы и сцены"),
            ("music", "♫", "Музыка"),
            ("library", "▤", "Проекты и результаты"),
            ("settings", "⚙", "Настройки"),
        ]

        for key, icon, title in nav_entries:
            item = tk.Frame(nav, bg=PANEL)
            item.pack(fill="x", pady=2)
            indicator = tk.Frame(item, bg=PANEL, width=3)
            indicator.pack(side="left", fill="y", padx=(0, 7))
            nav_button = tk.Button(
                item,
                text=f"{icon}   {title}",
                command=lambda page=key: self.show_page(page),
                bg=PANEL,
                fg="#B6C2D3",
                activebackground="#1A2940",
                activeforeground=WHITE,
                anchor="w",
                font=("Arial", 9, "bold"),
                relief="flat",
                bd=0,
                padx=10,
                pady=11,
                cursor="hand2",
                highlightthickness=0
            )
            nav_button.pack(side="left", fill="x", expand=True)
            self.nav_items[key] = (indicator, nav_button)

        sidebar_bottom = tk.Frame(self.sidebar, bg=PANEL)
        sidebar_bottom.pack(side="bottom", fill="x", padx=14, pady=16)
        tk.Frame(sidebar_bottom, bg=BORDER, height=1).pack(fill="x", pady=(0, 12))
        self.button(
            sidebar_bottom,
            "📁  Папка результатов",
            self.open_output,
            color=SURFACE_2
        ).pack(fill="x")
        self.label(
            sidebar_bottom,
            "Формат 9:16  ·  720 × 1280",
            color=MUTED,
            font=("Arial", 8)
        ).pack(anchor="w", pady=(12, 0))

        self.main_area = tk.Frame(self.root, bg=BG)
        self.main_area.grid(row=0, column=1, sticky="nsew")
        self.main_area.grid_rowconfigure(1, weight=1)
        self.main_area.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self.main_area, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)

        heading = tk.Frame(header, bg=BG)
        heading.grid(row=0, column=0, sticky="w")
        self.label(
            heading,
            "",
            color=WHITE,
            font=("Arial", 18, "bold"),
            textvariable=self.page_title_var
        ).pack(anchor="w")
        self.label(
            heading,
            "",
            color=MUTED,
            font=("Arial", 9),
            textvariable=self.page_subtitle_var
        ).pack(anchor="w", pady=(4, 0))

        header_actions = tk.Frame(header, bg=BG)
        header_actions.grid(row=0, column=1, sticky="e", padx=(14, 0))
        self.button(
            header_actions,
            "Результаты",
            self.open_output,
            color=SURFACE_2
        ).pack(side="left", padx=(0, 8))
        self.create_button = self.button(
            header_actions,
            "✦  СОЗДАТЬ КЛИП",
            self.start_creation,
            color=CYAN
        )
        self.create_button.configure(font=("Arial", 9, "bold"), pady=10)
        self.create_button.pack(side="left")
        self.cancel_button = self.button(
            header_actions,
            "Остановить",
            self.cancel_creation,
            color="#633344"
        )
        self.cancel_button.configure(state="disabled")
        self.cancel_button.pack(side="left", padx=(8, 0))

        self.page_container = tk.Frame(self.main_area, bg=BG)
        self.page_container.grid(row=1, column=0, sticky="nsew", padx=18, pady=(4, 12))
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)

        self.tab_create = tk.Frame(self.page_container, bg=BG)
        self.tab_ai = tk.Frame(self.page_container, bg=BG)
        self.tab_materials = tk.Frame(self.page_container, bg=BG)
        self.tab_music = tk.Frame(self.page_container, bg=BG)
        self.tab_library = tk.Frame(self.page_container, bg=BG)
        self.tab_settings = tk.Frame(self.page_container, bg=BG)

        self.pages = {
            "create": self.tab_create,
            "ai": self.tab_ai,
            "materials": self.tab_materials,
            "music": self.tab_music,
            "library": self.tab_library,
            "settings": self.tab_settings,
        }

        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        self.build_create_tab()
        self.build_ai_tab()
        self.build_materials_tab()
        self.build_music_tab()
        self.build_library_tab()
        self.build_settings_tab()

        self.footer = tk.Frame(
            self.root,
            bg=PANEL,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1
        )
        self.footer.grid(row=1, column=1, sticky="ew")
        self.footer.grid_columnconfigure(1, weight=1)

        status_row = tk.Frame(self.footer, bg=PANEL)
        status_row.grid(row=0, column=0, sticky="ew", padx=18, pady=(8, 4))
        status_row.grid_columnconfigure(1, weight=1)
        self.label(
            status_row,
            "●",
            color=CYAN,
            font=("Arial", 9, "bold")
        ).grid(row=0, column=0, padx=(0, 8))
        self.label(
            status_row,
            "",
            color="#D4DCE8",
            font=("Arial", 9),
            textvariable=self.status_var,
            anchor="w"
        ).grid(row=0, column=1, sticky="ew")
        self.label(
            status_row,
            "",
            color=CYAN,
            font=("Arial", 9, "bold"),
            textvariable=self.progress_percent_var
        ).grid(row=0, column=2, padx=(12, 0))

        self.progress_bar = ttk.Progressbar(
            self.footer,
            mode="determinate",
            maximum=100,
            variable=self.progress_var,
            style="Horizontal.TProgressbar"
        )
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 11))

        self.show_page("create")

    # --------------------------------------------------------

    def show_page(self, key):
        if key not in self.pages:
            return

        self.pages[key].tkraise()
        title, subtitle = self.PAGE_META[key]
        self.page_title_var.set(title)
        self.page_subtitle_var.set(subtitle)

        for page_key, (indicator, nav_button) in self.nav_items.items():
            active = page_key == key
            indicator.configure(bg=CYAN if active else PANEL)
            nav_button.configure(
                bg="#1A2940" if active else PANEL,
                fg=CYAN if active else "#B6C2D3"
            )

        if key == "create":
            self.schedule_preview()

    # --------------------------------------------------------
    # СОЗДАНИЕ ВИДЕО
    # --------------------------------------------------------

    def build_create_tab(self):
        self.tab_create.grid_columnconfigure(0, weight=7, minsize=330)
        self.tab_create.grid_columnconfigure(1, weight=4, minsize=200)
        self.tab_create.grid_rowconfigure(0, weight=1)

        self.editor_panel = self.card(self.tab_create)
        self.editor_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.editor_panel.grid_columnconfigure(0, weight=1)
        self.editor_panel.grid_rowconfigure(1, weight=1)

        editor_heading = tk.Frame(self.editor_panel, bg=SURFACE)
        editor_heading.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 10))
        editor_heading.grid_columnconfigure(0, weight=1)
        self.label(
            editor_heading,
            "Сценарий клипа",
            color=WHITE,
            font=("Arial", 12, "bold")
        ).grid(row=0, column=0, sticky="w")
        self.label(
            editor_heading,
            "",
            color=MUTED,
            font=("Arial", 8),
            textvariable=self.script_meta_var
        ).grid(row=0, column=1, sticky="e")

        editor_box = tk.Frame(
            self.editor_panel,
            bg=EDITOR_BG,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1
        )
        editor_box.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 10))
        editor_box.grid_columnconfigure(0, weight=1)
        editor_box.grid_rowconfigure(0, weight=1)

        self.script_text = tk.Text(
            editor_box,
            bg=EDITOR_BG,
            fg=WHITE,
            insertbackground=CYAN,
            selectbackground=PURPLE,
            selectforeground=WHITE,
            font=("Arial", 11),
            wrap="word",
            undo=True,
            relief="flat",
            bd=0,
            padx=13,
            pady=12,
            spacing1=2,
            spacing3=3,
            highlightthickness=0
        )
        script_scroll = ttk.Scrollbar(editor_box, orient="vertical", command=self.script_text.yview)
        self.script_text.configure(yscrollcommand=script_scroll.set)
        self.script_text.grid(row=0, column=0, sticky="nsew")
        script_scroll.grid(row=0, column=1, sticky="ns")
        self.script_text.insert(
            "1.0",
            "Привет! Это Нейрохак. Сегодня расскажу о бесплатной нейросети, "
            "которая поможет тебе экономить время. Подписывайся на наше сообщество!"
        )
        self.script_text.edit_modified(False)
        self.script_text.bind("<<Modified>>", self.on_script_changed)

        editor_actions = tk.Frame(self.editor_panel, bg=SURFACE)
        editor_actions.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 11))
        self.button(
            editor_actions,
            "Сохранить",
            self.save_project,
            color=SURFACE_2
        ).pack(side="left", padx=(0, 4))
        self.button(
            editor_actions,
            "Открыть",
            self.load_project,
            color=SURFACE_2
        ).pack(side="left", padx=4)
        self.button(
            editor_actions,
            "Шаблон",
            self.insert_script_template,
            color=SURFACE_2
        ).pack(side="left", padx=4)
        self.button(
            editor_actions,
            "Сцены",
            self.prepare_scenes,
            color=PURPLE
        ).pack(side="right")

        options = tk.Frame(
            self.editor_panel,
            bg=SURFACE_2,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1
        )
        options.grid(row=3, column=0, sticky="ew", padx=15, pady=(0, 15))
        for column in (1, 3):
            options.grid_columnconfigure(column, weight=1)

        self.label(options, "ГОЛОС", color=MUTED, font=("Arial", 8, "bold")).grid(
            row=0, column=0, sticky="w", padx=(11, 5), pady=(10, 6)
        )
        self.voice_combo = ttk.Combobox(
            options,
            textvariable=self.voice_var,
            values=list(VOICE_MODELS),
            state="readonly",
            width=11,
            style="Dark.TCombobox"
        )
        self.voice_combo.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(8, 5))

        self.label(options, "СКОРОСТЬ", color=MUTED, font=("Arial", 8, "bold")).grid(
            row=0, column=2, sticky="w", padx=(4, 5), pady=(10, 6)
        )
        self.speed_combo = ttk.Combobox(
            options,
            textvariable=self.speed_var,
            values=list(VOICE_SPEEDS),
            state="readonly",
            width=11,
            style="Dark.TCombobox"
        )
        self.speed_combo.grid(row=0, column=3, sticky="ew", padx=(0, 10), pady=(8, 5))

        self.subtitle_check = tk.Checkbutton(
            options,
            text="Субтитры",
            variable=self.subtitle_var,
            command=self.on_preview_setting_changed,
            bg=SURFACE_2,
            fg=CYAN,
            selectcolor=BG,
            activebackground=SURFACE_2,
            activeforeground=CYAN,
            font=("Arial", 9, "bold"),
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2"
        )
        self.subtitle_check.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 8))

        self.label(options, "РАЗМЕР", color=MUTED, font=("Arial", 8, "bold")).grid(
            row=1, column=2, sticky="w", padx=(4, 5), pady=(0, 7)
        )
        self.subtitle_combo = ttk.Combobox(
            options,
            textvariable=self.subtitle_size,
            values=list(SUBTITLE_SIZES),
            state="readonly",
            width=11,
            style="Dark.TCombobox"
        )
        self.subtitle_combo.grid(row=1, column=3, sticky="ew", padx=(0, 10), pady=(0, 7))
        self.subtitle_combo.bind("<<ComboboxSelected>>", self._subtitle_size_changed)

        self.srt_check = tk.Checkbutton(
            options,
            text="Экспортировать субтитры .srt",
            variable=self.export_srt_var,
            bg=SURFACE_2,
            fg=MUTED,
            selectcolor=BG,
            activebackground=SURFACE_2,
            activeforeground=WHITE,
            font=("Arial", 8),
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2"
        )
        self.srt_check.grid(row=2, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 10))

        self.button(
            options,
            "Проверить голос",
            self.test_voice,
            color="#25354C"
        ).grid(row=2, column=2, columnspan=2, sticky="e", padx=10, pady=(0, 10))

        self.preview_panel = self.card(self.tab_create)
        self.preview_panel.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        self.preview_panel.grid_columnconfigure(0, weight=1)
        self.preview_panel.grid_rowconfigure(2, weight=1)

        preview_heading = tk.Frame(self.preview_panel, bg=SURFACE)
        preview_heading.grid(row=0, column=0, sticky="ew", padx=15, pady=(14, 2))
        preview_heading.grid_columnconfigure(0, weight=1)
        self.label(
            preview_heading,
            "Предпросмотр",
            color=WHITE,
            font=("Arial", 12, "bold")
        ).grid(row=0, column=0, sticky="w")
        self.label(
            preview_heading,
            "9:16",
            color=CYAN,
            font=("Arial", 9, "bold")
        ).grid(row=0, column=1, sticky="e")
        self.label(
            self.preview_panel,
            "Так будет выглядеть вертикальный кадр",
            color=MUTED,
            font=("Arial", 8)
        ).grid(row=1, column=0, sticky="w", padx=15, pady=(0, 6))

        self.preview_canvas = tk.Canvas(
            self.preview_panel,
            bg=SURFACE,
            bd=0,
            highlightthickness=0
        )
        self.preview_canvas.grid(row=2, column=0, sticky="nsew", padx=7, pady=3)
        self.preview_canvas.bind("<Configure>", self.draw_preview)

        preview_footer = tk.Frame(self.preview_panel, bg=SURFACE)
        preview_footer.grid(row=3, column=0, sticky="ew", padx=15, pady=(5, 14))
        self.label(
            preview_footer,
            "",
            color=MUTED,
            font=("Arial", 8),
            textvariable=self.preview_info_var
        ).pack(anchor="w")
        self.label(
            preview_footer,
            "720 × 1280 px  ·  25 FPS",
            color="#697A92",
            font=("Arial", 8)
        ).pack(anchor="w", pady=(3, 0))

    # --------------------------------------------------------

    def insert_script_template(self):
        template = (
            "ЗАЦЕПКА: Скажи, чем эта тема удивит зрителя.\n\n"
            "СУТЬ: Объясни главную мысль простыми словами.\n\n"
            "ПОЛЬЗА: Дай конкретный совет или короткий пример.\n\n"
            "ПРИЗЫВ: Предложи подписаться, сохранить или попробовать."
        )
        self.script_text.insert("insert", template)
        self.script_text.focus_set()
        self.update_script_details()
        self.schedule_preview()
        self.is_dirty = True
        self.schedule_autosave()

    def on_script_changed(self, _event=None):
        if not self.script_text.edit_modified():
            return
        self.script_text.edit_modified(False)
        self.update_script_details()
        self.schedule_preview()
        if not self._loading_project:
            self.is_dirty = True
            self.schedule_autosave()

    def on_preview_setting_changed(self):
        self.preview_info_var.set(
            "Субтитры включены" if self.subtitle_var.get() else "Субтитры выключены"
        )
        self.schedule_preview()

    def _subtitle_size_changed(self, _event=None):
        self.schedule_preview()

    def update_script_details(self):
        if not hasattr(self, "script_text"):
            return
        text = self.script_text.get("1.0", "end-1c").strip()
        word_count = len(re.findall(r"\S+", text))
        scene_count = len(split_script(text))
        estimate = max(1, round(word_count / 2.7)) if word_count else 0
        self.script_meta_var.set(
            f"{word_count} {russian_plural(word_count, 'слово', 'слова', 'слов')}"
            f"  ·  {scene_count} {russian_plural(scene_count, 'сцена', 'сцены', 'сцен')}"
            f"  ·  около {estimate} сек."
        )

    def schedule_preview(self):
        if not hasattr(self, "preview_canvas"):
            return
        if self._preview_after is not None:
            try:
                self.root.after_cancel(self._preview_after)
            except Exception:
                pass
        self._preview_after = self.root.after(70, self.draw_preview)

    @staticmethod
    def _rounded_rectangle(canvas, x1, y1, x2, y2, radius, **kwargs):
        radius = max(2, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2 - radius,
            x1, y1 + radius,
        ]
        return canvas.create_polygon(
            *points,
            smooth=True,
            splinesteps=18,
            **kwargs
        )

    @staticmethod
    def _mix_color(first, second, ratio):
        ratio = max(0.0, min(1.0, ratio))
        a = tuple(int(first[index:index + 2], 16) for index in (1, 3, 5))
        b = tuple(int(second[index:index + 2], 16) for index in (1, 3, 5))
        mixed = tuple(round(a[i] + (b[i] - a[i]) * ratio) for i in range(3))
        return "#" + "".join(f"{channel:02x}" for channel in mixed)

    def draw_preview(self, _event=None):
        if not hasattr(self, "preview_canvas"):
            return
        canvas = self.preview_canvas
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        if width < 40 or height < 40:
            return

        canvas.delete("all")
        available_width = max(40, width - 28)
        available_height = max(60, height - 22)
        phone_width = min(available_width, available_height * 9 / 16)
        phone_height = phone_width * 16 / 9
        left = (width - phone_width) / 2
        top = (height - phone_height) / 2
        right = left + phone_width
        bottom = top + phone_height
        radius = max(9, phone_width * 0.075)

        self._rounded_rectangle(
            canvas,
            left - 2,
            top - 2,
            right + 2,
            bottom + 2,
            radius + 2,
            fill="#050810",
            outline="#2B3C55",
            width=2
        )

        inner_left = left + 2
        inner_right = right - 2
        inner_top = top + 2
        inner_bottom = bottom - 2
        gradient_steps = 20
        for step in range(gradient_steps):
            y1 = inner_top + (inner_bottom - inner_top) * step / gradient_steps
            y2 = inner_top + (inner_bottom - inner_top) * (step + 1) / gradient_steps + 1
            shade = self._mix_color("#142443", "#080D19", step / (gradient_steps - 1))
            canvas.create_rectangle(
                inner_left,
                y1,
                inner_right,
                y2,
                fill=shade,
                outline=""
            )

        center_x = (left + right) / 2
        phone_height = inner_bottom - inner_top
        canvas.create_text(
            center_x,
            inner_top + phone_height * 0.09,
            text="NEUROHACK  ·  VK CLIPS",
            fill=CYAN,
            font=("Arial", max(7, int(phone_width * 0.045)), "bold")
        )

        icon_y = inner_top + phone_height * 0.37
        icon_radius = phone_width * 0.19
        canvas.create_oval(
            center_x - icon_radius,
            icon_y - icon_radius,
            center_x + icon_radius,
            icon_y + icon_radius,
            fill="#142844",
            outline="#24607A",
            width=max(1, int(phone_width * 0.009))
        )
        canvas.create_oval(
            center_x - icon_radius * 0.68,
            icon_y - icon_radius * 0.68,
            center_x + icon_radius * 0.68,
            icon_y + icon_radius * 0.68,
            outline="#31506F",
            width=1
        )
        canvas.create_text(
            center_x,
            icon_y,
            text="✦",
            fill=CYAN,
            font=("Arial", max(15, int(phone_width * 0.15)), "bold")
        )
        canvas.create_text(
            center_x,
            icon_y + icon_radius + phone_height * 0.055,
            text="ИДЕЯ  ·  ГОЛОС  ·  ВИДЕО",
            fill="#99AFC9",
            font=("Arial", max(6, int(phone_width * 0.032)), "bold")
        )

        subtitle_top = inner_top + phone_height * 0.68
        subtitle_bottom = inner_top + phone_height * 0.88
        self._rounded_rectangle(
            canvas,
            left + phone_width * 0.075,
            subtitle_top,
            right - phone_width * 0.075,
            subtitle_bottom,
            max(5, phone_width * 0.035),
            fill="#080B13",
            outline="#26374F",
            width=1
        )

        script = self.script_text.get("1.0", "end-1c").strip() if hasattr(self, "script_text") else ""
        snippet = " ".join(script.split()[:10]) if script else "Ваш текст появится здесь"
        if not self.subtitle_var.get():
            snippet = "Субтитры выключены"
        subtitle_scale = {
            "Маленькие": 0.052,
            "Средние": 0.062,
            "Крупные": 0.073
        }.get(self.subtitle_size.get(), 0.062)
        canvas.create_text(
            center_x,
            (subtitle_top + subtitle_bottom) / 2,
            text=snippet,
            width=phone_width * 0.72,
            justify="center",
            fill=WHITE if self.subtitle_var.get() else "#8190A7",
            font=("Arial", max(8, int(phone_width * subtitle_scale)), "bold")
        )

        canvas.create_text(
            center_x,
            inner_bottom - phone_height * 0.045,
            text="●  NEUROHACK STUDIO",
            fill="#6F829D",
            font=("Arial", max(6, int(phone_width * 0.03)), "bold")
        )

    # ========================================================
    # ИИ-ПОМОЩНИК
    # ========================================================

    def build_ai_tab(self):
        self.tab_ai.grid_columnconfigure(0, weight=1)
        self.tab_ai.grid_rowconfigure(1, weight=1)

        prompt_panel = self.card(self.tab_ai)
        prompt_panel.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        prompt_panel.grid_columnconfigure(0, weight=1)

        self.label(
            prompt_panel,
            "О чём будет ролик?",
            color=WHITE,
            font=("Arial", 12, "bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 3))
        self.label(
            prompt_panel,
            "Укажите тему — помощник подготовит сценарий, заголовок и описание.",
            color=MUTED,
            font=("Arial", 9)
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

        input_row = tk.Frame(prompt_panel, bg=SURFACE)
        input_row.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 14))
        input_row.grid_columnconfigure(0, weight=1)
        self.ai_topic_entry = ttk.Entry(
            input_row,
            textvariable=self.ai_topic,
            style="Dark.TEntry"
        )
        self.ai_topic_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        self.ai_topic_entry.insert(0, "Например: нейросеть для учёбы")
        self.ai_topic_entry.configure(foreground=MUTED)
        self.ai_topic_entry.bind("<FocusIn>", self._clear_ai_placeholder)
        self.ai_topic_entry.bind("<FocusOut>", self._restore_ai_placeholder)

        duration_box = tk.Frame(input_row, bg=SURFACE)
        duration_box.grid(row=0, column=1, sticky="e", padx=(0, 10))
        self.label(duration_box, "Длительность", color=MUTED, font=("Arial", 8)).pack(anchor="w", pady=(0, 3))
        ttk.Combobox(
            duration_box,
            textvariable=self.ai_duration,
            values=["15–30 секунд", "30–60 секунд", "60–90 секунд"],
            state="readonly",
            width=16,
            style="Dark.TCombobox"
        ).pack()

        self.button(
            input_row,
            "Создать сценарий",
            self.ai_generate,
            color=CYAN
        ).grid(row=0, column=2, sticky="e", padx=(0, 7))
        self.button(
            input_row,
            "10 идей",
            self.ai_ideas,
            color=SURFACE_2
        ).grid(row=0, column=3, sticky="e")

        result_panel = self.card(self.tab_ai)
        result_panel.grid(row=1, column=0, sticky="nsew")
        result_panel.grid_columnconfigure(0, weight=1)
        result_panel.grid_rowconfigure(1, weight=1)

        result_heading = tk.Frame(result_panel, bg=SURFACE)
        result_heading.grid(row=0, column=0, sticky="ew", padx=15, pady=(12, 8))
        result_heading.grid_columnconfigure(0, weight=1)
        self.label(
            result_heading,
            "Результат генерации",
            color=WHITE,
            font=("Arial", 11, "bold")
        ).grid(row=0, column=0, sticky="w")
        self.label(
            result_heading,
            "Можно отредактировать перед переносом",
            color=MUTED,
            font=("Arial", 8)
        ).grid(row=0, column=1, sticky="e")

        result_box = tk.Frame(
            result_panel,
            bg=EDITOR_BG,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1
        )
        result_box.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 10))
        result_box.grid_columnconfigure(0, weight=1)
        result_box.grid_rowconfigure(0, weight=1)
        self.ai_result = tk.Text(
            result_box,
            bg=EDITOR_BG,
            fg=WHITE,
            insertbackground=CYAN,
            selectbackground=PURPLE,
            selectforeground=WHITE,
            wrap="word",
            font=("Arial", 10),
            undo=True,
            relief="flat",
            bd=0,
            padx=13,
            pady=12,
            highlightthickness=0
        )
        result_scroll = ttk.Scrollbar(result_box, orient="vertical", command=self.ai_result.yview)
        self.ai_result.configure(yscrollcommand=result_scroll.set)
        self.ai_result.grid(row=0, column=0, sticky="nsew")
        result_scroll.grid(row=0, column=1, sticky="ns")

        result_actions = tk.Frame(result_panel, bg=SURFACE)
        result_actions.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 13))
        self.button(
            result_actions,
            "Копировать сценарий",
            self.copy_ai_script,
            color=SURFACE_2
        ).pack(side="left")
        self.button(
            result_actions,
            "Передать в редактор  →",
            self.ai_to_video,
            color=PURPLE
        ).pack(side="right")

    def _clear_ai_placeholder(self, _event=None):
        if self.ai_topic_entry.get() == "Например: нейросеть для учёбы":
            self.ai_topic_entry.delete(0, tk.END)
            self.ai_topic_entry.configure(foreground=WHITE)

    def _restore_ai_placeholder(self, _event=None):
        if not self.ai_topic_entry.get().strip():
            self.ai_topic_entry.delete(0, tk.END)
            self.ai_topic_entry.insert(0, "Например: нейросеть для учёбы")
            self.ai_topic_entry.configure(foreground=MUTED)

    def ai_generate(self):
        try:
            topic = self.ai_topic.get().strip()
            if topic == "Например: нейросеть для учёбы":
                topic = ""

            script = generate_script(topic, self.ai_duration.get())
            title = generate_title(topic)
            description = generate_description(topic)
            self.ai_script = script

            result = (
                f"ЗАГОЛОВОК:\n{title}\n\n"
                f"СЦЕНАРИЙ:\n{script}\n\n"
                f"ОПИСАНИЕ:\n{description}"
            )
            self.ai_result.delete("1.0", tk.END)
            self.ai_result.insert("1.0", result)
        except Exception as error:
            messagebox.showerror("Помощник", str(error))

    def get_ai_script_from_result(self):
        result = self.ai_result.get("1.0", "end-1c")
        match = re.search(
            r"(?is)СЦЕНАРИЙ:\s*(.*?)(?:\n\s*ОПИСАНИЕ:|\Z)",
            result
        )
        if match and match.group(1).strip():
            return match.group(1).strip()
        return self.ai_script.strip()

    def copy_ai_script(self):
        script = self.get_ai_script_from_result()
        if not script:
            messagebox.showwarning("Помощник", "Сначала создай сценарий.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(script)
        self.status_var.set("Сценарий скопирован в буфер обмена")

    def ai_to_video(self):
        script = self.get_ai_script_from_result()
        if not script:
            messagebox.showwarning("Помощник", "Сначала создай сценарий.")
            return

        self.script_text.delete("1.0", tk.END)
        self.script_text.insert("1.0", script)
        self.update_script_details()
        self.show_page("create")

    def ai_ideas(self):
        self.ai_script = ""
        ideas = generate_ideas(10)
        result = "10 ИДЕЙ ДЛЯ VK КЛИПОВ:\n\n"
        for index, idea in enumerate(ideas, 1):
            result += f"{index}. {idea}\n"
        self.ai_result.delete("1.0", tk.END)
        self.ai_result.insert("1.0", result)

    # ========================================================
    # МАТЕРИАЛЫ, МУЗЫКА И НАСТРОЙКИ
    # ========================================================

    def build_materials_tab(self):
        self.tab_materials.grid_columnconfigure(0, weight=1)
        self.tab_materials.grid_columnconfigure(1, weight=1)
        self.tab_materials.grid_rowconfigure(0, weight=1)

        material_panel = self.card(self.tab_materials)
        material_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        material_panel.grid_columnconfigure(0, weight=1)
        material_panel.grid_rowconfigure(2, weight=1)

        material_heading = tk.Frame(material_panel, bg=SURFACE)
        material_heading.grid(row=0, column=0, sticky="ew", padx=15, pady=(14, 5))
        material_heading.grid_columnconfigure(0, weight=1)
        self.label(
            material_heading,
            "Исходные материалы",
            color=WHITE,
            font=("Arial", 12, "bold")
        ).grid(row=0, column=0, sticky="w")
        self.label(
            material_heading,
            "",
            color=MUTED,
            font=("Arial", 8),
            textvariable=self.material_count_var
        ).grid(row=0, column=1, sticky="e")

        material_actions = tk.Frame(material_panel, bg=SURFACE)
        material_actions.grid(row=1, column=0, sticky="ew", padx=14, pady=(2, 9))
        self.button(
            material_actions,
            "+ Добавить",
            self.add_materials,
            color=CYAN
        ).pack(side="left", padx=(0, 6))
        self.button(
            material_actions,
            "Убрать",
            self.remove_selected_material,
            color=SURFACE_2
        ).pack(side="left", padx=6)
        self.button(
            material_actions,
            "Очистить",
            self.clear_materials,
            color=SURFACE_2
        ).pack(side="right")

        material_list_box = tk.Frame(
            material_panel,
            bg=EDITOR_BG,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1
        )
        material_list_box.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 9))
        material_list_box.grid_columnconfigure(0, weight=1)
        material_list_box.grid_rowconfigure(0, weight=1)
        self.material_list = tk.Listbox(
            material_list_box,
            bg=EDITOR_BG,
            fg=WHITE,
            selectbackground=PURPLE,
            selectforeground=WHITE,
            activestyle="none",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Arial", 9),
            padx=8,
            pady=6
        )
        material_scroll = ttk.Scrollbar(material_list_box, orient="vertical", command=self.material_list.yview)
        self.material_list.configure(yscrollcommand=material_scroll.set)
        self.material_list.grid(row=0, column=0, sticky="nsew")
        material_scroll.grid(row=0, column=1, sticky="ns")
        self.label(
            material_panel,
            "Поддерживаются изображения и видеофайлы.",
            color=MUTED,
            font=("Arial", 8)
        ).grid(row=3, column=0, sticky="w", padx=15, pady=(0, 13))

        scene_panel = self.card(self.tab_materials)
        scene_panel.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        scene_panel.grid_columnconfigure(0, weight=1)
        scene_panel.grid_rowconfigure(2, weight=1)

        scene_heading = tk.Frame(scene_panel, bg=SURFACE)
        scene_heading.grid(row=0, column=0, sticky="ew", padx=15, pady=(14, 7))
        scene_heading.grid_columnconfigure(0, weight=1)
        self.label(
            scene_heading,
            "Сцены сценария",
            color=WHITE,
            font=("Arial", 12, "bold")
        ).grid(row=0, column=0, sticky="w")
        self.label(
            scene_heading,
            "",
            color=MUTED,
            font=("Arial", 8),
            textvariable=self.scene_count_var
        ).grid(row=0, column=1, sticky="e")

        scene_controls = tk.Frame(scene_panel, bg=SURFACE)
        scene_controls.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 9))
        self.label(scene_controls, "Режим", color=MUTED, font=("Arial", 8, "bold")).pack(side="left", padx=(0, 7))
        self.mode_combo = ttk.Combobox(
            scene_controls,
            textvariable=self.mode_var,
            values=["Автоматически", "Вручную"],
            state="readonly",
            width=12,
            style="Dark.TCombobox"
        )
        self.mode_combo.pack(side="left", padx=(0, 8))
        self.button(
            scene_controls,
            "Разбить",
            self.prepare_scenes,
            color=SURFACE_2
        ).pack(side="right")

        scene_list_box = tk.Frame(
            scene_panel,
            bg=EDITOR_BG,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1
        )
        scene_list_box.grid(row=2, column=0, sticky="nsew", padx=14, pady=(0, 9))
        scene_list_box.grid_columnconfigure(0, weight=1)
        scene_list_box.grid_rowconfigure(0, weight=1)
        self.scene_list = tk.Listbox(
            scene_list_box,
            bg=EDITOR_BG,
            fg=WHITE,
            selectbackground=PURPLE,
            selectforeground=WHITE,
            activestyle="none",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Arial", 9),
            padx=8,
            pady=6
        )
        scene_scroll = ttk.Scrollbar(scene_list_box, orient="vertical", command=self.scene_list.yview)
        self.scene_list.configure(yscrollcommand=scene_scroll.set)
        self.scene_list.grid(row=0, column=0, sticky="nsew")
        scene_scroll.grid(row=0, column=1, sticky="ns")
        scene_actions = tk.Frame(scene_panel, bg=SURFACE)
        scene_actions.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 13))
        self.button(
            scene_actions,
            "Снять",
            self.clear_scene_material,
            color=SURFACE_2
        ).pack(side="left")
        self.button(
            scene_actions,
            "Назначить",
            self.assign_material,
            color=PURPLE
        ).pack(side="right")

    def build_music_tab(self):
        self.tab_music.grid_columnconfigure(0, weight=1)
        self.tab_music.grid_rowconfigure(1, weight=1)

        library_panel = self.card(self.tab_music)
        library_panel.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        library_panel.grid_columnconfigure(0, weight=1)
        self.label(
            library_panel,
            "Музыкальная библиотека",
            color=WHITE,
            font=("Arial", 12, "bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 3))
        self.label(
            library_panel,
            "Выберите трек для фона клипа или добавьте собственный MP3.",
            color=MUTED,
            font=("Arial", 9)
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))

        library_controls = tk.Frame(library_panel, bg=SURFACE)
        library_controls.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))
        library_controls.grid_columnconfigure(0, weight=1)
        self.music_combo = ttk.Combobox(
            library_controls,
            textvariable=self.music_var,
            state="readonly",
            style="Dark.TCombobox"
        )
        self.music_combo.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.button(
            library_controls,
            "Прослушать",
            self.preview_music,
            color=SURFACE_2
        ).grid(row=0, column=1, padx=4)
        self.button(
            library_controls,
            "+  Добавить MP3",
            self.add_music,
            color=CYAN
        ).grid(row=0, column=2, padx=4)
        self.button(
            library_controls,
            "Обновить",
            self.refresh_music,
            color=SURFACE_2
        ).grid(row=0, column=3, padx=4)
        self.button(
            library_controls,
            "Открыть папку",
            lambda: open_with_default_app(MUSIC),
            color=SURFACE_2
        ).grid(row=0, column=4, padx=(4, 0))

        volume_panel = self.card(self.tab_music)
        volume_panel.grid(row=1, column=0, sticky="nsew")
        volume_panel.grid_columnconfigure(0, weight=1)
        self.label(
            volume_panel,
            "Громкость фоновой музыки",
            color=WHITE,
            font=("Arial", 12, "bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(14, 3))
        self.label(
            volume_panel,
            "Рекомендуется 10–15%. Музыка должна быть разрешена для публикации.",
            color=MUTED,
            font=("Arial", 9)
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 16))

        volume_row = tk.Frame(volume_panel, bg=SURFACE)
        volume_row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 14))
        volume_row.grid_columnconfigure(0, weight=1)
        self.volume_scale = tk.Scale(
            volume_row,
            from_=0,
            to=50,
            variable=self.volume_var,
            orient="horizontal",
            resolution=1,
            showvalue=False,
            command=self.update_volume_display,
            bg=SURFACE,
            fg=WHITE,
            troughcolor="#27374D",
            activebackground=CYAN,
            highlightthickness=0,
            bd=0,
            sliderrelief="flat",
            cursor="hand2"
        )
        self.volume_scale.grid(row=0, column=0, sticky="ew", padx=(0, 14))
        self.label(
            volume_row,
            "",
            color=CYAN,
            font=("Arial", 11, "bold"),
            textvariable=self.volume_label_var
        ).grid(row=0, column=1, sticky="e")
        self.update_volume_display(self.volume_var.get())

        folder_hint = self.card(self.tab_music)
        folder_hint.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.label(
            folder_hint,
            f"Папка библиотеки: {MUSIC}",
            color=MUTED,
            font=("Arial", 8),
            wraplength=800,
            justify="left"
        ).pack(anchor="w", padx=15, pady=12)

    def update_volume_display(self, value):
        try:
            self.volume_label_var.set(f"{int(float(value))}%")
        except (TypeError, ValueError):
            self.volume_label_var.set(f"{int(self.volume_var.get())}%")

    def build_library_tab(self):
        self.tab_library.grid_columnconfigure(0, weight=1)
        self.tab_library.grid_columnconfigure(1, weight=1)
        self.tab_library.grid_rowconfigure(0, weight=1)

        video_panel = self.card(self.tab_library)
        video_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        video_panel.grid_columnconfigure(0, weight=1)
        video_panel.grid_rowconfigure(1, weight=1)
        video_heading = tk.Frame(video_panel, bg=SURFACE)
        video_heading.grid(row=0, column=0, sticky="ew", padx=15, pady=(14, 8))
        video_heading.grid_columnconfigure(0, weight=1)
        self.label(
            video_heading,
            "Готовые клипы",
            color=WHITE,
            font=("Arial", 12, "bold")
        ).grid(row=0, column=0, sticky="w")
        self.label(
            video_heading,
            "",
            color=MUTED,
            font=("Arial", 8),
            textvariable=self.library_video_count_var
        ).grid(row=0, column=1, sticky="e")

        video_box = tk.Frame(
            video_panel,
            bg=EDITOR_BG,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1
        )
        video_box.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 9))
        video_box.grid_columnconfigure(0, weight=1)
        video_box.grid_rowconfigure(0, weight=1)
        self.library_video_list = tk.Listbox(
            video_box,
            bg=EDITOR_BG,
            fg=WHITE,
            selectbackground=PURPLE,
            selectforeground=WHITE,
            activestyle="none",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Arial", 9),
            padx=8,
            pady=6
        )
        video_scroll = ttk.Scrollbar(video_box, orient="vertical", command=self.library_video_list.yview)
        self.library_video_list.configure(yscrollcommand=video_scroll.set)
        self.library_video_list.grid(row=0, column=0, sticky="nsew")
        video_scroll.grid(row=0, column=1, sticky="ns")
        self.library_video_list.bind("<Double-Button-1>", lambda _event: self.open_selected_video())

        video_actions = tk.Frame(video_panel, bg=SURFACE)
        video_actions.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 13))
        self.button(
            video_actions,
            "Открыть клип",
            self.open_selected_video,
            color=CYAN
        ).pack(side="left", padx=(0, 6))
        self.button(
            video_actions,
            "Обновить",
            self.refresh_library,
            color=SURFACE_2
        ).pack(side="left", padx=6)
        self.button(
            video_actions,
            "Папка",
            self.open_output,
            color=SURFACE_2
        ).pack(side="right")

        project_panel = self.card(self.tab_library)
        project_panel.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        project_panel.grid_columnconfigure(0, weight=1)
        project_panel.grid_rowconfigure(1, weight=1)
        project_heading = tk.Frame(project_panel, bg=SURFACE)
        project_heading.grid(row=0, column=0, sticky="ew", padx=15, pady=(14, 8))
        project_heading.grid_columnconfigure(0, weight=1)
        self.label(
            project_heading,
            "Проекты",
            color=WHITE,
            font=("Arial", 12, "bold")
        ).grid(row=0, column=0, sticky="w")
        self.label(
            project_heading,
            "",
            color=MUTED,
            font=("Arial", 8),
            textvariable=self.library_project_count_var
        ).grid(row=0, column=1, sticky="e")

        project_box = tk.Frame(
            project_panel,
            bg=EDITOR_BG,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1
        )
        project_box.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 9))
        project_box.grid_columnconfigure(0, weight=1)
        project_box.grid_rowconfigure(0, weight=1)
        self.library_project_list = tk.Listbox(
            project_box,
            bg=EDITOR_BG,
            fg=WHITE,
            selectbackground=PURPLE,
            selectforeground=WHITE,
            activestyle="none",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Arial", 9),
            padx=8,
            pady=6
        )
        project_scroll = ttk.Scrollbar(project_box, orient="vertical", command=self.library_project_list.yview)
        self.library_project_list.configure(yscrollcommand=project_scroll.set)
        self.library_project_list.grid(row=0, column=0, sticky="nsew")
        project_scroll.grid(row=0, column=1, sticky="ns")
        self.library_project_list.bind("<Double-Button-1>", lambda _event: self.load_selected_project())

        project_actions = tk.Frame(project_panel, bg=SURFACE)
        project_actions.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 13))
        self.button(
            project_actions,
            "Открыть",
            self.load_selected_project,
            color=PURPLE
        ).pack(side="left", padx=(0, 6))
        self.button(
            project_actions,
            "Обновить",
            self.refresh_library,
            color=SURFACE_2
        ).pack(side="left", padx=6)
        self.button(
            project_actions,
            "Сохранить",
            self.save_project,
            color=SURFACE_2
        ).pack(side="right")

    def refresh_library(self):
        if not hasattr(self, "library_video_list"):
            return

        self.output_video_files = sorted(
            (
                path for path in OUTPUT.iterdir()
                if path.is_file() and path.suffix.lower() == ".mp4"
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True
        )
        self.library_video_list.delete(0, tk.END)
        for path in self.output_video_files:
            modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
            size_mb = path.stat().st_size / (1024 * 1024)
            self.library_video_list.insert(
                tk.END,
                f"{path.name}  ·  {size_mb:.1f} MB  ·  {modified}"
            )
        video_count = len(self.output_video_files)
        self.library_video_count_var.set(
            f"{video_count} {russian_plural(video_count, 'клип', 'клипа', 'клипов')}"
        )

        self.project_file_paths = sorted(
            (
                path for path in PROJECTS.glob("*.json")
                if path.is_file() and path.resolve() != AUTOSAVE_PATH.resolve()
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True
        )
        self.library_project_list.delete(0, tk.END)
        for path in self.project_file_paths:
            modified = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d.%m.%Y %H:%M")
            self.library_project_list.insert(
                tk.END,
                f"{path.stem}  ·  {modified}"
            )
        project_count = len(self.project_file_paths)
        self.library_project_count_var.set(
            f"{project_count} {russian_plural(project_count, 'проект', 'проекта', 'проектов')}"
        )

    def open_selected_video(self):
        selection = self.library_video_list.curselection()
        if not selection:
            messagebox.showinfo("Клипы", "Выберите клип в списке.")
            return
        path = self.output_video_files[selection[0]]
        if not path.exists():
            self.refresh_library()
            messagebox.showwarning("Клипы", "Файл больше не найден. Список обновлён.")
            return
        open_with_default_app(path)

    def load_selected_project(self):
        selection = self.library_project_list.curselection()
        if not selection:
            messagebox.showinfo("Проекты", "Выберите проект в списке.")
            return
        self.load_project(self.project_file_paths[selection[0]])

    def build_settings_tab(self):
        self.tab_settings.grid_columnconfigure(0, weight=1)
        self.tab_settings.grid_columnconfigure(1, weight=1)
        self.tab_settings.grid_rowconfigure(0, weight=1)

        info_panel = self.card(self.tab_settings)
        info_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        self.label(
            info_panel,
            "Параметры проекта",
            color=WHITE,
            font=("Arial", 12, "bold")
        ).pack(anchor="w", padx=16, pady=(15, 10))
        information = (
            "Видео: 720 × 1280 px, 25 FPS\n"
            "Формат: вертикальный 9:16, H.264\n"
            "Озвучка: Piper · русский язык\n"
            "Субтитры и фоновая музыка — по настройкам проекта.\n\n"
            "ИИ-помощник использует встроенные шаблоны и работает без интернета и платных API."
        )
        self.label(
            info_panel,
            information,
            color="#C0CBD9",
            font=("Arial", 10),
            justify="left",
            anchor="nw",
            wraplength=420
        ).pack(fill="x", padx=16, pady=(0, 14))
        tk.Frame(info_panel, bg=BORDER, height=1).pack(fill="x", padx=16, pady=(0, 12))
        self.button(
            info_panel,
            "Открыть папку программы",
            lambda: open_with_default_app(BASE),
            color=SURFACE_2
        ).pack(anchor="w", padx=16, pady=(0, 15))

        diagnostics = self.card(self.tab_settings)
        diagnostics.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        diagnostics.grid_columnconfigure(0, weight=1)
        self.label(
            diagnostics,
            "Состояние компонентов",
            color=WHITE,
            font=("Arial", 12, "bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(15, 4))
        self.component_status_var = tk.StringVar(value="Проверка ещё не запускалась")
        self.label(
            diagnostics,
            "",
            color=MUTED,
            font=("Arial", 9),
            textvariable=self.component_status_var,
            wraplength=360,
            justify="left",
            anchor="w"
        ).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.button(
            diagnostics,
            "Проверить компоненты",
            self.show_components,
            color=CYAN
        ).grid(row=2, column=0, sticky="w", padx=16, pady=(0, 16))

        directories = self.card(self.tab_settings)
        directories.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        directories.grid_columnconfigure(0, weight=1)
        self.label(
            directories,
            "Папки приложения",
            color=WHITE,
            font=("Arial", 10, "bold")
        ).grid(row=0, column=0, sticky="w", padx=15, pady=(11, 3))
        self.label(
            directories,
            f"Результаты: {OUTPUT}    ·    Проекты: {PROJECTS}    ·    Музыка: {MUSIC}",
            color=MUTED,
            font=("Arial", 8),
            wraplength=850,
            justify="left"
        ).grid(row=1, column=0, sticky="w", padx=15, pady=(0, 11))

    # ========================================================
    # КОПИРОВАНИЕ И ВСТАВКА
    # ========================================================

    def enable_clipboard(self):
        def handle_key(event):
            if not (event.state & 0x4):
                return

            actions = {
                67: "<<Copy>>",
                86: "<<Paste>>",
                88: "<<Cut>>",
                65: "<<SelectAll>>"
            }

            action = actions.get(event.keycode)

            if action:
                event.widget.event_generate(action)
                return "break"

        def show_menu(event):
            widget = event.widget

            if not isinstance(
                widget,
                (tk.Text, tk.Entry, ttk.Entry)
            ):
                return

            menu = tk.Menu(widget, tearoff=0)

            for title, action in [
                ("Вырезать", "<<Cut>>"),
                ("Копировать", "<<Copy>>"),
                ("Вставить", "<<Paste>>"),
                ("Выделить всё", "<<SelectAll>>")
            ]:
                menu.add_command(
                    label=title,
                    command=lambda a=action: widget.event_generate(a)
                )

            menu.tk_popup(
                event.x_root,
                event.y_root
            )

        self.root.bind_all(
            "<Control-KeyPress>",
            handle_key,
            add="+"
        )

        for widget_class in ["Text", "Entry", "TEntry"]:
            self.root.bind_class(
                widget_class,
                "<Button-3>",
                show_menu,
                add="+"
            )

    # ========================================================
    # МАТЕРИАЛЫ
    # ========================================================

    def add_materials(self):
        files = filedialog.askopenfilenames(
            title="Добавить фото и видео",
            filetypes=[
                (
                    "Фото и видео",
                    "*.jpg *.jpeg *.png *.mp4 *.mov *.mkv *.avi"
                )
            ]
        )

        for file in files:
            if file not in self.materials:
                self.materials.append(file)

        if files:
            self.refresh_materials()
            self.is_dirty = True
            self.schedule_autosave()

    def remove_selected_material(self):
        selection = self.material_list.curselection()
        if not selection:
            messagebox.showinfo("Материалы", "Выберите файл, который нужно убрать.")
            return

        removed = self.materials.pop(selection[0])
        self.scene_assignments = {
            index: path
            for index, path in self.scene_assignments.items()
            if str(path) != str(removed)
        }
        self.refresh_materials()
        self.refresh_scenes()
        self.is_dirty = True
        self.schedule_autosave()

    def refresh_materials(self):
        self.material_list.delete(0, tk.END)

        for item in self.materials:
            self.material_list.insert(
                tk.END,
                Path(item).name
            )

        count = len(self.materials)
        suffix = russian_plural(count, "файл", "файла", "файлов")
        self.material_count_var.set(f"{count} {suffix}")

    def clear_materials(self):
        if not self.materials and not self.scene_assignments:
            return
        self.materials.clear()
        self.scene_assignments.clear()
        self.refresh_materials()
        self.refresh_scenes()
        self.is_dirty = True
        self.schedule_autosave()

    # ========================================================
    # СЦЕНЫ
    # ========================================================

    def prepare_scenes(self):
        text = self.script_text.get(
            "1.0",
            tk.END
        ).strip()

        old_scenes = list(self.prepared_scenes)
        old_assignments = dict(self.scene_assignments)
        new_scenes = split_script(text)
        retained_assignments = {}

        for old_start, new_start, size in SequenceMatcher(
            a=old_scenes,
            b=new_scenes,
            autojunk=False
        ).get_matching_blocks():
            for offset in range(size):
                old_index = old_start + offset
                new_index = new_start + offset
                if old_index in old_assignments:
                    retained_assignments[new_index] = old_assignments[old_index]

        self.prepared_scenes = new_scenes
        self.scene_assignments = retained_assignments
        self.update_script_details()
        self.refresh_scenes()
        self.is_dirty = True
        self.schedule_autosave()

        messagebox.showinfo(
            "Сцены",
            f"Подготовлено сцен: {len(self.prepared_scenes)}. "
            f"Сохранено назначений: {len(retained_assignments)}."
        )

    def refresh_scenes(self):
        self.scene_list.delete(0, tk.END)

        for index, scene in enumerate(
            self.prepared_scenes
        ):
            material = self.scene_assignments.get(index)

            name = (
                Path(material).name
                if material else
                "не назначен"
            )

            self.scene_list.insert(
                tk.END,
                f"{index + 1}. {scene[:50]} [{name}]"
            )

        count = len(self.prepared_scenes)
        suffix = russian_plural(count, "сцена", "сцены", "сцен")
        self.scene_count_var.set(f"{count} {suffix}")

    def clear_scene_material(self):
        selected = self.scene_list.curselection()
        if not selected:
            messagebox.showinfo("Сцены", "Сначала выберите сцену.")
            return
        if self.scene_assignments.pop(selected[0], None) is None:
            messagebox.showinfo("Сцены", "Для этой сцены материал не назначен.")
            return
        self.refresh_scenes()
        self.scene_list.selection_set(selected[0])
        self.is_dirty = True
        self.schedule_autosave()

    def assign_material(self):
        selected = self.scene_list.curselection()

        if not selected:
            messagebox.showwarning(
                "Сцены",
                "Сначала выбери сцену."
            )
            return

        file = filedialog.askopenfilename(
            title="Материал для сцены",
            filetypes=[
                (
                    "Фото и видео",
                    "*.jpg *.jpeg *.png *.mp4 *.mov *.mkv *.avi"
                )
            ]
        )

        if file:
            self.scene_assignments[selected[0]] = file

            if file not in self.materials:
                self.materials.append(file)

            self.refresh_materials()
            self.refresh_scenes()
            self.scene_list.selection_set(selected[0])
            self.is_dirty = True
            self.schedule_autosave()

    # ========================================================
    # МУЗЫКА
    # ========================================================

    def refresh_music(self):
        files = sorted(MUSIC.glob("*.mp3"))

        self.music_files = {
            file.name: file
            for file in files
        }

        values = [
            "Без музыки"
        ] + list(self.music_files)

        self.music_combo["values"] = values

        if self.music_var.get() not in values:
            self.music_var.set("Без музыки")

    def add_music(self):
        files = filedialog.askopenfilenames(
            title="Добавить музыку",
            filetypes=[("MP3", "*.mp3")]
        )

        for file in files:
            source = Path(file)
            destination = MUSIC / source.name

            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)

        self.refresh_music()

    def preview_music(self):
        name = self.music_var.get()
        if name == "Без музыки":
            messagebox.showinfo("Музыка", "Сначала выберите трек из библиотеки.")
            return
        path = MUSIC / name
        if not path.is_file():
            self.refresh_music()
            messagebox.showwarning("Музыка", "Файл не найден. Библиотека обновлена.")
            return
        open_with_default_app(path)

    # ========================================================
    # СОХРАНЕНИЕ ПРОЕКТА
    # ========================================================

    def collect_project_data(self):
        return {
            "version": 2,
            "script": self.script_text.get("1.0", "end-1c").strip(),
            "voice": self.voice_var.get(),
            "speed": self.speed_var.get(),
            "subtitles": self.subtitle_var.get(),
            "export_srt": self.export_srt_var.get(),
            "subtitle_size": self.subtitle_size.get(),
            "materials": list(self.materials),
            "mode": self.mode_var.get(),
            "assignments": {str(key): value for key, value in self.scene_assignments.items()},
            "music": self.music_var.get(),
            "volume": float(self.volume_var.get()),
            "project_file": str(self.current_project_file) if self.current_project_file else ""
        }

    @staticmethod
    def write_project_file(path, data):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with open(temporary, "w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
        temporary.replace(path)

    def save_project(self):
        file = filedialog.asksaveasfilename(
            initialdir=PROJECTS,
            defaultextension=".json",
            filetypes=[("Проект НЕЙРОХАК", "*.json")]
        )
        if not file:
            return

        try:
            self.current_project_file = Path(file).resolve()
            self.write_project_file(self.current_project_file, self.collect_project_data())
            self.is_dirty = False
            if self._autosave_after is not None:
                try:
                    self.root.after_cancel(self._autosave_after)
                except Exception:
                    pass
                self._autosave_after = None
            try:
                AUTOSAVE_PATH.unlink(missing_ok=True)
            except OSError:
                pass
            self.refresh_library()
            self.status_var.set(f"Проект сохранён: {self.current_project_file.name}")
            messagebox.showinfo("Проект", "Проект сохранён.")
        except Exception as error:
            write_error(error)
            messagebox.showerror("Ошибка сохранения", str(error))

    def apply_project_data(self, data):
        if not isinstance(data, dict):
            raise ValueError("Файл проекта имеет неверный формат.")

        self._loading_project = True
        try:
            script = data.get("script", "")
            script = script if isinstance(script, str) else str(script)
            self.script_text.delete("1.0", tk.END)
            self.script_text.insert("1.0", script)
            self.script_text.edit_modified(False)

            voice = data.get("voice", "Мужской")
            self.voice_var.set(
                voice if isinstance(voice, str) and voice in VOICE_MODELS else "Мужской"
            )
            speed = data.get("speed", "Нормальная")
            self.speed_var.set(
                speed if isinstance(speed, str) and speed in VOICE_SPEEDS else "Нормальная"
            )
            self.subtitle_var.set(bool(data.get("subtitles", True)))
            self.export_srt_var.set(bool(data.get("export_srt", True)))
            subtitle_size = data.get("subtitle_size", "Средние")
            self.subtitle_size.set(
                subtitle_size
                if isinstance(subtitle_size, str) and subtitle_size in SUBTITLE_SIZES
                else "Средние"
            )
            mode = data.get("mode", "Автоматически")
            self.mode_var.set(
                mode if mode in ("Автоматически", "Вручную") else "Автоматически"
            )

            materials = data.get("materials", [])
            if not isinstance(materials, list):
                materials = []
            self.materials = [str(item) for item in materials if isinstance(item, (str, Path))]
            self.prepared_scenes = split_script(script)
            assignments = data.get("assignments", {})
            self.scene_assignments = {}
            if isinstance(assignments, dict):
                for key, value in assignments.items():
                    try:
                        index = int(key)
                    except (TypeError, ValueError):
                        continue
                    if 0 <= index < len(self.prepared_scenes) and isinstance(value, str):
                        self.scene_assignments[index] = value

            try:
                volume = float(data.get("volume", 12))
                self.volume_var.set(max(0, min(50, volume)))
            except (TypeError, ValueError):
                self.volume_var.set(12)

            self.refresh_music()
            music = data.get("music", "Без музыки")
            self.music_var.set(
                music
                if isinstance(music, str) and music in self.music_combo["values"]
                else "Без музыки"
            )
            self.refresh_materials()
            self.refresh_scenes()
            self.update_script_details()
            self.preview_info_var.set(
                "Субтитры включены" if self.subtitle_var.get() else "Субтитры выключены"
            )
            self.schedule_preview()
            self.update_volume_display(self.volume_var.get())
        finally:
            self._loading_project = False

    def load_project(self, path=None, show_message=True):
        if path is None:
            path = filedialog.askopenfilename(
                initialdir=PROJECTS,
                filetypes=[("Проект НЕЙРОХАК", "*.json")]
            )
        if not path:
            return

        path = Path(path)
        try:
            with open(path, "r", encoding="utf-8") as source:
                data = json.load(source)
            self.apply_project_data(data)
            self.current_project_file = path.resolve()
            self.is_dirty = False
            if self._autosave_after is not None:
                try:
                    self.root.after_cancel(self._autosave_after)
                except Exception:
                    pass
                self._autosave_after = None
            try:
                AUTOSAVE_PATH.unlink(missing_ok=True)
            except OSError:
                pass
            self.refresh_library()
            self.status_var.set(f"Проект открыт: {path.name}")
            if show_message:
                messagebox.showinfo("Проект", "Проект открыт.")
        except Exception as error:
            write_error(error)
            messagebox.showerror("Ошибка открытия проекта", str(error))

    def on_project_setting_changed(self, *_args):
        if self._loading_project:
            return
        self.is_dirty = True
        self.schedule_autosave()

    def schedule_autosave(self):
        if self._loading_project or not self.is_dirty:
            return
        if self._autosave_after is not None:
            try:
                self.root.after_cancel(self._autosave_after)
            except Exception:
                pass
        self._autosave_after = self.root.after(1200, self.write_autosave)

    def write_autosave(self):
        self._autosave_after = None
        if self._loading_project or not self.is_dirty:
            return
        try:
            self.write_project_file(AUTOSAVE_PATH, self.collect_project_data())
        except Exception as error:
            write_error(error)

    def restore_autosave(self):
        if not AUTOSAVE_PATH.exists():
            return
        try:
            with open(AUTOSAVE_PATH, "r", encoding="utf-8") as source:
                data = json.load(source)
        except Exception as error:
            write_error(error)
            return

        if not messagebox.askyesno(
            "Восстановить работу?",
            "Найдена автокопия последней сессии. Восстановить сценарий и настройки?"
        ):
            try:
                AUTOSAVE_PATH.unlink()
            except OSError:
                pass
            return

        try:
            self.apply_project_data(data)
            source_project = data.get("project_file")
            self.current_project_file = (
                Path(source_project)
                if isinstance(source_project, str) and source_project
                else None
            )
            self.is_dirty = True
            self.status_var.set("Последняя сессия восстановлена")
        except Exception as error:
            write_error(error)
            messagebox.showerror("Автосохранение", str(error))

    def on_close(self):
        if self.busy:
            if not messagebox.askyesno(
                "Задача выполняется",
                "Остановить текущую задачу и закрыть программу?"
            ):
                return
            self._close_when_idle = True
            self.cancel_creation()
            return

        if self.is_dirty:
            self.write_autosave()
        self.root.destroy()

    # ========================================================
    # ПРОВЕРКА ГОЛОСА
    # ========================================================

    def test_voice(self):
        if self.busy:
            return

        problems = check_components()

        if problems:
            messagebox.showerror(
                "Компоненты",
                "\n".join(problems)
            )
            return

        voice = self.voice_var.get()
        speed = self.speed_var.get()

        self.busy = True
        self.cancel_event.clear()
        self.set_progress(0)
        self.create_button.configure(
            state="disabled",
            text="Проверяем голос…"
        )
        self.cancel_button.configure(state="normal")
        self.status_var.set("Проверка озвучки...")

        def worker():
            try:
                file = OUTPUT / "test_voice.wav"

                generate_voice(
                    "Привет! Это Нейрохак Студия. "
                    "Проверяем качество русской озвучки.",
                    voice,
                    speed,
                    file,
                    cancel_event=self.cancel_event
                )

                self.root.after(
                    0,
                    lambda: open_with_default_app(file)
                )

                self.update_progress(100, "Проверка голоса завершена")

            except TaskCancelled:
                self.update_status("Проверка голоса отменена")

            except Exception as error:
                write_error(error)
                text = str(error)

                self.root.after(
                    0,
                    lambda text=text: messagebox.showerror(
                        "Ошибка озвучки",
                        text
                    )
                )

            finally:
                self.root.after(
                    0,
                    self.finish_task
                )

        threading.Thread(
            target=worker,
            daemon=True
        ).start()

    # ========================================================
    # СОЗДАНИЕ КЛИПА
    # ========================================================

    def start_creation(self):
        if self.busy:
            return

        problems = check_components()

        if problems:
            messagebox.showerror(
                "Компоненты",
                "\n".join(problems)
            )
            return

        script = self.script_text.get(
            "1.0",
            tk.END
        ).strip()

        if not script:
            messagebox.showwarning(
                "Сценарий",
                "Напиши сценарий клипа."
            )
            return

        scenes = split_script(script)

        if not scenes:
            return

        if self.mode_var.get() == "Вручную":
            if (
                self.prepared_scenes != scenes
                and self.scene_assignments
            ):
                messagebox.showwarning(
                    "Сцены изменились",
                    "Подготовь сцены заново."
                )
                return

        valid_materials = [
            str(path) for path in self.materials
            if Path(path).is_file()
        ]
        valid_assignments = {
            int(index): str(path)
            for index, path in self.scene_assignments.items()
            if Path(path).is_file()
        }
        referenced = set(map(str, self.materials)) | set(
            str(path) for path in self.scene_assignments.values()
        )
        missing_materials = sorted(
            path for path in referenced if not Path(path).is_file()
        )
        if missing_materials:
            preview = "\n".join(Path(path).name for path in missing_materials[:5])
            if not messagebox.askyesno(
                "Материалы не найдены",
                f"Не удалось найти файлов: {len(missing_materials)}.\n{preview}\n\n"
                "Продолжить без недоступных материалов?"
            ):
                return
            self.materials = valid_materials
            self.scene_assignments = valid_assignments
            self.refresh_materials()
            self.refresh_scenes()
            self.is_dirty = True
            self.schedule_autosave()

        settings = {
            "scenes": scenes,
            "voice": self.voice_var.get(),
            "speed": self.speed_var.get(),
            "subtitles": self.subtitle_var.get(),
            "export_srt": self.export_srt_var.get(),
            "subtitle_size": self.subtitle_size.get(),
            "materials": valid_materials,
            "mode": self.mode_var.get(),
            "assignments": valid_assignments,
            "music": self.music_var.get(),
            "volume": self.volume_var.get()
        }

        self.busy = True
        self.cancel_event.clear()
        self.set_progress(0)
        self.create_button.configure(
            state="disabled",
            text="СОБИРАЕМ КЛИП…"
        )
        self.cancel_button.configure(state="normal")
        self.update_status("Подготовка к созданию клипа...")

        threading.Thread(
            target=self.process_video,
            args=(settings,),
            daemon=True
        ).start()

    # --------------------------------------------------------

    def set_progress(self, value):
        value = max(0.0, min(100.0, float(value)))
        self.progress_var.set(value)
        self.progress_percent_var.set(f"{round(value)}%")

    def cancel_creation(self):
        if not self.busy or self.cancel_event.is_set():
            return
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status_var.set("Останавливаем задачу… дождитесь завершения текущего этапа.")

    def update_status(self, text):
        self.root.after(
            0,
            lambda text=text: self.status_var.set(text)
        )

    def update_progress(self, value, text=None):
        def apply_update():
            self.set_progress(value)
            if text is not None:
                self.status_var.set(text)

        self.root.after(0, apply_update)

    # --------------------------------------------------------

    def process_video(self, settings):
        try:
            timestamp = datetime.now().strftime(
                "%Y%m%d_%H%M%S_%f"
            )

            final_file = OUTPUT / (
                f"NEUROHACK_42_{timestamp}.mp4"
            )

            self.last_srt = None
            with tempfile.TemporaryDirectory(
                prefix="neurohack42_"
            ) as temp:
                workdir = Path(temp)

                scene_files = []
                captions = []
                timeline = 0.0
                scenes = settings["scenes"]
                scene_total = max(1, len(scenes))

                for index, text in enumerate(scenes):
                    if self.cancel_event.is_set():
                        raise TaskCancelled("Задача отменена пользователем.")
                    number = index + 1

                    self.update_progress(
                        index / scene_total * 78,
                        f"Сцена {number}/{len(scenes)} · генерируем озвучку"
                    )

                    voice_file = workdir / (
                        f"voice_{number:03d}.wav"
                    )

                    generate_voice(
                        text,
                        settings["voice"],
                        settings["speed"],
                        voice_file,
                        cancel_event=self.cancel_event
                    )
                    self.update_progress(
                        (index + 0.42) / scene_total * 78,
                        f"Сцена {number}/{len(scenes)} · готовим графику и субтитры"
                    )

                    overlay_file = workdir / (
                        f"overlay_{number:03d}.png"
                    )

                    create_base_overlay(
                        overlay_file,
                        number
                    )

                    subtitle_files = []
                    phrases = split_subtitles(text)

                    if settings.get("export_srt", True) and phrases:
                        speech_duration = audio_duration(voice_file)
                        phrase_duration = speech_duration / len(phrases)
                        for phrase_index, phrase in enumerate(phrases):
                            start = timeline + phrase_index * phrase_duration
                            end = timeline + (phrase_index + 1) * phrase_duration
                            captions.append((start, end, phrase))
                        timeline += speech_duration + 0.20

                    if settings["subtitles"]:
                        for phrase_index, phrase in enumerate(phrases):
                            if self.cancel_event.is_set():
                                raise TaskCancelled("Задача отменена пользователем.")
                            subtitle_file = workdir / (
                                f"sub_{number:03d}_"
                                f"{phrase_index:03d}.png"
                            )
                            create_subtitle_image(
                                phrase,
                                subtitle_file,
                                settings["subtitle_size"]
                            )
                            subtitle_files.append(subtitle_file)

                    material = None

                    if settings["mode"] == "Вручную":
                        material = settings[
                            "assignments"
                        ].get(index)

                    elif settings["materials"]:
                        material = settings[
                            "materials"
                        ][
                            index % len(
                                settings["materials"]
                            )
                        ]

                    scene_file = workdir / (
                        f"scene_{number:03d}.mp4"
                    )

                    self.update_progress(
                        (index + 0.5) / scene_total * 78,
                        f"Сцена {number}/{len(scenes)} · собираем видео"
                    )

                    make_scene(
                        material,
                        voice_file,
                        scene_file,
                        overlay_file,
                        subtitle_files,
                        settings["subtitles"],
                        cancel_event=self.cancel_event
                    )

                    scene_files.append(scene_file)
                    self.update_progress(
                        (index + 1) / scene_total * 78,
                        f"Сцена {number}/{len(scenes)} готова"
                    )

                self.update_progress(82, "Объединяем сцены...")

                combined_file = workdir / "combined.mp4"

                combine_scenes(
                    scene_files,
                    combined_file,
                    workdir,
                    cancel_event=self.cancel_event
                )

                music_file = None
                music_name = settings["music"]

                if music_name != "Без музыки":
                    candidate = MUSIC / music_name

                    if candidate.exists():
                        music_file = candidate

                self.update_progress(92, "Добавляем фоновую музыку...")

                add_background_music(
                    combined_file,
                    music_file,
                    settings["volume"] / 100,
                    final_file,
                    cancel_event=self.cancel_event
                )

                if self.cancel_event.is_set():
                    raise TaskCancelled("Задача отменена пользователем.")
                if settings.get("export_srt", True) and captions:
                    srt_file = final_file.with_suffix(".srt")
                    write_srt(srt_file, captions)
                    self.last_srt = srt_file

                if self.cancel_event.is_set():
                    raise TaskCancelled("Задача отменена пользователем.")
                self.last_video = final_file
                self.update_progress(100, "Финальные штрихи...")

            self.update_status("✅ Клип готов: " + final_file.name)
            self.root.after(0, self.refresh_library)
            completion_message = "VK-клип создан!\n\n" + str(final_file)
            if self.last_srt and self.last_srt.exists():
                completion_message += "\n\nСубтитры: " + str(self.last_srt)
            self.root.after(
                0,
                lambda text=completion_message: messagebox.showinfo("Готово!", text)
            )

        except TaskCancelled:
            for partial in (locals().get("final_file"), locals().get("srt_file")):
                if partial and Path(partial).exists():
                    try:
                        Path(partial).unlink()
                    except OSError:
                        pass
            self.update_status("⏹ Создание клипа отменено")

        except Exception as error:
            for partial in (locals().get("final_file"), locals().get("srt_file")):
                if partial and Path(partial).exists():
                    try:
                        Path(partial).unlink()
                    except OSError:
                        pass
            write_error(error)
            text = str(error)

            self.update_status(
                "❌ Ошибка создания клипа"
            )

            self.root.after(
                0,
                lambda text=text: messagebox.showerror(
                    "Ошибка",
                    text[:3500]
                    + "\n\nПодробности: error_log.txt"
                )
            )

        finally:
            self.root.after(
                0,
                self.finish_task
            )

    # ========================================================
    # ЗАВЕРШЕНИЕ
    # ========================================================

    def finish_task(self):
        self.busy = False
        self.create_button.configure(
            state="normal",
            text="✦  СОЗДАТЬ КЛИП"
        )
        self.cancel_button.configure(state="disabled")
        self.cancel_event.clear()
        if self._close_when_idle:
            self._close_when_idle = False
            if self.is_dirty:
                self.write_autosave()
            self.root.destroy()

    # ========================================================
    # ПРОСМОТР
    # ========================================================

    def preview_video(self):
        if self.last_video and self.last_video.exists():
            open_with_default_app(self.last_video)
            return

        videos = sorted(
            (
                path for path in OUTPUT.iterdir()
                if path.is_file() and path.suffix.lower() == ".mp4"
            ),
            key=lambda file: file.stat().st_mtime,
            reverse=True
        )

        if videos:
            open_with_default_app(videos[0])
        else:
            messagebox.showinfo(
                "Просмотр",
                "Сначала создай клип."
            )

    def open_output(self):
        open_with_default_app(OUTPUT)

    # ========================================================
    # ПРОВЕРКА КОМПОНЕНТОВ
    # ========================================================

    def show_components(self):
        problems = check_components()

        if problems:
            self.component_status_var.set(
                f"Нужно исправить: {len(problems)} пунктов."
            )
            messagebox.showwarning(
                "Компоненты",
                "\n".join(problems)
            )
        else:
            self.component_status_var.set("Все компоненты найдены и готовы к работе.")
            messagebox.showinfo(
                "Компоненты",
                "✅ FFmpeg найден\n"
                "✅ Piper найден\n"
                "✅ eSpeak найден\n"
                "✅ Мужской голос найден\n"
                "✅ Женский голос найден"
            )


# ============================================================
# ЗАПУСК
# ============================================================

def main():
    root = tk.Tk()
    NeuroHackStudio(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        write_error(error)
        raise

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


def run_command(command, input_data=None, env=None):
    result = subprocess.run(
        [str(item) for item in command],
        input=input_data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(BASE),
        env=env,
        creationflags=getattr(
            subprocess,
            "CREATE_NO_WINDOW",
            0
        )
    )

    if result.returncode != 0:
        error = result.stderr.decode(
            "utf-8",
            errors="replace"
        )

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


def split_subtitles(text, max_words=5):
    words = text.split()

    return [
        " ".join(words[i:i + max_words])
        for i in range(0, len(words), max_words)
    ]


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

def generate_voice(text, voice, speed, output_file):
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
        env=env
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
    subtitles_enabled
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

    run_command(command)


# ============================================================
# ОБЪЕДИНЕНИЕ СЦЕН
# ============================================================

def combine_scenes(scene_files, output_file, workdir):
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
    ])


# ============================================================
# ФОНОВАЯ МУЗЫКА
# ============================================================

def add_background_music(
    video_file,
    music_file,
    volume,
    output_file
):
    if not music_file:
        shutil.copy2(video_file, output_file)
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
    ])


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

    def __init__(self, root):
        self.root = root

        root.title(APP_NAME)
        root.geometry("1080x800")
        root.minsize(780, 560)
        root.configure(bg=BG)

        self.materials = []
        self.scene_assignments = {}
        self.prepared_scenes = []

        self.last_video = None
        self.busy = False
        self.ai_script = ""

        self.voice_var = tk.StringVar(value="Мужской")
        self.speed_var = tk.StringVar(value="Нормальная")

        self.subtitle_var = tk.BooleanVar(value=True)
        self.subtitle_size = tk.StringVar(value="Средние")

        self.mode_var = tk.StringVar(
            value="Автоматически"
        )

        self.music_var = tk.StringVar(
            value="Без музыки"
        )

        self.volume_var = tk.DoubleVar(value=12)

        self.status_var = tk.StringVar(
            value="Готов к работе"
        )

        self.ai_topic = tk.StringVar()
        self.ai_duration = tk.StringVar(
            value="30–60 секунд"
        )

        self.setup_style()
        self.build_interface()
        self.enable_clipboard()
        self.refresh_music()

    # --------------------------------------------------------

    def setup_style(self):
        style = ttk.Style()

        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(
            "TNotebook",
            background=BG,
            borderwidth=0
        )

        style.configure(
            "TNotebook.Tab",
            background=PANEL,
            foreground=WHITE,
            padding=(15, 12)
        )

        style.map(
            "TNotebook.Tab",
            background=[("selected", PURPLE)],
            foreground=[("selected", WHITE)]
        )

    # --------------------------------------------------------

    def button(self, parent, text, command, color=PURPLE):
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg=WHITE,
            activebackground=CYAN,
            activeforeground=BG,
            font=("Arial", 10, "bold"),
            relief="flat",
            padx=12,
            pady=9,
            cursor="hand2"
        )

    # --------------------------------------------------------

    def label(self, parent, text):
        return tk.Label(
            parent,
            text=text,
            bg=BG,
            fg=WHITE,
            font=("Arial", 10)
        )

    # ========================================================
    # ИНТЕРФЕЙС
    # ========================================================

    def build_interface(self):
        header = tk.Frame(self.root, bg=BG)

        header.pack(
            fill="x",
            padx=16,
            pady=(12, 5)
        )

        tk.Label(
            header,
            text="⚡ НЕЙРОХАК СТУДИЯ 4.2",
            bg=BG,
            fg=CYAN,
            font=("Arial", 19, "bold")
        ).pack(anchor="w")

        tk.Label(
            header,
            text="VK КЛИПЫ • КИБЕРПАНК • АВТОМАТИЗАЦИЯ",
            bg=BG,
            fg=GRAY,
            font=("Arial", 9)
        ).pack(anchor="w")

        # Нижняя панель остаётся видимой.

        bottom = tk.Frame(self.root, bg=PANEL)
        bottom.pack(side="bottom", fill="x")

        tk.Label(
            bottom,
            textvariable=self.status_var,
            bg=PANEL,
            fg=CYAN,
            anchor="w"
        ).pack(
            fill="x",
            padx=12,
            pady=(7, 0)
        )

        controls = tk.Frame(bottom, bg=PANEL)

        controls.pack(
            fill="x",
            padx=10,
            pady=8
        )

        self.create_button = self.button(
            controls,
            "🎬 СОЗДАТЬ VK КЛИП",
            self.start_creation,
            CYAN
        )

        self.create_button.configure(
            fg=BG,
            font=("Arial", 12, "bold")
        )

        self.create_button.pack(
            side="left",
            padx=5
        )

        self.button(
            controls,
            "▶ ПРОСМОТР",
            self.preview_video
        ).pack(side="left", padx=5)

        self.button(
            controls,
            "📁 РЕЗУЛЬТАТЫ",
            self.open_output
        ).pack(side="left", padx=5)

        self.notebook = ttk.Notebook(self.root)

        self.notebook.pack(
            fill="both",
            expand=True,
            padx=12,
            pady=10
        )

        self.tab_create = tk.Frame(self.notebook, bg=BG)
        self.tab_ai = tk.Frame(self.notebook, bg=BG)
        self.tab_materials = tk.Frame(self.notebook, bg=BG)
        self.tab_music = tk.Frame(self.notebook, bg=BG)
        self.tab_settings = tk.Frame(self.notebook, bg=BG)

        self.notebook.add(
            self.tab_create,
            text="Создание видео"
        )

        self.notebook.add(
            self.tab_ai,
            text="🤖 ИИ-ПОМОЩНИК"
        )

        self.notebook.add(
            self.tab_materials,
            text="Материалы"
        )

        self.notebook.add(
            self.tab_music,
            text="Музыка"
        )

        self.notebook.add(
            self.tab_settings,
            text="Настройки"
        )

        self.build_create_tab()
        self.build_ai_tab()
        self.build_materials_tab()
        self.build_music_tab()
        self.build_settings_tab()

    # ========================================================
    # СОЗДАНИЕ ВИДЕО
    # ========================================================

    def build_create_tab(self):
        top = tk.Frame(self.tab_create, bg=BG)

        top.pack(
            fill="x",
            padx=12,
            pady=10
        )

        self.label(top, "Голос:").grid(
            row=0, column=0, padx=5, pady=6
        )

        ttk.Combobox(
            top,
            textvariable=self.voice_var,
            values=list(VOICE_MODELS),
            state="readonly",
            width=13
        ).grid(row=0, column=1, padx=5)

        self.label(top, "Скорость:").grid(
            row=0, column=2, padx=5
        )

        ttk.Combobox(
            top,
            textvariable=self.speed_var,
            values=list(VOICE_SPEEDS),
            state="readonly",
            width=13
        ).grid(row=0, column=3, padx=5)

        self.button(
            top,
            "🔊 Проверить голос",
            self.test_voice
        ).grid(row=0, column=4, padx=10)

        tk.Checkbutton(
            top,
            text="Субтитры ВКЛ",
            variable=self.subtitle_var,
            bg=BG,
            fg=CYAN,
            selectcolor=PANEL,
            activebackground=BG,
            activeforeground=CYAN
        ).grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=10
        )

        self.label(
            top,
            "Размер субтитров:"
        ).grid(row=1, column=2, padx=5)

        ttk.Combobox(
            top,
            textvariable=self.subtitle_size,
            values=list(SUBTITLE_SIZES),
            state="readonly",
            width=13
        ).grid(row=1, column=3, padx=5)

        self.label(
            self.tab_create,
            "Сценарий для VK Клипа:"
        ).pack(
            anchor="w",
            padx=17,
            pady=(5, 3)
        )

        self.script_text = tk.Text(
            self.tab_create,
            bg=PANEL,
            fg=WHITE,
            insertbackground=CYAN,
            selectbackground=PURPLE,
            font=("Arial", 12),
            wrap="word",
            undo=True,
            relief="flat"
        )

        self.script_text.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=7
        )

        self.script_text.insert(
            "1.0",
            "Привет! Это Нейрохак. "
            "Сегодня расскажу о бесплатной нейросети, "
            "которая поможет тебе экономить время. "
            "Подписывайся на наше сообщество!"
        )

        actions = tk.Frame(
            self.tab_create,
            bg=BG
        )

        actions.pack(
            fill="x",
            padx=15,
            pady=8
        )

        self.button(
            actions,
            "💾 Сохранить проект",
            self.save_project
        ).pack(side="left", padx=4)

        self.button(
            actions,
            "📂 Открыть проект",
            self.load_project
        ).pack(side="left", padx=4)

        self.button(
            actions,
            "🎞 Подготовить сцены",
            self.prepare_scenes
        ).pack(side="left", padx=4)

    # ========================================================
    # НОВАЯ ВКЛАДКА ИИ-ПОМОЩНИК
    # ========================================================

    def build_ai_tab(self):
        tk.Label(
            self.tab_ai,
            text="🤖 ПОМОЩНИК НЕЙРОХАК",
            bg=BG,
            fg=CYAN,
            font=("Arial", 18, "bold")
        ).pack(pady=12)

        self.label(
            self.tab_ai,
            "Тема будущего VK Клипа:"
        ).pack(anchor="w", padx=20)

        self.ai_topic_entry = ttk.Entry(
            self.tab_ai,
            textvariable=self.ai_topic,
            width=70
        )

        self.ai_topic_entry.pack(
            fill="x",
            padx=20,
            pady=8
        )

        self.label(
            self.tab_ai,
            "Продолжительность:"
        ).pack(anchor="w", padx=20)

        ttk.Combobox(
            self.tab_ai,
            textvariable=self.ai_duration,
            values=[
                "15–30 секунд",
                "30–60 секунд",
                "60–90 секунд"
            ],
            state="readonly",
            width=25
        ).pack(
            anchor="w",
            padx=20,
            pady=8
        )

        buttons = tk.Frame(self.tab_ai, bg=BG)

        buttons.pack(
            fill="x",
            padx=15,
            pady=5
        )

        self.button(
            buttons,
            "⚡ СОЗДАТЬ СЦЕНАРИЙ",
            self.ai_generate,
            CYAN
        ).pack(side="left", padx=5)

        self.button(
            buttons,
            "💡 СОЗДАТЬ 10 ИДЕЙ",
            self.ai_ideas
        ).pack(side="left", padx=5)

        self.label(
            self.tab_ai,
            "Результат:"
        ).pack(anchor="w", padx=20, pady=(8, 0))

        self.ai_result = tk.Text(
            self.tab_ai,
            bg=PANEL,
            fg=WHITE,
            insertbackground=CYAN,
            selectbackground=PURPLE,
            wrap="word",
            font=("Arial", 11),
            undo=True
        )

        self.ai_result.pack(
            fill="both",
            expand=True,
            padx=20,
            pady=8
        )

        self.button(
            self.tab_ai,
            "🎬 ПЕРЕДАТЬ СЦЕНАРИЙ В СОЗДАНИЕ ВИДЕО",
            self.ai_to_video
        ).pack(
            anchor="w",
            padx=20,
            pady=(3, 12)
        )

    # --------------------------------------------------------

    def ai_generate(self):
        try:
            topic = self.ai_topic.get().strip()

            script = generate_script(
                topic,
                self.ai_duration.get()
            )

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
            messagebox.showerror(
                "Помощник",
                str(error)
            )

    # --------------------------------------------------------

    def ai_to_video(self):
        if not self.ai_script:
            messagebox.showwarning(
                "Помощник",
                "Сначала создай сценарий."
            )
            return

        self.script_text.delete("1.0", tk.END)
        self.script_text.insert(
            "1.0",
            self.ai_script
        )

        self.notebook.select(self.tab_create)

    # --------------------------------------------------------

    def ai_ideas(self):
        ideas = generate_ideas(10)

        result = "10 ИДЕЙ ДЛЯ VK КЛИПОВ:\n\n"

        for index, idea in enumerate(ideas, 1):
            result += f"{index}. {idea}\n"

        self.ai_result.delete("1.0", tk.END)
        self.ai_result.insert("1.0", result)

    # ========================================================
    # МАТЕРИАЛЫ
    # ========================================================

    def build_materials_tab(self):
        top = tk.Frame(self.tab_materials, bg=BG)

        top.pack(
            fill="x",
            padx=12,
            pady=12
        )

        self.button(
            top,
            "➕ Добавить фото и видео",
            self.add_materials
        ).pack(side="left", padx=5)

        self.button(
            top,
            "🗑 Очистить список",
            self.clear_materials
        ).pack(side="left", padx=5)

        self.label(
            self.tab_materials,
            "Добавленные материалы:"
        ).pack(anchor="w", padx=16)

        self.material_list = tk.Listbox(
            self.tab_materials,
            bg=PANEL,
            fg=WHITE,
            selectbackground=PURPLE,
            height=7
        )

        self.material_list.pack(
            fill="x",
            padx=15,
            pady=7
        )

        mode_frame = tk.Frame(
            self.tab_materials,
            bg=BG
        )

        mode_frame.pack(fill="x", padx=15)

        self.label(
            mode_frame,
            "Распределение:"
        ).pack(side="left", padx=5)

        ttk.Combobox(
            mode_frame,
            textvariable=self.mode_var,
            values=["Автоматически", "Вручную"],
            state="readonly",
            width=20
        ).pack(side="left", padx=5)

        self.button(
            mode_frame,
            "Подготовить сцены",
            self.prepare_scenes
        ).pack(side="left", padx=5)

        self.label(
            self.tab_materials,
            "Сцены:"
        ).pack(
            anchor="w",
            padx=16,
            pady=(15, 0)
        )

        self.scene_list = tk.Listbox(
            self.tab_materials,
            bg=PANEL,
            fg=WHITE,
            selectbackground=PURPLE,
            height=7
        )

        self.scene_list.pack(
            fill="both",
            expand=True,
            padx=15,
            pady=7
        )

        self.button(
            self.tab_materials,
            "📌 Назначить материал сцене",
            self.assign_material
        ).pack(
            anchor="w",
            padx=15,
            pady=8
        )

    # ========================================================
    # МУЗЫКА
    # ========================================================

    def build_music_tab(self):
        self.label(
            self.tab_music,
            "🎵 Музыкальная библиотека"
        ).pack(
            anchor="w",
            padx=20,
            pady=20
        )

        self.music_combo = ttk.Combobox(
            self.tab_music,
            textvariable=self.music_var,
            state="readonly",
            width=65
        )

        self.music_combo.pack(
            anchor="w",
            padx=20,
            pady=10
        )

        buttons = tk.Frame(self.tab_music, bg=BG)

        buttons.pack(anchor="w", padx=15)

        self.button(
            buttons,
            "➕ Добавить MP3",
            self.add_music
        ).pack(side="left", padx=5)

        self.button(
            buttons,
            "🔄 Обновить",
            self.refresh_music
        ).pack(side="left", padx=5)

        self.button(
            buttons,
            "📁 Папка music",
            lambda: os.startfile(str(MUSIC))
        ).pack(side="left", padx=5)

        self.label(
            self.tab_music,
            "Громкость фоновой музыки:"
        ).pack(
            anchor="w",
            padx=20,
            pady=(30, 5)
        )

        tk.Scale(
            self.tab_music,
            from_=0,
            to=50,
            variable=self.volume_var,
            orient="horizontal",
            resolution=1,
            length=400,
            bg=BG,
            fg=WHITE,
            troughcolor=PANEL,
            highlightthickness=0
        ).pack(anchor="w", padx=20)

        self.label(
            self.tab_music,
            "Рекомендуется 10–15%. "
            "Используй музыку с разрешением на публикацию."
        ).pack(
            anchor="w",
            padx=20,
            pady=15
        )

    # ========================================================
    # НАСТРОЙКИ
    # ========================================================

    def build_settings_tab(self):
        information = (
            "НЕЙРОХАК СТУДИЯ 4.2\n\n"
            "Разрешение: 720 × 1280\n"
            "Частота: 25 FPS\n"
            "Видеокодек: H.264\n"
            "Озвучка: Piper\n\n"
            "Субтитры: белые, с голубыми акцентами\n"
            "Музыка: MP3\n"
            "Сценарии: встроенный помощник\n\n"
            "Помощник работает по шаблонам,\n"
            "без интернета и платных API."
        )

        self.label(
            self.tab_settings,
            information
        ).pack(
            anchor="w",
            padx=20,
            pady=20
        )

        self.button(
            self.tab_settings,
            "🔍 Проверить компоненты",
            self.show_components
        ).pack(anchor="w", padx=20)

        self.button(
            self.tab_settings,
            "📁 Папка программы",
            lambda: os.startfile(str(BASE))
        ).pack(
            anchor="w",
            padx=20,
            pady=10
        )

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

        self.refresh_materials()

    def refresh_materials(self):
        self.material_list.delete(0, tk.END)

        for item in self.materials:
            self.material_list.insert(
                tk.END,
                Path(item).name
            )

    def clear_materials(self):
        self.materials.clear()
        self.scene_assignments.clear()

        self.refresh_materials()
        self.refresh_scenes()

    # ========================================================
    # СЦЕНЫ
    # ========================================================

    def prepare_scenes(self):
        text = self.script_text.get(
            "1.0",
            tk.END
        ).strip()

        self.prepared_scenes = split_script(text)
        self.scene_assignments.clear()

        self.refresh_scenes()

        messagebox.showinfo(
            "Сцены",
            f"Подготовлено сцен: {len(self.prepared_scenes)}"
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

    # ========================================================
    # СОХРАНЕНИЕ ПРОЕКТА
    # ========================================================

    def save_project(self):
        file = filedialog.asksaveasfilename(
            initialdir=PROJECTS,
            defaultextension=".json",
            filetypes=[
                ("Проект НЕЙРОХАК", "*.json")
            ]
        )

        if not file:
            return

        data = {
            "script": self.script_text.get(
                "1.0",
                tk.END
            ).strip(),

            "voice": self.voice_var.get(),
            "speed": self.speed_var.get(),

            "subtitles": self.subtitle_var.get(),
            "subtitle_size": self.subtitle_size.get(),

            "materials": self.materials,
            "mode": self.mode_var.get(),

            "assignments": self.scene_assignments,

            "music": self.music_var.get(),
            "volume": self.volume_var.get()
        }

        with open(
            file,
            "w",
            encoding="utf-8"
        ) as output:
            json.dump(
                data,
                output,
                ensure_ascii=False,
                indent=2
            )

        messagebox.showinfo(
            "Проект",
            "Проект сохранён."
        )

    # ========================================================
    # ОТКРЫТИЕ ПРОЕКТА
    # ========================================================

    def load_project(self):
        file = filedialog.askopenfilename(
            initialdir=PROJECTS,
            filetypes=[
                ("Проект НЕЙРОХАК", "*.json")
            ]
        )

        if not file:
            return

        try:
            with open(
                file,
                "r",
                encoding="utf-8"
            ) as source:
                data = json.load(source)

            self.script_text.delete("1.0", tk.END)

            self.script_text.insert(
                "1.0",
                data.get("script", "")
            )

            self.voice_var.set(
                data.get("voice", "Мужской")
            )

            self.speed_var.set(
                data.get("speed", "Нормальная")
            )

            self.subtitle_var.set(
                data.get("subtitles", True)
            )

            self.subtitle_size.set(
                data.get("subtitle_size", "Средние")
            )

            self.materials = data.get("materials", [])

            self.mode_var.set(
                data.get("mode", "Автоматически")
            )

            self.volume_var.set(
                data.get("volume", 12)
            )

            self.refresh_music()

            music = data.get("music", "Без музыки")

            if music in self.music_combo["values"]:
                self.music_var.set(music)

            self.prepared_scenes = split_script(
                data.get("script", "")
            )

            self.scene_assignments = {
                int(key): value
                for key, value in data.get(
                    "assignments", {}
                ).items()
            }

            self.refresh_materials()
            self.refresh_scenes()

            messagebox.showinfo(
                "Проект",
                "Проект открыт."
            )

        except Exception as error:
            write_error(error)

            messagebox.showerror(
                "Ошибка",
                str(error)
            )

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

        self.status_var.set(
            "Проверка озвучки..."
        )

        def worker():
            try:
                file = OUTPUT / "test_voice.wav"

                generate_voice(
                    "Привет! Это Нейрохак Студия. "
                    "Проверяем качество русской озвучки.",
                    voice,
                    speed,
                    file
                )

                self.root.after(
                    0,
                    lambda: os.startfile(str(file))
                )

                self.update_status(
                    "Проверка голоса завершена"
                )

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

        settings = {
            "scenes": scenes,

            "voice": self.voice_var.get(),
            "speed": self.speed_var.get(),

            "subtitles": self.subtitle_var.get(),
            "subtitle_size": self.subtitle_size.get(),

            "materials": list(self.materials),
            "mode": self.mode_var.get(),

            "assignments": dict(
                self.scene_assignments
            ),

            "music": self.music_var.get(),
            "volume": self.volume_var.get()
        }

        self.busy = True

        self.create_button.configure(
            state="disabled"
        )

        self.update_status(
            "Начинаем создание клипа..."
        )

        threading.Thread(
            target=self.process_video,
            args=(settings,),
            daemon=True
        ).start()

    # --------------------------------------------------------

    def update_status(self, text):
        self.root.after(
            0,
            lambda text=text: self.status_var.set(text)
        )

    # --------------------------------------------------------

    def process_video(self, settings):
        try:
            timestamp = datetime.now().strftime(
                "%Y%m%d_%H%M%S_%f"
            )

            final_file = OUTPUT / (
                f"NEUROHACK_42_{timestamp}.mp4"
            )

            with tempfile.TemporaryDirectory(
                prefix="neurohack42_"
            ) as temp:
                workdir = Path(temp)

                scene_files = []
                scenes = settings["scenes"]

                for index, text in enumerate(scenes):
                    number = index + 1

                    self.update_status(
                        f"Сцена {number}/{len(scenes)}: озвучка"
                    )

                    voice_file = workdir / (
                        f"voice_{number:03d}.wav"
                    )

                    generate_voice(
                        text,
                        settings["voice"],
                        settings["speed"],
                        voice_file
                    )

                    overlay_file = workdir / (
                        f"overlay_{number:03d}.png"
                    )

                    create_base_overlay(
                        overlay_file,
                        number
                    )

                    subtitle_files = []

                    if settings["subtitles"]:
                        phrases = split_subtitles(text)

                        for phrase_index, phrase in enumerate(
                            phrases
                        ):
                            subtitle_file = workdir / (
                                f"sub_{number:03d}_"
                                f"{phrase_index:03d}.png"
                            )

                            create_subtitle_image(
                                phrase,
                                subtitle_file,
                                settings["subtitle_size"]
                            )

                            subtitle_files.append(
                                subtitle_file
                            )

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

                    self.update_status(
                        f"Сцена {number}/{len(scenes)}: видео"
                    )

                    make_scene(
                        material,
                        voice_file,
                        scene_file,
                        overlay_file,
                        subtitle_files,
                        settings["subtitles"]
                    )

                    scene_files.append(scene_file)

                self.update_status(
                    "Объединение сцен..."
                )

                combined_file = workdir / "combined.mp4"

                combine_scenes(
                    scene_files,
                    combined_file,
                    workdir
                )

                music_file = None
                music_name = settings["music"]

                if music_name != "Без музыки":
                    candidate = MUSIC / music_name

                    if candidate.exists():
                        music_file = candidate

                self.update_status(
                    "Добавление музыки..."
                )

                add_background_music(
                    combined_file,
                    music_file,
                    settings["volume"] / 100,
                    final_file
                )

                self.last_video = final_file

            self.update_status(
                "✅ Клип готов: " + final_file.name
            )

            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Готово!",
                    "VK Клип создан!\n\n"
                    + str(final_file)
                )
            )

        except Exception as error:
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
            state="normal"
        )

    # ========================================================
    # ПРОСМОТР
    # ========================================================

    def preview_video(self):
        if self.last_video and self.last_video.exists():
            os.startfile(str(self.last_video))
            return

        videos = sorted(
            OUTPUT.glob("*.mp4"),
            key=lambda file: file.stat().st_mtime,
            reverse=True
        )

        if videos:
            os.startfile(str(videos[0]))
        else:
            messagebox.showinfo(
                "Просмотр",
                "Сначала создай клип."
            )

    def open_output(self):
        os.startfile(str(OUTPUT))

    # ========================================================
    # ПРОВЕРКА КОМПОНЕНТОВ
    # ========================================================

    def show_components(self):
        problems = check_components()

        if problems:
            messagebox.showwarning(
                "Компоненты",
                "\n".join(problems)
            )
        else:
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

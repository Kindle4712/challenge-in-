"""Render the main SGLang request path as a report-ready PNG."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "figures" / "request_flow.png"
WIDTH = 1800
HEIGHT = 1870
BACKGROUND = "#ffffff"
INK = "#17212b"
LINE = "#51606d"
FILL = "#edf3f5"
ACCENT = "#d9ece5"


def font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/mnt/c/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def main() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    title_font = font(48)
    box_font = font(31)
    note_font = font(25)
    draw.text((110, 70), "SGLang /generate: main request path", fill=INK, font=title_font)
    draw.text((110, 137), "v0.5.14  |  Radix Cache enabled  |  streaming response", fill=LINE, font=note_font)

    stages = [
        ("1", "HTTP POST /generate", "input_ids + sampling_params"),
        ("2", "TokenizerManager.generate_request", "receive, validate, dispatch"),
        ("3", "Scheduler waiting_queue", "event_loop_normal selects waiting requests"),
        ("4", "get_new_batch_prefill / Req.init_next_round_input", "RadixCache.match_prefix finds reusable KV"),
        ("5", "PrefillAdder / ScheduleBatch", "schedule only uncached prompt tokens"),
        ("6", "Model worker: Prefill -> Decode", "compute suffix KV and output tokens"),
    ]
    left, right = 160, 1640
    box_height, gap = 165, 61
    top = 235
    for index, (number, heading, detail) in enumerate(stages):
        y1 = top + index * (box_height + gap)
        y2 = y1 + box_height
        fill = ACCENT if index in (3, 6) else FILL
        draw.rounded_rectangle((left, y1, right, y2), radius=8, fill=fill, outline=LINE, width=3)
        draw.ellipse((left + 30, y1 + 42, left + 111, y1 + 123), fill=INK)
        digit_box = draw.textbbox((0, 0), number, font=box_font)
        digit_width = digit_box[2] - digit_box[0]
        draw.text((left + 70 - digit_width / 2, y1 + 64), number, fill="#ffffff", font=box_font)
        draw.text((left + 145, y1 + 37), heading, fill=INK, font=box_font)
        draw.text((left + 145, y1 + 96), detail, fill=LINE, font=note_font)
        if index < len(stages) - 1:
            center = WIDTH // 2
            draw.line((center, y2, center, y2 + gap - 17), fill=LINE, width=5)
            draw.polygon(
                [(center - 15, y2 + gap - 25), (center + 15, y2 + gap - 25), (center, y2 + gap - 5)],
                fill=LINE,
            )
    branch_y = top + len(stages) * (box_height + gap) - gap + 65
    center = WIDTH // 2
    branch_centers = (510, 1290)
    draw.line((center, branch_y - 65, center, branch_y - 30), fill=LINE, width=5)
    draw.line((branch_centers[0], branch_y - 30, branch_centers[1], branch_y - 30), fill=LINE, width=5)
    for branch_center in branch_centers:
        draw.line((branch_center, branch_y - 30, branch_center, branch_y - 12), fill=LINE, width=5)
        draw.polygon(
            [(branch_center - 14, branch_y - 17), (branch_center + 14, branch_y - 17),
             (branch_center, branch_y + 4)],
            fill=LINE,
        )
    branches = [
        (160, "RadixCache KV update", "cache_unfinished_req / cache_finished_req", ACCENT),
        (940, "TokenizerManager streaming", "incremental SSE events to client", FILL),
    ]
    for x1, heading, detail, fill in branches:
        draw.rounded_rectangle((x1, branch_y, x1 + 700, branch_y + box_height),
                               radius=8, fill=fill, outline=LINE, width=3)
        draw.text((x1 + 30, branch_y + 32), heading, fill=INK, font=box_font)
        draw.text((x1 + 30, branch_y + 94), detail, fill=LINE, font=note_font)
    draw.text((160, branch_y + box_height + 45),
              "Policy helper: match_prefix_for_req (not a required FCFS step)",
              fill=LINE, font=note_font)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, optimize=True)
    print(OUTPUT)


if __name__ == "__main__":
    main()

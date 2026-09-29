from pathlib import Path

from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


source = Path(r"C:\Users\kindl\AppData\Local\Temp\codex-clipboard-71b61428-96b8-40b9-b3f1-fb0bc355926b.png")
output = Path("sglang_request_flow.pdf")
font_path = Path(r"C:\Windows\Fonts\simsunb.ttf")

with Image.open(source) as image:
    width, height = image.size

pdfmetrics.registerFont(TTFont("SimSun", str(font_path)))
pdf = canvas.Canvas(str(output), pagesize=(width, height), pageCompression=1)
pdf.setTitle("SGLang 请求处理流程：从客户端到流式输出")
pdf.setAuthor("OpenAI")
pdf.drawImage(str(source), 0, 0, width=width, height=height, preserveAspectRatio=True, mask="auto")

# Keep an embedded Chinese font in the PDF while remaining visually invisible.
pdf.setFont("SimSun", 1)
pdf.setFillColorRGB(1, 1, 1)
pdf.drawString(0, 0, "中文字体嵌入")
pdf.showPage()
pdf.save()

print(f"created {output.resolve()} ({width}x{height})")

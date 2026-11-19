"""
make_icon.py — draw the app icon (a microphone on the app's accent colour) and save it as
src/assets/mytranscribe.ico (16 to 256 px, PNG inside) and mytranscribe.png (256 px).

    python installer/make_icon.py
"""

import struct
import sys
from pathlib import Path

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PyQt6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath, QPen

ASSETS = Path(__file__).resolve().parent.parent / "src" / "assets"
ACCENT, ACCENT_DARK, WHITE = QColor("#C96442"), QColor("#A94F31"), QColor("#FFFFFF")
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def draw(size: int) -> QImage:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 256.0
    # Tile: rounded square, a slightly darker lower half for depth.
    tile = QPainterPath()
    tile.addRoundedRect(QRectF(8 * s, 8 * s, 240 * s, 240 * s), 56 * s, 56 * s)
    p.fillPath(tile, ACCENT)
    p.save()
    p.setClipPath(tile)
    p.fillRect(QRectF(0, 168 * s, size, size), ACCENT_DARK)
    p.restore()
    # Microphone: capsule, cradle, stem, foot. Strokes thicken at small sizes to stay legible.
    stroke = max(18 * s, 1.6 if size <= 20 else 2.2)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(WHITE)
    p.drawRoundedRect(QRectF(98 * s, 46 * s, 60 * s, 104 * s), 30 * s, 30 * s)
    pen = QPen(WHITE, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawArc(QRectF(70 * s, 66 * s, 116 * s, 116 * s), 200 * 16, 140 * 16)
    p.drawLine(int(128 * s), int(182 * s), int(128 * s), int(204 * s))
    p.drawLine(int(100 * s), int(208 * s), int(156 * s), int(208 * s))
    p.end()
    return img


def png_bytes(img: QImage) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(data)


def write_ico(path: Path, images) -> None:
    pngs = [png_bytes(i) for i in images]
    header = struct.pack("<HHH", 0, 1, len(pngs))
    offset = 6 + 16 * len(pngs)
    entries, blobs = b"", b""
    for img, blob in zip(images, pngs):
        w = img.width()
        entries += struct.pack("<BBBBHHII", 0 if w >= 256 else w, 0 if w >= 256 else w, 0, 0, 1, 32,
                               len(blob), offset + len(blobs))
        blobs += blob
    path.write_bytes(header + entries + blobs)


def main():
    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])  # noqa: F841 (painting needs one)
    images = [draw(n) for n in SIZES]
    write_ico(ASSETS / "mytranscribe.ico", images)
    images[-1].save(str(ASSETS / "mytranscribe.png"))
    print("Wrote", ASSETS / "mytranscribe.ico")


if __name__ == "__main__":
    main()

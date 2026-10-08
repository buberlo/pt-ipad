#!/usr/bin/env python3
"""Render the original P.T. monogram icon; standard library only, no font or game assets."""
import math
from pathlib import Path
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / 'build/port-src/assets/apple/Assets.xcassets/AppIcon.appiconset/Icon.png'


def letter(x, y):
    p = (130 <= x <= 205 and 325 <= y <= 720) or (205 <= x <= 270 and 325 <= y <= 555)
    p |= x >= 205 and ((x - 270) / 110) ** 2 + ((y - 440) / 115) ** 2 <= 1
    hole = (205 <= x <= 270 and 393 <= y <= 487)
    hole |= x >= 205 and ((x - 270) / 38) ** 2 + ((y - 440) / 47) ** 2 <= 1
    t = (505 <= x <= 760 and 325 <= y <= 400) or (600 <= x <= 675 and 400 <= y <= 720)
    dots = (x - 420) ** 2 + (y - 685) ** 2 <= 33 ** 2 or (x - 835) ** 2 + (y - 685) ** 2 <= 33 ** 2
    return (p and not hole) or t or dots


def chunk(kind, data):
    return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))


def render():
    rows = bytearray()
    for y in range(1024):
        rows.append(0)  # PNG filter: none; opaque RGB, never pre-round the icon.
        for x in range(1024):
            glow = max(0., 1. - math.hypot(x - 512, y - 490) / 740.)
            noise = ((x * 73856093 ^ y * 19349663) & 15) / 8.
            background = (int(9 + 8 * glow + noise), int(13 + 11 * glow + noise), int(12 + 9 * glow + noise))
            coverage = sum(letter(x + dx, y + dy) for dx, dy in ((.25,.25),(.75,.25),(.25,.75),(.75,.75))) / 4.
            # Fine deterministic weathering retains clear letters at small Home Screen sizes.
            if (x * 83492791 ^ y * 2971215073) % 379 == 0:
                coverage *= .5
            ink = (230, 232, 219)
            rows.extend(int(a + (b - a) * coverage) for a, b in zip(background, ink))
    data = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', 1024, 1024, 8, 2, 0, 0, 0))
    data += chunk(b'IDAT', zlib.compress(bytes(rows), 9)) + chunk(b'IEND', b'')
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    DESTINATION.write_bytes(data)
    print(DESTINATION)


if __name__ == '__main__':
    render()

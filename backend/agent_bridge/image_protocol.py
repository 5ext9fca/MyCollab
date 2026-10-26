"""图像清单与 PNG 有界校验；不重建像素、不转换或调用模型。"""
import hashlib
import re
import struct
import zlib

from .protocol import ProtocolError, bounded_json, fields, text

IMAGE_KINDS = ("image_generate", "image_edit")
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 16 * 1024 * 1024


def validate_manifest(value):
    bounded_json(value, 8192)
    fields(value, ("candidates",))
    candidates = value["candidates"]
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 4:
        raise ProtocolError("须提供 1–4 个候选。")
    keys = set()
    for item in candidates:
        fields(item, ("key", "name", "sha256", "size", "width", "height"))
        key = item["key"]
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", key) or key in keys:
            raise ProtocolError("候选编号无效或重复。")
        keys.add(key)
        text(item["name"], 120, True)
        if not re.fullmatch(r"[^/\\\x00-\x1f]+\.png", item["name"]):
            raise ProtocolError("候选文件名须为不含路径的 PNG 名称。")
        if not isinstance(item["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
            raise ProtocolError("候选摘要无效。")
        for key in ("size", "width", "height"):
            if type(item[key]) is not int or item[key] <= 0:
                raise ProtocolError("候选大小和尺寸必须为正整数。")
        if item["size"] > MAX_IMAGE_BYTES or item["width"] * item["height"] > MAX_PIXELS:
            raise ProtocolError("候选超出 20 MiB 或 1600 万像素上限。")
    return value


def inspect_png(data):
    if not 0 < len(data) <= MAX_IMAGE_BYTES or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ProtocolError("只接受有界静态 PNG 文件。")
    position, width, height, has_data, ended = 8, 0, 0, False, False
    compressed = []
    while position + 12 <= len(data):
        length = struct.unpack(">I", data[position:position + 4])[0]
        kind = data[position + 4:position + 8]
        end = position + 12 + length
        if end > len(data) or length > MAX_IMAGE_BYTES:
            raise ProtocolError("PNG 数据块长度无效。")
        body = data[position + 8:position + 8 + length]
        crc = struct.unpack(">I", data[position + 8 + length:end])[0]
        if zlib.crc32(kind + body) & 0xffffffff != crc:
            raise ProtocolError("PNG 校验失败。")
        if position == 8:
            if kind != b"IHDR" or length != 13:
                raise ProtocolError("PNG 文件头无效。")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
            if not width or not height or width * height > MAX_PIXELS or depth != 8 or color not in (2, 6) or compression or filtering or interlace:
                raise ProtocolError("请在本地转换为 8 位 RGB/RGBA 非交错静态 PNG。")
        elif kind == b"IHDR" or kind in (b"acTL", b"fcTL", b"fdAT"):
            raise ProtocolError("不接受重复文件头或动画 PNG。")
        if kind == b"IDAT":
            has_data = True
            compressed.append(body)
        if kind == b"IEND":
            if length or end != len(data):
                raise ProtocolError("PNG 尾部无效。")
            ended = True
            break
        position = end
    if not has_data or not ended:
        raise ProtocolError("PNG 数据不完整。")
    # 分块验证压缩流长度与行过滤器；不分配整幅位图，拒绝截断或压缩炸弹。
    stride = width * (4 if color == 6 else 3) + 1
    expected, total = stride * height, 0
    decoder = zlib.decompressobj()
    try:
        for chunk in compressed:
            pending = chunk
            while pending:
                block = decoder.decompress(pending, 65536)
                pending = decoder.unconsumed_tail
                if total + len(block) > expected:
                    raise ProtocolError('PNG 像素数据超出声明尺寸。')
                offset = (-total) % stride
                if any(value > 4 for value in block[offset::stride]):
                    raise ProtocolError('PNG 行过滤器无效。')
                total += len(block)
                if decoder.unused_data:
                    raise ProtocolError('PNG 包含多余压缩数据。')
        if not decoder.eof or total != expected:
            raise ProtocolError('PNG 压缩数据不完整。')
    except zlib.error as exc:
        raise ProtocolError('PNG 压缩数据无效。') from exc
    return {"width": width, "height": height, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}

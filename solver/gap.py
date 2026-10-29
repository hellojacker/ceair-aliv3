# -*- coding: utf-8 -*-
"""缺口识别：把"块轮廓"沿 x 滑动，与背景强边缘对齐打分，取得分最高的位置。

两套实现都在本模块，数学同源但用途不同，故意不合并：

    detect_gap(back, piece)   生产路径（solve.py 调用）：返回最优 x，只做 x 越界检查；
                              与已上线标定的结果逐像素一致，改动会直接影响通过率。
    solve(back, piece)        诊断路径（gap2 调用）：额外返回完整打分表，y 也做越界检查，
                              用于离线分析/画分布，不参与主链判定。

numpy / PIL 在函数内导入：主链只有真正做缺口识别时才付这份导入成本（与原 ceair_solver 一致）。
"""
import math

from .config import MAPPING_A, MAPPING_B

def sobel_mag(gray):
    import numpy as np
    g = gray.astype(np.float32)
    kx = np.zeros_like(g)
    ky = np.zeros_like(g)
    kx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    ky[1:-1, :] = g[2:, :] - g[:-2, :]
    return np.sqrt(kx ** 2 + ky ** 2)


def boundary(mask):
    import numpy as np
    b = np.zeros_like(mask)
    m = mask
    inner = m.copy()
    inner[1:, :] &= m[:-1, :]
    inner[:-1, :] &= m[1:, :]
    inner[:, 1:] &= m[:, :-1]
    inner[:, :-1] &= m[:, 1:]
    b = m & ~inner
    return b


def load(path):
    import numpy as np
    from PIL import Image
    return np.array(Image.open(path).convert('RGBA'))


def solve(bg_path, piece_path, verbose=True):
    import numpy as np
    bg = load(bg_path)
    pc = load(piece_path)
    H, W = bg.shape[:2]

    pm = pc[:, :, 3] > 8
    ys, xs = np.where(pm)
    py0, py1 = int(ys.min()), int(ys.max())
    px0, px1 = int(xs.min()), int(xs.max())
    bw, bh = px1 - px0 + 1, py1 - py0 + 1

    gray = bg[:, :, :3].mean(axis=2)
    edge = sobel_mag(gray)
    # 边缘归一化到 0..1（用高分位数抗异常）
    e_norm = np.clip(edge / max(1.0, np.percentile(edge, 99.0)), 0, 1)

    bmask = boundary(pm)
    bys, bxs = np.where(bmask)
    if verbose:
        print('piece bbox x %d..%d y %d..%d (%dx%d), boundary px=%d' % (px0, px1, py0, py1, bw, bh, len(bxs)))

    scores = []
    for x in range(0, W - bw - px0 + 1):
        gx = bxs + x
        gy = bys
        ok = (gx >= 0) & (gx < W) & (gy >= 0) & (gy < H)
        if ok.sum() < 10:
            continue
        scores.append((float(e_norm[gy[ok], gx[ok]].mean()), x))
    scores.sort(reverse=True)
    if verbose:
        print('top-8 edge-align:')
        for s, x in scores[:8]:
            print('   x=%-4d score=%.4f' % (x, s))
    best_x = scores[0][1]
    if verbose:
        print('=> gap x (piece canvas left offset) =', best_x, ' piece left in canvas =', px0,
              ' => 块落在背景 x =', best_x + px0)
    return best_x, scores


# ─────────────────────────── 缺口识别（numpy + PIL） ───────────────────────────
def detect_gap(back_path, piece_path, verbose=True):
    import numpy as np
    from PIL import Image

    bg = np.array(Image.open(back_path).convert("RGBA"))
    pc = np.array(Image.open(piece_path).convert("RGBA"))
    H, W = bg.shape[:2]
    pm = pc[:, :, 3] > 8
    ys, xs = np.where(pm)
    if not len(xs):
        raise RuntimeError("拼图块掩膜为空")
    py0, py1, px0, px1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
    bw, bh = px1 - px0 + 1, py1 - py0 + 1

    g = bg[:, :, :3].mean(axis=2).astype("float32")
    kx = np.zeros_like(g); ky = np.zeros_like(g)
    kx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    ky[1:-1, :] = g[2:, :] - g[:-2, :]
    edge = np.sqrt(kx ** 2 + ky ** 2)
    e = np.clip(edge / max(1.0, float(np.percentile(edge, 99.0))), 0, 1)

    inner = pm.copy()
    for a, b in ((slice(1, None), slice(None, -1)), (slice(None, -1), slice(1, None))):
        pass
    inner = pm.copy()
    inner[1:, :] &= pm[:-1, :]; inner[:-1, :] &= pm[1:, :]
    inner[:, 1:] &= pm[:, :-1]; inner[:, :-1] &= pm[:, 1:]
    bmask = pm & ~inner
    bys, bxs = np.where(bmask)

    best, scores = None, []
    for x in range(0, W - bw - px0 + 1):
        gx = bxs + x
        ok = (gx >= 0) & (gx < W)
        if ok.sum() < 10:
            continue
        sc = float(e[bys[ok], gx[ok]].mean())
        scores.append((sc, x))
        if best is None or sc > best[0]:
            best = (sc, x)
    scores.sort(reverse=True)
    if verbose:
        print("  缺口识别 top3:", [(round(s, 4), x) for s, x in scores[:3]])
    return best[1]


def inverse_mapping(px):
    """xPos = A s² + B s  →  s"""
    a, b = MAPPING_A, MAPPING_B
    return (-b + math.sqrt(b * b + 4 * a * px)) / (2 * a)


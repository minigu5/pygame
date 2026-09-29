"""A simple human silhouette in three poses, and how one painting maps onto each.

The painting lives on one canvas laid out for the standing pose. Every other
pose is a transform of that canvas under its own silhouette mask, so a stroke
on the head is on the head whatever the pose:

- crouch keeps the head and neck rows as they are and squashes the rest;
- lie turns the canvas a quarter counter-clockwise (head to the left) and
  flattens it into a long, low figure.

The pose silhouettes are drawn by hand, so parts of them fall on canvas cells
the standing figure never shows. `extend_paint` fills those from the nearest
painted cell so a body painted standing is painted lying down too.

Poses are visual only for now: the server's 24x32 hitbox does not change, so
each pose rect sits on the hitbox's feet, centred on it. The sizes come from
shared/tuning.json so the server can adopt them later.

Walking is a fourth, visual-only pose the size of the standing one: the figure
seen from the side, facing right, in a cycle of WALK_FRAMES silhouettes with
the arms and legs swinging. The renderer mirrors it to face left. It takes
the standing canvas as it is, so the head stays painted; the rest of the
painting is only ever judged at attention, which is the pose a body hides in.
"""

from __future__ import annotations

import math

import pygame

from gamemap import load_tuning

CELLS_PER_PIXEL = 4     # canvas cells per world pixel, so a 24x32 body is 96x128

POSES = ("stand", "crouch", "lie")
POSE_LABELS = {"stand": "차렷", "crouch": "웅크리기", "lie": "눕기"}
POSE_LABELS_ASCII = {"stand": "stand", "crouch": "crouch", "lie": "lie"}

_tuning = load_tuning()
POSE_SIZES: dict[str, tuple[int, int]] = {
    pose: (int(size[0]), int(size[1])) for pose, size in _tuning["shape_sizes"].items()
}
assert POSE_SIZES["stand"] == (_tuning["player_width"], _tuning["player_height"]), (
    "the standing pose must be the size of the server's hitbox"
)
POSE_SIZES["walk"] = POSE_SIZES["stand"]    # never sent to the server: the hitbox is the standing one

WALK_FRAMES = 8                     # silhouettes in one walk cycle: legs pass at 0 and 4, widest at 2 and 6
ARM_SWING = math.radians(38)
LEG_SWING = math.radians(30)
HEAD_ROWS = 9 * CELLS_PER_PIXEL     # the top of the canvas that crouching leaves unsquashed
LIE_DROP = 1 * CELLS_PER_PIXEL      # the flattened canvas sits this much lower, on the lying figure
EXTEND_SHIFTS = (1, 2, 4, 8, 16)    # paint spreads 31 cells (~8 world px) past the standing figure
SOLID_CACHE = 64

Color = tuple[int, int, int]


def canvas_size() -> tuple[int, int]:
    return cell_size("stand")


def cell_size(pose: str) -> tuple[int, int]:
    width, height = POSE_SIZES[pose]
    return (width * CELLS_PER_PIXEL, height * CELLS_PER_PIXEL)


def pose_rect(pose: str, x: float, y: float, hitbox_w: float, hitbox_h: float) -> pygame.FRect:
    """Where the pose is drawn in world space: feet on the hitbox's feet, centred on it."""
    width, height = POSE_SIZES[pose]
    return pygame.FRect(x + (hitbox_w - width) / 2, y + hitbox_h - height, width, height)


def _crouch_squash() -> float:
    """Canvas rows per crouch row below the head."""
    _, stand_h = canvas_size()
    _, crouch_h = cell_size("crouch")
    return (stand_h - HEAD_ROWS) / (crouch_h - HEAD_ROWS)


def to_canvas(pose: str, px: float, py: float) -> tuple[float, float]:
    """A point in the pose's cell grid mapped back onto the standing canvas."""
    if pose == "crouch":
        if py < HEAD_ROWS:
            return (px, py)
        return (px, HEAD_ROWS + (py - HEAD_ROWS) * _crouch_squash())
    if pose == "lie":
        stand_w, stand_h = canvas_size()
        lie_w, lie_h = cell_size("lie")
        # Undo the drop and the flattening, then the quarter turn: rotate()
        # sends canvas (x, y) to (y, W-1-x), so a turned (rx, ry) came from (W-1-ry, rx).
        rx, ry = px * stand_h / lie_w, (py - LIE_DROP) * stand_w / lie_h
        return (stand_w - 1 - ry, rx)
    return (px, py)


def stamp_geometry(pose: str, px: float, py: float, radius: float) -> tuple[float, float, float, float]:
    """A round brush at (px, py) in the pose becomes this (cx, cy, rx, ry) on the canvas.

    Measured from where the circle's four extreme points land, so a brush that
    straddles the crouch head/body seam is squashed exactly as much as it shows.
    """
    points = [to_canvas(pose, px + dx, py + dy) for dx, dy in ((-radius, 0), (radius, 0), (0, -radius), (0, radius))]
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2)


def to_pose_space(canvas: pygame.Surface, pose: str) -> pygame.Surface:
    """The standing canvas transformed to the pose's cell grid."""
    if pose == "crouch":
        width, height = cell_size("crouch")
        _, stand_h = canvas_size()
        out = pygame.Surface((width, height), 0, 32)
        out.blit(canvas.subsurface((0, 0, width, HEAD_ROWS)), (0, 0))
        body = canvas.subsurface((0, HEAD_ROWS, width, stand_h - HEAD_ROWS))
        out.blit(pygame.transform.smoothscale(body, (width, height - HEAD_ROWS)), (0, HEAD_ROWS))
        return out
    if pose == "lie":
        flat = pygame.transform.smoothscale(pygame.transform.rotate(canvas, 90), cell_size("lie"))
        out = flat.copy()
        out.blit(flat, (0, LIE_DROP))
        return out
    return canvas


_masks: dict[tuple[str, int], pygame.Surface] = {}
_solids: dict[tuple[Color, str, int], pygame.Surface] = {}
_stand_bits: pygame.mask.Mask | None = None


def mask(pose: str, frame: int = 0) -> pygame.Surface:
    """White silhouette with alpha, in the pose's cell grid.

    `frame` picks a step of the walk cycle; only the walking pose has one.
    """
    frame = frame % WALK_FRAMES if pose == "walk" else 0
    if (pose, frame) not in _masks:
        _masks[(pose, frame)] = _draw_mask(pose, frame)
    return _masks[(pose, frame)]


def sprite(canvas: pygame.Surface, pose: str, frame: int = 0) -> pygame.Surface:
    """The painting cut to the pose's silhouette: colour from the canvas, alpha from the mask."""
    out = mask(pose, frame).copy()
    out.blit(to_pose_space(canvas, pose), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


def solid_sprite(color: Color, pose: str, frame: int = 0) -> pygame.Surface:
    """The silhouette in one flat colour, for players whose painting we do not have."""
    frame = frame % WALK_FRAMES if pose == "walk" else 0
    key = (tuple(color), pose, frame)
    if key not in _solids:
        if len(_solids) >= SOLID_CACHE:
            _solids.clear()
        out = mask(pose, frame).copy()
        out.fill((*key[0], 255), special_flags=pygame.BLEND_RGBA_MULT)
        _solids[key] = out
    return _solids[key]


def extend_paint(canvas: pygame.Surface, painted: pygame.Surface) -> pygame.Surface:
    """The canvas with every cell outside the standing figure that was never
    painted taking the colour of the nearest cell that was, or is on the figure.

    Other poses show cells the standing figure hides; this keeps them from
    showing the bare base colour around a body that was painted standing.
    """
    global _stand_bits
    if _stand_bits is None:
        _stand_bits = pygame.mask.from_surface(mask("stand"))
    known = pygame.mask.from_surface(painted, threshold=0)
    known.draw(_stand_bits, (0, 0))
    inside = known.to_surface(setcolor=(255, 255, 255, 255), unsetcolor=(0, 0, 0, 0))
    inside.blit(canvas, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    # Grow the known cells outward by doubling shifts (1, 2, 4, ...): each
    # pass unions the copies shifted by `shift` in all eight directions, and
    # the unshifted copy goes last so cells already set keep their own colour.
    grown = inside
    for shift in EXTEND_SHIFTS:
        ring = pygame.Surface(grown.get_size(), pygame.SRCALPHA)
        for dx in (-shift, 0, shift):
            for dy in (-shift, 0, shift):
                if dx or dy:
                    ring.blit(grown, (dx, dy))
        ring.blit(grown, (0, 0))
        grown = ring

    out = canvas.copy()
    out.blit(grown, (0, 0))
    return out


def _draw_mask(pose: str, frame: int = 0) -> pygame.Surface:
    surface = pygame.Surface(cell_size(pose), pygame.SRCALPHA)
    # Transparent but white: the multiply then leaves the canvas colour under
    # the see-through cells, so smooth scaling never darkens the edges.
    surface.fill((255, 255, 255, 0))
    white = (255, 255, 255, 255)
    k = CELLS_PER_PIXEL

    def box(x: float, y: float, w: float, h: float, radius: float = 0) -> None:
        pygame.draw.rect(
            surface, white, pygame.Rect(round(x * k), round(y * k), round(w * k), round(h * k)),
            border_radius=round(radius * k),
        )

    def ball(x: float, y: float, r: float) -> None:
        pygame.draw.circle(surface, white, (round(x * k), round(y * k)), round(r * k))

    def limb(x0: float, y0: float, x1: float, y1: float, width: float) -> None:
        """A thick line with round ends, for a limb swung away from the vertical."""
        pygame.draw.line(surface, white, (x0 * k, y0 * k), (x1 * k, y1 * k), round(width * k))
        ball(x0, y0, width / 2)
        ball(x1, y1, width / 2)

    if pose == "stand":
        # Standing to attention on a 24x32 grid: arms straight down the sides.
        ball(12, 4.5, 3.5)               # head
        box(10.5, 7.5, 3, 2)             # neck
        box(4.5, 9, 15, 2.5, 1)          # shoulders, joining the arms to the body
        box(7.5, 9, 9, 11, 1.5)          # torso
        box(4.5, 9.5, 2.75, 11, 1)       # arms
        box(16.75, 9.5, 2.75, 11, 1)
        box(7.5, 19.5, 3.5, 12.5, 0.75)  # legs
        box(13, 19.5, 3.5, 12.5, 0.75)
        box(7, 30, 4.5, 2, 0.5)          # feet
        box(12.5, 30, 4.5, 2, 0.5)
    elif pose == "walk":
        # Seen from the side, facing right, mid-stride: the arms and legs swing
        # about the shoulder and hip, each pair in opposite phase, and the arm
        # on the far side moves with the near leg the way a walker's does.
        swing = math.sin(2 * math.pi * frame / WALK_FRAMES)
        ball(12, 4.5, 3.5)               # head
        box(10.5, 7.5, 3, 2)             # neck
        box(8.5, 9, 7, 11.5, 1.5)        # torso, narrower than from the front
        for side in (1, -1):
            arm = ARM_SWING * swing * side
            limb(12, 10.75, 12 + 9 * math.sin(arm), 10.75 + 9 * math.cos(arm), 2.75)
            leg = LEG_SWING * swing * side
            ankle_x = 12 + 9.5 * math.sin(leg)
            # Feet stay on the ground: the legs open like a compass, and the
            # trailing foot comes up on its toes at the widest stride.
            heel = 30 - (1.5 * max(0.0, -swing * side))
            limb(12, 20.5, ankle_x, heel, 3.5)
            box(ankle_x - 1.75, heel, 5.25, 2, 0.5)   # foot, toes forward
    elif pose == "crouch":
        # Squatting on a 24x20 grid: the head where it stands, knees up, arms round them.
        ball(12, 4.5, 3.5)               # head, same place as standing
        box(10.5, 7.5, 3, 1.5)           # neck
        box(6.5, 8.5, 11, 7, 2.5)        # hunched torso
        box(4, 10, 2.5, 6.5, 1)          # arms
        box(17.5, 10, 2.5, 6.5, 1)
        box(5, 13, 14, 4, 1.5)           # thighs
        box(6, 15.5, 3.5, 4.5, 0.75)     # shins
        box(14.5, 15.5, 3.5, 4.5, 0.75)
        box(5, 18, 5, 2, 0.5)            # feet
        box(14, 18, 5, 2, 0.5)
    elif pose == "lie":
        # Flat on the back on a 36x12 grid, head to the left, one arm on the chest.
        ball(4.5, 8, 3.5)                # head
        box(8, 7, 2, 2)                  # neck
        box(10, 4, 12, 8, 1.5)           # torso, down to the ground
        box(11.5, 2.5, 10, 2, 0.75)      # arm lying across the top
        box(22, 4.5, 10, 3.25, 0.75)     # legs
        box(22, 8.25, 10, 3.75, 0.75)
        box(31.5, 4, 4, 3.75, 0.75)      # feet
        box(31.5, 8.25, 4, 3.75, 0.75)
    return surface

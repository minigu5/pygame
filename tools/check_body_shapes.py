"""Paint the body in every pose headless and check the painting stays put.

Covers the silhouettes, the pose-to-canvas mapping (a stroke on the head in
one pose is on the head in the others), brush strokes and undo, and that the
renderer puts each pose's feet on the hitbox's feet.

Usage: python tools/check_body_shapes.py [screenshot-dir]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "client"))

import pygame  # noqa: E402

import body_shape  # noqa: E402
from body_canvas import BodyCanvas  # noqa: E402
from body_shape import POSES  # noqa: E402
from gamemap import GameMap, load_tuning  # noqa: E402
from render import Renderer  # noqa: E402
from ui_brush import TOOLS, Brush, PaintTarget  # noqa: E402

failures: list[str] = []

BASE = (210, 120, 90)
RED = (255, 0, 0)
BLUE = (0, 0, 255)


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{'  ' + detail if detail else ''}")
    if not ok:
        failures.append(label)


def close(a, b, tolerance: int = 8) -> bool:
    return all(abs(int(x) - int(y)) <= tolerance for x, y in zip(a[:3], b[:3]))


def opaque_share(surface: pygame.Surface) -> float:
    return pygame.mask.from_surface(surface).count() / (surface.get_width() * surface.get_height())


def main() -> int:
    pygame.init()
    screen = pygame.display.set_mode((960, 540))
    font = pygame.font.SysFont("menlo,monospace", 14)
    shots = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    # --- silhouettes -------------------------------------------------------
    for pose in POSES:
        mask = body_shape.mask(pose)
        cells = body_shape.cell_size(pose)
        share = opaque_share(mask)
        check(f"{pose}: mask is the pose's size", mask.get_size() == cells, f"{mask.get_size()}")
        check(f"{pose}: mask is a figure, not a block", 0.25 < share < 0.75, f"{share:.0%} opaque")
        corners = [mask.get_at((0, 0))[3], mask.get_at((cells[0] - 1, 0))[3]]
        check(f"{pose}: corners are see-through", all(a == 0 for a in corners))
    stand_w, stand_h = body_shape.cell_size("stand")
    check("stand: head is solid", body_shape.mask("stand").get_at((stand_w // 2, 16))[3] == 255)
    check("stand: gap between the legs", body_shape.mask("stand").get_at((stand_w // 2, stand_h - 20))[3] == 0)
    check(
        "crouch: head sits where the standing head is",
        body_shape.mask("crouch").get_at((stand_w // 2, 16))[3] == 255 and body_shape.mask("crouch").get_at((stand_w // 2, 1))[3] == 0,
    )
    for pose in POSES:
        cells_w, cells_h = body_shape.cell_size(pose)
        last = max(py for py in range(cells_h) for px in range(cells_w) if body_shape.mask(pose).get_at((px, py))[3])
        check(f"{pose}: the figure touches the ground", last == cells_h - 1, f"lowest row {last} of {cells_h}")

    # --- walk cycle ----------------------------------------------------------
    check("walk: the size of the standing pose", body_shape.cell_size("walk") == (stand_w, stand_h))
    walk_frames = [pygame.image.tobytes(body_shape.mask("walk", i), "RGBA") for i in range(body_shape.WALK_FRAMES)]
    # A silhouette cannot tell the left leg from the right, so the two halves
    # of the cycle look alike: closed, half open and full stride.
    check("walk: the limbs move between frames", len(set(walk_frames)) >= 3, f"{len(set(walk_frames))} distinct")
    check("walk: the cycle wraps around", pygame.image.tobytes(body_shape.mask("walk", body_shape.WALK_FRAMES), "RGBA") == walk_frames[0])
    for i in range(body_shape.WALK_FRAMES):
        walk = body_shape.mask("walk", i)
        check(f"walk {i}: head where the standing head is", walk.get_at((stand_w // 2, 16))[3] == 255 and walk.get_at((stand_w // 2, 1))[3] == 0)
        planted = any(walk.get_at((px, stand_h - 1))[3] for px in range(stand_w))
        check(f"walk {i}: a foot on the ground", planted)
        check(f"walk {i}: a figure, not a block", 0.2 < opaque_share(walk) < 0.7, f"{opaque_share(walk):.0%}")
    stride = body_shape.mask("walk", 2)
    row = 29 * body_shape.CELLS_PER_PIXEL
    feet = [px for px in range(stand_w) if stride.get_at((px, row))[3]]
    check("walk: legs open front and back at full stride", feet and feet[0] < stand_w // 2 - 12 and feet[-1] > stand_w // 2 + 12, f"{feet[0] if feet else '-'}..{feet[-1] if feet else '-'}")
    check("walk: the standing pose has no walk cycle", body_shape.mask("stand", 3) is body_shape.mask("stand"))

    # Shrinking a sprite must not darken its edge: see-through cells keep the canvas colour.
    blank = body_shape.sprite(BodyCanvas(BASE).surface, "stand")
    small = pygame.transform.smoothscale(blank, (21, 28))
    edge = [small.get_at((px, py)) for px in range(21) for py in range(28) if 0 < small.get_at((px, py))[3] < 255]
    check("no dark fringe when drawn small", edge and all(close(c, BASE, 6) for c in edge), f"{len(edge)} edge px, e.g. {edge[0] if edge else '-'}")

    # --- one painting, every pose ------------------------------------------
    canvas = BodyCanvas(BASE)
    brush = Brush(font, canvas)
    for pose in POSES:
        cells_w, cells_h = body_shape.cell_size(pose)
        # A cell well inside the head in this pose.
        head = {"stand": (cells_w // 2, 16), "crouch": (cells_w // 2, 14), "lie": (18, 28)}[pose]
        cx, cy = body_shape.to_canvas(pose, *head)
        canvas.stamp(cx, cy, 3, 3, RED)
        sprite = body_shape.sprite(canvas.surface, pose)
        check(
            f"{pose}: a stamp mapped through the pose lands under the cursor",
            close(sprite.get_at(head), RED) and sprite.get_at(head)[3] == 255,
            f"{sprite.get_at(head)}",
        )
        canvas.undo()
    # The same spot on the head seen from every pose.
    stand_head = (stand_w // 2, 16)
    canvas.stamp(*stand_head, 4, 4, BLUE)
    for pose in POSES:
        seen = {"stand": stand_head, "crouch": stand_head, "lie": (18, 23 + body_shape.LIE_DROP)}[pose]
        sprite = body_shape.sprite(canvas.surface, pose)
        check(f"{pose}: the head painted while standing is blue here too", close(sprite.get_at(seen), BLUE, 40), f"{sprite.get_at(seen)}")
    # ...and paint on the shoulders stays off the crouching head.
    canvas.stamp(stand_w // 2, 42, 4, 4, RED)
    crouched = body_shape.sprite(canvas.surface, "crouch")
    check("crouch: shoulder paint does not climb onto the head", close(crouched.get_at((stand_w // 2, 16)), BLUE, 40) and not close(crouched.get_at((stand_w // 2, 16)), RED, 60))
    canvas.undo()
    canvas.undo()

    # A body painted all over while standing is painted all over in every pose.
    for py in range(stand_h):
        for px in range(stand_w):
            if body_shape.mask("stand").get_at((px, py))[3]:
                canvas.surface.set_at((px, py), BLUE)
                canvas.painted.set_at((px, py), (255, 255, 255, 255))
    canvas.version += 1
    for pose in ("crouch", "lie"):
        shown = body_shape.sprite(canvas.extended(), pose)
        cells_w, cells_h = body_shape.cell_size(pose)
        bare = sum(
            1 for py in range(cells_h) for px in range(cells_w)
            if shown.get_at((px, py))[3] and close(shown.get_at((px, py)), BASE, 30)
        )
        check(f"{pose}: no bare skin after painting the whole standing body", bare == 0, f"{bare} bare cells")
    # Paint laid down lying, on a part the standing figure hides, stays put.
    canvas = BodyCanvas(BASE)
    brush = Brush(font, canvas)
    lie_w, lie_h = body_shape.cell_size("lie")
    lie_target = PaintTarget(pygame.Rect(300, 40, lie_w * 4, lie_h * 4), "lie")
    arm = (60, 14)      # on the arm across the chest
    brush.press((300 + arm[0] * 4 + 2, 40 + arm[1] * 4 + 2), lie_target, RED)
    brush.release()
    check("lie: paint on the arm shows while lying", close(body_shape.sprite(canvas.extended(), "lie").get_at(arm), RED, 40))
    check("lie: ...and is remembered as painted", canvas.painted.get_at((int(body_shape.to_canvas("lie", *arm)[0]), int(body_shape.to_canvas("lie", *arm)[1])))[3] > 0)
    canvas.undo()

    # --- brush feel ----------------------------------------------------------
    canvas.stamp(48, 64, 14, 14, RED)
    centre, edge, outside = canvas.surface.get_at((48, 64)), canvas.surface.get_at((48, 64 + 13)), canvas.surface.get_at((48, 64 + 16))
    check("brush: solid in the middle", close(centre, RED), f"{centre}")
    check("brush: soft at the edge", not close(edge, RED) and not close(edge, BASE), f"{edge}")
    check("brush: nothing beyond the radius", close(outside, BASE), f"{outside}")
    canvas.undo()
    # The edge stays just as soft when the cursor crawls and stamps pile up.
    crawl_target = PaintTarget(pygame.Rect(300, 40, stand_w * 4, stand_h * 4), "stand")
    brush.bar.selected = 2
    brush.press((300 + 20 * 4, 40 + 64 * 4), crawl_target, RED)
    for step in range(1, 120):
        brush.move((300 + 20 * 4 + step, 40 + 64 * 4), crawl_target, RED)
    brush.release()
    crawled = canvas.surface.get_at((30, 64 + 13))
    check("brush: still soft after a slow stroke", close(crawled, edge, 12), f"{crawled} vs single stamp {edge}")
    canvas.undo()
    brush.bar.selected = 0

    # --- strokes through the screen ----------------------------------------
    target = PaintTarget(pygame.Rect(300, 40, stand_w * 4, stand_h * 4), "stand")     # 4 screen px per cell
    at = lambda cx, cy: (300 + cx * 4 + 2, 40 + cy * 4 + 2)  # noqa: E731
    brush.move(at(48, 40), target, RED)
    brush.move(at(48, 60), target, RED)
    check("stroke: moving without the button paints nothing", canvas.undo_depth == 0 and close(canvas.surface.get_at((48, 50)), BASE))
    brush.press(at(48, 40), target, RED)
    brush.move(at(48, 90), target, RED)
    check("stroke: dragging paints a continuous line", all(close(canvas.surface.get_at((48, y)), RED) for y in range(40, 91, 5)))
    brush.move((10, 10), target, RED)
    brush.move(at(20, 100), target, RED)
    check("stroke: no line across a gap in the body", close(canvas.surface.get_at((34, 95)), BASE))
    brush.release()
    check("stroke: press to release is one undo step", canvas.undo_depth == 1)
    brush.bar.selected = 3
    brush.press(at(48, 60), target, RED)
    brush.release()
    check("eraser: brings the base colour back", close(canvas.surface.get_at((48, 60)), BASE), f"{canvas.surface.get_at((48, 60))}")
    check("eraser: is its own undo step", canvas.undo_depth == 2)
    canvas.undo()
    check("undo: the eraser stroke comes back whole", close(canvas.surface.get_at((48, 60)), RED))
    brush.bar.selected = 3
    brush.press(at(10, 10), target, RED)      # erasing an untouched patch changes nothing
    brush.release()
    check("undo: a stroke that changed nothing is not a step", canvas.undo_depth == 1)
    brush.bar.selected = 0
    brush.press(at(48, 40), None, RED)
    brush.release()
    check("stroke: nothing painted while the target is off limits", canvas.undo_depth == 1)
    canvas.undo()
    for index in range(25):
        brush.press(at(10 + index * 3, 30 + index * 3), target, BLUE)
        brush.release()
    steps = 0
    while canvas.undo():
        steps += 1
    check("undo: at least 20 steps", steps >= 20, f"{steps} steps")
    check("undo: back to the blank body", close(canvas.surface.get_at((48, 64)), BASE))

    # Crouching: a round brush on screen is round on screen.
    crouch_w, crouch_h = body_shape.cell_size("crouch")
    crouch_target = PaintTarget(pygame.Rect(300, 40, crouch_w * 4, crouch_h * 4), "crouch")
    brush.bar.selected = 1
    bluish = lambda c: c[2] > c[0] and c[2] > c[1]  # noqa: E731
    radius = TOOLS[1][2]
    for pose, cx, cy in (("crouch", crouch_w // 2, 60), ("lie", 60, 24)):
        cells_w, cells_h = body_shape.cell_size(pose)
        target = PaintTarget(pygame.Rect(300, 40, cells_w * 4, cells_h * 4), pose)
        brush.press((300 + cx * 4 + 2, 40 + cy * 4 + 2), target, BLUE)
        brush.release()
        seen = body_shape.sprite(canvas.surface, pose)
        across = sum(bluish(seen.get_at((px, cy))) for px in range(cells_w))
        down = sum(bluish(seen.get_at((cx, py))) for py in range(cells_h))
        check(
            f"{pose}: the brush stays round on screen",
            abs(across - down) <= 2 and 2 * radius - 2 <= across <= 2 * radius + 3,
            f"{across} cells wide, {down} cells tall, radius {radius}",
        )
        canvas.undo()
    # Straddling the crouch head/body seam the brush is still the size the cursor shows.
    crouch_target = PaintTarget(pygame.Rect(300, 40, crouch_w * 4, crouch_h * 4), "crouch")
    brush.bar.selected = 2
    radius = TOOLS[2][2]
    for cy in (body_shape.HEAD_ROWS - 1, body_shape.HEAD_ROWS):
        brush.press((300 + crouch_w * 2, 40 + cy * 4 + 2), crouch_target, BLUE)
        brush.release()
        seen = body_shape.sprite(canvas.surface, "crouch")
        above = sum(bluish(seen.get_at((crouch_w // 2, py))) for py in range(0, cy))
        below = sum(bluish(seen.get_at((crouch_w // 2, py))) for py in range(cy + 1, crouch_h))
        # The soft rim does not count as blue, so both sides fall short of the radius alike.
        check(f"crouch: brush at row {cy} reaches as far up as down", abs(above - below) <= 2 and above >= radius * 0.6, f"{above} up, {below} down")
        canvas.undo()
    brush.bar.selected = 1

    # --- rendering ---------------------------------------------------------
    tuning = load_tuning()
    game_map = GameMap.load("map_01")
    renderer = Renderer(screen, game_map, tuning)
    room = game_map.rooms[0]
    size = game_map.tile_size
    x = (room["rect"][0] + room["rect"][2] / 2) * size
    y = (room["rect"][1] + room["rect"][3] - 3) * size
    canvas.stamp(48, 40, 10, 10, BLUE)
    canvas.stamp(48, 90, 10, 10, RED)

    def settle(zoom: float) -> None:
        renderer.zoom = zoom
        for _ in range(90):
            renderer.frame(room["id"], x + 12, y + 16)

    settle(1.0)
    hitbox = renderer.to_screen(x + tuning["player_width"], y + tuning["player_height"])
    for pose in POSES:
        rect = renderer.body_rect(pose, x, y)
        check(f"{pose}: feet on the hitbox's feet", abs(rect.bottom - round(hitbox[1])) <= 1, f"{rect.bottom} vs {hitbox[1]:.0f}")
        me = {"x": x, "y": y, "pose": pose, "sprite": body_shape.sprite(canvas.extended(), pose)}
        others = [{"i": "p2", "x": x - 60, "y": y, "fz": False, "c": [40, 200, 60]}]
        renderer.draw(room["id"], None, others, [pose])
        without = screen.get_at(rect.center)[:3]
        renderer.draw(room["id"], me, others, [pose])
        check(f"{pose}: the body is drawn", screen.get_at(rect.center)[:3] != without, f"{without} -> {screen.get_at(rect.center)[:3]}")
        if shots:
            pygame.image.save(screen, str(shots / f"body_{pose}_zoom1.png"))
    check("lie: wider and lower than standing", renderer.body_rect("lie", x, y).width > renderer.body_rect("stand", x, y).width and renderer.body_rect("lie", x, y).height < renderer.body_rect("crouch", x, y).height)

    settle(16.0)
    for pose in POSES:
        me = {"x": x, "y": y, "pose": pose, "sprite": body_shape.sprite(canvas.extended(), pose)}
        renderer.draw(room["id"], me, [], [pose])
        rect = renderer.body_rect(pose, x, y)
        target = PaintTarget(rect, pose)
        brush.move(rect.center, target, RED)
        brush.draw_cursor(screen, target)
        check(f"{pose}: zoomed body fills much of the screen", rect.height > 250 or rect.width > 350, f"{rect.size}")
        if shots:
            pygame.image.save(screen, str(shots / f"body_{pose}_zoom16.png"))

    pygame.quit()
    print()
    print("all checks passed" if not failures else f"{len(failures)} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

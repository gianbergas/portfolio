import pygame
import sys
from dataclasses import dataclass
import random
import math

WIDTH, HEIGHT = 960, 540
FPS = 60
TILE = 48

# --- Feel / movement ---
GRAVITY = 2100
MOVE_ACCEL = 5600
MOVE_FRICTION = 4600
MAX_RUN_SPEED = 440
MAX_WALK_SPEED = 320

JUMP_VEL = 920               # higher jump
COYOTE_TIME = 0.10
JUMP_BUFFER = 0.12

# Jump shaping (variable jump)
JUMP_CUT_MULT = 0.45         # when you release SPACE early, cut upward speed
FALL_GRAVITY_MULT = 1.35     # stronger gravity while falling -> snappier
LOW_JUMP_GRAVITY_MULT = 1.15 # stronger gravity if jump released early

# Double jump
ALLOW_DOUBLE_JUMP = True
DOUBLE_JUMP_VEL = 860

# Dash
DASH_SPEED = 820
DASH_TIME = 0.12
DASH_COOLDOWN = 0.35

KILL_BOUNCE_VEL = 560

COLOR_BG = (10, 12, 18)
COLOR_UI = (220, 235, 255)
COLOR_PLAYER = (120, 255, 190)
COLOR_PLAYER_OUTLINE = (20, 30, 35)
COLOR_SOLID = (55, 85, 125)
COLOR_SOLID_TOP = (95, 165, 255)
COLOR_COIN = (255, 220, 80)
COLOR_ENEMY = (255, 110, 160)
COLOR_HAZARD = (255, 60, 60)

LEVEL = [
"................................................................",
"................................................................",
"................................................................",
"....................o...............o...........................",
"...............#######.........................o................",
"......................................#####.....................",
".........o.....................o...............................",
"......#####.............#####..............#######.............",
"...............................................................",
"..................o.....................o......................",
".............#############.....................................",
"...............................................................",
"....@......................................................E...",
"#########################.....##########################...#####",
"................................................................",
]


@dataclass
class Enemy:
    rect: pygame.Rect
    vx: float = -140.0
    alive: bool = True


@dataclass
class Coin:
    rect: pygame.Rect
    taken: bool = False


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    radius: float


def clamp(v, a, b):
    return a if v < a else b if v > b else v


def tiles_from_level(level_rows):
    solids = []
    coins = []
    enemies = []
    hazards = []
    spawn = (TILE, TILE)

    for y, row in enumerate(level_rows):
        for x, ch in enumerate(row):
            rx, ry = x * TILE, y * TILE
            if ch == '#':
                solids.append(pygame.Rect(rx, ry, TILE, TILE))
            elif ch == 'o':
                coins.append(Coin(pygame.Rect(rx + TILE//4, ry + TILE//4, TILE//2, TILE//2)))
            elif ch == 'E':
                enemies.append(Enemy(pygame.Rect(rx + 10, ry + 10, TILE - 20, TILE - 20)))
            elif ch == 'x':
                hazards.append(pygame.Rect(rx, ry + TILE//2, TILE, TILE//2))
            elif ch == '@':
                spawn = (rx + 10, ry - 10)

    return solids, coins, enemies, hazards, spawn


def rect_move_collide(rect, dx, dy, solids):
    rect.x += int(dx)
    hit_x = []
    for s in solids:
        if rect.colliderect(s):
            hit_x.append(s)
    for s in hit_x:
        if dx > 0:
            rect.right = s.left
        elif dx < 0:
            rect.left = s.right

    rect.y += int(dy)
    hit_y = []
    for s in solids:
        if rect.colliderect(s):
            hit_y.append(s)
    for s in hit_y:
        if dy > 0:
            rect.bottom = s.top
        elif dy < 0:
            rect.top = s.bottom

    return hit_x, hit_y


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Platformer 2D - Juice Edition (class-based)")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 18)
        self.big = pygame.font.SysFont("consolas", 44, bold=True)

        self.solids, self.coins, self.enemies, self.hazards, self.spawn = tiles_from_level(LEVEL)
        self.world_w = len(LEVEL[0]) * TILE
        self.world_h = len(LEVEL) * TILE

        self.particles = []
        self.reset_all()

    def spawn_particles(self, x, y, count=10, speed=160, life=0.35, radius=3.0, up_bias=0.2):
        for _ in range(count):
            ang = random.random() * math.tau
            sp = speed * (0.35 + 0.65 * random.random())
            vx = math.cos(ang) * sp
            vy = math.sin(ang) * sp - speed * up_bias
            self.particles.append(Particle(x, y, vx, vy, life * (0.6 + 0.8 * random.random()), radius * (0.7 + 0.8 * random.random())))

    def reset_all(self):
        self.player = pygame.Rect(self.spawn[0], self.spawn[1], 30, 40)
        self.vx = 0.0
        self.vy = 0.0

        self.on_ground = False
        self.coyote = 0.0
        self.jump_buffer = 0.0

        self.score = 0
        self.lives = 3
        self.dead_timer = 0.0
        self.win = False

        # Jump / dash state
        self.jump_was_held = False
        self.can_double = ALLOW_DOUBLE_JUMP
        self.dashing = False
        self.dash_t = 0.0
        self.dash_cd = 0.0
        self.facing = 1

        for c in self.coins:
            c.taken = False
        for e in self.enemies:
            e.alive = True
            e.vx = -140.0

        # Smooth camera
        self.cam_x = 0.0
        self.cam_y = 0.0
        self.cam_vx = 0.0
        self.cam_vy = 0.0

        self.particles.clear()

    def respawn(self):
        self.player.x, self.player.y = self.spawn
        self.vx, self.vy = 0.0, 0.0
        self.dead_timer = 0.8
        self.win = False
        self.dashing = False
        self.dash_t = 0.0
        self.dash_cd = 0.0
        self.can_double = ALLOW_DOUBLE_JUMP

    def kill_player(self):
        self.lives -= 1
        if self.lives <= 0:
            self.reset_all()
            return
        self.respawn()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_r:
                    self.reset_all()
                if event.key == pygame.K_SPACE:
                    self.jump_buffer = JUMP_BUFFER

    def update_particles(self, dt):
        for p in self.particles:
            p.life -= dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vx *= (1.0 - 2.0 * dt)
            p.vy += 900 * dt
        self.particles = [p for p in self.particles if p.life > 0]

    def update(self, dt):
        keys = pygame.key.get_pressed()

        if self.dead_timer > 0:
            self.dead_timer -= dt

        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        sprint = keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]
        jump_held = keys[pygame.K_SPACE]

        # Direction / facing
        if left ^ right:
            self.facing = -1 if left else 1

        # Dash cooldown
        self.dash_cd = max(0.0, self.dash_cd - dt)

        # Start dash (SHIFT) only if cooldown done and not already dashing
        dash_pressed = sprint and not (self.dashing)
        if dash_pressed and self.dash_cd <= 0 and self.dead_timer <= 0 and not self.win:
            self.dashing = True
            self.dash_t = DASH_TIME
            self.dash_cd = DASH_COOLDOWN
            self.vy = 0.0
            self.vx = DASH_SPEED * self.facing
            # dash trail particles
            self.spawn_particles(self.player.centerx, self.player.centery, count=14, speed=240, life=0.22, radius=2.6, up_bias=0.1)

        # Horizontal movement (disabled/limited during dash)
        target_max = MAX_RUN_SPEED if sprint else MAX_WALK_SPEED
        if not self.dashing:
            if left ^ right:
                ax = MOVE_ACCEL * (-1 if left else 1)
            else:
                ax = -MOVE_FRICTION * (1 if self.vx > 0 else -1) if abs(self.vx) > 5 else 0.0

            self.vx += ax * dt
            self.vx = clamp(self.vx, -target_max, target_max)

        # Coyote time & jump buffer
        if self.on_ground:
            self.coyote = COYOTE_TIME
        else:
            self.coyote = max(0.0, self.coyote - dt)

        if self.jump_buffer > 0:
            self.jump_buffer -= dt

        # Jump trigger (buffer + coyote)
        did_jump = False
        if self.dead_timer <= 0 and self.jump_buffer > 0 and self.coyote > 0:
            self.vy = -JUMP_VEL
            self.on_ground = False
            self.coyote = 0.0
            self.jump_buffer = 0.0
            did_jump = True
            self.spawn_particles(self.player.centerx, self.player.bottom, count=10, speed=160, life=0.25, radius=2.8, up_bias=0.9)

        # Double jump (if in air, buffer used, and available)
        if (not did_jump) and self.dead_timer <= 0 and self.jump_buffer > 0 and (not self.on_ground) and self.can_double:
            self.vy = -DOUBLE_JUMP_VEL
            self.jump_buffer = 0.0
            self.can_double = False
            self.spawn_particles(self.player.centerx, self.player.centery, count=18, speed=220, life=0.28, radius=2.6, up_bias=0.8)

        # Apply gravity (shaped)
        if not self.dashing:
            g = GRAVITY
            if self.vy > 0:
                g *= FALL_GRAVITY_MULT
            elif (self.vy < 0) and (not jump_held):
                g *= LOW_JUMP_GRAVITY_MULT

            self.vy += g * dt
            self.vy = min(self.vy, 1400)
        else:
            # dash timer
            self.dash_t -= dt
            if self.dash_t <= 0:
                self.dashing = False

        # Jump cut (release space while moving up)
        if self.jump_was_held and (not jump_held) and self.vy < 0:
            self.vy *= JUMP_CUT_MULT
        self.jump_was_held = jump_held

        # Move + collide
        was_on_ground = self.on_ground
        _, hit_y = rect_move_collide(self.player, self.vx * dt, self.vy * dt, self.solids)

        self.on_ground = False
        if hit_y:
            if self.vy > 0:
                self.on_ground = True
                if not was_on_ground:
                    # landing puff
                    self.spawn_particles(self.player.centerx, self.player.bottom, count=12, speed=140, life=0.22, radius=2.8, up_bias=1.0)
            self.vy = 0.0

        # Restore double jump on ground
        if self.on_ground:
            self.can_double = ALLOW_DOUBLE_JUMP

        # World bounds / fall death
        self.player.x = clamp(self.player.x, 0, self.world_w - self.player.w)
        if self.player.y > self.world_h + 200:
            self.kill_player()

        # Coins
        for c in self.coins:
            if not c.taken and self.player.colliderect(c.rect):
                c.taken = True
                self.score += 1
                self.spawn_particles(c.rect.centerx, c.rect.centery, count=10, speed=180, life=0.22, radius=2.4, up_bias=0.6)

        # Hazards
        for h in self.hazards:
            if self.player.colliderect(h):
                self.kill_player()

        # Enemies
        for e in self.enemies:
            if not e.alive:
                continue

            ex_old = e.rect.x
            e.rect.x += int(e.vx * dt)
            if any(e.rect.colliderect(s) for s in self.solids):
                e.rect.x = ex_old
                e.vx *= -1

            e.rect.y += int(900 * dt)
            for s in self.solids:
                if e.rect.colliderect(s):
                    e.rect.bottom = s.top

            if self.player.colliderect(e.rect):
                stomp = (self.player.bottom - e.rect.top) < 16 and self.vy > 0
                if stomp:
                    e.alive = False
                    self.vy = -KILL_BOUNCE_VEL
                    self.score += 3
                    self.spawn_particles(e.rect.centerx, e.rect.centery, count=18, speed=260, life=0.28, radius=2.6, up_bias=0.9)
                else:
                    self.kill_player()

        # Win condition
        if all(c.taken for c in self.coins):
            self.win = True

        # Smooth camera (spring)
        target_x = clamp(self.player.centerx - WIDTH // 2, 0, max(0, self.world_w - WIDTH))
        target_y = clamp(self.player.centery - HEIGHT // 2, 0, max(0, self.world_h - HEIGHT))

        # spring smoothing
        stiffness = 18.0
        damping = 9.5
        ax = (target_x - self.cam_x) * stiffness - self.cam_vx * damping
        ay = (target_y - self.cam_y) * stiffness - self.cam_vy * damping
        self.cam_vx += ax * dt
        self.cam_vy += ay * dt
        self.cam_x += self.cam_vx * dt
        self.cam_y += self.cam_vy * dt

        self.update_particles(dt)

    def draw(self):
        self.screen.fill(COLOR_BG)

        # simple parallax dots
        for i in range(120):
            px = (i * 83 + 200) % self.world_w
            py = (i * 137 + 90) % self.world_h
            x = px - self.cam_x * 0.35
            y = py - self.cam_y * 0.35
            if -10 < x < WIDTH + 10 and -10 < y < HEIGHT + 10:
                self.screen.fill((18, 24, 40), (int(x), int(y), 2, 2))

        # Solids
        for s in self.solids:
            r = pygame.Rect(s.x - self.cam_x, s.y - self.cam_y, s.w, s.h)
            pygame.draw.rect(self.screen, COLOR_SOLID, r, border_radius=10)
            top = pygame.Rect(r.x, r.y, r.w, 10)
            pygame.draw.rect(self.screen, COLOR_SOLID_TOP, top, border_radius=10)

        # Hazards
        for h in self.hazards:
            r = pygame.Rect(h.x - self.cam_x, h.y - self.cam_y, h.w, h.h)
            pygame.draw.rect(self.screen, COLOR_HAZARD, r, border_radius=8)

        # Coins
        for c in self.coins:
            if c.taken:
                continue
            r = pygame.Rect(c.rect.x - self.cam_x, c.rect.y - self.cam_y, c.rect.w, c.rect.h)
            pygame.draw.ellipse(self.screen, COLOR_COIN, r)
            pygame.draw.ellipse(self.screen, (120, 90, 10), r, 2)

        # Enemies
        for e in self.enemies:
            if not e.alive:
                continue
            r = pygame.Rect(e.rect.x - self.cam_x, e.rect.y - self.cam_y, e.rect.w, e.rect.h)
            pygame.draw.rect(self.screen, COLOR_ENEMY, r, border_radius=12)
            pygame.draw.rect(self.screen, (40, 20, 30), r, 2, border_radius=12)

        # Particles
        for p in self.particles:
            alpha = int(255 * clamp(p.life / 0.35, 0, 1))
            surf = pygame.Surface((10, 10), pygame.SRCALPHA)
            pygame.draw.circle(surf, (120, 255, 190, alpha), (5, 5), max(1, int(p.radius)))
            self.screen.blit(surf, (p.x - self.cam_x - 5, p.y - self.cam_y - 5))

        # Player
        pr = pygame.Rect(self.player.x - self.cam_x, self.player.y - self.cam_y, self.player.w, self.player.h)
        pygame.draw.rect(self.screen, COLOR_PLAYER, pr, border_radius=12)
        pygame.draw.rect(self.screen, COLOR_PLAYER_OUTLINE, pr, 2, border_radius=12)

        # UI
        dash_txt = "READY" if self.dash_cd <= 0 else f"{self.dash_cd:.1f}s"
        ui = f"Coins: {self.score}/{len(self.coins)}   Lives: {self.lives}   Dash: {dash_txt}   Double: {'ON' if self.can_double else 'USED'}"
        self.screen.blit(self.font.render(ui, True, COLOR_UI), (14, 12))
        hint = "Arrows/A-D move | SPACE jump (variable) | SPACE (air) double | SHIFT dash | R restart | ESC quit"
        self.screen.blit(self.font.render(hint, True, (140, 160, 190)), (14, 36))

        if self.dead_timer > 0:
            msg = "Ouch!"
            self.screen.blit(self.big.render(msg, True, (255, 160, 160)), (WIDTH//2 - 60, 80))

        if self.win:
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            self.screen.blit(overlay, (0, 0))
            txt = self.big.render("YOU WIN!", True, (160, 255, 190))
            self.screen.blit(txt, (WIDTH//2 - txt.get_width()//2, HEIGHT//2 - 60))
            sub = self.font.render("Press R to play again", True, COLOR_UI)
            self.screen.blit(sub, (WIDTH//2 - sub.get_width()//2, HEIGHT//2))

        pygame.display.flip()

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 1/30)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit()
                    if event.key == pygame.K_r:
                        self.reset_all()
                    if event.key == pygame.K_SPACE:
                        self.jump_buffer = JUMP_BUFFER

            if not self.win:
                self.update(dt)
            self.draw()


if __name__ == "__main__":
    Game().run()

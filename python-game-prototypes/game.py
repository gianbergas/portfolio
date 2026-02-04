# game.py  (single-file arcade: neon arena)
# Requires: pip install pygame-ce
# Works on Python 3.10+ (3.12/3.13 ok). "3.14" not needed.

from __future__ import annotations
import math
import random
import sys
from dataclasses import dataclass

import pygame

Vec = pygame.math.Vector2

# ----------------------------- Config -----------------------------
WIDTH, HEIGHT = 1100, 650
FPS = 120
TITLE = "NEON ARENA (single-file)"

# Gameplay tuning
PLAYER_SPEED = 520.0
PLAYER_ACCEL = 14.0
PLAYER_FRICTION = 10.0
PLAYER_RADIUS = 15
PLAYER_MAX_HP = 100

DASH_SPEED = 980.0
DASH_TIME = 0.11
DASH_COOLDOWN = 0.35
STAMINA_MAX = 100.0
STAMINA_REGEN = 35.0
DASH_COST = 35.0

BULLET_SPEED = 1100.0
BULLET_LIFE = 0.9
FIRE_COOLDOWN = 0.12
BULLET_DAMAGE = 16

ENEMY_SPAWN_BASE = 0.85
ENEMY_SPAWN_MIN = 0.25
ENEMY_HP = 40
ENEMY_SPEED = 250.0
ENEMY_RADIUS = 14
ENEMY_DAMAGE = 18
ENEMY_HIT_KNOCK = 460.0

ARENA_PAD = 60  # how close to edges entities can go

# Visual tuning
SHAKE_DECAY = 14.0
GLOW_SCALE = 2  # internal glow surface scale
PARALLAX_LAYERS = 4

# ----------------------------- Helpers -----------------------------
def clamp(x, a, b):
    return a if x < a else b if x > b else x

def lerp(a, b, t):
    return a + (b - a) * t

def smoothstep(t):
    t = clamp(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)

def color_mul(c, k):
    return (int(c[0]*k), int(c[1]*k), int(c[2]*k))

def circle_sdf(p: Vec, r: float) -> float:
    return p.length() - r

# ----------------------------- Particles -----------------------------
@dataclass
class Particle:
    pos: Vec
    vel: Vec
    life: float
    max_life: float
    size: float
    color: pygame.Color
    drag: float = 0.0
    glow: bool = True

    def update(self, dt: float):
        self.life -= dt
        if self.life <= 0:
            return
        if self.drag > 0:
            self.vel -= self.vel * clamp(self.drag * dt, 0, 0.9)
        self.pos += self.vel * dt

    def draw(self, surf: pygame.Surface, camera: Vec):
        if self.life <= 0:
            return
        t = 1.0 - (self.life / self.max_life)
        alpha = int(255 * (1.0 - smoothstep(t)))
        s = lerp(self.size, 0.0, smoothstep(t))
        if s <= 0.5:
            return
        col = self.color
        col.a = alpha
        pygame.draw.circle(surf, col, (self.pos - camera), int(s))

# ----------------------------- Entities -----------------------------
@dataclass
class Bullet:
    pos: Vec
    vel: Vec
    life: float
    damage: int
    radius: int = 4

    def update(self, dt: float):
        self.life -= dt
        self.pos += self.vel * dt

    def draw(self, surf: pygame.Surface, camera: Vec):
        pygame.draw.circle(surf, (220, 240, 255), (self.pos - camera), self.radius)

@dataclass
class Enemy:
    pos: Vec
    vel: Vec
    hp: int
    radius: int = ENEMY_RADIUS
    hurt_t: float = 0.0
    atk_cd: float = 0.0

    def update(self, dt: float, player_pos: Vec, enemies: list["Enemy"]):
        self.hurt_t = max(0.0, self.hurt_t - dt)
        self.atk_cd = max(0.0, self.atk_cd - dt)

        # Seek player
        to_p = (player_pos - self.pos)
        dist = to_p.length() + 1e-6
        desire = to_p / dist

        # Separation (avoid clumping)
        sep = Vec(0, 0)
        for e in enemies:
            if e is self:
                continue
            d = self.pos - e.pos
            l = d.length()
            if 0 < l < 2.2 * self.radius:
                sep += (d / l) * (2.2 * self.radius - l)
        if sep.length_squared() > 0:
            sep = sep.normalize()

        steer = desire * 1.0 + sep * 1.4
        if steer.length_squared() > 0:
            steer = steer.normalize()

        target_vel = steer * ENEMY_SPEED
        self.vel = self.vel.lerp(target_vel, clamp(8.0 * dt, 0, 1))
        self.pos += self.vel * dt

        # Arena clamp
        self.pos.x = clamp(self.pos.x, ARENA_PAD, WIDTH - ARENA_PAD)
        self.pos.y = clamp(self.pos.y, ARENA_PAD, HEIGHT - ARENA_PAD)

    def draw(self, surf: pygame.Surface, camera: Vec):
        p = self.pos - camera
        base = pygame.Color(255, 70, 90)
        if self.hurt_t > 0:
            k = 1.6
        else:
            k = 1.0
        c = pygame.Color(*color_mul(base, k))
        pygame.draw.circle(surf, c, p, self.radius)
        # little core
        pygame.draw.circle(surf, (255, 210, 220), p, max(2, self.radius//3))

# ----------------------------- Game -----------------------------
class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption(TITLE)
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.Clock()

        # render targets
        self.scene = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.glow = pygame.Surface((WIDTH * GLOW_SCALE, HEIGHT * GLOW_SCALE), pygame.SRCALPHA)

        self.font = pygame.font.Font(None, 28)
        self.font_big = pygame.font.Font(None, 70)
        self.font_mid = pygame.font.Font(None, 44)

        self.reset()

    def reset(self):
        self.state = "menu"  # menu, play, pause, over
        self.time = 0.0

        self.player_pos = Vec(WIDTH/2, HEIGHT/2)
        self.player_vel = Vec(0, 0)
        self.player_hp = PLAYER_MAX_HP
        self.iframes = 0.0

        self.stamina = STAMINA_MAX
        self.dash_t = 0.0
        self.dash_cd = 0.0

        self.fire_cd = 0.0
        self.bullets: list[Bullet] = []
        self.enemies: list[Enemy] = []
        self.particles: list[Particle] = []

        self.score = 0
        self.combo = 0
        self.combo_t = 0.0

        self.spawn_t = 0.0
        self.spawn_interval = ENEMY_SPAWN_BASE

        self.camera = Vec(0, 0)
        self.cam_shake = 0.0
        self.cam_shake_seed = random.random() * 9999.0

        # background "stars" per layer
        self.stars = []
        for layer in range(PARALLAX_LAYERS):
            pts = []
            n = 120 // (layer + 1)
            for _ in range(n):
                pts.append((random.randrange(0, WIDTH), random.randrange(0, HEIGHT), random.randint(1, 2)))
            self.stars.append(pts)

    # ---------------- input ----------------
    def want_quit(self, ev):
        return ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE and self.state == "menu")

    def handle_events(self):
        for ev in pygame.event.get():
            if self.want_quit(ev):
                pygame.quit()
                raise SystemExit

            if ev.type == pygame.KEYDOWN:
                if self.state == "menu":
                    if ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.state = "play"
                elif self.state == "play":
                    if ev.key == pygame.K_p:
                        self.state = "pause"
                elif self.state == "pause":
                    if ev.key == pygame.K_p:
                        self.state = "play"
                elif self.state == "over":
                    if ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.reset()
                        self.state = "play"

    # ---------------- updates ----------------
    def add_shake(self, amount: float):
        self.cam_shake = max(self.cam_shake, amount)

    def spawn_enemy(self):
        # spawn at edges
        side = random.choice([0, 1, 2, 3])
        if side == 0:
            pos = Vec(-20, random.uniform(0, HEIGHT))
        elif side == 1:
            pos = Vec(WIDTH + 20, random.uniform(0, HEIGHT))
        elif side == 2:
            pos = Vec(random.uniform(0, WIDTH), -20)
        else:
            pos = Vec(random.uniform(0, WIDTH), HEIGHT + 20)

        # clamp into arena band
        pos.x = clamp(pos.x, ARENA_PAD, WIDTH - ARENA_PAD)
        pos.y = clamp(pos.y, ARENA_PAD, HEIGHT - ARENA_PAD)

        self.enemies.append(Enemy(pos=pos, vel=Vec(0, 0), hp=ENEMY_HP))

    def shoot(self, dir_vec: Vec):
        if self.fire_cd > 0:
            return
        if dir_vec.length_squared() == 0:
            return
        d = dir_vec.normalize()
        self.fire_cd = FIRE_COOLDOWN

        self.bullets.append(Bullet(
            pos=self.player_pos + d * (PLAYER_RADIUS + 6),
            vel=d * BULLET_SPEED,
            life=BULLET_LIFE,
            damage=BULLET_DAMAGE
        ))

        # muzzle particles
        for _ in range(10):
            ang = math.atan2(d.y, d.x) + random.uniform(-0.5, 0.5)
            v = Vec(math.cos(ang), math.sin(ang)) * random.uniform(180, 460)
            self.particles.append(Particle(
                pos=self.player_pos + d * (PLAYER_RADIUS + 2),
                vel=v,
                life=random.uniform(0.18, 0.32),
                max_life=0.32,
                size=random.uniform(4, 7),
                color=pygame.Color(140, 220, 255),
                drag=5.0,
                glow=True
            ))

    def dash(self, dir_vec: Vec):
        if self.dash_cd > 0 or self.dash_t > 0:
            return
        if self.stamina < DASH_COST:
            return
        if dir_vec.length_squared() == 0:
            return
        self.stamina -= DASH_COST
        self.dash_t = DASH_TIME
        self.dash_cd = DASH_COOLDOWN

        d = dir_vec.normalize()
        self.player_vel = d * DASH_SPEED
        self.add_shake(6.0)

        # dash trail burst
        for _ in range(26):
            v = Vec(random.uniform(-1, 1), random.uniform(-1, 1))
            if v.length_squared() == 0:
                v = Vec(1, 0)
            v = v.normalize() * random.uniform(120, 520)
            self.particles.append(Particle(
                pos=self.player_pos,
                vel=v,
                life=random.uniform(0.22, 0.48),
                max_life=0.48,
                size=random.uniform(3, 8),
                color=pygame.Color(255, 80, 190),
                drag=4.5,
                glow=True
            ))

    def player_take_hit(self, dmg: int, knock_dir: Vec):
        if self.iframes > 0:
            return
        self.player_hp -= dmg
        self.iframes = 0.55
        self.add_shake(10.0)

        if knock_dir.length_squared() > 0:
            self.player_vel += knock_dir.normalize() * ENEMY_HIT_KNOCK

        for _ in range(30):
            v = Vec(random.uniform(-1, 1), random.uniform(-1, 1))
            if v.length_squared() == 0:
                v = Vec(0.2, 1)
            v = v.normalize() * random.uniform(120, 620)
            self.particles.append(Particle(
                pos=self.player_pos,
                vel=v,
                life=random.uniform(0.18, 0.55),
                max_life=0.55,
                size=random.uniform(3, 9),
                color=pygame.Color(255, 120, 120),
                drag=5.2,
                glow=True
            ))

    def update_play(self, dt: float):
        self.time += dt
        keys = pygame.key.get_pressed()
        mx, my = pygame.mouse.get_pos()
        mouse = Vec(mx, my)
        aim = (mouse + self.camera) - self.player_pos

        # Movement input
        move = Vec(0, 0)
        if keys[pygame.K_w] or keys[pygame.K_UP]: move.y -= 1
        if keys[pygame.K_s] or keys[pygame.K_DOWN]: move.y += 1
        if keys[pygame.K_a] or keys[pygame.K_LEFT]: move.x -= 1
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: move.x += 1
        if move.length_squared() > 0:
            move = move.normalize()

        # Dash
        if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
            if move.length_squared() > 0:
                self.dash(move)

        # Shooting
        if pygame.mouse.get_pressed()[0]:
            self.shoot(aim)

        # Timers
        self.fire_cd = max(0.0, self.fire_cd - dt)
        self.dash_cd = max(0.0, self.dash_cd - dt)
        self.iframes = max(0.0, self.iframes - dt)
        self.combo_t = max(0.0, self.combo_t - dt)

        # Stamina regen (slower while dashing)
        regen = STAMINA_REGEN * (0.55 if self.dash_t > 0 else 1.0)
        self.stamina = clamp(self.stamina + regen * dt, 0.0, STAMINA_MAX)

        # Physics: accel + friction (unless dashing)
        if self.dash_t > 0:
            self.dash_t -= dt
            # spawn dash trail continuously
            for _ in range(3):
                v = Vec(random.uniform(-1, 1), random.uniform(-1, 1))
                if v.length_squared() == 0:
                    v = Vec(1, 0)
                v = v.normalize() * random.uniform(60, 220)
                self.particles.append(Particle(
                    pos=self.player_pos,
                    vel=v,
                    life=random.uniform(0.10, 0.22),
                    max_life=0.22,
                    size=random.uniform(3, 6),
                    color=pygame.Color(255, 100, 210),
                    drag=6.0,
                    glow=True
                ))
        else:
            target = move * PLAYER_SPEED
            self.player_vel = self.player_vel.lerp(target, clamp(PLAYER_ACCEL * dt, 0, 1))
            self.player_vel -= self.player_vel * clamp(PLAYER_FRICTION * dt, 0, 0.9)

        self.player_pos += self.player_vel * dt

        # Arena clamp
        self.player_pos.x = clamp(self.player_pos.x, ARENA_PAD, WIDTH - ARENA_PAD)
        self.player_pos.y = clamp(self.player_pos.y, ARENA_PAD, HEIGHT - ARENA_PAD)

        # Bullets update + cull
        for b in self.bullets:
            b.update(dt)
        self.bullets = [b for b in self.bullets if b.life > 0
                        and -120 < b.pos.x < WIDTH + 120 and -120 < b.pos.y < HEIGHT + 120]

        # Enemy spawn ramps with score
        self.spawn_interval = max(ENEMY_SPAWN_MIN, ENEMY_SPAWN_BASE - self.score / 3000.0)
        self.spawn_t -= dt
        if self.spawn_t <= 0:
            self.spawn_t = self.spawn_interval
            # spawn more as time grows
            extra = 1 if self.score > 800 else 0
            for _ in range(1 + extra):
                self.spawn_enemy()

        # Enemies update
        for e in self.enemies:
            e.update(dt, self.player_pos, self.enemies)

        # Collisions: bullets vs enemies
        dead = []
        for e in self.enemies:
            for b in self.bullets:
                if (e.pos - b.pos).length_squared() <= (e.radius + b.radius) ** 2:
                    e.hp -= b.damage
                    e.hurt_t = 0.10
                    b.life = 0
                    self.add_shake(2.5)

                    # hit particles
                    hit_dir = (e.pos - b.pos)
                    if hit_dir.length_squared() == 0:
                        hit_dir = Vec(1, 0)
                    hit_dir = hit_dir.normalize()

                    for _ in range(14):
                        ang = math.atan2(hit_dir.y, hit_dir.x) + random.uniform(-1.0, 1.0)
                        v = Vec(math.cos(ang), math.sin(ang)) * random.uniform(160, 520)
                        self.particles.append(Particle(
                            pos=e.pos,
                            vel=v,
                            life=random.uniform(0.10, 0.26),
                            max_life=0.26,
                            size=random.uniform(3, 7),
                            color=pygame.Color(255, 170, 210),
                            drag=6.8,
                            glow=True
                        ))

                    if e.hp <= 0:
                        dead.append(e)
                        self.score += 50
                        if self.combo_t > 0:
                            self.combo += 1
                        else:
                            self.combo = 1
                        self.combo_t = 1.1
                        self.score += int(10 * (self.combo - 1))
                        self.add_shake(6.5)

                        # death burst
                        for _ in range(42):
                            v = Vec(random.uniform(-1, 1), random.uniform(-1, 1))
                            if v.length_squared() == 0:
                                v = Vec(1, 0)
                            v = v.normalize() * random.uniform(140, 760)
                            self.particles.append(Particle(
                                pos=e.pos,
                                vel=v,
                                life=random.uniform(0.18, 0.62),
                                max_life=0.62,
                                size=random.uniform(3, 10),
                                color=pygame.Color(255, 70, 90),
                                drag=4.2,
                                glow=True
                            ))

        if dead:
            self.enemies = [e for e in self.enemies if e not in dead]

        # Collisions: enemies vs player
        for e in self.enemies:
            d = self.player_pos - e.pos
            dist = d.length()
            if dist < (PLAYER_RADIUS + e.radius):
                # push out
                if dist > 0:
                    push = d / dist
                else:
                    push = Vec(1, 0)
                overlap = (PLAYER_RADIUS + e.radius) - dist
                self.player_pos += push * overlap * 0.7
                e.pos -= push * overlap * 0.3

                if e.atk_cd <= 0:
                    e.atk_cd = 0.85
                    self.player_take_hit(ENEMY_DAMAGE, push)

        # Particles update
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.life > 0]

        # Camera: follow player with subtle smoothing + shake
        target_cam = self.player_pos - Vec(WIDTH/2, HEIGHT/2)
        self.camera = self.camera.lerp(target_cam, clamp(9.0 * dt, 0, 1))

        if self.cam_shake > 0:
            self.cam_shake = max(0.0, self.cam_shake - SHAKE_DECAY * dt)
        # end conditions
        if self.player_hp <= 0:
            self.state = "over"

    # ---------------- drawing ----------------
    def draw_background(self):
        self.scene.fill((7, 8, 14))

        # Subtle vignette-like gradient with circles
        cx, cy = WIDTH/2, HEIGHT/2
        for i in range(6):
            r = 220 + i * 120
            a = 10 + i * 10
            col = pygame.Color(30, 25, 60, a)
            pygame.draw.circle(self.scene, col, (cx, cy), r)

        # Parallax stars
        for layer in range(PARALLAX_LAYERS):
            factor = 0.18 + layer * 0.12
            for (x, y, s) in self.stars[layer]:
                px = (x - self.camera.x * factor) % WIDTH
                py = (y - self.camera.y * factor) % HEIGHT
                pygame.draw.circle(self.scene, (40, 45, 80), (px, py), s)

        # Arena border
        rect = pygame.Rect(ARENA_PAD, ARENA_PAD, WIDTH - 2*ARENA_PAD, HEIGHT - 2*ARENA_PAD)
        pygame.draw.rect(self.scene, (35, 30, 70), rect, 2, border_radius=18)

        # Neon corners (glow markers)
        for corner in [(ARENA_PAD, ARENA_PAD), (WIDTH-ARENA_PAD, ARENA_PAD),
                       (ARENA_PAD, HEIGHT-ARENA_PAD), (WIDTH-ARENA_PAD, HEIGHT-ARENA_PAD)]:
            pygame.draw.circle(self.scene, (60, 50, 120), corner, 7)

    def draw_player(self):
        p = self.player_pos - self.camera

        # iframes flicker
        visible = True
        if self.iframes > 0:
            visible = (int(self.iframes * 24) % 2) == 0
        if not visible:
            return

        # Body
        pygame.draw.circle(self.scene, (120, 255, 190), p, PLAYER_RADIUS)
        pygame.draw.circle(self.scene, (10, 18, 14), p, max(3, PLAYER_RADIUS//3))

        # Aim line
        mx, my = pygame.mouse.get_pos()
        aim = Vec(mx, my) - p
        if aim.length_squared() > 0:
            d = aim.normalize()
            tip = p + d * (PLAYER_RADIUS + 16)
            pygame.draw.line(self.scene, (140, 220, 255), p, tip, 2)
            pygame.draw.circle(self.scene, (220, 240, 255), tip, 3)

    def draw_ui(self):
        # HP bar
        hp = clamp(self.player_hp / PLAYER_MAX_HP, 0, 1)
        st = clamp(self.stamina / STAMINA_MAX, 0, 1)

        # top left
        x, y = 18, 16
        w, h = 260, 16
        pygame.draw.rect(self.scene, (20, 20, 30), (x, y, w, h), border_radius=8)
        pygame.draw.rect(self.scene, (80, 255, 170), (x, y, int(w*hp), h), border_radius=8)

        y2 = y + 24
        pygame.draw.rect(self.scene, (20, 20, 30), (x, y2, w, h), border_radius=8)
        pygame.draw.rect(self.scene, (255, 110, 220), (x, y2, int(w*st), h), border_radius=8)

        # score + combo
        score_txt = self.font.render(f"SCORE {self.score}", True, (220, 235, 255))
        self.scene.blit(score_txt, (WIDTH - score_txt.get_width() - 18, 14))

        if self.combo > 1 and self.combo_t > 0:
            combo_alpha = int(255 * smoothstep(self.combo_t / 1.1))
            combo_surf = self.font.render(f"COMBO x{self.combo}", True, (255, 170, 220))
            combo_surf.set_alpha(combo_alpha)
            self.scene.blit(combo_surf, (WIDTH - combo_surf.get_width() - 18, 40))

        hint = self.font.render("WASD/Arrows move  |  Shift dash  |  LMB shoot  |  P pause", True, (140, 150, 190))
        self.scene.blit(hint, (18, HEIGHT - 32))

    def draw_glow(self):
        # Clear glow target (scaled)
        self.glow.fill((0, 0, 0, 0))
        gs = self.glow

        def draw_glow_circle(pos, r, col, strength=1.0):
            # draw multiple circles for soft glow
            p = (int(pos[0]*GLOW_SCALE), int(pos[1]*GLOW_SCALE))
            base = pygame.Color(*col)
            for i in range(5):
                rr = int((r + i*8) * GLOW_SCALE)
                a = int(70 * strength / (i+1))
                c = pygame.Color(base.r, base.g, base.b, a)
                pygame.draw.circle(gs, c, p, rr)

        # Player glow
        p = self.player_pos - self.camera
        draw_glow_circle(p, PLAYER_RADIUS, (120, 255, 190), strength=1.2)

        # Enemies glow
        for e in self.enemies:
            ep = e.pos - self.camera
            k = 1.35 if e.hurt_t > 0 else 1.0
            draw_glow_circle(ep, e.radius, (255, int(70*k), int(90*k)), strength=1.0)

        # Bullets glow
        for b in self.bullets:
            bp = b.pos - self.camera
            draw_glow_circle(bp, b.radius+2, (190, 235, 255), strength=0.9)

        # Particles glow (only some)
        for part in self.particles:
            if not part.glow or part.life <= 0:
                continue
            t = part.life / part.max_life
            strength = 0.9 * t
            draw_glow_circle(part.pos - self.camera, part.size*0.8, (part.color.r, part.color.g, part.color.b), strength=strength)

        # Blur-ish by scaling down/up (cheap)
        tmp = pygame.transform.smoothscale(self.glow, (WIDTH, HEIGHT))
        tmp2 = pygame.transform.smoothscale(tmp, (WIDTH*GLOW_SCALE, HEIGHT*GLOW_SCALE))
        self.glow.blit(tmp2, (0, 0))

        # Composite glow onto scene
        glow_small = pygame.transform.smoothscale(self.glow, (WIDTH, HEIGHT))
        self.scene.blit(glow_small, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

    def apply_camera_shake(self):
        if self.cam_shake <= 0:
            return Vec(0, 0)
        t = self.time * 38.0 + self.cam_shake_seed
        sx = (math.sin(t) + math.sin(t*1.7)) * 0.5
        sy = (math.cos(t*1.3) + math.sin(t*2.1)) * 0.5
        mag = self.cam_shake * 1.8
        return Vec(sx, sy) * mag

    def draw_menu(self):
        self.scene.fill((7, 8, 14))
        title = self.font_big.render("NEON ARENA", True, (220, 235, 255))
        self.scene.blit(title, (WIDTH/2 - title.get_width()/2, 170))

        sub = self.font_mid.render("Survive. Build combo. Don’t get touched.", True, (160, 170, 210))
        self.scene.blit(sub, (WIDTH/2 - sub.get_width()/2, 250))

        prompt = self.font.render("Press ENTER / SPACE to start   |   ESC to quit", True, (255, 120, 220))
        self.scene.blit(prompt, (WIDTH/2 - prompt.get_width()/2, 330))

    def draw_pause(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.scene.blit(overlay, (0, 0))
        txt = self.font_big.render("PAUSED", True, (220, 235, 255))
        self.scene.blit(txt, (WIDTH/2 - txt.get_width()/2, HEIGHT/2 - 70))
        hint = self.font.render("Press P to resume", True, (255, 120, 220))
        self.scene.blit(hint, (WIDTH/2 - hint.get_width()/2, HEIGHT/2 + 10))

    def draw_over(self):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.scene.blit(overlay, (0, 0))
        txt = self.font_big.render("GAME OVER", True, (255, 110, 130))
        self.scene.blit(txt, (WIDTH/2 - txt.get_width()/2, HEIGHT/2 - 90))
        score = self.font_mid.render(f"SCORE: {self.score}", True, (220, 235, 255))
        self.scene.blit(score, (WIDTH/2 - score.get_width()/2, HEIGHT/2 - 20))
        prompt = self.font.render("Press ENTER / SPACE to restart", True, (255, 170, 220))
        self.scene.blit(prompt, (WIDTH/2 - prompt.get_width()/2, HEIGHT/2 + 40))

    def render_play(self):
        self.draw_background()

        # camera shake offset
        shake = self.apply_camera_shake()
        cam_prev = self.camera.copy()
        self.camera += shake

        # Draw entities
        for b in self.bullets:
            b.draw(self.scene, self.camera)
        for e in self.enemies:
            e.draw(self.scene, self.camera)

        # Player + particles last
        self.draw_player()

        for p in self.particles:
            p.draw(self.scene, self.camera)

        # Glow pass
        self.draw_glow()

        # UI
        self.draw_ui()

        # restore camera (so logic isn't affected)
        self.camera = cam_prev

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 1/30)  # safety clamp
            self.handle_events()

            if self.state == "menu":
                self.draw_menu()

            elif self.state == "play":
                self.update_play(dt)
                self.render_play()

            elif self.state == "pause":
                # still render play scene behind pause overlay
                self.render_play()
                self.draw_pause()

            elif self.state == "over":
                self.render_play()
                self.draw_over()

            self.screen.blit(self.scene, (0, 0))
            pygame.display.flip()


if __name__ == "__main__":
    try:
        Game().run()
    except SystemExit:
        pass

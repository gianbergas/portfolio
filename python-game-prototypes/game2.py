import math
import random
import sys
from dataclasses import dataclass

import pygame

# =========================
# NEON KEYBOARD ARENA (single-file)
# No mouse. Arrows/WASD move. SPACE shoot. SHIFT dash. ESC pause.
# =========================

WIDTH, HEIGHT = 1100, 650
FPS = 60

# Colors (keep neon-ish but not fancy)
BG = (8, 10, 16)
FG = (220, 235, 255)
MUTED = (140, 150, 190)
ACCENT = (255, 120, 220)
CYAN = (120, 220, 255)
GREEN = (80, 255, 170)
RED = (255, 90, 110)
YELLOW = (255, 220, 120)

def clamp(x, a, b): return a if x < a else b if x > b else x
def lerp(a, b, t): return a + (b - a) * t

def vec_len(x, y):
    return math.hypot(x, y)

def norm(x, y):
    l = vec_len(x, y)
    if l <= 1e-9:
        return 0.0, 0.0
    return x / l, y / l

def rect_keep_in(r: pygame.Rect):
    r.x = clamp(r.x, 20, WIDTH - 20 - r.w)
    r.y = clamp(r.y, 20, HEIGHT - 20 - r.h)

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    radius: float
    color: tuple

@dataclass
class Bullet:
    x: float
    y: float
    vx: float
    vy: float
    damage: float
    life: float
    pierce: int = 0

@dataclass
class Pickup:
    x: float
    y: float
    kind: str  # "hp" "xp" "shield"
    value: float
    t: float = 0.0

@dataclass
class Enemy:
    x: float
    y: float
    vx: float
    vy: float
    hp: float
    max_hp: float
    speed: float
    radius: float
    kind: str  # "grunt" "runner" "tank" "elite"
    touch_damage: float
    score: int
    knock_resist: float

class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("NEON KEYBOARD ARENA (no mouse)")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()

        self.font = pygame.font.SysFont("consolas", 18)
        self.big = pygame.font.SysFont("consolas", 52, bold=True)
        self.mid = pygame.font.SysFont("consolas", 26, bold=True)

        self.state = "menu"  # menu, play, pause, perk, gameover
        self.reset_run()

    # ---------- Core reset ----------
    def reset_run(self):
        self.player = pygame.Rect(WIDTH//2 - 10, HEIGHT//2 - 10, 20, 20)
        self.px, self.py = float(self.player.centerx), float(self.player.centery)

        self.hp_max = 100.0
        self.hp = self.hp_max

        self.shield_max = 40.0
        self.shield = 0.0

        self.stam_max = 100.0
        self.stam = self.stam_max

        self.base_speed = 240.0
        self.dash_speed = 860.0
        self.dash_cost = 40.0
        self.dash_time = 0.12
        self.dash_t = 0.0
        self.iframes = 0.0

        self.last_dir = (1.0, 0.0)  # shooting direction
        self.fire_cd = 0.0
        self.fire_rate = 7.0  # shots/sec
        self.bullet_speed = 650.0
        self.bullet_damage = 14.0
        self.bullet_pierce = 0

        self.bullets: list[Bullet] = []
        self.enemies: list[Enemy] = []
        self.pickups: list[Pickup] = []
        self.particles: list[Particle] = []

        self.score = 0
        self.combo = 0
        self.combo_t = 0.0
        self.combo_window = 2.2

        self.time_alive = 0.0
        self.wave = 1
        self.spawn_budget = 5.0
        self.spawn_timer = 0.0

        # progression
        self.level = 1
        self.xp = 0.0
        self.xp_to_next = 50.0
        self.perk_points = 0

        # perks toggles/stats
        self.perks = {
            "Rapid": 0,      # +fire rate
            "Power": 0,      # +damage
            "Pierce": 0,     # +pierce
            "Leech": 0,      # heal on kill
            "Shield": 0,     # shield regen
            "Dash+": 0,      # dash cheaper / more iframes
            "Magnet": 0,     # pickup attraction
        }
        self.pending_perk_choices = []

    # ---------- Spawning ----------
    def spawn_enemy(self, kind: str):
        # spawn at edges
        side = random.randint(0, 3)
        if side == 0:   x, y = -30, random.uniform(0, HEIGHT)
        elif side == 1: x, y = WIDTH + 30, random.uniform(0, HEIGHT)
        elif side == 2: x, y = random.uniform(0, WIDTH), -30
        else:           x, y = random.uniform(0, WIDTH), HEIGHT + 30

        if kind == "grunt":
            hp, spd, rad, dmg, score, kr = 34, 120, 14, 14, 20, 0.9
        elif kind == "runner":
            hp, spd, rad, dmg, score, kr = 24, 185, 12, 12, 22, 0.75
        elif kind == "tank":
            hp, spd, rad, dmg, score, kr = 85, 85, 18, 18, 40, 0.98
        else:  # elite
            hp, spd, rad, dmg, score, kr = 140, 110, 22, 22, 90, 0.995

        e = Enemy(x, y, 0.0, 0.0, float(hp), float(hp), float(spd), float(rad), kind, float(dmg), int(score), float(kr))
        self.enemies.append(e)

    def wave_logic(self, dt: float):
        self.time_alive += dt
        self.spawn_timer -= dt

        # ramp difficulty slowly
        target_budget = 5.0 + self.time_alive * 0.18 + self.wave * 0.8
        self.spawn_budget = lerp(self.spawn_budget, target_budget, 0.03)

        if self.spawn_timer <= 0:
            self.spawn_timer = clamp(0.85 - self.time_alive * 0.003, 0.28, 0.85)

            # spend budget
            budget = self.spawn_budget
            # occasional elite
            if self.time_alive > 35 and random.random() < 0.08:
                self.spawn_enemy("elite")
                budget -= 4.5

            while budget > 0:
                roll = random.random()
                if self.time_alive > 20 and roll < 0.18:
                    self.spawn_enemy("tank")
                    budget -= 2.4
                elif roll < 0.55:
                    self.spawn_enemy("grunt")
                    budget -= 1.0
                else:
                    self.spawn_enemy("runner")
                    budget -= 1.2

        # wave counter purely cosmetic
        self.wave = 1 + int(self.time_alive // 25)

    # ---------- Effects ----------
    def puff(self, x, y, color, n=10, spd=240, life=0.5, r=2.5):
        for _ in range(n):
            ang = random.random() * math.tau
            v = random.uniform(spd * 0.2, spd)
            vx, vy = math.cos(ang) * v, math.sin(ang) * v
            p = Particle(x, y, vx, vy, life, life, random.uniform(r * 0.6, r * 1.4), color)
            self.particles.append(p)

    # ---------- Perks ----------
    def level_up(self):
        self.level += 1
        self.perk_points += 1
        self.xp -= self.xp_to_next
        self.xp_to_next = int(self.xp_to_next * 1.35 + 10)

        # enter perk choice state
        self.state = "perk"
        keys = list(self.perks.keys())
        random.shuffle(keys)
        self.pending_perk_choices = keys[:3]

    def apply_perk(self, name: str):
        self.perks[name] += 1
        # apply immediate stat changes
        if name == "Rapid":
            self.fire_rate += 0.85
        elif name == "Power":
            self.bullet_damage += 2.6
        elif name == "Pierce":
            self.bullet_pierce += 1
        elif name == "Dash+":
            self.dash_cost = max(18.0, self.dash_cost - 4.0)
            self.dash_time = min(0.18, self.dash_time + 0.01)
        elif name == "Shield":
            self.shield_max += 6.0
        # Leech/Magnet are handled in logic
        self.state = "play"

    # ---------- Input ----------
    def read_move_dir(self):
        keys = pygame.key.get_pressed()
        dx = (1 if (keys[pygame.K_RIGHT] or keys[pygame.K_d]) else 0) - (1 if (keys[pygame.K_LEFT] or keys[pygame.K_a]) else 0)
        dy = (1 if (keys[pygame.K_DOWN] or keys[pygame.K_s]) else 0) - (1 if (keys[pygame.K_UP] or keys[pygame.K_w]) else 0)
        if dx != 0 or dy != 0:
            ndx, ndy = norm(dx, dy)
            # last_dir for shooting
            self.last_dir = (ndx, ndy)
            return ndx, ndy
        return 0.0, 0.0

    def try_dash(self):
        if self.dash_t > 0:
            return
        if self.stam < self.dash_cost:
            return
        self.stam -= self.dash_cost
        self.dash_t = self.dash_time
        # iframes during dash (plus tiny extra if perk)
        extra = 0.03 * self.perks["Dash+"]
        self.iframes = max(self.iframes, self.dash_time + 0.05 + extra)
        self.puff(self.px, self.py, CYAN, n=16, spd=420, life=0.45, r=3.0)

    def shoot(self):
        if self.fire_cd > 0:
            return
        self.fire_cd = 1.0 / self.fire_rate
        dx, dy = self.last_dir
        if dx == 0 and dy == 0:
            dx, dy = 1.0, 0.0
        vx, vy = dx * self.bullet_speed, dy * self.bullet_speed
        b = Bullet(self.px, self.py, vx, vy, self.bullet_damage, 1.25, pierce=self.bullet_pierce)
        self.bullets.append(b)
        self.puff(self.px + dx * 12, self.py + dy * 12, ACCENT, n=7, spd=260, life=0.25, r=2.2)

    # ---------- Collisions ----------
    def circle_hit(self, ax, ay, ar, bx, by, br):
        dx = ax - bx
        dy = ay - by
        return dx*dx + dy*dy <= (ar + br) * (ar + br)

    # ---------- Update ----------
    def update_play(self, dt: float):
        # regen
        self.stam = clamp(self.stam + 34.0 * dt, 0, self.stam_max)
        if self.perks["Shield"] > 0:
            self.shield = clamp(self.shield + (2.0 + 0.6 * self.perks["Shield"]) * dt, 0, self.shield_max)

        if self.iframes > 0:
            self.iframes -= dt

        if self.fire_cd > 0:
            self.fire_cd -= dt

        if self.combo_t > 0:
            self.combo_t -= dt
        else:
            self.combo = 0

        # movement
        mx, my = self.read_move_dir()
        spd = self.base_speed
        if self.dash_t > 0:
            self.dash_t -= dt
            spd = self.dash_speed

        self.px += mx * spd * dt
        self.py += my * spd * dt

        # keep in bounds
        self.px = clamp(self.px, 30, WIDTH - 30)
        self.py = clamp(self.py, 30, HEIGHT - 30)
        self.player.center = (int(self.px), int(self.py))

        # enemies
        for e in self.enemies:
            dx, dy = self.px - e.x, self.py - e.y
            ndx, ndy = norm(dx, dy)
            e.vx = lerp(e.vx, ndx * e.speed, 0.08)
            e.vy = lerp(e.vy, ndy * e.speed, 0.08)
            e.x += e.vx * dt
            e.y += e.vy * dt

        # bullets
        for b in self.bullets:
            b.x += b.vx * dt
            b.y += b.vy * dt
            b.life -= dt

        self.bullets = [b for b in self.bullets if b.life > 0 and -80 < b.x < WIDTH + 80 and -80 < b.y < HEIGHT + 80]

        # pickups (magnet)
        for p in self.pickups:
            p.t += dt
            if self.perks["Magnet"] > 0:
                dx, dy = self.px - p.x, self.py - p.y
                d = vec_len(dx, dy)
                if d < 220 + 40 * self.perks["Magnet"]:
                    ndx, ndy = norm(dx, dy)
                    pull = 120 + 90 * self.perks["Magnet"]
                    p.x += ndx * pull * dt
                    p.y += ndy * pull * dt

        # bullet-enemy collisions
        kills = 0
        for b in list(self.bullets):
            for e in list(self.enemies):
                if self.circle_hit(b.x, b.y, 6, e.x, e.y, e.radius):
                    e.hp -= b.damage
                    # knockback a bit
                    kdx, kdy = norm(e.x - b.x, e.y - b.y)
                    kb = 140 * (1.0 - e.knock_resist)
                    e.x += kdx * kb * dt * 22
                    e.y += kdy * kb * dt * 22
                    self.puff(e.x, e.y, CYAN if e.kind in ("runner", "elite") else MUTED, n=8, spd=220, life=0.3, r=2.2)

                    if b.pierce > 0:
                        b.pierce -= 1
                    else:
                        b.life = 0

                    if e.hp <= 0:
                        kills += 1
                        self.on_kill(e)
                    # stop checking this bullet if it died
                    if b.life <= 0:
                        break
            # bullet removed later by filter

        self.enemies = [e for e in self.enemies if e.hp > 0]
        self.bullets = [b for b in self.bullets if b.life > 0]

        # enemy-player collisions
        if self.iframes <= 0:
            pr = 14
            for e in self.enemies:
                if self.circle_hit(self.px, self.py, pr, e.x, e.y, e.radius):
                    self.take_hit(e.touch_damage, e)
                    break

        # player-pickup collisions
        pr = 14
        for p in list(self.pickups):
            if self.circle_hit(self.px, self.py, pr, p.x, p.y, 10):
                if p.kind == "hp":
                    self.hp = clamp(self.hp + p.value, 0, self.hp_max)
                elif p.kind == "xp":
                    self.xp += p.value
                elif p.kind == "shield":
                    self.shield = clamp(self.shield + p.value, 0, self.shield_max)
                self.puff(p.x, p.y, GREEN if p.kind == "hp" else YELLOW, n=10, spd=240, life=0.35, r=2.2)
                self.pickups.remove(p)

        # level up check
        while self.xp >= self.xp_to_next:
            self.level_up()
            break  # one level at a time to force perk choice

        # particles
        for p in self.particles:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vx *= 0.96
            p.vy *= 0.96
            p.life -= dt
        self.particles = [p for p in self.particles if p.life > 0]

        # wave spawns
        self.wave_logic(dt)

        # death
        if self.hp <= 0:
            self.state = "gameover"

    def on_kill(self, e: Enemy):
        # score + combo
        self.combo = min(999, self.combo + 1)
        self.combo_t = self.combo_window
        gained = e.score + int(e.score * 0.04 * self.combo)
        self.score += gained

        # xp
        xp_gain = 8 + (2 if e.kind == "runner" else 0) + (8 if e.kind == "tank" else 0) + (18 if e.kind == "elite" else 0)
        self.xp += xp_gain

        # leech
        if self.perks["Leech"] > 0:
            self.hp = clamp(self.hp + (1.2 + 0.6 * self.perks["Leech"]), 0, self.hp_max)

        # drops
        if random.random() < 0.18:
            self.pickups.append(Pickup(e.x, e.y, "xp", random.uniform(8, 14)))
        if random.random() < 0.09:
            self.pickups.append(Pickup(e.x, e.y, "hp", random.uniform(8, 14)))
        if random.random() < 0.06:
            self.pickups.append(Pickup(e.x, e.y, "shield", random.uniform(8, 14)))

        # death effect
        self.puff(e.x, e.y, ACCENT if e.kind == "elite" else CYAN, n=18, spd=380, life=0.55, r=3.0)

    def take_hit(self, dmg: float, e: Enemy):
        self.iframes = 0.65
        # knockback player
        dx, dy = norm(self.px - e.x, self.py - e.y)
        self.px += dx * 26
        self.py += dy * 26

        # shield first
        if self.shield > 0:
            s = min(self.shield, dmg)
            self.shield -= s
            dmg -= s

        if dmg > 0:
            self.hp -= dmg

        self.combo = 0
        self.combo_t = 0.0
        self.puff(self.px, self.py, RED, n=14, spd=360, life=0.45, r=3.0)

    # ---------- Draw ----------
    def draw_bar(self, x, y, w, h, val01, col, back=(25, 30, 44), border=8):
        pygame.draw.rect(self.screen, back, (x, y, w, h), border_radius=border)
        pygame.draw.rect(self.screen, col, (x, y, int(w * val01), h), border_radius=border)

    def draw_play(self):
        self.screen.fill(BG)

        # arena border
        pygame.draw.rect(self.screen, (18, 22, 34), (18, 18, WIDTH-36, HEIGHT-36), width=2, border_radius=12)

        # particles
        for p in self.particles:
            a = clamp(p.life / p.max_life, 0, 1)
            r = max(1, int(p.radius * (0.6 + 0.6 * a)))
            pygame.draw.circle(self.screen, p.color, (int(p.x), int(p.y)), r)

        # pickups
        for pk in self.pickups:
            bob = math.sin(pk.t * 6) * 3
            col = YELLOW if pk.kind == "xp" else GREEN if pk.kind == "hp" else CYAN
            pygame.draw.circle(self.screen, col, (int(pk.x), int(pk.y + bob)), 7)
            pygame.draw.circle(self.screen, (20, 20, 26), (int(pk.x), int(pk.y + bob)), 7, 2)

        # bullets
        for b in self.bullets:
            pygame.draw.circle(self.screen, ACCENT, (int(b.x), int(b.y)), 4)
            pygame.draw.circle(self.screen, (20, 20, 26), (int(b.x), int(b.y)), 4, 1)

        # enemies
        for e in self.enemies:
            if e.kind == "grunt":
                col = (140, 160, 220)
            elif e.kind == "runner":
                col = CYAN
            elif e.kind == "tank":
                col = (190, 200, 230)
            else:
                col = ACCENT

            pygame.draw.circle(self.screen, col, (int(e.x), int(e.y)), int(e.radius))
            # hp ring for elites/tanks
            if e.kind in ("tank", "elite"):
                t = e.hp / e.max_hp
                pygame.draw.circle(self.screen, (20, 20, 26), (int(e.x), int(e.y)), int(e.radius) + 5, 2)
                pygame.draw.arc(self.screen, col, pygame.Rect(int(e.x - e.radius - 6), int(e.y - e.radius - 6), int((e.radius+6)*2), int((e.radius+6)*2)),
                                -math.pi/2, -math.pi/2 + math.tau * t, 3)

        # player
        pr = 12
        player_col = FG if self.iframes <= 0 else (180, 190, 230)
        pygame.draw.circle(self.screen, player_col, (int(self.px), int(self.py)), pr)
        pygame.draw.circle(self.screen, (20, 20, 26), (int(self.px), int(self.py)), pr, 2)

        # facing indicator (shoot direction)
        fx, fy = self.last_dir
        pygame.draw.line(self.screen, CYAN, (self.px, self.py), (self.px + fx * 22, self.py + fy * 22), 3)

        # UI
        # HP + Shield + Stamina
        self.draw_bar(24, 22, 260, 14, self.hp / self.hp_max, GREEN)
        self.draw_bar(24, 40, 260, 12, (self.shield / max(1.0, self.shield_max)), CYAN)
        self.draw_bar(24, 56, 260, 10, (self.stam / self.stam_max), YELLOW)

        # XP
        xp01 = self.xp / self.xp_to_next
        self.draw_bar(24, 72, 260, 8, xp01, ACCENT, back=(18, 18, 28), border=6)

        # right text
        txt = self.font.render(f"SCORE {self.score}", True, FG)
        self.screen.blit(txt, (WIDTH - txt.get_width() - 24, 22))

        txt2 = self.font.render(f"LV {self.level}  WAVE {self.wave}  ENEMIES {len(self.enemies)}", True, MUTED)
        self.screen.blit(txt2, (WIDTH - txt2.get_width() - 24, 44))

        if self.combo > 1:
            c = self.mid.render(f"COMBO x{self.combo}", True, ACCENT)
            self.screen.blit(c, (WIDTH - c.get_width() - 24, 70))

        hint = self.font.render("ARROWS/WASD move  |  SPACE shoot  |  SHIFT dash  |  ESC pause", True, (120, 130, 170))
        self.screen.blit(hint, (24, HEIGHT - 28))

    def draw_menu(self):
        self.screen.fill(BG)
        title = self.big.render("NEON KEYBOARD ARENA", True, FG)
        self.screen.blit(title, (WIDTH//2 - title.get_width()//2, 160))

        sub = self.mid.render("No mouse. Pure keyboard. Survive. Level up. Get stronger.", True, MUTED)
        self.screen.blit(sub, (WIDTH//2 - sub.get_width()//2, 230))

        how = self.font.render("ENTER / SPACE start  |  ESC quit", True, ACCENT)
        self.screen.blit(how, (WIDTH//2 - how.get_width()//2, 300))

        tip = self.font.render("Tip: keep moving; last movement sets aim direction.", True, (120, 130, 170))
        self.screen.blit(tip, (WIDTH//2 - tip.get_width()//2, 340))

    def draw_pause(self):
        self.draw_play()
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))
        t = self.big.render("PAUSED", True, FG)
        self.screen.blit(t, (WIDTH//2 - t.get_width()//2, 210))
        s = self.mid.render("ESC resume  |  R restart  |  Q quit to menu", True, MUTED)
        self.screen.blit(s, (WIDTH//2 - s.get_width()//2, 290))

    def draw_gameover(self):
        self.draw_play()
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 185))
        self.screen.blit(overlay, (0, 0))
        t = self.big.render("GAME OVER", True, RED)
        self.screen.blit(t, (WIDTH//2 - t.get_width()//2, 190))
        s = self.mid.render(f"Score: {self.score}   Level: {self.level}   Time: {int(self.time_alive)}s", True, FG)
        self.screen.blit(s, (WIDTH//2 - s.get_width()//2, 260))
        h = self.mid.render("ENTER retry  |  Q menu", True, MUTED)
        self.screen.blit(h, (WIDTH//2 - h.get_width()//2, 315))

    def draw_perk(self):
        self.draw_play()
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))

        t = self.mid.render(f"LEVEL UP! Choose a perk (1/2/3)", True, FG)
        self.screen.blit(t, (WIDTH//2 - t.get_width()//2, 150))

        # cards
        card_w, card_h = 280, 170
        start_x = WIDTH//2 - (card_w*3 + 30*2)//2
        y = 220

        descriptions = {
            "Rapid":  "Faster fire rate (+shots/sec).",
            "Power":  "Higher bullet damage.",
            "Pierce": "Bullets pierce +1 enemy.",
            "Leech":  "Heal a bit on kill.",
            "Shield": "Slow shield regen + higher cap.",
            "Dash+":  "Dash cheaper + more i-frames.",
            "Magnet": "Pickups pull toward you.",
        }

        for i, name in enumerate(self.pending_perk_choices):
            x = start_x + i*(card_w + 30)
            pygame.draw.rect(self.screen, (18, 22, 34), (x, y, card_w, card_h), border_radius=14)
            pygame.draw.rect(self.screen, (60, 70, 110), (x, y, card_w, card_h), width=2, border_radius=14)

            n = self.mid.render(f"{i+1}. {name}", True, ACCENT)
            self.screen.blit(n, (x + 18, y + 18))

            lvl = self.font.render(f"Current: {self.perks[name]}", True, MUTED)
            self.screen.blit(lvl, (x + 18, y + 60))

            d = self.font.render(descriptions.get(name, ""), True, FG)
            self.screen.blit(d, (x + 18, y + 92))

    # ---------- Events ----------
    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)

            if ev.type == pygame.KEYDOWN:
                if self.state == "menu":
                    if ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.reset_run()
                        self.state = "play"
                    elif ev.key == pygame.K_ESCAPE:
                        pygame.quit()
                        sys.exit(0)

                elif self.state == "play":
                    if ev.key == pygame.K_ESCAPE:
                        self.state = "pause"
                    elif ev.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                        self.try_dash()
                    elif ev.key == pygame.K_SPACE:
                        self.shoot()

                elif self.state == "pause":
                    if ev.key == pygame.K_ESCAPE:
                        self.state = "play"
                    elif ev.key == pygame.K_r:
                        self.reset_run()
                        self.state = "play"
                    elif ev.key == pygame.K_q:
                        self.state = "menu"

                elif self.state == "gameover":
                    if ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self.reset_run()
                        self.state = "play"
                    elif ev.key == pygame.K_q:
                        self.state = "menu"

                elif self.state == "perk":
                    if ev.key in (pygame.K_1, pygame.K_KP1):
                        self.apply_perk(self.pending_perk_choices[0])
                    elif ev.key in (pygame.K_2, pygame.K_KP2):
                        self.apply_perk(self.pending_perk_choices[1])
                    elif ev.key in (pygame.K_3, pygame.K_KP3):
                        self.apply_perk(self.pending_perk_choices[2])

    def update(self, dt: float):
        if self.state == "play":
            # hold-to-shoot: if SPACE held, shoot continuously (optional)
            keys = pygame.key.get_pressed()
            if keys[pygame.K_SPACE]:
                self.shoot()
            if keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]:
                # dash only triggers on keydown (avoid spam), so do nothing here
                pass
            self.update_play(dt)

    def draw(self):
        if self.state == "menu":
            self.draw_menu()
        elif self.state == "play":
            self.draw_play()
        elif self.state == "pause":
            self.draw_pause()
        elif self.state == "gameover":
            self.draw_gameover()
        elif self.state == "perk":
            self.draw_perk()

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self.draw()
            pygame.display.flip()

if __name__ == "__main__":
    Game().run()

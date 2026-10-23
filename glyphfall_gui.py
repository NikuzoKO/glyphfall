#!/usr/bin/env python3
"""glyphfall, native front end: pygame instead of a terminal.

Same Game as the curses version. The map is drawn with smooth movement, hold-to-walk and
real multitouch (one thumb on the d-pad, one on the skills). Menus are the existing curses
screens drawn on a character grid, so every menu works unchanged.
"""
import os
import sys
import time
import math
import types
import glob
import random
import curses
import collections

os.environ.setdefault('SDL_TOUCH_MOUSE_EVENTS', '0')
os.environ.setdefault('SDL_MOUSE_TOUCH_EVENTS', '0')
import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import glyphfall as G

BG = (22, 21, 36)
PAL = {0: (225, 220, 240), 1: (225, 220, 240), 2: (240, 105, 125), 3: (115, 215, 145), 4: (245, 200, 105),
       5: (120, 160, 255), 6: (210, 140, 255), 7: (105, 215, 225)}
LINES = set('─│┌┐└┘')
SHADES = {'█': 1.0, '▓': 0.75, '▒': 0.5, '░': 0.25}
RARITY_RGB = {'normal': PAL[1], 'magic': PAL[7], 'rare': PAL[4], 'legend': PAL[6], 'mythic': PAL[2], 'unique': PAL[3]}


def find_font(name):
    hits = glob.glob(f'/usr/share/fonts/**/{name}', recursive=True)
    return hits[0] if hits else None


class Glyphs:
    """Per-glyph rendering with a fallback font (DejaVu Sans Mono lacks a few symbols)."""

    def __init__(self):
        self.mono, self.sans = find_font('DejaVuSansMono.ttf'), find_font('DejaVuSans.ttf')
        self.fonts, self.cache, self.texts = {}, {}, collections.OrderedDict()
        chars = sorted({c for c in open(G.__file__, encoding='utf8').read() if ord(c) > 127})
        f = self.font(24, 'mono')
        ref = self.sig(f, '')
        self.mono_missing = {c for c in chars if self.sig(f, c) == ref}

    @staticmethod
    def sig(f, c):
        s = f.render(c, True, (255, 255, 255))
        return s.get_size(), pygame.image.tobytes(s, 'RGBA')

    def font(self, size, which='sans'):
        key = (size, which)
        if key not in self.fonts:
            self.fonts[key] = pygame.font.Font(self.mono if which == 'mono' else self.sans, size)
        return self.fonts[key]

    def glyph(self, ch, color, size):
        key = (ch, color, size)
        s = self.cache.get(key)
        if s is None:
            s = self.font(size, 'sans' if ch in self.mono_missing else 'mono').render(ch, True, color)
            self.cache[key] = s
        return s

    def text(self, s, color, size):
        key = (s, color, size)
        t = self.texts.get(key)
        if t is None:
            t = self.font(size).render(s, True, color)
            self.texts[key] = t
            if len(self.texts) > 600:
                self.texts.popitem(last=False)
        return t


class GridWin:
    """Just enough of a curses window for the existing menus, drawn with pygame."""

    def __init__(self, app):
        self.app = app
        f = app.glyphs.font(26, 'mono')
        self.cw, self.chh = f.size('M')[0], f.get_linesize()
        self.cols, self.rows = app.W // self.cw, app.UH // self.chh
        self.cells, self.tmo, self.mouse = {}, 20000, (0, 0, 0, 0, 0)

    def getmaxyx(self):
        return self.rows, self.cols

    def erase(self):
        self.cells = {}

    def addstr(self, y, x, s, attr=0):
        for i, ch in enumerate(s):
            if 0 <= y < self.rows and 0 <= x + i < self.cols:
                self.cells[(y, x + i)] = (ch, attr)

    def keypad(self, flag):
        pass

    def timeout(self, ms):
        self.tmo = ms

    def refresh(self):
        a = self.app
        a.screen.fill(BG)
        ox = (a.W - self.cols * self.cw) // 2
        for (y, x), (ch, attr) in self.cells.items():
            fg = PAL.get((attr >> 8) & 0xFF, PAL[1])
            if attr & curses.A_BOLD:
                fg = tuple(min(255, int(c * 1.12)) for c in fg)
            if attr & curses.A_DIM:
                fg = tuple(int(c * 0.55) for c in fg)
            px, py = ox + x * self.cw, y * self.chh
            if attr & curses.A_REVERSE:
                pygame.draw.rect(a.screen, fg, (px, py, self.cw, self.chh))
                fg = BG
            if ch in LINES or ch in SHADES:
                self.draw_line_char(a.screen, ch, fg, px, py)
            elif ch != ' ':
                g = a.glyphs.glyph(ch, fg, 26)
                a.screen.blit(g, (px + (self.cw - g.get_width()) // 2, py + (self.chh - g.get_height()) // 2))
        a.present()

    def draw_line_char(self, scr, ch, fg, px, py):
        cw, chh = self.cw, self.chh
        cx, cy = px + cw // 2, py + chh // 2
        if ch in SHADES:
            k = SHADES[ch]
            pygame.draw.rect(scr, tuple(int(BG[i] + (fg[i] - BG[i]) * k) for i in range(3)), (px, py, cw, chh))
            return
        segs = {'─': [((px, cy), (px + cw, cy))], '│': [((cx, py), (cx, py + chh))],
                '┌': [((cx, cy), (px + cw, cy)), ((cx, cy), (cx, py + chh))],
                '┐': [((px, cy), (cx, cy)), ((cx, cy), (cx, py + chh))],
                '└': [((cx, py), (cx, cy)), ((cx, cy), (px + cw, cy))],
                '┘': [((px, cy), (cx, cy)), ((cx, py), (cx, cy))]}[ch]
        for a, b in segs:
            pygame.draw.line(scr, fg, a, b, 2)

    def getch(self):
        deadline = time.time() + (self.tmo / 1000 if self.tmo > 0 else 1e9)
        while True:
            rem = deadline - time.time()
            if rem <= 0:
                return -1
            e = pygame.event.wait(int(min(rem, 0.25) * 1000) + 1)
            if e.type == pygame.NOEVENT:
                continue
            if e.type == pygame.QUIT:
                self.app.quit()
            if e.type == pygame.KEYDOWN:
                c = self.app.keycode(e)
                if c is not None:
                    return c
            p = self.app.pointer(e)
            if p and p[0] == 'down':
                self.mouse = (0, int((p[2] - (self.app.W - self.cols * self.cw) // 2) // self.cw), int(p[3] // self.chh), 0, curses.BUTTON1_PRESSED)
                return curses.KEY_MOUSE


TICK = 0.4     # seconds per world turn (enemies act, regen, cooldowns count down)
STEP, MELEE, CAST = 0.19, 0.34, 0.3   # player action lock times


class App:
    def __init__(self):
        pygame.init()
        pygame.key.set_repeat()
        win = os.environ.get('GF_WINDOW')
        if win:
            w, h = (int(v) for v in win.lower().split('x'))
            self.screen = pygame.display.set_mode((w, h))
        else:
            self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.display = self.screen
        pygame.display.set_caption('glyphfall')
        pygame.mouse.set_visible(bool(win))
        self.W, self.H = self.display.get_size()
        # draw on an opaque canvas: the Wayland window surface carries alpha, and alpha blits onto it
        # would leave the compositor blending the window with whatever is behind it
        self.screen = pygame.Surface((self.W, self.H)).convert()
        self.nav = int(os.environ.get('GF_NAV', '0' if win else '80'))  # the phone's nav bar overlays the bottom
        self.UH = self.H - self.nav
        self.T = max(24, self.UH // 19)
        self.glyphs = Glyphs()
        self.grid = GridWin(self)
        shim = types.SimpleNamespace(**{k: getattr(curses, k) for k in dir(curses) if k.isupper()})
        shim.error = curses.error
        shim.color_pair = lambda n: n << 8
        shim.getmouse = lambda: self.grid.mouse
        G.curses = shim
        self.clock = pygame.time.Clock()
        self.finger_seen = 0.0
        self.held, self.queue = {}, collections.deque()
        self.next_act, self.fl = 0.0, []
        self.next_tick = time.time() + TICK
        self.flash, self.shake, self.hurt_a = {}, 0.0, 0.0
        self.btn_cache = {}
        self.quit_armed = 0.0
        self.pp = None
        self.cam = None
        self.tiles = self.make_tiles()
        self.debug = os.environ.get('GF_DEBUG')
        try:
            self.g = G.Game.load() if os.path.exists(G.SAVE) else G.Game()
        except Exception:
            self.g = G.Game()
        self.g.fx = []
        self.level_id = id(self.g.g)
        mins = os.environ.get('GF_MINS')
        self.end = time.time() + int(mins if mins else 120) * 60
        self.warned = False
        self.layout()

    # ---------- input plumbing
    def keycode(self, e):
        k = e.key
        table = {pygame.K_ESCAPE: 27, pygame.K_RETURN: 10, pygame.K_KP_ENTER: 10, pygame.K_UP: curses.KEY_UP, pygame.K_DOWN: curses.KEY_DOWN,
                 pygame.K_LEFT: curses.KEY_LEFT, pygame.K_RIGHT: curses.KEY_RIGHT}
        if k in table:
            return table[k]
        if e.unicode and len(e.unicode) == 1 and e.unicode.isprintable():
            return ord(e.unicode)
        return None

    def pointer(self, e):
        W, H = self.W, self.H
        t = e.type
        if t in (pygame.FINGERDOWN, pygame.FINGERUP, pygame.FINGERMOTION):
            self.finger_seen = time.time()
            kind = {pygame.FINGERDOWN: 'down', pygame.FINGERUP: 'up', pygame.FINGERMOTION: 'move'}[t]
            return (kind, ('f', e.finger_id), e.x * W, e.y * H)
        if t in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            if getattr(e, 'touch', False) and time.time() - self.finger_seen < 2:
                return None
            if t == pygame.MOUSEMOTION and not e.buttons[0]:
                return None
            if t != pygame.MOUSEMOTION and e.button != 1:
                return None
            kind = {pygame.MOUSEBUTTONDOWN: 'down', pygame.MOUSEBUTTONUP: 'up', pygame.MOUSEMOTION: 'move'}[t]
            return (kind, ('m',), e.pos[0], e.pos[1])
        return None

    def present(self):
        self.display.blit(self.screen, (0, 0))
        pygame.display.flip()

    def quit(self):
        self.g.save()
        pygame.quit()
        sys.exit(0)

    # ---------- layout of the touch overlay
    def layout(self):
        W, UH = self.W, self.UH
        B = int(UH * 0.145)
        gap = max(4, int(B * 0.08))
        m = int(UH * 0.025)
        self.btns = []
        pw, ph = int(B * 1.2), int(B * 0.62)
        for i, (lab, key) in enumerate((('HP', ord('p')), ('MP', ord('o')))):
            self.btns.append(dict(kind='pot', rect=pygame.Rect(m + i * (pw + gap), int(UH * 0.115), pw, ph), label=lab, key=key, rep=0))
        sw, sh = int(B * 1.7), int(B * 1.12)
        ah = int(B * 0.62)
        right = W - m
        ytop = UH - m - ah - gap - 2 * sh - gap
        for i in range(4):
            self.btns.append(dict(kind='skill', slot=i, rect=pygame.Rect(right - 2 * sw - gap + (i % 2) * (sw + gap), ytop + (i // 2) * (sh + gap), sw, sh),
                                  key=ord('1') + i, rep=0.32))
        aw = (2 * sw + gap - 4 * gap) // 5
        for i, (lab, key) in enumerate(G.ACTIONS + [('Quit', ord('Q'))]):
            self.btns.append(dict(kind='act', rect=pygame.Rect(right - 2 * sw - gap + i * (aw + gap), UH - m - ah, aw, ah), label=lab, key=key, rep=0))
        self.stick_r = int(UH * 0.17)
        self.stick_home = (m + int(B * 2.1), UH - m - int(B * 1.7))
        self.stick_zone = pygame.Rect(0, int(UH * 0.2), int(W * 0.45), UH - int(UH * 0.2))

    def tile_of(self, x, y):
        cx, cy = self.cam
        return int((x + cx) // self.T), int((y + cy) // self.T)

    def btn_at(self, x, y):
        for b in self.btns:
            if b['rect'].collidepoint(x, y):
                return b
        return None

    # ---------- input handling
    def on_pointer(self, kind, pid, x, y):
        now = time.time()
        if self.debug:
            open('/tmp/gf_input.log', 'a').write(f'{kind} {pid} {x:.0f},{y:.0f}\n')
        if kind == 'down':
            b = self.btn_at(x, y)
            if b:
                self.held[pid] = dict(btn=b, next=now + 0.26 if b['rep'] else 1e18)
                self.press(b['key'], now)
            elif self.stick_zone.collidepoint(x, y) and not any(h.get('stick') for h in self.held.values()):
                R = self.stick_r
                cx = min(max(x, R + 6), self.W - R - 6)
                cy = min(max(y, R + 6), self.UH - R - 6)
                self.held[pid] = dict(btn=None, stick=True, c=(cx, cy), k=(x, y), next=1e18)
        elif kind == 'move' and pid in self.held:
            h = self.held[pid]
            if h.get('stick'):
                h['k'] = (x, y)
        elif kind == 'up':
            self.held.pop(pid, None)

    def press(self, key, now):
        self.queue.append(key)
        while len(self.queue) > 4:
            self.queue.popleft()

    def repeat_held(self, now):
        for pid, h in list(self.held.items()):
            if now < h['next'] or not h['btn']:
                continue
            if h['btn']['rep']:
                self.fire(h['btn']['key'], now, h['btn']['rep'])
                h['next'] = now + h['btn']['rep']

    def stick_vec(self):
        for h in self.held.values():
            if h.get('stick'):
                vx, vy = h['k'][0] - h['c'][0], h['k'][1] - h['c'][1]
                m = math.hypot(vx, vy)
                R = self.stick_r
                if m > R:
                    vx, vy, m = vx * R / m, vy * R / m, R
                return h['c'], (vx, vy), m / R
        return None

    def stick_dir(self):
        v = self.stick_vec()
        if not v or v[2] < 0.28:
            return None
        o = round(math.atan2(v[1][1], v[1][0]) / (math.pi / 4)) % 8
        return ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))[o]

    def key_dir(self):
        k = pygame.key.get_pressed()
        dx = (k[pygame.K_RIGHT] or k[pygame.K_d] or k[pygame.K_l]) - (k[pygame.K_LEFT] or k[pygame.K_a] or k[pygame.K_h])
        dy = (k[pygame.K_DOWN] or k[pygame.K_s] or k[pygame.K_j]) - (k[pygame.K_UP] or k[pygame.K_w] or k[pygame.K_k])
        return (dx, dy) if dx or dy else None

    def fire(self, key, now, interval):
        if not self.queue:
            self.queue.append(key)

    def pump_queue(self, now):
        if self.queue and now >= self.next_act:
            key = self.queue.popleft()
            used = self.act(key)
            self.next_act = max(self.next_act, now + (used if used else 0.05))

    # ---------- game actions
    def move(self, dx, dy):
        g = self.g
        tries = [(dx, dy)] + ([(dx, 0), (0, dy)] if dx and dy else [])
        for mx, my in tries:
            hit = g.enemy_at(g.px + mx, g.py + my)
            if g.step(mx, my):
                g.vision()
                if hit and self.pp:
                    self.pp[0] += mx * 0.4
                    self.pp[1] += my * 0.4
                return MELEE if hit else STEP
        return 0.0

    def act(self, c):
        """Run one input; returns how long the player is locked afterwards (0 = nothing happened)."""
        g = self.g
        used = 0.0
        if c in G.KEYS:
            used = self.move(*G.KEYS[c])
        elif ord('1') <= c <= ord('4'):
            used = CAST if g.cast(c - ord('1')) else 0.0
        elif c in (ord('.'), ord(' ')):
            used = STEP
        elif c in (ord('>'), 10, 13):
            used = 0.3 if g.descend() else 0.0
            if used:
                g.save()
        elif c in (ord('p'), ord('o')):
            used = 0.2 if g.use_cons('hp' if c == ord('p') else 'mp') else 0.0
        elif c == ord('i'):
            self.menu(G.menu_inv)
        elif c == ord('K'):
            self.menu(G.menu_skills)
        elif c == ord('t'):
            self.menu(G.menu_tree)
        elif c == ord('Q'):
            now = time.time()
            if now - self.quit_armed < 2.5:
                self.quit()
            self.quit_armed = now
            g.say('Tap Quit again to save and exit')
        self.check_dead()
        return used

    def check_dead(self):
        g = self.g
        if g.dead:
            g.respawn()
            g.save()

    def world_tick(self, now):
        """Enemies, regen, cooldowns and buffs advance on the wall clock, not on player actions."""
        if now < self.next_tick:
            return
        self.next_tick = max(self.next_tick + TICK, now - TICK)
        g = self.g
        g.end_turn()
        if g.turn % 60 == 0:
            g.save()
        self.check_dead()

    def menu(self, fn):
        self.held.clear()
        self.queue.clear()
        self.grid.timeout(20000)
        fn(self.grid, self.g)
        self.held.clear()
        self.queue.clear()
        self.next_act = time.time() + 0.15
        self.next_tick = time.time() + TICK

    # ---------- visuals
    def make_tiles(self):
        T = self.T
        out = {}
        for lvl, k in enumerate((1.0, 0.82, 0.64, 0.48)):
            col = lambda c, k=k: tuple(int(v * k) for v in c)
            w = pygame.Surface((T, T))
            w.fill(col((66, 64, 98)))
            pygame.draw.rect(w, col((96, 94, 140)), (0, 0, T, 3))
            pygame.draw.rect(w, col((96, 94, 140)), (0, 0, 3, T))
            pygame.draw.rect(w, col((44, 43, 70)), (0, T - 3, T, 3))
            pygame.draw.rect(w, col((44, 43, 70)), (T - 3, 0, 3, T))
            out[('wall', lvl)] = w
            f = pygame.Surface((T, T))
            f.fill(col((30, 29, 48)))
            d = self.glyphs.glyph('·', col((110, 108, 150)), int(T * 0.9))
            f.blit(d, ((T - d.get_width()) // 2, (T - d.get_height()) // 2))
            out[('floor', lvl)] = f
            s = f.copy()
            d = self.glyphs.glyph('▼', col(PAL[4]), int(T * 0.8))
            s.blit(d, ((T - d.get_width()) // 2, (T - d.get_height()) // 2))
            out[('stairs', lvl)] = s
        wd = pygame.Surface((T, T))
        wd.fill((34, 33, 52))
        pygame.draw.rect(wd, (46, 45, 70), (0, 0, T, 3))
        out['wall_dim'] = wd
        fd = pygame.Surface((T, T))
        fd.fill((24, 23, 38))
        d = self.glyphs.glyph('·', (52, 51, 76), int(T * 0.9))
        fd.blit(d, ((T - d.get_width()) // 2, (T - d.get_height()) // 2))
        out['floor_dim'] = fd
        sd = fd.copy()
        d = self.glyphs.glyph('▼', (110, 90, 50), int(T * 0.8))
        sd.blit(d, ((T - d.get_width()) // 2, (T - d.get_height()) // 2))
        out['stairs_dim'] = sd
        rnd = random.Random(7)
        def outdoor(kind, k):
            c = lambda v: tuple(int(q * k) for q in v)
            sf = pygame.Surface((T, T))
            if kind in 'gfp':
                sf.fill(c({'g': (38, 78, 36), 'f': (38, 78, 36), 'p': (96, 80, 52)[:3]}[kind]))
                for _ in range(5):
                    a, b = rnd.randint(0, T - 3), rnd.randint(0, T - 3)
                    pygame.draw.rect(sf, c((54, 104, 48) if kind != 'p' else (116, 98, 66)), (a, b, 2, 2))
                if kind == 'f':
                    for col_ in ((230, 210, 90), (230, 120, 160), (240, 240, 240)):
                        pygame.draw.circle(sf, c(col_), (rnd.randint(4, T - 5), rnd.randint(4, T - 5)), max(2, T // 14))
            elif kind == '~':
                sf.fill(c((30, 70, 130)))
                for yy in (T // 4, T // 2, 3 * T // 4):
                    pygame.draw.line(sf, c((90, 140, 210)), (T // 6, yy), (T // 2, yy), 2)
            else:
                sf.fill(c((38, 78, 36)))
                if kind == 'T':
                    pygame.draw.rect(sf, c((84, 58, 34)), (T // 2 - 2, T // 2, 4, T // 2 - 2))
                    pygame.draw.circle(sf, c((22, 70, 30)), (T // 2, T // 2 - 1), int(T * 0.4))
                    pygame.draw.circle(sf, c((36, 104, 44)), (T // 2 - 3, T // 2 - 4), int(T * 0.22))
                else:
                    pygame.draw.polygon(sf, c((110, 110, 118)), [(T // 6, T - 4), (T // 3, T // 4), (2 * T // 3, T // 5), (T - 4, T - 4)])
                    pygame.draw.polygon(sf, c((150, 150, 158)), [(T // 3, T // 4), (2 * T // 3, T // 5), (T // 2, T // 2)])
            return sf
        for kind in 'gfpT~r':
            for lvl, k in enumerate((1.0, 0.82, 0.64, 0.48)):
                out[('o' + kind, lvl)] = outdoor(kind, k)
            out['o' + kind + '_dim'] = outdoor(kind, 0.4)
        for lvl, k in enumerate((1.0, 0.82, 0.64, 0.48)):
            for nm in ('stairs',):
                st_ = outdoor('g', k)
                d = self.glyphs.glyph('▼', tuple(int(v * k) for v in PAL[4]), int(T * 0.8))
                st_.blit(d, ((T - d.get_width()) // 2, (T - d.get_height()) // 2))
                out[('stairs', lvl)] = st_
        sd = outdoor('g', 0.4)
        d = self.glyphs.glyph('▼', (110, 90, 50), int(T * 0.8))
        sd.blit(d, ((T - d.get_width()) // 2, (T - d.get_height()) // 2))
        out['stairs_dim'] = sd
        tele = pygame.Surface((T, T), pygame.SRCALPHA)
        tele.fill((255, 60, 70, 255))
        out['tele'] = tele
        glow = pygame.Surface((T * 3, T * 3), pygame.SRCALPHA)
        for r in range(T, 0, -3):
            pygame.draw.circle(glow, (120, 210, 230, int(70 * (1 - r / T))), (T * 3 // 2, T * 3 // 2), r + T // 2)
        out['glow'] = glow
        return out

    def snap_level(self):
        g = self.g
        self.pp = [float(g.px), float(g.py)]
        self.cam = None
        self.fl.clear()
        self.flash.clear()
        self.level_id = id(g.g)

    def update(self, dt):
        g = self.g
        if self.level_id != id(g.g) or self.pp is None:
            self.snap_level()
        k = 1 - math.exp(-dt * 21)
        for i, v in enumerate((g.px, g.py)):
            if abs(v - self.pp[i]) > 6:
                self.pp[i] = float(v)
            self.pp[i] += (v - self.pp[i]) * k
        for e in g.en:
            if 'rx' not in e or abs(e['x'] - e['rx']) > 6 or abs(e['y'] - e['ry']) > 6:
                e['rx'], e['ry'] = float(e['x']), float(e['y'])
            e['rx'] += (e['x'] - e['rx']) * k
            e['ry'] += (e['y'] - e['ry']) * k
        T = self.T
        for fx in g.fx:
            if fx[0] == 'dmg':
                _, e, dmg, crit = fx
                self.flash[id(e)] = 0.12
                self.fl.append(dict(x=e['rx'] * T + T / 2 if 'rx' in e else e['x'] * T + T / 2, y=(e['ry'] if 'ry' in e else e['y']) * T, text=str(dmg),
                                    color=(255, 235, 140) if crit else (255, 255, 255), size=int(T * (1.0 if crit else 0.7)), t=0.8, vx=random.uniform(-14, 14)))
            elif fx[0] == 'absorb':
                e = fx[1]
                self.fl.append(dict(x=e['x'] * T + T / 2, y=e['y'] * T, text='ward', color=PAL[5], size=int(T * 0.6), t=0.7, vx=0))
            elif fx[0] == 'die':
                e = fx[1]
                self.fl.append(dict(x=e.get('rx', e['x']) * T + T / 2, y=e.get('ry', e['y']) * T + T / 2, text=e['gl'], color=PAL[2], size=int(T * 1.0), t=0.35, vx=0, die=True))
            elif fx[0] == 'hurt':
                self.shake = min(14.0, 5 + fx[1] * 0.1)
                self.hurt_a = 0.55
        g.fx.clear()
        for f in self.fl:
            f['t'] -= dt
            if not f.get('die'):
                f['y'] -= 46 * dt
                f['x'] += f['vx'] * dt
        self.fl = [f for f in self.fl if f['t'] > 0]
        for key in list(self.flash):
            self.flash[key] -= dt
            if self.flash[key] <= 0:
                del self.flash[key]
        self.shake = max(0.0, self.shake - dt * 40)
        self.hurt_a = max(0.0, self.hurt_a - dt * 1.4)
        # camera follows the smoothed player position, clamped to the map
        tx = self.pp[0] * T + T / 2 - self.W / 2
        ty = self.pp[1] * T + T / 2 - self.UH / 2
        if self.cam is None:
            self.cam = [tx, ty]
        else:
            kc = 1 - math.exp(-dt * 10)
            self.cam[0] += (tx - self.cam[0]) * kc
            self.cam[1] += (ty - self.cam[1]) * kc

    def busy(self):
        """Anything moving or being touched? Otherwise only the idle bob needs frames, so render at half rate."""
        if self.held or self.queue or self.fl or self.flash or self.shake or self.hurt_a or self.pp is None:
            return True
        g = self.g
        if abs(g.px - self.pp[0]) > 0.01 or abs(g.py - self.pp[1]) > 0.01:
            return True
        return any(abs(e['x'] - e.get('rx', e['x'])) > 0.01 or abs(e['y'] - e.get('ry', e['y'])) > 0.01 for e in g.en)

    def draw(self):
        g, T, scr = self.g, self.T, self.screen
        scr.fill(BG)
        sx = random.uniform(-1, 1) * self.shake
        sy = random.uniform(-1, 1) * self.shake
        cx, cy = self.cam[0] - sx, self.cam[1] - sy
        x0, y0 = max(0, int(cx // T)), max(0, int(cy // T))
        x1, y1 = min(G.W, int((cx + self.W) // T) + 1), min(G.H, int((cy + self.UH + T) // T) + 1)
        vis, seen, tl = g.vis, g.seen, self.tiles
        px, py = g.px, g.py
        for ty in range(y0, y1):
            row, srow = g.g[ty], seen[ty]
            for tx in range(x0, x1):
                if not srow[tx]:
                    continue
                t = row[tx]
                if (tx, ty) in vis:
                    lvl = min(3, int(math.hypot(tx - px, ty - py) / 9 * 3.2))
                    s = tl[('stairs', lvl) if t == '>' else ('o' + g.ter[ty][tx], lvl)]
                else:
                    s = tl['stairs_dim' if t == '>' else 'o' + g.ter[ty][tx] + '_dim']
                scr.blit(s, (tx * T - cx, ty * T - cy))
        now = time.time()
        pulse = 0.5 + 0.5 * math.sin(now * 9)
        for e in g.en:
            if e['tele']:
                a = 150 if e['tele']['t'] <= 1 else int(70 + 60 * pulse)
                tl['tele'].set_alpha(a)
                for (x, y) in e['tele']['tiles']:
                    if seen[y][x]:
                        scr.blit(tl['tele'], (x * T - cx, y * T - cy))
        for (x, y) in g.chests:
            if seen[y][x]:
                self.put_glyph('▣', PAL[4], x * T - cx, y * T - cy, 0.9)
        for (x, y), its in g.items.items():
            if (x, y) in vis:
                it = its[-1]
                col = RARITY_RGB.get(it['rarity'], PAL[1])
                gl = {'gem': '◈', 'cons': '!', 'key': '⚷', 'rune': '◇'}.get(it['slot'], '◆')
                self.put_glyph(gl, col, x * T - cx, y * T - cy + math.sin(now * 3 + x) * 2, 0.9)
        for e in sorted(g.en, key=lambda e: e['ry'] if 'ry' in e else e['y']):
            if (e['x'], e['y']) not in vis:
                continue
            ex, ey = e.get('rx', e['x']) * T - cx, e.get('ry', e['y']) * T - cy
            col = PAL[5] if e.get('shield', 0) > 0 else PAL[2] if e['champ'] else PAL[3] if e['slow'] else (235, 130, 130)
            if self.flash.get(id(e), 0) > 0:
                col = (255, 255, 255)
            self.put_glyph(e['gl'], col, ex, ey, 1.0 if e['boss'] else 0.95)
            if e['hp'] < e['mhp']:
                w = T - 6
                pygame.draw.rect(scr, (60, 30, 40), (ex + 3, ey - 2, w, 4))
                pygame.draw.rect(scr, PAL[2], (ex + 3, ey - 2, max(0, w * e['hp'] / e['mhp']), 4))
        gx, gy = self.pp[0] * T - cx, self.pp[1] * T - cy
        scr.blit(tl['glow'], (gx - T, gy - T))
        self.put_glyph('@', PAL[7], gx, gy, 1.05, bold=True)
        for f in self.fl:
            a = min(1.0, f['t'] / 0.4)
            surf = self.glyphs.glyph(f['text'], f['color'], f['size']) if len(f['text']) == 1 else self.glyphs.text(f['text'], f['color'], f['size'])
            if f.get('die'):
                s2 = pygame.transform.rotozoom(surf, 0, 1 + (0.35 - f['t']) * 3)
                s2.set_alpha(int(255 * a))
                scr.blit(s2, (f['x'] - cx - s2.get_width() / 2, f['y'] - cy - s2.get_height() / 2))
            else:
                s2 = surf.copy()
                s2.set_alpha(int(255 * a))
                scr.blit(s2, (f['x'] - cx - s2.get_width() / 2, f['y'] - cy))
        if self.hurt_a > 0:
            v = pygame.Surface((self.W, self.UH), pygame.SRCALPHA)
            for i in range(14):
                pygame.draw.rect(v, (220, 30, 50, int(self.hurt_a * 150 * (1 - i / 14))), (i * 6, i * 6, self.W - i * 12, self.UH - i * 12), 6)
            scr.blit(v, (0, 0))
        self.draw_hud()
        self.draw_controls()

    def put_glyph(self, ch, color, x, y, scale, bold=False):
        T = self.T
        s = self.glyphs.glyph(ch, color, int(T * scale))
        self.screen.blit(s, (x + (T - s.get_width()) / 2, y + (T - s.get_height()) / 2))

    def bar(self, x, y, w, h, frac, col, back=(40, 38, 60)):
        pygame.draw.rect(self.screen, back, (x, y, w, h), border_radius=h // 3)
        if frac > 0:
            pygame.draw.rect(self.screen, col, (x, y, max(2, w * min(1, frac)), h), border_radius=h // 3)

    def draw_hud(self):
        g, scr, gl = self.g, self.screen, self.glyphs
        s = g.stats()
        u = max(12, self.UH // 30)
        bw = int(self.W * 0.2)
        self.bar(10, 8, bw, u, g.hp / s['hp'], PAL[2])
        scr.blit(gl.text(f'♥ {g.hp}/{s["hp"]}', PAL[1], u), (14, 8 + u))
        self.bar(10 + bw + 14, 8, bw * 0.8, u, g.mana / s['mana'], PAL[5])
        scr.blit(gl.text(f'✦ {g.mana}/{s["mana"]}', PAL[1], u), (14 + bw + 14, 8 + u))
        need = int(18 * g.lvl ** 1.5)
        right = self.W - 12
        t = gl.text(f'Lv {g.lvl}   ▼ Depth {g.depth}' + (f'   ✚{g.points}' if g.points else ''), PAL[4], int(u * 1.15))
        scr.blit(t, (right - t.get_width(), 6))
        self.bar(right - 220, 8 + int(u * 1.5), 220, 6, g.xp / need, PAL[4])
        left = max(0, int(self.end - time.time()) // 60)
        t = gl.text(f'⚙ {g.res["scrap"]}   ✧ {g.res["essence"]}   ⚷ {g.keys}   {left}m', PAL[1], u)
        t.set_alpha(190)
        scr.blit(t, (right - t.get_width(), 8 + int(u * 1.5) + 12))
        y = self.UH - 6
        for i, m in enumerate(reversed(g.log[-3:])):
            c = (235, 232, 245) if i == 0 else (150, 148, 175)
            t = gl.text(m, c, u)
            scr.blit(t, (self.W // 2 - t.get_width() // 2, y - (i + 1) * (u + 6)))

    def draw_stick(self):
        v = self.stick_vec()
        R = self.stick_r
        surf = pygame.Surface((R * 2 + 8, R * 2 + 8), pygame.SRCALPHA)
        mid = (R + 4, R + 4)
        if v:
            c, (vx, vy), mag = v
            pygame.draw.circle(surf, (30, 30, 50, 120), mid, R)
            pygame.draw.circle(surf, (150, 148, 200, 200), mid, R, 3)
            kn = (mid[0] + vx, mid[1] + vy)
            pygame.draw.circle(surf, (210, 208, 245, 210 if mag >= 0.28 else 130), kn, int(R * 0.42))
            self.screen.blit(surf, (c[0] - R - 4, c[1] - R - 4))
        else:
            pygame.draw.circle(surf, (30, 30, 50, 70), mid, R)
            pygame.draw.circle(surf, (110, 108, 150, 130), mid, R, 2)
            pygame.draw.circle(surf, (150, 148, 200, 110), mid, int(R * 0.42))
            self.screen.blit(surf, (self.stick_home[0] - R - 4, self.stick_home[1] - R - 4))

    def draw_controls(self):
        g, scr, gl = self.g, self.screen, self.glyphs
        self.draw_stick()
        down = {id(h['btn']) for h in self.held.values() if h['btn']}
        for b in self.btns:
            r = b['rect']
            pressed = id(b) in down
            kind = b['kind']
            fill, border, lines, color = (30, 30, 50), (110, 108, 150), [], PAL[1]
            if kind == 'pot':
                k = 'hp' if b['label'] == 'HP' else 'mp'
                n = g.cons.get(k, 0)
                ok = n and not g.potion_cd
                col = PAL[2] if k == 'hp' else PAL[5]
                lines = [f'{b["label"]} x{n}']
                border, color = (col if ok else (90, 88, 120)), (col if ok else (130, 128, 150))
            elif kind == 'skill':
                key = g.slots[b['slot']]
                sk = G.SKILLS[key]
                cd = g.cd.get(key, 0)
                ec = g.eff_cost(key)
                ready = not cd and g.mana >= ec
                lines = [f'{b["slot"] + 1} {sk["name"][:11]}', f'{ec}mp' + (f'  cd {cd}' if cd else '') + (' ✚' if g.mas(key)['points'] else '')]
                border = PAL[2] if ready else (90, 88, 120)
                color = PAL[1] if ready else (130, 128, 150)
            else:
                lines = [b['label']]
                if b['key'] == ord('>') and g.g[g.py][g.px] == '>':
                    border, color = PAL[4], PAL[4]
                if b['key'] == ord('Q') and time.time() - self.quit_armed < 2.5:
                    border, color = PAL[2], PAL[2]
            sk_ = (r.size, fill, border, pressed)
            surf = self.btn_cache.get(sk_)
            if surf is None:
                surf = self.btn_cache[sk_] = pygame.Surface(r.size, pygame.SRCALPHA)
                pygame.draw.rect(surf, fill + ((230 if pressed else 150),), surf.get_rect(), border_radius=10)
                pygame.draw.rect(surf, border + (255,), surf.get_rect(), 3 if pressed else 2, border_radius=10)
            scr.blit(surf, r.topleft)
            if kind == 'skill':
                key = g.slots[b['slot']]
                cd = g.cd.get(key, 0)
                total = max(1, G.SKILLS[key]['cd'])
                if cd:
                    ov = pygame.Surface((r.w - 6, int((r.h - 6) * cd / total)), pygame.SRCALPHA)
                    ov.fill((10, 10, 20, 150))
                    scr.blit(ov, (r.x + 3, r.y + 3))
            size = int(r.h * (0.3 if kind == 'skill' else 0.42))
            total_h = len(lines) * size * 1.15
            for i, ln in enumerate(lines):
                sz = size if not (kind == 'skill' and i) else int(size * 0.9)
                t = gl.text(ln, color, sz)
                while t.get_width() > r.w - 10 and sz > 8:
                    sz -= 1
                    t = gl.text(ln, color, sz)
                scr.blit(t, (r.centerx - t.get_width() / 2, r.centery - total_h / 2 + i * size * 1.15))

    # ---------- main loop
    def landing(self):
        g = self.g
        g.save()
        w = self.grid
        w.erase()
        G.put(w, 2, 2, 'Time. Saved.', G.cp(4, True))
        G.put(w, 4, 2, 'Next: bus stop -> work,')
        G.put(w, 5, 2, "or lunch at grandmother's.")
        G.put(w, 7, 2, 'tap or any key: close      C: keep playing 10m', curses.A_DIM)
        w.refresh()
        w.timeout(-1)
        c = w.getch()
        if c == ord('C'):
            self.end, self.warned = time.time() + 600, True
            self.next_tick = time.time() + TICK
            w.timeout(20000)
            return
        self.quit()

    def run(self):
        last = time.time()
        while True:
            now = time.time()
            dt = min(0.05, now - last)
            last = now
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    self.quit()
                elif e.type == pygame.KEYDOWN:
                    c = self.keycode(e)
                    if c is not None:
                        self.queue.append(c)
                        while len(self.queue) > 4:
                            self.queue.popleft()
                else:
                    p = self.pointer(e)
                    if p:
                        self.on_pointer(*p)
            self.repeat_held(now)
            self.pump_queue(now)
            if not self.queue and now >= self.next_act:
                d = self.stick_dir() or self.key_dir()
                if d:
                    self.next_act = now + (self.move(*d) or 0.05)
            self.world_tick(now)
            left = self.end - now
            if left <= 600 and not self.warned:
                self.warned = True
                self.g.say('10 minutes left. Find a good stopping spot.')
            if left <= 0:
                self.landing()
            self.update(dt)
            self.draw()
            self.present()
            self.clock.tick(30 if self.busy() else 8 if pygame.display.get_active() else 2)


if __name__ == '__main__':
    App().run()

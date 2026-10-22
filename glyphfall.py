#!/usr/bin/env python3
"""glyphfall: terminal ARPG. Classless, skill-swap builds, affix loot, infinite passive grid."""
import curses, locale, random, zlib, json, os, sys, time, signal

SAVE = os.path.expanduser('~/.local/share/glyphfall/save.json')

W, H = 80, 40
RARITY = ['normal', 'magic', 'rare', 'legend']
RCOL = {'normal': 1, 'magic': 7, 'rare': 4, 'legend': 6}
TAGS = ['fire', 'cold', 'lightning', 'phys', 'poison', 'necro', 'projectile', 'aoe', 'melee', 'chain', 'movement']

# ---- skills: no classes, just a pool. tags feed the *_pct stats from gear and tree.
SKILLS = {
    'whirlwind': dict(name='Whirlwind', cost=6, cd=0, tags={'phys', 'melee', 'aoe'}, base=10, desc='Hit everything adjacent. Scales with weapon.'),
    'fireball': dict(name='Fireball', cost=8, cd=0, tags={'fire', 'projectile'}, base=14, rng=8, desc='Hurl fire at the nearest enemy. Burns.'),
    'frost_nova': dict(name='Frost Nova', cost=10, cd=4, tags={'cold', 'aoe'}, base=9, desc='Ring of ice, radius 2. Slows.'),
    'blink': dict(name='Blink Strike', cost=6, cd=3, tags={'phys', 'movement', 'melee'}, base=8, desc='Teleport 5 tiles the way you face, strike on landing.'),
    'chain_lightning': dict(name='Chain Lightning', cost=9, cd=0, tags={'lightning', 'chain', 'projectile'}, base=10, rng=7, desc='Arcs through up to 4 enemies.'),
    'bone_spear': dict(name='Bone Spear', cost=9, cd=1, tags={'phys', 'necro', 'projectile'}, base=16, rng=9, desc='Pierces a whole line of enemies.'),
    'poison_cloud': dict(name='Poison Cloud', cost=11, cd=3, tags={'poison', 'aoe'}, base=4, rng=7, desc='Toxic cloud at target. Heavy damage over time.'),
    'soul_siphon': dict(name='Soul Siphon', cost=7, cd=0, tags={'necro', 'projectile'}, base=8, rng=6, desc='Drain a target, heal 40% of damage.'),
    'blood_pact': dict(name='Blood Pact', cost=0, cd=8, tags={'necro'}, base=0, desc='Pay 12% life: +20 mana and +50% damage for 6 turns.'),
}
START_SKILLS = ['whirlwind', 'fireball', 'frost_nova', 'blink']

# ---- loot: (stat, label, lo, hi). value scales with item level.
AFFIXES = [('hp', '+{} Life', 5, 12), ('mana', '+{} Mana', 4, 10), ('weapon', '+{} Weapon Dmg', 1, 3),
           ('dmg_pct', '+{}% Damage', 4, 10), ('crit', '+{}% Crit', 2, 5), ('leech', '+{}% Life Leech', 1, 3),
           ('armor', '+{} Armor', 3, 8), ('regen', '+{} Regen/10t', 1, 3), ('mregen', '+{} Mana Regen/10t', 1, 3),
           ('find', '+{}% Item Find', 5, 15)] + \
          [(t + '_pct', '+{}% ' + t.title() + ' Dmg', 8, 20) for t in TAGS]
BASES = {'weapon': ['Rusty Blade', 'Bone Club', 'Cleaver', 'Glaive', 'Wand', 'Hookblade'],
         'armor': ['Rags', 'Hide Vest', 'Chain Coat', 'Plate Scrap', 'Ash Robe'],
         'charm': ['Fang', 'Rune Stone', 'Eye Idol', 'Ember Shard', 'Bone Ring']}
PRE = ['Sturdy', 'Fierce', 'Gloomy', 'Wicked', 'Feral', 'Hexed', 'Arcane', 'Savage']
RARE_A = ['Doom', 'Gore', 'Dread', 'Soul', 'Void', 'Rot', 'Storm', 'Ash']
RARE_B = ['Bite', 'Coil', 'Brand', 'Edge', 'Veil', 'Grip', 'Song', 'Maw']

# ---- enemies: name, glyph, hp, dmg, xp, min depth, flags
ENEMIES = [('Rat', 'r', 8, 3, 4, 1, ''), ('Skeleton', 's', 14, 5, 7, 1, ''), ('Imp', 'i', 10, 4, 8, 2, 'ranged'),
           ('Ghoul', 'g', 26, 7, 12, 3, ''), ('Wraith', 'W', 18, 8, 16, 4, 'fast'), ('Cultist', 'c', 22, 6, 14, 5, 'ranged'),
           ('Golem', 'G', 60, 11, 30, 7, '')]


def tuple_aff(it):
    if 'aff' in it:
        it['aff'] = [tuple(a) for a in it['aff']]
    return it


def node_at(seed, x, y):
    """Infinite passive grid: every (x,y) is a deterministic node."""
    if (x, y) == (0, 0):
        return dict(kind='origin', name='Origin', stats={})
    r = random.Random(zlib.crc32(f'{seed}:{x}:{y}'.encode()))
    roll = r.random()
    scale = 1 + (abs(x) + abs(y)) * 0.04
    if roll < 0.04:
        k = r.choice([('Glass Cannon', {'more_dmg': 60, 'hp_mult': -40}), ('Arcane Surge', {'mana': 40, 'mregen': 3, 'dmg_pct': -10}),
                      ('Iron Will', {'armor': 30, 'hp': 20, 'crit': -5}), ('Vampiric Pact', {'leech': 8, 'hp_mult': -20}),
                      ('Elemental Rage', {'fire_pct': 40, 'cold_pct': 40, 'lightning_pct': 40, 'phys_pct': -30})])
        return dict(kind='key', name=k[0], stats=k[1])
    if roll < 0.20:
        if r.random() < 0.7:
            t = r.choice(TAGS)
            return dict(kind='notable', name=r.choice(['Mastery', 'Focus', 'Fury', 'Pull', 'Edge']) + ' of ' + t.title(), stats={t + '_pct': int(18 * scale)})
        s = r.choice([('leech', 3, 'Hunger'), ('find', 15, 'Fortune'), ('crit', 6, 'Precision'), ('hp', 25, 'Vigor')])
        return dict(kind='notable', name=s[2], stats={s[0]: int(s[1] * scale)})
    s = r.choice([('hp', 6), ('mana', 4), ('weapon', 1), ('dmg_pct', 3), ('crit', 2), ('armor', 3), ('regen', 1)])
    return dict(kind='minor', name='Minor ' + s[0], stats={s[0]: max(1, int(s[1] * scale))})


def node_at_skill(seed, key, x, y):
    """Per-skill infinite grid. Stats are sk_* and only apply while that skill is being cast."""
    if (x, y) == (0, 0):
        return dict(kind='origin', name=SKILLS[key]['name'], stats={})
    sk = SKILLS[key]
    r = random.Random(zlib.crc32(f'{seed}:{key}:{x}:{y}'.encode()))
    sc = 1 + (abs(x) + abs(y)) * 0.05
    roll = r.random()
    if roll < 0.05:
        k = r.choice([('Overload', {'sk_dmg': 80, 'sk_cost': -4}), ('Efficiency', {'sk_cost': 4, 'sk_dmg': -15}),
                      ('Echo Chamber', {'sk_echo': 35, 'sk_dmg': -15}), ('Bloodthirst', {'sk_leech': 18}),
                      ('Executioner', {'sk_crit': 25, 'sk_dmg': -10})])
        return dict(kind='key', name=k[0], stats=k[1])
    if roll < 0.22:
        opts = [('sk_dmg', int(22 * sc), 'Power'), ('sk_echo', int(12 * sc), 'Echo'), ('sk_burn', int(25 * sc), 'Searing'),
                ('sk_slow', 2, 'Chill'), ('sk_leech', int(6 * sc), 'Thirst')]
        if 'aoe' in sk['tags']:
            opts.append(('sk_radius', 1, 'Reach'))
        if 'rng' in sk or 'projectile' in sk['tags']:
            opts.append(('sk_range', 2, 'Far Sight'))
        if 'chain' in sk['tags']:
            opts.append(('sk_chain', 1, 'Arc'))
        o = r.choice(opts)
        return dict(kind='notable', name=f'{o[2]} ({sk["name"]})', stats={o[0]: o[1]})
    opts = [('sk_dmg', int(7 * sc)), ('sk_crit', int(3 * sc)), ('sk_leech', max(1, int(1.5 * sc))), ('sk_cost', 1)]
    if sk['cd'] > 0:
        opts.append(('sk_cd', 1))
    o = r.choice(opts)
    return dict(kind='minor', name='Minor ' + o[0][3:], stats={o[0]: o[1]})


class Game:
    def __init__(self, seed=None):
        self.seed = seed or random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.depth = 0
        self.lvl, self.xp, self.points = 1, 0, 0
        self.alloc = {(0, 0)}
        self.equip = {'weapon': None, 'armor': None, 'charm': None}
        self.pack = []
        self.known = list(START_SKILLS)
        self.slots = list(START_SKILLS)
        self.cd, self.buffs, self.log = {}, {}, []
        self.mastery = {}
        self.ms, self.cur = {}, None
        self.face = (1, 0)
        self.turn = 0
        self.dead = False
        self.hp, self.mana = 60, 30
        self.new_level()
        self.hp, self.mana = self.st('hp'), self.st('mana')

    # ---- persistence (current level is regenerated from seed+depth on load)
    def save(self):
        d = dict(seed=self.seed, depth=self.depth, lvl=self.lvl, xp=self.xp, points=self.points, alloc=sorted(self.alloc),
                 equip=self.equip, pack=self.pack, known=self.known, slots=self.slots, hp=self.hp, mana=self.mana, turn=self.turn,
                 best=getattr(self, 'best', self.depth), deaths=getattr(self, 'deaths', 0),
                 mastery={k: dict(m, alloc=sorted(m['alloc'])) for k, m in self.mastery.items()})
        os.makedirs(os.path.dirname(SAVE), exist_ok=True)
        with open(SAVE + '.tmp', 'w') as f:
            json.dump(d, f)
        os.replace(SAVE + '.tmp', SAVE)

    @classmethod
    def load(cls):
        d = json.load(open(SAVE))
        g = cls.__new__(cls)
        g.seed, g.lvl, g.xp, g.points = d['seed'], d['lvl'], d['xp'], d['points']
        g.rng = random.Random(g.seed + d['turn'])
        g.alloc = {tuple(p) for p in d['alloc']}
        g.equip, g.pack, g.known, g.slots = d['equip'], [tuple_aff(i) for i in d['pack']], d['known'], d['slots']
        for k, it in g.equip.items():
            if it:
                tuple_aff(it)
        g.cd, g.buffs, g.log = {}, {}, []
        g.mastery = {k: dict(m, alloc={tuple(p) for p in m['alloc']}) for k, m in d.get('mastery', {}).items()}
        g.ms, g.cur = {}, None
        g.face, g.turn, g.dead = (1, 0), d['turn'], False
        g.depth = d['depth'] - 1
        g.best, g.deaths = d.get('best', d['depth']), d.get('deaths', 0)
        g.new_level()
        g.hp, g.mana = min(d['hp'], g.st('hp')), min(d['mana'], g.st('mana'))
        g.say('Welcome back.')
        return g

    def respawn(self):
        # death is a setback, not a wipe: lose 1 depth and a quarter of the xp bar, keep everything else
        self.deaths = getattr(self, 'deaths', 0) + 1
        self.xp = int(self.xp * 0.75)
        self.depth = max(0, self.depth - 2)
        self.dead = False
        self.new_level()
        self.hp, self.mana = self.st('hp'), self.st('mana')
        self.say('You wake at the entrance. Depth lost, gear kept.')

    # ---- skill mastery: casting a skill trains it; its own grid improves only that skill
    def mas(self, key):
        return self.mastery.setdefault(key, dict(xp=0, lvl=0, points=0, alloc={(0, 0)}))

    def mstats(self, key):
        out = {}
        for p in self.mas(key)['alloc']:
            for k, v in node_at_skill(self.seed, key, *p)['stats'].items():
                out[k] = out.get(k, 0) + v
        return out

    def train(self, key, n):
        m = self.mas(key)
        m['xp'] += n
        while m['xp'] >= int(6 * (m['lvl'] + 1) ** 1.5):
            m['xp'] -= int(6 * (m['lvl'] + 1) ** 1.5)
            m['lvl'] += 1
            m['points'] += 1
            self.say(f'{SKILLS[key]["name"]} mastery {m["lvl"]}! +1 point (Skl > Master)')

    def eff_cost(self, key):
        return max(0, SKILLS[key]['cost'] - self.mstats(key).get('sk_cost', 0))

    # ---- stats
    def stats(self):
        s = {}
        def add(d):
            for k, v in d.items():
                s[k] = s.get(k, 0) + v
        for it in self.equip.values():
            if it:
                add(dict(it['aff']))
        for p in self.alloc:
            add(node_at(self.seed, *p)['stats'])
        s['hp'] = int((60 + 4 * (self.lvl - 1) + s.get('hp', 0)) * (1 + s.get('hp_mult', 0) / 100))
        s['mana'] = 30 + 2 * (self.lvl - 1) + s.get('mana', 0)
        s['weapon'] = 3 + s.get('weapon', 0)
        return s

    def st(self, k):
        return self.stats().get(k, 0)

    def say(self, m):
        self.log.append(m)
        del self.log[:-40]

    # ---- level gen
    def new_level(self):
        self.depth += 1
        self.best = max(getattr(self, 'best', 0), self.depth)
        r = random.Random(f'{self.seed}:{self.depth}')
        g = [['#'] * W for _ in range(H)]
        rooms = []
        for _ in range(80):
            w, h = r.randint(5, 12), r.randint(4, 7)
            x, y = r.randint(1, W - w - 2), r.randint(1, H - h - 2)
            if any(x < a + c + 1 and a < x + w + 1 and y < b + d + 1 and b < y + h + 1 for a, b, c, d in rooms):
                continue
            for j in range(y, y + h):
                for i in range(x, x + w):
                    g[j][i] = '.'
            rooms.append((x, y, w, h))
            if len(rooms) >= 11:
                break
        cen = [(x + w // 2, y + h // 2) for x, y, w, h in rooms]
        for (x1, y1), (x2, y2) in zip(cen, cen[1:]):
            for i in range(min(x1, x2), max(x1, x2) + 1):
                g[y1][i] = '.'
            for j in range(min(y1, y2), max(y1, y2) + 1):
                g[j][x2] = '.'
        self.g = g
        self.px, self.py = cen[0]
        sx, sy = cen[-1]
        g[sy][sx] = '>'
        self.seen = [[False] * W for _ in range(H)]
        self.items, self.en = {}, []
        boss = self.depth % 5 == 0
        for k, (x, y, w, h) in enumerate(rooms[1:], 1):
            n = r.randint(1, 2 + self.depth // 3)
            for _ in range(n):
                ex, ey = r.randint(x, x + w - 1), r.randint(y, y + h - 1)
                if (ex, ey) != (sx, sy) and not self.enemy_at(ex, ey):
                    self.spawn(ex, ey, r)
            if r.random() < 0.35:
                self.drop(r.randint(x, x + w - 1), r.randint(y, y + h - 1), 0)
        if boss:
            e = self.spawn(sx - 1, sy, r, boss=True)
        self.say(f'-- Depth {self.depth} --' + ('  A presence guards the stairs.' if boss else ''))
        self.vision()

    def spawn(self, x, y, r, boss=False):
        pool = [e for e in ENEMIES if e[5] <= self.depth] or ENEMIES[:1]
        n, gl, hp, dm, xp, _, fl = r.choice(pool[-5:])
        tier = (self.depth - 1) // 10
        sc = (1 + 0.22 * (self.depth - 1)) * (1.5 ** tier)
        pre = ['', 'Elder ', 'Ancient ', 'Primal ', 'Eternal '][min(tier, 4)] + ('Mythic ' * max(0, tier - 4))
        champ = r.random() < 0.12
        if boss:
            n, gl, hp, dm, xp, fl, champ = 'Warden', 'Ω', hp * 5, dm * 2, xp * 8, '', False
        if champ:
            hp, dm, xp, gl = hp * 2, int(dm * 1.5), xp * 3, gl.upper()
        e = dict(name=pre + ('Champion ' if champ else '') + n, gl=gl, hp=int(hp * sc), mhp=int(hp * sc), dmg=max(1, int(dm * sc)), xp=int(xp * sc),
                 x=x, y=y, fl=fl, slow=0, dots=[], champ=champ or boss, boss=boss, awake=False)
        self.en.append(e)
        return e

    def enemy_at(self, x, y):
        return next((e for e in self.en if e['x'] == x and e['y'] == y), None)

    # ---- loot
    def drop(self, x, y, bonus):
        find = 1 + self.st('find') / 100
        roll = self.rng.random()
        if roll < 0.12 * find:
            it = dict(slot='gem', skill=self.rng.choice(list(SKILLS)), rarity='magic')
        else:
            it = self.make_item(self.depth, bonus, find)
        self.items.setdefault((x, y), []).append(it)

    def make_item(self, ilvl, bonus, find=1):
        r = self.rng
        x = r.random() / (find * (1 + bonus * 0.4)) ** 0.5
        rar = 'legend' if x < 0.01 else 'rare' if x < 0.10 else 'magic' if x < 0.40 else 'normal'
        slot = r.choice(['weapon', 'armor', 'charm'])
        n = {'normal': 0, 'magic': r.randint(1, 2), 'rare': r.randint(3, 4), 'legend': r.randint(5, 6)}[rar]
        aff, used = [], set()
        sc = (1 + 0.08 * ilvl) * (1.5 ** ((ilvl - 1) // 10))
        if slot == 'weapon':
            aff.append(('weapon', int((2 + r.randint(0, 2)) * sc)))
        if slot == 'armor':
            aff.append(('armor', int((3 + r.randint(0, 3)) * sc)))
        for _ in range(n):
            a = r.choice(AFFIXES)
            if a[0] in used:
                continue
            used.add(a[0])
            aff.append((a[0], max(1, int(r.uniform(a[2], a[3]) * sc))))
        base = r.choice(BASES[slot])
        name = base if rar == 'normal' else f'{r.choice(PRE)} {base}' if rar == 'magic' else \
            f'{r.choice(RARE_A)}{r.choice(RARE_B).lower()} {base}' if rar == 'rare' else f'★ {r.choice(RARE_A)}{r.choice(RARE_B).lower()}, the {base}'
        return dict(slot=slot, rarity=rar, name=name, aff=aff, ilvl=ilvl)

    def aff_text(self, stat, v):
        for a in AFFIXES:
            if a[0] == stat:
                return a[1].format(v)
        return {'more_dmg': '+{}% More Damage', 'hp_mult': '{:+}% Max Life', 'sk_dmg': '{:+}% skill damage', 'sk_cost': '{:+} mana discount',
                'sk_cd': '-{} cooldown', 'sk_crit': '+{}% skill crit', 'sk_leech': '+{}% skill leech', 'sk_echo': '{}% chance to cast twice',
                'sk_burn': 'hits burn for {}% over 3 turns', 'sk_slow': 'hits slow for {} turns', 'sk_range': '+{} range',
                'sk_radius': '+{} radius', 'sk_chain': '+{} chain/targets'}.get(stat, stat + ' {}').format(v)

    def pickup(self):
        for it in self.items.pop((self.px, self.py), []):
            if it['slot'] == 'gem':
                sk = it['skill']
                if sk in self.known:
                    self.gain_xp(10 * self.depth)
                    self.say(f'Duplicate gem {SKILLS[sk]["name"]} -> xp')
                else:
                    self.known.append(sk)
                    self.say(f'LEARNED {SKILLS[sk]["name"]}! (K to slot it)')
            elif len(self.pack) >= 24:
                self.say('Pack full.')
                self.items.setdefault((self.px, self.py), []).append(it)
            else:
                self.pack.append(it)
                self.say(f'Picked up {it["name"]}')

    # ---- vision
    def los(self, x0, y0, x1, y1):
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx, sy = (1 if x1 > x0 else -1), (1 if y1 > y0 else -1)
        err, x, y = dx - dy, x0, y0
        while (x, y) != (x1, y1):
            if (x, y) != (x0, y0) and self.g[y][x] == '#':
                return False
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x += sx
            if e2 < dx:
                err += dx
                y += sy
        return True

    def vision(self):
        self.vis = set()
        R = 9
        for y in range(max(0, self.py - R), min(H, self.py + R + 1)):
            for x in range(max(0, self.px - R), min(W, self.px + R + 1)):
                if (x - self.px) ** 2 + (y - self.py) ** 2 <= R * R and self.los(self.px, self.py, x, y):
                    self.vis.add((x, y))
                    self.seen[y][x] = True
        for e in self.en:
            if (e['x'], e['y']) in self.vis:
                e['awake'] = True

    # ---- combat
    def calc(self, base, tags, melee_weapon=False):
        s = self.stats()
        d = base + (s['weapon'] * 0.6 if melee_weapon else 0)
        pct = s.get('dmg_pct', 0) + sum(s.get(t + '_pct', 0) for t in tags) + self.ms.get('sk_dmg', 0)
        if 'pact' in self.buffs:
            pct += 50
        d *= max(0.1, 1 + pct / 100) * (1 + s.get('more_dmg', 0) / 100)
        crit = self.rng.random() * 100 < 5 + s.get('crit', 0) + self.ms.get('sk_crit', 0)
        if crit:
            d *= 2
        return max(1, int(d)), crit

    def hit(self, e, dmg, crit=False, src=''):
        if e['hp'] <= 0:
            return 0
        e['hp'] -= dmg
        e['awake'] = True
        lc = self.st('leech') + self.ms.get('sk_leech', 0)
        if lc:
            self.hp = min(self.st('hp'), self.hp + max(0, int(dmg * lc / 100)))
        self.say(f'{src}{e["name"]} -{dmg}{"!" if crit else ""}' + (' (dies)' if e['hp'] <= 0 else ''))
        if e['hp'] > 0 and self.ms:
            if self.ms.get('sk_burn'):
                e['dots'].append((max(1, int(dmg * self.ms['sk_burn'] / 100)), 3))
            if self.ms.get('sk_slow'):
                e['slow'] = max(e['slow'], self.ms['sk_slow'])
        if e['hp'] <= 0:
            self.kill(e)
        return dmg

    def kill(self, e):
        if e in self.en:
            self.en.remove(e)
        if self.cur:
            self.train(self.cur, 2)
        self.gain_xp(e['xp'])
        if e['champ'] or self.rng.random() < 0.28:
            for _ in range(3 if e['boss'] else 1):
                self.drop(e['x'], e['y'], 2 if e['champ'] else 0)

    def gain_xp(self, n):
        self.xp += n
        while self.xp >= int(18 * self.lvl ** 1.5):
            self.xp -= int(18 * self.lvl ** 1.5)
            self.lvl += 1
            self.points += 1
            self.hp = min(self.st('hp'), self.hp + self.st('hp') // 3)
            self.say(f'LEVEL {self.lvl}! +1 passive point (T)')

    def nearest(self, rng):
        rng += self.ms.get('sk_range', 0)
        c = [e for e in self.en if (e['x'], e['y']) in self.vis and (e['x'] - self.px) ** 2 + (e['y'] - self.py) ** 2 <= rng * rng]
        return min(c, key=lambda e: (e['x'] - self.px) ** 2 + (e['y'] - self.py) ** 2) if c else None

    def adjacent(self):
        return [e for e in self.en if max(abs(e['x'] - self.px), abs(e['y'] - self.py)) == 1]

    def cast(self, idx):
        if idx >= len(self.slots) or not self.slots[idx]:
            return False
        key = self.slots[idx]
        sk = SKILLS[key]
        if self.cd.get(key, 0) > 0:
            self.say(f'{sk["name"]} cooling ({self.cd[key]})')
            return False
        ms = self.mstats(key)
        cost = self.eff_cost(key)
        if self.mana < cost:
            self.say('Not enough mana')
            return False
        self.ms, self.cur = ms, key
        try:
            ok = getattr(self, 'sk_' + key)(sk)
            if ok:
                self.mana -= cost
                self.cd[key] = max(0, sk['cd'] - ms.get('sk_cd', 0))
                self.train(key, 1)
                if self.rng.random() * 100 < ms.get('sk_echo', 0):
                    self.say('Echo!')
                    getattr(self, 'sk_' + key)(sk)
        finally:
            self.ms, self.cur = {}, None
        return ok

    def sk_whirlwind(self, sk):
        rr = 1 + self.ms.get('sk_radius', 0)
        adj = [e for e in self.en if max(abs(e['x'] - self.px), abs(e['y'] - self.py)) <= rr]
        if not adj:
            self.say('Nothing adjacent')
            return False
        for e in adj:
            d, c = self.calc(sk['base'], sk['tags'], True)
            self.hit(e, d, c, 'Whirl: ')
        return True

    def sk_fireball(self, sk):
        e = self.nearest(sk['rng'])
        if not e:
            self.say('No target')
            return False
        d, c = self.calc(sk['base'], sk['tags'])
        self.hit(e, d, c, 'Fireball: ')
        if e in self.en:
            e['dots'].append((max(1, d // 4), 3))
        return True

    def sk_frost_nova(self, sk):
        hit = [e for e in self.en if (e['x'] - self.px) ** 2 + (e['y'] - self.py) ** 2 <= (2 + self.ms.get('sk_radius', 0)) ** 2 + 1]
        if not hit:
            self.say('Nothing in range')
            return False
        for e in hit:
            d, c = self.calc(sk['base'], sk['tags'])
            self.hit(e, d, c, 'Nova: ')
            e['slow'] = 3
        return True

    def sk_blink(self, sk):
        dx, dy = self.face
        x, y = self.px, self.py
        for _ in range(5):
            nx, ny = x + dx, y + dy
            if self.g[ny][nx] == '#' or self.enemy_at(nx, ny):
                break
            x, y = nx, ny
        if (x, y) == (self.px, self.py):
            self.say('Blocked')
            return False
        self.px, self.py = x, y
        for e in self.adjacent():
            d, c = self.calc(sk['base'], sk['tags'], True)
            self.hit(e, d, c, 'Blink: ')
        return True

    def sk_chain_lightning(self, sk):
        e = self.nearest(sk['rng'])
        if not e:
            self.say('No target')
            return False
        done, mult = [], 1.0
        for _ in range(4 + self.ms.get('sk_chain', 0)):
            if not e:
                break
            d, c = self.calc(sk['base'], sk['tags'])
            done.append(e)
            self.hit(e, int(d * mult), c, 'Arc: ')
            mult *= 0.8
            cand = [o for o in self.en if o not in done and (o['x'] - e['x']) ** 2 + (o['y'] - e['y']) ** 2 <= 16]
            e = min(cand, key=lambda o: (o['x'] - e['x']) ** 2 + (o['y'] - e['y']) ** 2) if cand else None
        return True

    def sk_bone_spear(self, sk):
        t = self.nearest(sk['rng'])
        if not t:
            self.say('No target')
            return False
        dx, dy = t['x'] - self.px, t['y'] - self.py
        n = max(abs(dx), abs(dy))
        hit = set()
        for i in range(1, sk['rng'] + 1):
            x, y = self.px + round(dx * i / n), self.py + round(dy * i / n)
            if self.g[y][x] == '#':
                break
            e = self.enemy_at(x, y)
            if e and id(e) not in hit:
                hit.add(id(e))
                d, c = self.calc(sk['base'], sk['tags'])
                self.hit(e, d, c, 'Spear: ')
        return True

    def sk_poison_cloud(self, sk):
        t = self.nearest(sk['rng'])
        if not t:
            self.say('No target')
            return False
        for e in [e for e in self.en if (e['x'] - t['x']) ** 2 + (e['y'] - t['y']) ** 2 <= (2 + self.ms.get('sk_radius', 0)) ** 2 + 1]:
            d, _ = self.calc(sk['base'], sk['tags'])
            e['dots'].append((d, 5))
            e['awake'] = True
        self.say('Poison cloud blooms')
        return True

    def sk_soul_siphon(self, sk):
        e = self.nearest(sk['rng'])
        if not e:
            self.say('No target')
            return False
        d, c = self.calc(sk['base'], sk['tags'])
        got = self.hit(e, d, c, 'Siphon: ')
        self.hp = min(self.st('hp'), self.hp + int(got * 0.4))
        return True

    def sk_blood_pact(self, sk):
        cost = int(self.st('hp') * 0.12)
        if self.hp <= cost + 1:
            self.say('Too weak for the pact')
            return False
        self.hp -= cost
        self.mana = min(self.st('mana'), self.mana + 20)
        self.buffs['pact'] = 6
        self.say('Blood Pact: +50% damage')
        return True

    # ---- movement & turn
    def step(self, dx, dy):
        self.face = (dx, dy)
        nx, ny = self.px + dx, self.py + dy
        if self.g[ny][nx] == '#':
            return False
        e = self.enemy_at(nx, ny)
        if e:
            d, c = self.calc(0, {'phys', 'melee'}, True)
            self.hit(e, d, c, 'You: ')
        else:
            self.px, self.py = nx, ny
            self.pickup()
        return True

    def descend(self):
        if self.g[self.py][self.px] != '>':
            self.say('No stairs here')
            return False
        self.new_level()
        return True

    def end_turn(self):
        self.turn += 1
        s = self.stats()
        if self.turn % 2 == 0:
            self.mana = min(s['mana'], self.mana + 1)
        if self.turn % 10 == 0:
            self.hp = min(s['hp'], self.hp + 1 + s.get('regen', 0))
            self.mana = min(s['mana'], self.mana + s.get('mregen', 0))
        for k in list(self.cd):
            self.cd[k] = max(0, self.cd[k] - 1)
        for k in list(self.buffs):
            self.buffs[k] -= 1
            if self.buffs[k] <= 0:
                del self.buffs[k]
        self.vision()
        for e in list(self.en):
            if e not in self.en:
                continue
            nd = []
            for d, t in e['dots']:
                e['hp'] -= d
                if t > 1:
                    nd.append((d, t - 1))
            e['dots'] = nd
            if e['hp'] <= 0:
                self.say(f'{e["name"]} succumbs')
                self.kill(e)
                continue
            if not e['awake']:
                continue
            if e['slow'] > 0:
                e['slow'] -= 1
                if self.turn % 2:
                    continue
            for _ in range(2 if 'fast' in e['fl'] else 1):
                self.enemy_act(e)
        if self.hp <= 0:
            self.dead = True

    def hurt(self, e, mult=1.0):
        a = self.stats().get('armor', 0)
        d = max(1, int(e['dmg'] * mult * (1 - a / (a + 30 + 8 * self.depth))))
        self.hp -= d
        self.say(f'{e["name"]} hits you -{d}')

    def enemy_act(self, e):
        dx, dy = self.px - e['x'], self.py - e['y']
        dist = max(abs(dx), abs(dy))
        if dist == 1:
            self.hurt(e)
        elif 'ranged' in e['fl'] and dist <= 6 and self.los(e['x'], e['y'], self.px, self.py):
            self.hurt(e, 0.8)
        elif dist <= 16:
            sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
            for mx, my in ([(sx, sy), (sx, 0), (0, sy)] if abs(dx) > abs(dy) else [(sx, sy), (0, sy), (sx, 0)]):
                if (mx or my) and self.g[e['y'] + my][e['x'] + mx] != '#' and not self.enemy_at(e['x'] + mx, e['y'] + my) \
                        and (e['x'] + mx, e['y'] + my) != (self.px, self.py):
                    e['x'] += mx
                    e['y'] += my
                    break

    # ---- passive tree
    def frontier(self, alloc=None):
        out = set()
        alloc = self.alloc if alloc is None else alloc
        for x, y in alloc:
            for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                p = (x + d[0], y + d[1])
                if p not in alloc:
                    out.add(p)
        return out

    def take(self, p):
        if self.points > 0 and p in self.frontier():
            self.alloc.add(p)
            self.points -= 1
            self.hp = min(self.hp, self.st('hp'))
            return True
        return False

    def take_skill(self, key, p):
        m = self.mas(key)
        if m['points'] > 0 and p in self.frontier(m['alloc']):
            m['alloc'].add(p)
            m['points'] -= 1
            return True
        return False

    def equip_item(self, i):
        it = self.pack[i]
        old = self.equip[it['slot']]
        self.equip[it['slot']] = it
        self.pack.pop(i)
        if old:
            self.pack.append(old)
        self.hp = min(self.hp, self.st('hp'))


# =================== curses UI ===================
def cp(n, bold=False):
    return curses.color_pair(n) | (curses.A_BOLD if bold else 0)


SHADOW = None  # tests: list of lists mirroring what put() wrote


def put(win, y, x, s, a=0):
    h, w = win.getmaxyx()
    if SHADOW is not None:
        for i, ch in enumerate(s):
            if 0 <= y < len(SHADOW) and 0 <= x + i < len(SHADOW[0]):
                SHADOW[y][x + i] = ch
    if 0 <= y < h and x < w:
        try:
            win.addstr(y, max(0, x), s[:w - x - (1 if y == h - 1 else 0)], a)
        except curses.error:
            pass


# ---- touch widgets: every button is (y, x, h, w, key); a tap becomes that key press
def box(win, y, x, h, w, lines, a=0):
    put(win, y, x, '┌' + '─' * (w - 2) + '┐', a)
    for j in range(1, h - 1):
        put(win, y + j, x, '│' + ' ' * (w - 2) + '│', a)
    put(win, y + h - 1, x, '└' + '─' * (w - 2) + '┘', a)
    top = y + (h - len(lines)) // 2
    for j, t in enumerate(lines):
        put(win, top + j, x + max(1, (w - len(t)) // 2), t[:w - 2], a)


def button(win, btns, y, x, h, w, lines, key, a=0):
    box(win, y, x, h, w, lines, a)
    btns.append((y, x, h, w, key))


def hit(btns, my, mx):
    for y, x, h, w, key in btns:
        if y <= my < y + h and x <= mx < x + w:
            return key
    return None


def menu_bar(win, defs):
    """Bottom row of 3-line buttons for menus. defs = [(label, key)]."""
    h, w = win.getmaxyx()
    btns = []
    bw = w // len(defs)
    for i, (lab, key) in enumerate(defs):
        button(win, btns, h - 3, i * bw, 3, bw, [lab], key, curses.A_DIM)
    return btns


def getin(win, btns):
    """Next key, or ('tap', y, x) for a touch that missed every button. -1 on timeout."""
    c = win.getch()
    if c != curses.KEY_MOUSE:
        return c
    try:
        _, mx, my, _, b = curses.getmouse()
    except curses.error:
        return -1
    if not b & (curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED):
        return -1
    k = hit(btns, my, mx)
    return k if k is not None else ('tap', my, mx)


PAD = [[('↖', ord('y')), ('↑', ord('k')), ('↗', ord('u'))],
       [('←', ord('h')), ('·', ord('.')), ('→', ord('l'))],
       [('↙', ord('b')), ('↓', ord('j')), ('↘', ord('n'))]]
ACTIONS = [('▼', ord('>')), ('Bag', ord('i')), ('Skl', ord('K')), ('Tre', ord('t'))]
PANEL = 20


def draw(win, g, btns, touch):
    win.erase()
    btns.clear()
    h, w = win.getmaxyx()
    s = g.stats()
    if touch:
        mx0, mw, my0, mh = PANEL, w - 2 * PANEL, 2, h - 4
    else:
        mx0, mw, my0, mh = 0, w, 2, h - 6
    cx0 = min(max(0, g.px - mw // 2), max(0, W - mw))
    cy0 = min(max(0, g.py - mh // 2), max(0, H - mh))
    g.view = (my0, mx0, mh, mw, cy0, cx0)
    inside = lambda sy, sx: 0 <= sy < mh and 0 <= sx < mw
    for sy in range(mh):
        for sx in range(min(mw - 1, W)):
            x, y = cx0 + sx, cy0 + sy
            if not (0 <= x < W and 0 <= y < H) or not g.seen[y][x]:
                continue
            t, v = g.g[y][x], (x, y) in g.vis
            ch = '▓' if t == '#' else '▼' if t == '>' else '·'
            col = cp(4, True) if t == '>' else cp(1)
            put(win, sy + my0, sx + mx0, ch, col if v else curses.A_DIM)
    for (x, y), its in g.items.items():
        if (x, y) in g.vis and inside(y - cy0, x - cx0):
            it = its[-1]
            put(win, y - cy0 + my0, x - cx0 + mx0, '◈' if it['slot'] == 'gem' else '◆', cp(RCOL[it['rarity']], True))
    for e in g.en:
        if (e['x'], e['y']) in g.vis and inside(e['y'] - cy0, e['x'] - cx0):
            put(win, e['y'] - cy0 + my0, e['x'] - cx0 + mx0, e['gl'], cp(2, True) if e['champ'] else cp(3 if e['slow'] else 2))
    put(win, g.py - cy0 + my0, g.px - cx0 + mx0, '@', cp(5, True))
    bar = lambda v, m, n: '█' * int(n * max(0, v) / max(1, m)) + '░' * (n - int(n * max(0, v) / max(1, m)))
    put(win, 0, 0, f'♥{g.hp}/{s["hp"]} {bar(g.hp, s["hp"], 10)}', cp(2, True))
    put(win, 1, 0, f'✦{g.mana}/{s["mana"]} {bar(g.mana, s["mana"], 10)}', cp(5))
    put(win, 0, w - 22, f'Lv{g.lvl} ▼D{g.depth}' + (f' ✚{g.points}' if g.points else ''), cp(4, True))
    put(win, 1, w - 22, f'xp {g.xp}/{int(18 * g.lvl ** 1.5)}  {getattr(g, "clock", "")}', curses.A_DIM)
    nlog = 2 if touch else 3
    for i, m in enumerate(g.log[-nlog:]):
        put(win, h - nlog - (0 if touch else 2) + i, 0, m, curses.A_DIM if i < nlog - 1 else 0)
    if touch:
        y0 = h - 2 - 9
        for r, row in enumerate(PAD):
            for c, (lab, key) in enumerate(row):
                button(win, btns, y0 + 3 * r, 1 + 6 * c, 3, 6, [lab], key, curses.A_DIM if key != ord('.') else 0)
        y1 = h - 2 - 11
        for i, k in enumerate(g.slots):
            sk = SKILLS[k]
            cd = g.cd.get(k, 0)
            ec = g.eff_cost(k)
            ready = not cd and g.mana >= ec
            second = f'{ec}mp' + (f' cd{cd}' if cd else '') + (' ✚' if g.mas(k)['points'] else '')
            button(win, btns, y1 + 4 * (i // 2), w - PANEL + 10 * (i % 2), 4, 10,
                   [f'{i + 1} {sk["name"][:7]}', second], ord('1') + i, cp(7, True) if ready else curses.A_DIM)
        for i, (lab, key) in enumerate(ACTIONS):
            on_stairs = key == ord('>') and g.g[g.py][g.px] == '>'
            button(win, btns, y1 + 8, w - PANEL + 5 * i, 3, 5, [lab], key, cp(4, True) if on_stairs else curses.A_DIM)
    else:
        sb = ''
        for i, k in enumerate(g.slots):
            sk = SKILLS[k]
            c = g.cd.get(k, 0)
            sb += f'{i + 1}:{sk["name"][:9]}{"(" + str(c) + ")" if c else "":<3}{g.eff_cost(k)} '
        put(win, h - 2, 0, sb, cp(7))
        put(win, h - 1, 0, 'hjklyubn/arrows move 1-4 skill i gear K skills t tree > stairs', curses.A_DIM)
    win.refresh()


KEYS = {ord('h'): (-1, 0), ord('l'): (1, 0), ord('k'): (0, -1), ord('j'): (0, 1), curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0),
        curses.KEY_UP: (0, -1), curses.KEY_DOWN: (0, 1), ord('a'): (-1, 0), ord('d'): (1, 0), ord('w'): (0, -1), ord('s'): (0, 1),
        ord('y'): (-1, -1), ord('u'): (1, -1), ord('b'): (-1, 1), ord('n'): (1, 1)}


def item_lines(g, it):
    if it['slot'] == 'gem':
        sk = SKILLS[it['skill']]
        return [(f'Skill gem: {sk["name"]}', cp(7, True)), (sk['desc'], 0), ('Tags: ' + ' '.join(sorted(sk['tags'])), curses.A_DIM)]
    out = [(it['name'], cp(RCOL[it['rarity']], True)), (f'{it["rarity"]} {it["slot"]} ilvl {it.get("ilvl", 1)}', curses.A_DIM)]
    out += [('  ' + g.aff_text(k, v), 0) for k, v in it['aff']]
    return out


def scroll_top(sel, avail, n):
    return max(0, min(sel - avail + 1, n - avail)) if sel >= avail else 0


def menu_inv(win, g):
    sel = 0
    while True:
        win.erase()
        h, w = win.getmaxyx()
        half = w // 2
        put(win, 0, 0, 'GEAR', cp(4, True))
        for y, (slot, it) in enumerate(g.equip.items(), 1):
            put(win, y, 0, f'[{slot[:3]}] ' + (it['name'] if it else '-'), cp(RCOL[it['rarity']]) if it else curses.A_DIM)
        avail = max(3, h - 5 - 3)
        n = len(g.pack)
        sel = min(sel, max(0, n - 1))
        top = scroll_top(sel, avail, n)
        for i in range(top, min(n, top + avail)):
            it = g.pack[i]
            nm = ('Gem: ' + SKILLS[it['skill']]['name']) if it['slot'] == 'gem' else it['name']
            put(win, 5 + i - top, 0, ('>' if i == sel else ' ') + nm[:half - 2], cp(RCOL[it['rarity']], i == sel))
        if g.pack:
            for j, (t, a) in enumerate(item_lines(g, g.pack[sel])):
                put(win, 1 + j, half, t, a)
        btns = menu_bar(win, [('↑', ord('k')), ('↓', ord('j')), ('Equip', 10), ('Drop', ord('x')), ('Back', 27)])
        win.refresh()
        c = getin(win, btns)
        if isinstance(c, tuple):
            row = c[1] - 5 + top
            if 5 <= c[1] < 5 + avail and 0 <= row < n and c[2] < half:
                if row == sel and g.pack[sel]['slot'] != 'gem':
                    g.equip_item(sel)
                sel = row
            continue
        if c in (27, ord('q'), ord('i')):
            return
        if c in (curses.KEY_DOWN, ord('j')) and g.pack:
            sel = (sel + 1) % n
        elif c in (curses.KEY_UP, ord('k')) and g.pack:
            sel = (sel - 1) % n
        elif c in (10, 13) and g.pack:
            if g.pack[sel]['slot'] != 'gem':
                g.equip_item(sel)
        elif c == ord('x') and g.pack:
            g.pack.pop(sel)


def menu_skills(win, g):
    sel = 0
    while True:
        win.erase()
        h, w = win.getmaxyx()
        half = w // 2
        put(win, 0, 0, 'SKILLS  tap a skill, then a slot button', cp(4, True))
        avail = max(3, h - 2 - 3)
        n = len(g.known)
        top = scroll_top(sel, avail, n)
        for i in range(top, min(n, top + avail)):
            k = g.known[i]
            sk = SKILLS[k]
            m = g.mas(k)
            put(win, 1 + i - top, 0, ('>' if i == sel else ' ') + f'{sk["name"]} ({g.eff_cost(k)}mp) m{m["lvl"]}' + (f' ✚{m["points"]}' if m['points'] else '') + (' *' if k in g.slots else ''),
                cp(7 if k in g.slots else 1, i == sel))
        for i, k in enumerate(g.slots):
            put(win, 1 + i, half, f'{i + 1}: {SKILLS[k]["name"]}', cp(7, True))
        sk = SKILLS[g.known[sel]]
        put(win, 6, half, sk['name'], cp(4, True))
        put(win, 7, half, sk['desc'][:w - half - 1])
        put(win, 8, half, 'tags: ' + ' '.join(sorted(sk['tags'])), curses.A_DIM)
        btns = menu_bar(win, [('↑', ord('k')), ('↓', ord('j')), ('→1', ord('1')), ('→2', ord('2')), ('→3', ord('3')), ('→4', ord('4')), ('Master', ord('m')), ('Back', 27)])
        win.refresh()
        c = getin(win, btns)
        if isinstance(c, tuple):
            row = c[1] - 1 + top
            if 1 <= c[1] < 1 + avail and 0 <= row < n and c[2] < half:
                sel = row
            continue
        if c in (27, ord('q')):
            return
        if c == ord('m'):
            menu_tree(win, g, g.known[sel])
        elif c in (curses.KEY_DOWN, ord('j')):
            sel = (sel + 1) % n
        elif c in (curses.KEY_UP, ord('k')):
            sel = (sel - 1) % n
        elif ord('1') <= c <= ord('4'):
            k = g.known[sel]
            i = c - ord('1')
            if k in g.slots:
                j = g.slots.index(k)
                g.slots[j], g.slots[i] = g.slots[i], g.slots[j]
            else:
                g.slots[i] = k


def menu_tree(win, g, key=None):
    cx, cy = 0, 0
    while True:
        win.erase()
        h, w = win.getmaxyx()
        if key:
            m = g.mas(key)
            alloc, pts, nodefn = m['alloc'], m['points'], lambda x, y: node_at_skill(g.seed, key, x, y)
            take = lambda p: g.take_skill(key, p)
            title = f'{SKILLS[key]["name"].upper()} MASTERY lv{m["lvl"]} ({m["xp"]}/{int(6 * (m["lvl"] + 1) ** 1.5)})'
        else:
            alloc, pts, nodefn, take, title = g.alloc, g.points, lambda x, y: node_at(g.seed, x, y), g.take, 'TREE'
        put(win, 0, 0, f'{title}  points:{pts}  tap a node to focus, tap it again to take', cp(4, True))
        fr = g.frontier(alloc)
        for sy in range(1, h - 7):
            if (sy - h // 2 + 2) % 2:
                continue
            y = cy + (sy - h // 2 + 2) // 2
            for sx in range(0, w - 1):
                if (sx - w // 2) % 4:
                    continue
                x = cx + (sx - w // 2) // 4
                if (x, y) in alloc:
                    ch, a = '◉', cp(3, True)
                elif (x, y) in fr:
                    n = nodefn(x, y)
                    ch = {'minor': '○', 'notable': '◈', 'key': '★'}[n['kind']]
                    a = cp(7 if n['kind'] == 'minor' else 4 if n['kind'] == 'notable' else 6, True)
                else:
                    ch, a = '·', curses.A_DIM
                if (x, y) == (cx, cy):
                    a |= curses.A_REVERSE
                put(win, sy, sx, ch, a)
        n = nodefn(cx, cy)
        state = 'taken' if (cx, cy) in alloc else 'available' if (cx, cy) in fr else 'unreachable'
        put(win, h - 6, 0, f'{n["name"]} [{n["kind"]}] {state}', cp(4, True))
        put(win, h - 5, 0, ', '.join(g.aff_text(k, v) for k, v in n['stats'].items()))
        btns = menu_bar(win, [('←', ord('h')), ('↑', ord('k')), ('↓', ord('j')), ('→', ord('l')), ('Take', 10), ('Back', 27)])
        win.refresh()
        c = getin(win, btns)
        if isinstance(c, tuple):
            ty, tx = c[1], c[2]
            if 1 <= ty < h - 7:
                dx, dy = round((tx - w // 2) / 4), round((ty - h // 2 + 2) / 2)
                if (dx, dy) == (0, 0):
                    if not take((cx, cy)):
                        g.say('Cannot take that')
                cx, cy = cx + dx, cy + dy
            continue
        if c in (27, ord('q'), ord('t')):
            return
        if c in KEYS:
            cx += KEYS[c][0]
            cy += KEYS[c][1]
        elif c in (10, 13):
            if not take((cx, cy)):
                g.say('Cannot take that')


def run(win):
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    for i, c in enumerate([curses.COLOR_WHITE, curses.COLOR_RED, curses.COLOR_GREEN, curses.COLOR_YELLOW, curses.COLOR_BLUE,
                           curses.COLOR_MAGENTA, curses.COLOR_CYAN], 1):
        curses.init_pair(i, c, -1)
    win.keypad(True)
    curses.mouseinterval(0)
    curses.mousemask(curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED | curses.BUTTON1_RELEASED)
    win.timeout(20000)
    try:
        g = Game.load() if os.path.exists(SAVE) else Game()
    except Exception:
        g = Game()
    mins = next((int(sys.argv[i + 1]) for i, a in enumerate(sys.argv) if a == '--mins'), 120)
    end = time.time() + mins * 60
    warned = False
    btns = []
    signal.signal(signal.SIGHUP, lambda *a: (g.save(), sys.exit(0)))
    while True:
        left = end - time.time()
        g.clock = f'{max(0, int(left // 60))}m left'
        if left <= 600 and not warned:
            warned = True
            g.say('10 minutes left. Find a good stopping spot.')
        touch = '--keys' not in sys.argv and win.getmaxyx()[0] >= 16 and (win.getmaxyx()[1] >= 80 or '--touch' in sys.argv)
        draw(win, g, btns, touch)
        if left <= 0:
            g.save()
            win.erase()
            put(win, 2, 2, 'Time. Saved.', cp(4, True))
            put(win, 4, 2, 'Next: bus stop -> work,')
            put(win, 5, 2, "or lunch at grandmother's.")
            put(win, 7, 2, 'any key: close   C: keep playing 10m', curses.A_DIM)
            win.refresh()
            win.timeout(-1)
            if win.getch() != ord('C'):
                return
            win.timeout(20000)
            end, warned = time.time() + 600, True
            continue
        c = getin(win, btns)
        if isinstance(c, tuple):  # tap on the map: step toward that tile
            my0, mx0, mh, mw, cy0, cx0 = g.view
            ty, tx = c[1] - my0 + cy0, c[2] - mx0 + cx0
            if my0 <= c[1] < my0 + mh and mx0 <= c[2] < mx0 + mw:
                dx, dy = (tx > g.px) - (tx < g.px), (ty > g.py) - (ty < g.py)
                c = ord('.') if not (dx or dy) else next(k for k, v in KEYS.items() if v == (dx, dy) and k < 256 and chr(k) in 'hjklyubn')
            else:
                continue
        if c == -1:
            continue
        used = False
        if c == ord('Q'):
            g.save()
            return
        if c in KEYS:
            used = g.step(*KEYS[c])
        elif ord('1') <= c <= ord('4'):
            used = g.cast(c - ord('1'))
        elif c in (ord('.'), ord(' ')):
            used = True
        elif c in (ord('>'), 10, 13):
            used = g.descend()
        elif c == ord('i'):
            menu_inv(win, g)
        elif c == ord('K'):
            menu_skills(win, g)
        elif c == ord('t'):
            menu_tree(win, g)
        if used:
            g.end_turn()
            if g.turn % 40 == 0 or c in (ord('>'), 10, 13):
                g.save()
        if g.dead:
            g.respawn()
            g.save()


if __name__ == '__main__':
    try:
        locale.setlocale(locale.LC_ALL, '')
    except locale.Error:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    curses.wrapper(run)

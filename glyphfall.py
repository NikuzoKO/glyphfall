#!/usr/bin/env python3
"""glyphfall: terminal ARPG. Classless, skill-swap builds, affix loot, infinite passive grid."""
import math, curses, locale, random, zlib, json, os, sys, time, signal

SAVE = os.path.expanduser('~/.local/share/glyphfall/save.json')

W, H = 80, 40
RARITY = ['normal', 'magic', 'rare', 'legend', 'mythic', 'unique']
RCOL = {'normal': 1, 'magic': 7, 'rare': 4, 'legend': 6, 'mythic': 2, 'unique': 3}
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
         'head': ['Cracked Skull', 'Leather Cap', 'Iron Helm', 'Horned Visor', 'Ash Hood'],
         'hands': ['Wraps', 'Hide Gloves', 'Chain Mitts', 'Plate Gauntlets', 'Ash Gloves'],
         'legs': ['Tatters', 'Hide Leggings', 'Chain Greaves', 'Plate Cuisses', 'Ash Breeches'],
         'boots': ['Rag Wraps', 'Hide Boots', 'Chain Sabatons', 'Plate Sabatons', 'Ash Sandals'],
         'sash': ['Frayed Cord', 'Hide Belt', 'Chain Girdle', 'Plate Girdle', 'Ash Sash'],
         'offhand': ['Buckler', 'Bone Shield', 'Kite Shield', 'Tower Shield', 'Orb', 'Grimoire', 'Skull Lantern', 'Rune Prism'],
         'charm': ['Fang', 'Rune Stone', 'Eye Idol', 'Ember Shard', 'Bone Ring']}
WEAPON_2H = ['Greataxe', 'Warhammer', 'Greatsword', 'Bone Staff', 'Halberd']
OFFHAND_FOCUS = {'Orb', 'Grimoire', 'Skull Lantern', 'Rune Prism'}
PRE = ['Sturdy', 'Fierce', 'Gloomy', 'Wicked', 'Feral', 'Hexed', 'Arcane', 'Savage']
RARE_A = ['Doom', 'Gore', 'Dread', 'Soul', 'Void', 'Rot', 'Storm', 'Ash']
RARE_B = ['Bite', 'Coil', 'Brand', 'Edge', 'Veil', 'Grip', 'Song', 'Maw']

# ---- enemies: name, glyph, hp, dmg, xp, min depth, flags
ENEMIES = [('Rat', 'r', 8, 3, 4, 1, ''), ('Skeleton', 's', 14, 5, 7, 1, ''), ('Imp', 'i', 10, 4, 8, 2, 'ranged'),
           ('Ghoul', 'g', 26, 7, 12, 3, ''), ('Wraith', 'W', 18, 8, 16, 4, 'fast'), ('Cultist', 'c', 22, 6, 14, 5, 'ranged'),
           ('Golem', 'G', 60, 11, 30, 7, '')]


# ---- build-defining powers. Legendary = rank 1, Mythic = same power at rank 2 (numbers x2) on stronger gear.
LEGEND_POWERS = ['cinder_heart', 'storm_mantle', 'frost_tyrant', 'plague_doctor', 'echo_ring', 'whirl_boots', 'overflow_stone',
                 'last_stand', 'prime_charm', 'blood_chalice', 'glass_idol']
POWER_TEXT = {
    'cinder_heart': ('Cinder Heart', lambda r: f'Fire skills explode on kill for {30 * r}% of the killing blow'),
    'storm_mantle': ('Storm Mantle', lambda r: f'Chain skills arc {2 * r} more times'),
    'frost_tyrant': ('Frost Tyrant', lambda r: f'Cold skills slow {2 + r} turns; slowed enemies take +{25 * r}% damage'),
    'plague_doctor': ('Plague Doctor', lambda r: f'Poison skills last {2 * r} longer and spread when the victim dies'),
    'echo_ring': ('Echo Ring', lambda r: f'All skills have +{15 * r}% chance to cast twice'),
    'whirl_boots': ('Whirling Treads', lambda r: f'Melee skills reach {r} tile{"s" if r > 1 else ""} further'),
    'overflow_stone': ('Overflow Stone', lambda r: f'+{40 * r}% skill damage while mana is above 90%'),
    'last_stand': ('Last Stand', lambda r: f'Below 35% life: +{60 * r}% skill damage, +{10 * r}% leech'),
    'prime_charm': ('Prime Charm', lambda r: f'Skill in slot 1: +{40 * r}% damage, {2 * r} mana cheaper'),
    'blood_chalice': ('Blood Chalice', lambda r: f'Each kill restores {2 * r} mana'),
    'glass_idol': ('Glass Idol', lambda r: f'+{40 * r}% more damage, {-25 * r}% max life'),
    # unique-only
    'skill_fusion': ('Prismatic Fusion', lambda r: 'Each skill also counts as having the tags of the skill in the next slot'),
    'double_slot': ('Twinned Casting', lambda r: 'Casting slot 1 has 40% to also cast slot 2 for free'),
    'mana_to_life': ('Soulbinding', lambda r: 'Missing mana is paid with life, 2 life per mana'),
    'kill_streak': ('Reaping', lambda r: 'Each kill within 6 turns: +10% skill damage, up to 10 stacks'),
    'find_idol': ('Gambler', lambda r: '+100% item find'),
    'deathless': ('Rebirth', lambda r: 'Once per level, lethal damage heals you to 50% and burns everything near'),
    'inferno': ('Wyrmfire', lambda r: 'Fire skills have no cooldown and always burn for 60%'),
}
UNIQUES = [
    dict(name='Prismatic Idol', slot='charm', power='skill_fusion', base={'crit': 6, 'mana': 15}),
    dict(name='Twinned Blade', slot='weapon', hands='2h', power='double_slot', base={'weapon': 6, 'dmg_pct': 12}),
    dict(name='Soulbinder Robe', slot='armor', power='mana_to_life', base={'armor': 8, 'mana': 25, 'leech': 3}),
    dict(name="Reaper's Tally", slot='charm', power='kill_streak', base={'crit': 4, 'weapon': 2}),
    dict(name="Gambler's Fang", slot='charm', power='find_idol', base={'dmg_pct': 8}),
    dict(name='Phoenix Coil', slot='armor', power='deathless', base={'hp': 30, 'armor': 10, 'regen': 2}),
    dict(name='Wyrmfang', slot='weapon', hands='2h', power='inferno', base={'weapon': 5, 'fire_pct': 35}),
]

# ---- skill-specific mastery nodes: {skill: {'notable': [(name, stats)], 'key': [(name, stats)]}}
SPECIALS = {
    'whirlwind': dict(notable=[('Reaping Heal', {'ww_heal': 3}), ('Open Wounds', {'ww_bleed': 35})], key=[('Cyclone', {'ww_twice': 1, 'sk_cost': -4})]),
    'fireball': dict(notable=[('Wildfire', {'fb_explode': 50}), ('Twin Fire', {'fb_twin': 1})], key=[('Meteor', {'fb_splash': 1, 'sk_dmg': 60, 'sk_cost': -5})]),
    'frost_nova': dict(notable=[('Shatter', {'shatter': 60}), ('Cold Snap', {'fn_mana': 2})], key=[('Absolute Zero', {'fn_pulse': 1, 'sk_cost': -3})]),
    'blink': dict(notable=[('Phantom Trail', {'bl_trail': 60}), ('Fleet Foot', {'bl_reset': 1})], key=[('Rift Walker', {'bl_range': 4, 'sk_cost': -3})]),
    'chain_lightning': dict(notable=[('Ball Lightning', {'cl_ramp': 1}), ('Static Charge', {'cl_slow': 2})], key=[('Storm Rod', {'cl_all': 1, 'sk_cost': -4})]),
    'bone_spear': dict(notable=[('Marrow Rend', {'bs_exec': 25}), ('Barrage', {'bs_fan': 2})], key=[('Skewer', {'bs_ramp': 25, 'sk_cost': -3})]),
    'poison_cloud': dict(notable=[('Plague', {'pc_spread': 1}), ('Lingering Haze', {'pc_long': 3})], key=[('Miasma', {'sk_radius': 2, 'sk_dmg': 40, 'sk_cost': -5})]),
    'soul_siphon': dict(notable=[('Soul Harvest', {'ss_mana': 3}), ('Twin Siphon', {'ss_twin': 1})], key=[('Lich Touch', {'ss_heal': 50, 'sk_cost': -2})]),
    'blood_pact': dict(notable=[('Thick Blood', {'bp_cheap': 1}), ('Lingering Oath', {'bp_long': 4})], key=[('Crimson Tide', {'bp_power': 50, 'sk_cost': -2})]),
}
ELABEL = {'more_dmg': '+{}% More Damage', 'hp_mult': '{:+}% Max Life', 'sk_dmg': '{:+}% skill damage', 'sk_cost': '{:+} mana discount',
          'sk_cd': '-{} cooldown', 'sk_crit': '+{}% skill crit', 'sk_leech': '+{}% skill leech', 'sk_echo': '{}% chance to cast twice',
          'sk_burn': 'hits burn for {}% over 3 turns', 'sk_slow': 'hits slow for {} turns', 'sk_range': '+{} range',
          'sk_radius': '+{} radius', 'sk_chain': '+{} chain/targets', 'ww_heal': 'heal {}% max life per enemy hit',
          'ww_bleed': 'bleed for {}% over 4 turns', 'ww_twice': 'hits every enemy twice', 'fb_explode': 'kills explode for {}% damage',
          'fb_twin': 'also hits a second target (70%)', 'fb_splash': 'splash around the target (60%)', 'shatter': 'slowed enemies take +{}% damage',
          'fn_mana': '+{} mana per enemy hit', 'fn_pulse': 'second pulse, wider (60%)', 'bl_trail': 'damages enemies along the path ({}%)',
          'bl_reset': 'kills reset the cooldown', 'bl_range': '+{} blink distance', 'cl_ramp': 'each arc hits 20% harder, not softer',
          'cl_slow': 'arcs slow for {} turns', 'cl_all': 'arcs through every enemy nearby', 'bs_exec': 'executes enemies below {}% life',
          'bs_fan': '+{} extra spears at other targets', 'bs_ramp': '+{}% damage per enemy pierced', 'pc_spread': 'poison spreads when victims die',
          'pc_long': 'poison lasts {} longer', 'spread': 'poison spreads when victims die', 'dur': 'poison lasts {} longer',
          'ss_mana': '+{} mana per cast', 'ss_twin': 'also drains a second target', 'ss_heal': '+{}% drain healing',
          'bp_cheap': 'costs half the life', 'bp_long': 'lasts {} more turns', 'bp_power': 'buff +{}% stronger'}


# ---- runes: socketed into gear. 'stat' runes add stats, 'tag' runes boost every skill that carries the tag.
# pct mode scales x1.5 per tier (keeps pace with depth tiers), int mode adds base per 2 tiers. 3 runes of a tier fuse into 1 of the next.
RUNES = {
    'ember': dict(name='Ember', kind='stat', stat='fire_pct', base=12, mode='pct'),
    'rime': dict(name='Rime', kind='stat', stat='cold_pct', base=12, mode='pct'),
    'volt': dict(name='Volt', kind='stat', stat='lightning_pct', base=12, mode='pct'),
    'bone': dict(name='Bone', kind='stat', stat='phys_pct', base=12, mode='pct'),
    'venom': dict(name='Venom', kind='stat', stat='poison_pct', base=12, mode='pct'),
    'soul': dict(name='Soul', kind='stat', stat='necro_pct', base=12, mode='pct'),
    'vigor': dict(name='Vigor', kind='stat', stat='hp', base=14, mode='pct'),
    'mind': dict(name='Mind', kind='stat', stat='mana', base=10, mode='pct'),
    'edge': dict(name='Edge', kind='stat', stat='weapon', base=3, mode='pct'),
    'ward': dict(name='Ward', kind='stat', stat='armor', base=8, mode='pct'),
    'fang': dict(name='Fang', kind='stat', stat='leech', base=2, mode='int'),
    'eye': dict(name='Eye', kind='stat', stat='crit', base=3, mode='int'),
    'fortune': dict(name='Fortune', kind='stat', stat='find', base=8, mode='pct'),
    'might': dict(name='Might', kind='stat', stat='dmg_pct', base=6, mode='pct'),
    'arc': dict(name='Arc', kind='tag', tag='chain', stat='sk_chain', base=1, mode='int'),
    'reach': dict(name='Reach', kind='tag', tag='aoe', stat='sk_radius', base=1, mode='int'),
    'distance': dict(name='Distance', kind='tag', tag='projectile', stat='sk_range', base=2, mode='int'),
    'cinder': dict(name='Cinder', kind='tag', tag='fire', stat='sk_burn', base=25, mode='pct'),
    'chill': dict(name='Chill', kind='tag', tag='cold', stat='sk_slow', base=1, mode='int'),
    'blight': dict(name='Blight', kind='tag', tag='poison', stat='dur', base=2, mode='int'),
    'brawn': dict(name='Brawn', kind='tag', tag='melee', stat='sk_dmg', base=15, mode='pct'),
    'swift': dict(name='Swift', kind='tag', tag='all', stat='sk_cd', base=1, mode='int'),
    'echo': dict(name='Echo', kind='tag', tag='all', stat='sk_echo', base=6, mode='pct'),
}
SOCKET_MAX = {'normal': 1, 'magic': 2, 'rare': 3, 'legend': 3, 'mythic': 4, 'unique': 2}


def rune_split(rk):
    t, n = rk.split(':')
    return t, int(n)


def rune_val(rk):
    t, n = rune_split(rk)
    d = RUNES[t]
    return max(1, int(d['base'] * 1.5 ** (n - 1))) if d['mode'] == 'pct' else d['base'] * (1 + (n - 1) // 2)


def rune_name(rk):
    t, n = rune_split(rk)
    return f'{RUNES[t]["name"]} T{n}'


# ---- enemy affixes (champions get 1-3 by depth) and boss kinds with telegraphed attacks
EAFF = {'fast': 'acts twice per turn', 'shielded': 'absorbs the first 40% of its life in damage', 'explosive': 'blasts adjacent tiles when it dies',
        'mender': 'heals nearby allies', 'thorned': 'reflects some damage when you are close', 'vampiric': 'heals when it hits you',
        'draining': 'its hits drain your mana', 'summoner': 'calls minions', 'teleporter': 'blinks next to you'}
BOSS_KINDS = [dict(name='Warden', gl='Ω', tele='slam', info='slams the ground around itself'),
              dict(name='Pyre Lord', gl='Ψ', tele='volley', info='rains fire where you stand'),
              dict(name='Void Seer', gl='Φ', tele='nova', info='sends a ring of void; stay close or run far'),
              dict(name='Bone Queen', gl='Σ', tele='cross', info='fires bone lines along her row and column')]


SLOTNAME = {'weapon': 'Weapon', 'offhand': 'Off-hand', 'armor': 'Body', 'head': 'Head', 'hands': 'Hands', 'legs': 'Legs',
            'boots': 'Boots', 'sash': 'Sash', 'charm': 'Amulet'}
ARMOR_SLOTS = ('armor', 'head', 'hands', 'legs', 'boots', 'sash')  # 'armor' = body (kept for old saves)
ARMOR_BASE = {'armor': 3, 'head': 2, 'hands': 1, 'legs': 2, 'boots': 1, 'sash': 1}
TAB_GROUP = {'weapon': ('weapon', 'offhand'), 'armor': ARMOR_SLOTS}
CONS = {'hp': ('Health Potion', 'Heal 40% of max life'), 'mp': ('Mana Potion', 'Restore 60% of max mana'),
        'rejuv': ('Rejuvenation', 'Heal and restore 50% of both'), 'map': ('Map Scroll', 'Reveal the whole level')}
SALVAGE = {'normal': 2, 'magic': 5, 'rare': 14, 'legend': 60, 'mythic': 200, 'unique': 120}
ESS = {'legend': 3, 'mythic': 12, 'unique': 8}
REROLL_SCRAP = {'magic': 10, 'rare': 30, 'legend': 120, 'mythic': 300, 'unique': 200}
REROLL_ESS = {'legend': 5, 'mythic': 15, 'unique': 10}


def tuple_aff(it):
    if 'aff' in it:
        it['aff'] = [tuple(a) for a in it['aff']]
    return it


# ---- passive tree: 11 class paths around the origin. Gates of opposite classes close each other, every class forks
# into 3 mutually exclusive arms, and bridge nodes join neighbouring classes. Nothing is random: the shape is the build.
class Tree:
    def __init__(self):
        self.n, self.edges = {}, set()

    def add(self, pos, name, kind, stats, cls=None):
        pos = (int(round(pos[0])), int(round(pos[1])))
        while pos in self.n:
            pos = (pos[0] + 1, pos[1])
        self.n[pos] = dict(id=pos, name=name, kind=kind, stats=stats, adj=set(), excl=set(), cls=cls)
        return pos

    def link(self, a, b):
        self.n[a]['adj'].add(b)
        self.n[b]['adj'].add(a)
        self.edges.add((min(a, b), max(a, b)))

    def exclude(self, *ids):
        for a in ids:
            self.n[a]['excl'] |= set(ids) - {a}


def tsum(*ds):
    out = {}
    for d in ds:
        for k, v in d.items():
            out[k] = out.get(k, 0) + v
    return out


def half(d):
    return {k: (v // 2 if v > 0 else -((-v) // 2)) or (1 if v > 0 else -1) for k, v in d.items()}


# name, signature stat, gate, trunk minor, trunk notable, 3 arms: (arm, minor, notable, key name, key stats)
CLASSES = [
    ('Warrior', {'armor': 6}, {'armor': 8, 'hp': 10}, {'armor': 5}, {'hp': 25, 'armor': 8}, [
        ('Bulwark', {'armor': 8}, {'armor': 16, 'hp': 18}, 'Unbroken', {'armor': 50, 'hp_mult': 15, 'dmg_pct': -15}),
        ('Duelist', {'weapon': 1, 'crit': 2}, {'weapon': 2, 'crit': 5}, 'Blademaster', {'phys_pct': 45, 'melee_pct': 25, 'armor': -20}),
        ('Vanguard', {'melee_pct': 9}, {'melee_pct': 18, 'leech': 2}, 'Warlord', {'more_dmg': 25, 'hp': 30})]),
    ('Barbarian', {'hp': 10}, {'hp': 14, 'leech': 1}, {'phys_pct': 8}, {'melee_pct': 16, 'hp': 20}, [
        ('Berserker', {'dmg_pct': 4}, {'dmg_pct': 8, 'crit': 4}, 'Bloodrage', {'more_dmg': 55, 'hp_mult': -35}),
        ('Reaver', {'leech': 1}, {'leech': 3, 'phys_pct': 12}, 'Gorehound', {'leech': 8, 'hp_mult': -15}),
        ('Brute', {'hp': 12}, {'hp': 26, 'weapon': 1}, 'Titan', {'hp_mult': 30, 'weapon': 2, 'crit': -5})]),
    ('Paladin', {'regen': 1}, {'armor': 6, 'regen': 1}, {'hp': 10}, {'armor': 10, 'regen': 1}, [
        ('Aegis', {'armor': 7}, {'armor': 14, 'regen': 1}, 'Sanctuary', {'regen': 4, 'armor': 25, 'dmg_pct': -20}),
        ('Crusader', {'melee_pct': 8}, {'melee_pct': 14, 'aoe_pct': 12}, 'Divine Wrath', {'aoe_pct': 40, 'phys_pct': 25, 'mana': -20}),
        ('Templar', {'hp': 12}, {'hp': 22, 'leech': 2}, 'Martyr', {'hp': 60, 'leech': 4, 'armor': -15})]),
    ('Cleric', {'mregen': 1}, {'mana': 10, 'regen': 1}, {'mana': 8}, {'hp': 18, 'mregen': 1}, [
        ('Healer', {'regen': 1}, {'regen': 2, 'hp': 16}, 'Lifebloom', {'regen': 5, 'mregen': 2, 'dmg_pct': -20}),
        ('Priest', {'mana': 10}, {'mana': 20, 'mregen': 2}, 'Wellspring', {'mana': 60, 'mregen': 4, 'hp_mult': -15}),
        ('Smiter', {'dmg_pct': 4}, {'dmg_pct': 8, 'crit': 4}, 'Judgement', {'crit': 22, 'dmg_pct': 18, 'regen': -1})]),
    ('Druid', {'poison_pct': 8}, {'hp': 10, 'regen': 1}, {'poison_pct': 8}, {'regen': 1, 'find': 8}, [
        ('Grove', {'poison_pct': 9}, {'poison_pct': 18, 'regen': 1}, 'Blight Mother', {'poison_pct': 60, 'aoe_pct': 20, 'armor': -15}),
        ('Tempest', {'lightning_pct': 9}, {'lightning_pct': 18, 'chain_pct': 10}, 'Stormcaller', {'lightning_pct': 50, 'chain_pct': 30, 'hp_mult': -15}),
        ('Rimewood', {'cold_pct': 9}, {'cold_pct': 18, 'hp': 16}, 'Winter Spirit', {'cold_pct': 50, 'armor': 30, 'mana': -20})]),
    ('Scout', {'crit': 3}, {'crit': 3, 'find': 6}, {'projectile_pct': 8}, {'crit': 5, 'find': 10}, [
        ('Archer', {'projectile_pct': 9}, {'projectile_pct': 18, 'crit': 4}, 'Deadeye', {'crit': 28, 'projectile_pct': 30, 'hp_mult': -15}),
        ('Trapper', {'poison_pct': 8}, {'poison_pct': 14, 'find': 10}, 'Venom Lord', {'poison_pct': 50, 'dmg_pct': 10, 'armor': -10}),
        ('Pathfinder', {'find': 8}, {'find': 16, 'movement_pct': 12}, 'Treasure Sense', {'find': 60, 'dmg_pct': -10})]),
    ('Necromancer', {'necro_pct': 8}, {'necro_pct': 8, 'mana': 8}, {'necro_pct': 8}, {'leech': 2, 'mana': 12}, [
        ('Bonecaller', {'necro_pct': 9}, {'necro_pct': 18, 'projectile_pct': 8}, 'Ossuary', {'necro_pct': 60, 'projectile_pct': 25, 'armor': -15}),
        ('Plaguebearer', {'poison_pct': 9}, {'poison_pct': 16, 'necro_pct': 10}, 'Pestilence', {'poison_pct': 45, 'necro_pct': 30, 'regen': -1}),
        ('Soulreaper', {'leech': 1}, {'leech': 3, 'mana': 14}, 'Lich', {'leech': 8, 'mana': 40, 'hp_mult': -25})]),
    ('Warlock', {'necro_pct': 6, 'fire_pct': 6}, {'fire_pct': 8, 'leech': 1}, {'fire_pct': 8}, {'necro_pct': 14, 'hp': 14}, [
        ('Hexer', {'necro_pct': 9}, {'necro_pct': 16, 'crit': 4}, 'Curse Master', {'necro_pct': 45, 'crit': 20, 'armor': -15}),
        ('Infernalist', {'fire_pct': 9}, {'fire_pct': 18, 'aoe_pct': 10}, 'Hellfire', {'fire_pct': 60, 'aoe_pct': 25, 'hp_mult': -20}),
        ('Pactbound', {'leech': 1}, {'leech': 3, 'hp': 16}, 'Soul Debt', {'more_dmg': 35, 'hp_mult': -30, 'leech': 3})]),
    ('Sorcerer', {'lightning_pct': 8}, {'lightning_pct': 10, 'mana': 8}, {'lightning_pct': 8}, {'chain_pct': 14, 'crit': 4}, [
        ('Stormcaller', {'lightning_pct': 9}, {'lightning_pct': 18, 'chain_pct': 12}, 'Living Storm', {'lightning_pct': 60, 'chain_pct': 35, 'armor': -15}),
        ('Arcanist', {'crit': 3}, {'crit': 6, 'mana': 14}, 'Overchannel', {'crit': 25, 'dmg_pct': 15, 'mana': -20}),
        ('Wildmage', {'dmg_pct': 3}, {'fire_pct': 12, 'cold_pct': 12, 'lightning_pct': 12}, 'Chaos Flux', {'fire_pct': 40, 'cold_pct': 40, 'lightning_pct': 40, 'phys_pct': -40})]),
    ('Wizard', {'cold_pct': 8}, {'cold_pct': 10, 'mana': 8}, {'aoe_pct': 8}, {'mana': 16, 'mregen': 1}, [
        ('Frostweaver', {'cold_pct': 9}, {'cold_pct': 18, 'aoe_pct': 10}, 'Glacier', {'cold_pct': 60, 'aoe_pct': 30, 'movement_pct': -20}),
        ('Scholar', {'mana': 10}, {'mana': 22, 'mregen': 2}, 'Archmind', {'mana': 70, 'mregen': 3, 'hp_mult': -15}),
        ('Evoker', {'aoe_pct': 9}, {'aoe_pct': 18, 'dmg_pct': 5}, 'Cataclysm', {'aoe_pct': 55, 'more_dmg': 15, 'crit': -5})]),
    ('Mage', {'fire_pct': 8}, {'fire_pct': 8, 'dmg_pct': 3}, {'projectile_pct': 8}, {'fire_pct': 14, 'mana': 10}, [
        ('Pyromancer', {'fire_pct': 9}, {'fire_pct': 18, 'projectile_pct': 10}, 'Phoenix Fire', {'fire_pct': 65, 'projectile_pct': 25, 'armor': -15}),
        ('Battlemage', {'armor': 6}, {'armor': 12, 'dmg_pct': 6}, 'Spellblade', {'melee_pct': 40, 'fire_pct': 25, 'mana': -15}),
        ('Channeler', {'mana': 8}, {'mana': 16, 'dmg_pct': 6}, 'Focus', {'dmg_pct': 30, 'mana': 30, 'hp_mult': -10})]),
]
NCLS = len(CLASSES)
CLS_COL = [2, 2, 4, 6, 3, 3, 5, 5, 6, 7, 7, 1]


def build_passive():
    t = Tree()
    org = t.add((0, 0), 'Origin', 'origin', {})
    pos = lambda k, along, across: (
        math.cos(2 * math.pi * k / NCLS - math.pi / 2) * (4.2 + along * 2.0) - math.sin(2 * math.pi * k / NCLS - math.pi / 2) * across * 1.35,
        math.sin(2 * math.pi * k / NCLS - math.pi / 2) * (4.2 + along * 2.0) + math.cos(2 * math.pi * k / NCLS - math.pi / 2) * across * 1.35)
    gates, outer = [], []
    for k, (cn, sig, gate, tm, tn, arms) in enumerate(CLASSES):
        g = t.add(pos(k, 0, 0), f'Path of the {cn}', 'gate', gate, k)
        t1 = t.add(pos(k, 1, 0), f'{cn} Training', 'minor', tm, k)
        t2 = t.add(pos(k, 2, 0), f'{cn} Mastery', 'notable', tn, k)
        t.link(org, g), t.link(g, t1), t.link(t1, t2)
        gates.append(g)
        firsts, keys, outs = [], [], []
        for i, (an, mn, nt, kn, ks) in enumerate(arms):
            a1 = t.add(pos(k, 3.2, (i - 1) * 1.7), f'{an} I', 'minor', mn, k)
            a2 = t.add(pos(k, 4.6, (i - 1) * 1.7), f'{an} II', 'notable', nt, k)
            ky = t.add(pos(k, 6.2, (i - 1) * 1.7), kn, 'key', ks, k)
            t.link(t2, a1), t.link(a1, a2), t.link(a2, ky)
            firsts.append(a1), keys.append(ky), outs.append(a2)
        t.exclude(*firsts)
        t.exclude(*keys)
        outer.append(outs)
    for k in range(NCLS):
        n = (k + 1) % NCLS
        # opposite classes close each other: a build commits to a side of the circle
        for o in ((k + NCLS // 2) % NCLS, (k + NCLS // 2 + 1) % NCLS):
            t.n[gates[k]]['excl'].add(gates[o])
            t.n[gates[o]]['excl'].add(gates[k])
        ca, cb = CLASSES[k], CLASSES[n]
        # ring node between neighbouring gates, bridge node between their outer arms
        gx = [(t.n[gates[k]]['id'][i] + t.n[gates[n]]['id'][i]) / 2 for i in (0, 1)]
        rg = t.add(gx, f'{ca[0]}-{cb[0]} Kinship', 'minor', tsum(half(ca[1]), half(cb[1])), None)
        t.link(gates[k], rg), t.link(gates[n], rg)
        a, b = outer[k][2], outer[n][0]
        mx = [(t.n[a]['id'][i] + t.n[b]['id'][i]) / 2 for i in (0, 1)]
        br = t.add(mx, f'{ca[0]}-{cb[0]} Bond', 'notable', tsum(half(ca[5][2][2]), half(cb[5][0][2])), None)
        t.link(a, br), t.link(b, br)
    return t


# ---- skill mastery trees: three aspects (Power, Control, Technique), each forks into two exclusive options that end in a
# capstone. Only one capstone per skill: you decide what the skill becomes.
def build_skill(key):
    sk, sp = SKILLS[key], SPECIALS.get(key)
    tags = sk['tags']
    t = Tree()
    org = t.add((0, 0), sk['name'], 'origin', {})
    if 'aoe' in tags:
        c1 = ('Wide Reach', {'sk_radius': 1})
    elif 'chain' in tags:
        c1 = ('Long Arc', {'sk_chain': 1})
    elif 'rng' in sk or 'projectile' in tags:
        c1 = ('Far Sight', {'sk_range': 2})
    else:
        c1 = ('Crippling', {'sk_slow': 2})
    cap_key = sp['key'][0] if sp else ('Overdrive', {'sk_dmg': 70, 'sk_cost': -4})
    n0, n1 = (sp['notable'] + [('Surge', {'sk_dmg': 25}), ('Vigor', {'sk_leech': 8})])[:2] if sp else (('Surge', {'sk_dmg': 25}), ('Vigor', {'sk_leech': 8}))
    asp = [
        ('Power', [('Might', {'sk_dmg': 10}), ('Keen Edge', {'sk_dmg': 15, 'sk_crit': 6})],
         [('Overload', {'sk_dmg': 40, 'sk_cost': -2}), cap_key],
         [('Precision', {'sk_crit': 18}), ('Executioner', {'sk_crit': 40, 'sk_dmg': -12})]),
        ('Control', [(c1[0], c1[1]), ('Searing', {'sk_burn': 30, 'sk_slow': 1})],
         [('Efficiency', {'sk_cost': 3, 'sk_dmg': -8}), ('Frugal Mastery', {'sk_cost': 7, 'sk_dmg': -20})],
         [('Echoes', {'sk_echo': 20}), ('Twin Cast', {'sk_echo': 45, 'sk_dmg': -18})]),
        ('Technique', [('Vitality', {'sk_leech': 4}), ('Focus', {'sk_dmg': 12, 'sk_leech': 3})],
         [n0, ('Sanguine', {'sk_leech': 18, 'sk_dmg': 15})],
         [n1, ('Immolation', {'sk_burn': 70, 'sk_dmg': 12})]),
    ]
    caps, ends = [], []
    for a, (an, mid, fa, fb) in enumerate(asp):
        ang = a * 2 * math.pi / 3 - math.pi / 2
        u, v = (math.cos(ang), math.sin(ang)), (-math.sin(ang), math.cos(ang))
        at = lambda along, across: (u[0] * along * 2.1 + v[0] * across * 1.8, u[1] * along * 2.1 + v[1] * across * 1.8)
        p1 = t.add(at(1, 0), f'{an}: {mid[0][0]}', 'minor', mid[0][1], a)
        p2 = t.add(at(2, 0), f'{an}: {mid[1][0]}', 'notable', mid[1][1], a)
        t.link(org, p1), t.link(p1, p2)
        forks = []
        for side, (fk, (cn, cs)) in enumerate(zip((fa[0], fb[0]), (fa[1], fb[1]))):
            sgn = -1 if side == 0 else 1
            f = t.add(at(3, sgn * 1.3), fk[0], 'notable', fk[1], a)
            c = t.add(at(4.3, sgn * 1.5), cn, 'key', cs, a)
            t.link(p2, f), t.link(f, c)
            forks.append(f), caps.append(c)
        t.exclude(*forks)
        ends.append(forks)
    t.exclude(*caps)
    for a in range(3):
        b = (a + 1) % 3
        pa, pb = ends[a][1], ends[b][0]
        mx = [(t.n[pa]['id'][i] + t.n[pb]['id'][i]) / 2 for i in (0, 1)]
        br = t.add(mx, f'{asp[a][0]}/{asp[b][0]} Link', 'minor', {'sk_dmg': 8, 'sk_leech': 2}, None)
        t.link(pa, br), t.link(pb, br)
    return t


_TREES = {}


def tree_of(key=None):
    if key not in _TREES:
        _TREES[key] = build_skill(key) if key else build_passive()
    return _TREES[key]


# ---- world: a grid of forest zones joined by gaps in the trees. Camps are the crossroads, dungeons hide in dead-end wilds.
ZW, ZH = 9, 7
HOME = (1, 3)
DIRS = {'N': (0, -1), 'S': (0, 1), 'W': (-1, 0), 'E': (1, 0)}
OPP = {'N': 'S', 'S': 'N', 'W': 'E', 'E': 'W'}
EXIT_AT = {'N': (W // 2, 0), 'S': (W // 2, H - 1), 'W': (0, H // 2), 'E': (W - 1, H // 2)}
EXIT_IN = {'N': (W // 2, 1), 'S': (W // 2, H - 2), 'W': (1, H // 2), 'E': (W - 2, H // 2)}
ZPRE = ['Mossy', 'Ashen', 'Thorn', 'Gloomy', 'Silent', 'Wild', 'Ember', 'Frost', 'Pale', 'Rotting', 'Sunken', 'Twisted', 'Howling']
ZNOUN = ['Glade', 'Thicket', 'Hollow', 'Clearing', 'Woods', 'Grove', 'Fen', 'Ridge', 'Dell', 'Copse', 'Meadow']
CAMPNAME = ['Hearthrest', 'Ashfire Camp', 'Lantern Rest', 'Oakshield Camp', "Wayfarer's Rest", 'Fernwatch', 'Stonering Camp', 'Embergate']
DUNGEON_KIND = ['Barrow', 'Crypt', 'Warren', 'Catacombs', 'Sunken Mine', 'Bone Vault', 'Deep Hollow']
DIRNAME = {'N': 'north', 'S': 'south', 'W': 'west', 'E': 'east'}
NPC_KINDS = ['Quartermaster', 'Ranger', 'Elder']


def build_world(seed):
    r = random.Random(f'{seed}:world')
    cells = [(x, y) for x in range(ZW) for y in range(ZH)]
    links = {c: set() for c in cells}
    nb = lambda c: [(d, (c[0] + dx, c[1] + dy)) for d, (dx, dy) in DIRS.items() if (c[0] + dx, c[1] + dy) in links]
    # randomized Prim: bushy tree, so there are real junctions
    seen, front = {HOME}, [(HOME, d, n) for d, n in nb(HOME)]
    while front:
        a, d, b = front.pop(r.randrange(len(front)))
        if b in seen:
            continue
        links[a].add(d), links[b].add(OPP[d])
        seen.add(b)
        front += [(b, d2, n2) for d2, n2 in nb(b) if n2 not in seen]
    for c in cells:  # shortcuts: not every path is a dead end
        for d, n in nb(c):
            if d not in links[c] and r.random() < 0.2:
                links[c].add(d), links[n].add(OPP[d])
    while len(links[HOME]) < 2:
        d, n = r.choice([(d, n) for d, n in nb(HOME) if d not in links[HOME]])
        links[HOME].add(d), links[n].add(OPP[d])
    dist, todo = {HOME: 0}, [HOME]
    for c in todo:
        for d in links[c]:
            n = (c[0] + DIRS[d][0], c[1] + DIRS[d][1])
            if n not in dist:
                dist[n] = dist[c] + 1
                todo.append(n)
    camps = [HOME]
    for gap in (5, 4, 3):
        for c in r.sample(cells, len(cells)):
            if len(links[c]) >= 3 and c not in camps and all(abs(c[0] - o[0]) + abs(c[1] - o[1]) >= gap for o in camps):
                camps.append(c)
    zones, names = {}, set()
    for c in cells:
        lvl = 1 + int(dist[c] * 2.0)
        if c in camps:
            nm = r.choice([n for n in CAMPNAME if n not in names] or CAMPNAME)
            kind = 'camp'
        else:
            nm = f'{r.choice(ZPRE)} {r.choice(ZNOUN)}'
            while nm in names:
                nm = f'{r.choice(ZPRE)} {r.choice(ZNOUN)}'
            kind = 'wild'
        names.add(nm)
        zones[c] = dict(pos=c, kind=kind, level=lvl, name=nm, links=sorted(links[c]), dungeon=None)
    wild = [c for c in cells if zones[c]['kind'] == 'wild' and zones[c]['level'] >= 2]
    ends = [c for c in wild if len(links[c]) == 1]
    pick = [c for c in ends if r.random() < 0.75] + [c for c in wild if len(links[c]) == 2 and r.random() < 0.1]
    early = [c for c in ends if zones[c]['level'] <= 7]
    if early and not any(zones[c]['level'] <= 7 for c in pick):
        pick.append(r.choice(early))
    for c in pick:
        z = zones[c]
        z['dungeon'] = dict(name=f'{r.choice(DUNGEON_KIND)} of {r.choice(RARE_A)}', floors=min(9, 3 + z["level"] // 5))
    return zones


class Game:
    streak = streak_t = pact_extra = last_dmg = fcount = fscrap = 0
    flag_reset = _boom = phoenix = False
    fx = None  # the native front end sets this to a list and drains it each frame
    extra_tags = frozenset()
    ms = {}
    cur = None

    def __init__(self, seed=None):
        self.seed = seed or random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        self.depth = 0
        self.lvl, self.xp, self.points = 1, 0, 0
        self.alloc = {(0, 0)}
        self.equip = {k: None for k in ('weapon', 'offhand', 'armor', 'head', 'hands', 'legs', 'boots', 'sash', 'charm')}
        self.pack = []
        self.known = list(START_SKILLS)
        self.slots = list(START_SKILLS)
        self.cd, self.buffs, self.log = {}, {}, []
        self.cons, self.keys, self.res = {'hp': 2, 'mp': 1}, 0, {'scrap': 0, 'essence': 0}
        self.mastery = {}
        self.zones, self.visited, self.camp, self.npcs, self.floor = build_world(self.seed), set(), HOME, {}, 0
        self.chests, self.potion_cd = {}, 0
        self.filter = {'normal': 'salvage', 'magic': 'keep', 'rare': 'keep'}
        self.runes = {}
        self.ms, self.cur = {}, None
        self.face = (1, 0)
        self.turn = 0
        self.dead = False
        self.hp, self.mana = 60, 30
        self.enter(HOME, 0)
        self.hp, self.mana = self.st('hp'), self.st('mana')

    # ---- persistence (current level is regenerated from seed+depth on load)
    def save(self):
        d = dict(seed=self.seed, depth=self.depth, zpos=list(self.zpos), floor=self.floor, visited=sorted(self.visited),
                 camp=list(self.camp), pos=[self.px, self.py], lvl=self.lvl, xp=self.xp, points=self.points, alloc=sorted(self.alloc),
                 equip=self.equip, pack=self.pack, known=self.known, slots=self.slots, hp=self.hp, mana=self.mana, turn=self.turn,
                 best=getattr(self, 'best', self.depth), deaths=getattr(self, 'deaths', 0),
                 mastery={k: dict(m, alloc=sorted(m['alloc'])) for k, m in self.mastery.items()},
                 cons=self.cons, keys=self.keys, res=self.res, filter=self.filter, runes=self.runes)
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
        for k in SLOTNAME:
            g.equip.setdefault(k, None)
        for k, it in g.equip.items():
            if it:
                tuple_aff(it)
        g.cd, g.buffs, g.log = {}, {}, []
        g.mastery = {k: dict(m, alloc={tuple(p) for p in m['alloc']}) for k, m in d.get('mastery', {}).items()}
        g.ms, g.cur = {}, None
        g.cons, g.keys, g.res = d.get('cons', {'hp': 2, 'mp': 1}), d.get('keys', 0), d.get('res', {'scrap': 0, 'essence': 0})
        g.potion_cd, g.chests = 0, {}
        g.filter = d.get('filter', {'normal': 'salvage', 'magic': 'keep', 'rare': 'keep'})
        g.runes = d.get('runes', {})
        g.face, g.turn, g.dead = (1, 0), d['turn'], False
        g.best, g.deaths = d.get('best', d['depth']), d.get('deaths', 0)
        g.zones, g.npcs, g.fcount, g.fscrap = build_world(g.seed), {}, 0, 0
        g.visited = {tuple(v) for v in d.get('visited', [])}
        g.camp = tuple(d.get('camp', HOME))
        # saves from before the class trees / zone world: refund old nodes, restart at the home camp
        tp = tree_of()
        if any(p not in tp.n for p in g.alloc):
            g.points += len(g.alloc) - 1
            g.alloc = {(0, 0)}
        for k, m in g.mastery.items():
            if k in SKILLS and any(p not in tree_of(k).n for p in m['alloc']):
                m['points'] += len(m['alloc']) - 1
                m['alloc'] = {(0, 0)}
        zp = tuple(d['zpos']) if 'zpos' in d else HOME
        g.enter(zp, d.get('floor', 0))
        if 'pos' in d and g.g[d['pos'][1]][d['pos'][0]] not in '#<>DEF' and not g.enemy_at(*d['pos']):
            g.px, g.py = d['pos']
            g.vision()
        g.hp, g.mana = min(d['hp'], g.st('hp')), min(d['mana'], g.st('mana'))
        g.say('Welcome back.')
        return g

    def respawn(self):
        # death is a setback, not a wipe: lose a quarter of the xp bar and wake at the last camp, keep everything else
        self.deaths = getattr(self, 'deaths', 0) + 1
        self.xp = int(self.xp * 0.75)
        self.dead = False
        self.enter(self.camp, 0)
        self.hp, self.mana = self.st('hp'), self.st('mana')
        self.say('You wake at the last camp you rested in. Gear kept.')

    # ---- skill mastery: casting a skill trains it; its own grid improves only that skill
    def mas(self, key):
        return self.mastery.setdefault(key, dict(xp=0, lvl=0, points=0, alloc={(0, 0)}))

    def mstats(self, key):
        out = {}
        tr = tree_of(key)
        for p in self.mas(key)['alloc']:
            for k, v in tr.n[p]['stats'].items():
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

    # ---- stats
    def stats(self):
        s = {}
        def add(d):
            for k, v in d.items():
                s[k] = s.get(k, 0) + v
        for it in self.equip.values():
            if it:
                add(dict(it['aff']))
        tp = tree_of()
        for p in self.alloc:
            add(tp.n[p]['stats'])
        for it in self.equip.values():
            for rk in (it or {}).get('sockets', []):
                if rk and RUNES[rune_split(rk)[0]]['kind'] == 'stat':
                    add({RUNES[rune_split(rk)[0]]['stat']: rune_val(rk)})
        pw = self.powers()
        if 'glass_idol' in pw:
            add({'more_dmg': 40 * pw['glass_idol'], 'hp_mult': -25 * pw['glass_idol']})
        if 'find_idol' in pw:
            add({'find': 100})
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
    # ---- zones: wild forest clearings, ally camps, dungeons (floors) hidden inside wild zones
    def where(self):
        z = self.zone
        if self.floor:
            return f'{z["dungeon"]["name"].split(" of ")[0]} F{self.floor}/{z["dungeon"]["floors"]}  L{self.depth}'
        return f'{z["name"]}  L{self.depth}'

    def enter(self, zpos, floor=0, arrive=None):
        if self.fcount:
            self.say(f'Filter: {self.fcount} items cleared (+{self.fscrap} scrap)')
            self.fcount = self.fscrap = 0
        z = self.zones[zpos]
        dg = z['dungeon'] if floor else None
        if arrive in EXIT_IN and arrive not in z['links']:
            arrive = None
        camp, cave = z['kind'] == 'camp', bool(floor)
        self.zpos, self.floor, self.zone = zpos, floor, z
        self.depth = z['level'] + floor   # "depth" is the difficulty everything scales with
        self.phoenix = False
        self.best = max(getattr(self, 'best', 0), self.depth)
        self.visited.add(zpos)
        if camp:
            self.camp = zpos
        self.bk_i = (zpos[0] * 7 + zpos[1] * 3) % len(BOSS_KINDS)
        r = random.Random(f'{self.seed}:{zpos}:{floor}')
        g = [['#'] * W for _ in range(H)]
        rooms = []

        def carve(x, y, w, h):
            rx, ry = w / 2, h / 2
            mx, my = x + rx - 0.5, y + ry - 0.5
            ph = r.random() * 6.28
            for j in range(y, y + h):
                for i in range(x, x + w):
                    ang = math.atan2((j - my) / ry, (i - mx) / rx)
                    lim = 1.0 + 0.18 * math.sin(3 * ang + ph) + 0.1 * math.sin(5 * ang - ph)
                    if ((i - mx) / rx) ** 2 + ((j - my) / ry) ** 2 <= lim * lim * 0.9:
                        g[j][i] = '.'
            rooms.append((x, y, w, h))

        walked = set()   # every corridor cell, so the decorations below can never cut a corridor

        def dig(x1, y1, x2, y2, store):
            x, y = x1, y1
            while True:
                for dx, dy in ((0, 0), (1, 0), (0, 1)):
                    if 0 < x + dx < W - 1 and 0 < y + dy < H - 1:
                        if g[y + dy][x + dx] == '#':
                            store.add((x + dx, y + dy))
                        g[y + dy][x + dx] = '.'
                        walked.add((x + dx, y + dy))
                if (x, y) == (x2, y2):
                    break
                if r.random() < 0.5 and x != x2 or y == y2:
                    x += 1 if x2 > x else -1
                else:
                    y += 1 if y2 > y else -1

        if camp:
            carve(W // 2 - 13, H // 2 - 8, 26, 16)
        else:
            for _ in range(80):
                w, h = r.randint(8, 16), r.randint(6, 10)
                x, y = r.randint(1, W - w - 2), r.randint(1, H - h - 2)
                if any(x < a + c + 1 and a < x + w + 1 and y < b + d + 1 and b < y + h + 1 for a, b, c, d in rooms):
                    continue
                carve(x, y, w, h)
                if len(rooms) >= (12 if cave else 11):
                    break
        cen = [(x + w // 2, y + h // 2) for x, y, w, h in rooms]
        path, epath = set(), set()
        for (x1, y1), (x2, y2) in zip(cen, cen[1:]):
            dig(x1, y1, x2, y2, path)
        if not cave:
            for d in z['links']:
                ix, iy = EXIT_IN[d]
                tgt = min(cen, key=lambda c: abs(c[0] - ix) + abs(c[1] - iy))
                dig(ix, iy, tgt[0], tgt[1], epath)
                epath.add((ix, iy))
                g[EXIT_AT[d][1]][EXIT_AT[d][0]] = 'E'
            path |= epath
        for x, y in cen:
            g[y][x] = '.'
        keep = set(cen) | {(x + dx, y + dy) for x, y in cen for dx in (-1, 0, 1) for dy in (-1, 0, 1)} | epath | walked
        if cave:
            ter = [['W' if g[j][i] == '#' else 'd' for i in range(W)] for j in range(H)]
        else:
            ter = [[('T' if r.random() < 0.8 else 'r') if g[j][i] == '#' else ('p' if (i, j) in path or g[j][i] == 'E' else 'f' if r.random() < 0.06 else 'g')
                    for i in range(W)] for j in range(H)]
            for _ in range(0 if camp else len(rooms) * 3):
                ox, oy = r.randint(2, W - 3), r.randint(2, H - 3)
                kind = r.choice('~~T')
                for _ in range(r.randint(3, 9)):
                    ox, oy = ox + r.randint(-1, 1), oy + r.randint(-1, 1)
                    if 0 < ox < W - 1 and 0 < oy < H - 1 and g[oy][ox] == '.' and (ox, oy) not in keep and (ox, oy) not in path:
                        g[oy][ox] = '#'
                        ter[oy][ox] = kind
        seen_ = {cen[0]}
        todo = [cen[0]]
        while todo:
            cx_, cy_ = todo.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (cx_ + dx, cy_ + dy)
                if 0 <= n[0] < W and 0 <= n[1] < H and n not in seen_ and g[n[1]][n[0]] != '#':
                    seen_.add(n)
                    todo.append(n)
        for j in range(H):
            for i in range(W):
                if g[j][i] != '#' and (i, j) not in seen_:
                    g[j][i] = '#'
                    ter[j][i] = 'W' if cave else 'T'
        self.ter, self.g = ter, g
        self.seen = [[False] * W for _ in range(H)]
        self.items, self.en, self.chests, self.npcs = {}, [], {}, {}
        sx, sy = cen[-1]
        if cave:
            g[cen[0][1]][cen[0][0]] = '<'
            if floor < dg['floors']:
                g[sy][sx] = '>'
        elif z['dungeon']:
            g[sy][sx] = 'D'
        if arrive in EXIT_IN:
            self.px, self.py = EXIT_IN[arrive]
        else:
            self.px, self.py = cen[-1] if arrive == 'D' else cen[0]
            if camp:
                self.px, self.py = cen[0][0] + 2, cen[0][1] + 1
        if arrive == 'D' or cave:
            self.px, self.py = (-1, -1)
            fp = self.free_near(*(cen[-1] if arrive == 'D' else cen[0]), 1)
            self.px, self.py = fp or (cen[-1] if arrive == 'D' else cen[0])
        if camp:
            self.fill_camp(r, cen[0])
        else:
            self.populate(r, rooms, cen, cave, floor == (dg or {}).get('floors'), (sx, sy))
        if camp:
            self.say(f'-- {z["name"]}: a safe camp. Rest at the fire. --')
        elif cave:
            self.say(f'-- {dg["name"]}, floor {floor}/{dg["floors"]} --' + ('  A boss waits below the last stair.' if floor == dg['floors'] else ''))
        else:
            self.say(f'-- {z["name"]} (lvl {z["level"]}) --' + (f'  {z["dungeon"]["name"]} lies here.' if z['dungeon'] else ''))
        self.vision()

    def populate(self, r, rooms, cen, cave, last, end):
        g = self.g
        mult = 1.35 if cave else 1.0
        L = self.depth
        near = lambda x, y: abs(x - self.px) + abs(y - self.py) < 9
        for k, (x, y, w, h) in enumerate(rooms):
            # enemy quantity grows with level: more per clearing, and bigger rooms hold more
            n = int(r.randint(1 + L // 6, 2 + L // 3 + L // 5) * mult * (0.6 + w * h / 130))
            for _ in range(min(n, 16)):
                ex, ey = r.randint(x, x + w - 1), r.randint(y, y + h - 1)
                if g[ey][ex] == '.' and (ex, ey) != end and not self.enemy_at(ex, ey) and not near(ex, ey):
                    self.spawn(ex, ey, r)
            if r.random() < 0.35:
                dx_, dy_ = r.randint(x, x + w - 1), r.randint(y, y + h - 1)
                if g[dy_][dx_] == '.':
                    self.drop(dx_, dy_, 0)
        if len(rooms) > 3 and r.random() < (0.95 if cave else 0.5):
            x, y, w, h = r.choice(rooms[2:-1])
            cxy = (r.randint(x, x + w - 1), r.randint(y, y + h - 1))
            if not self.enemy_at(*cxy) and g[cxy[1]][cxy[0]] == '.':
                self.chests[cxy] = True
        if cave and last:
            bp = self.free_near(end[0], end[1], 1) or end
            self.spawn(bp[0], bp[1], r, boss=True)
        elif self.zone['dungeon'] and not cave:
            for _ in range(2 + L // 8):  # the mouth of a dungeon is guarded
                fp = self.free_near(end[0], end[1], 3)
                if fp and fp != (self.px, self.py):
                    self.spawn(fp[0], fp[1], r)

    def fill_camp(self, r, c):
        g = self.g
        g[c[1]][c[0]] = 'F'
        spots = [(c[0] - 4, c[1] - 2), (c[0] + 4, c[1] - 2), (c[0], c[1] + 4)]
        for kind, (x, y) in zip(NPC_KINDS, spots):
            if g[y][x] == '#':
                continue
            self.npcs[(x, y)] = dict(kind=kind)

    def rest(self):
        s = self.stats()
        self.hp, self.mana = s['hp'], s['mana']
        self.cons['hp'] = max(self.cons.get('hp', 0), 2)
        self.cons['mp'] = max(self.cons.get('mp', 0), 1)
        self.say('You rest at the fire. Life, mana and potions restored.')
        self.save()

    def travel(self, d):
        nx, ny = self.zpos[0] + DIRS[d][0], self.zpos[1] + DIRS[d][1]
        self.enter((nx, ny), 0, OPP[d])
        self.save()

    def bump_npc(self, pos):
        k = self.npcs[pos]['kind']
        if k == 'Quartermaster':
            price = 10 + 3 * self.zone['level']
            if self.res['scrap'] < price:
                self.say(f'Quartermaster: potions are {price} scrap. You have {self.res["scrap"]}.')
            else:
                kind = 'hp' if self.cons.get('hp', 0) <= self.cons.get('mp', 0) else 'mp'
                self.res['scrap'] -= price
                self.cons[kind] = self.cons.get(kind, 0) + 1
                self.say(f'Quartermaster sells you a {CONS[kind][0]} for {price} scrap.')
        elif k == 'Ranger':
            tgt = [(abs(c[0] - self.zpos[0]) + abs(c[1] - self.zpos[1]), c) for c, z in self.zones.items() if z['dungeon'] and c not in self.visited]
            if not tgt:
                self.say('Ranger: you have walked every cave I know.')
            else:
                c = min(tgt)[1]
                dx, dy = c[0] - self.zpos[0], c[1] - self.zpos[1]
                way = ' '.join(x for x in (f'{abs(dy)} {DIRNAME["N" if dy < 0 else "S"]}' if dy else '', f'{abs(dx)} {DIRNAME["W" if dx < 0 else "E"]}' if dx else '') if x)
                self.say(f'Ranger: a dungeon lies {way} of here, past the trees.')
        else:
            out = []
            for d in self.zone['links']:
                z = self.zones[(self.zpos[0] + DIRS[d][0], self.zpos[1] + DIRS[d][1])]
                out.append(f'{DIRNAME[d]}: {z["name"]} (lvl {z["level"]})')
            self.say('Elder: ' + '; '.join(out))

    def spawn(self, x, y, r, boss=False, add=False):
        pool = [e for e in ENEMIES if e[5] <= self.depth] or ENEMIES[:1]
        n, gl, hp, dm, xp, _, fl = r.choice(pool[-5:])
        tier = (self.depth - 1) // 10
        sc = (1 + 0.22 * (self.depth - 1)) * (1.5 ** tier)
        pre = ['', 'Elder ', 'Ancient ', 'Primal ', 'Eternal '][min(tier, 4)] + ('Mythic ' * max(0, tier - 4))
        champ = not add and not boss and r.random() < 0.12
        aff, bk = [], None
        if boss:
            bk = BOSS_KINDS[self.bk_i]
            n, gl, hp, dm, xp, fl = bk['name'], bk['gl'], 70, 10, 100, ''
        elif add:
            hp, dm, xp = hp * 0.5, int(dm * 0.6), xp * 0.4
        elif champ:
            hp, dm, xp, gl = hp * 2, int(dm * 1.5), xp * 3, gl.upper()
            aff = r.sample(list(EAFF), 1 + (self.depth >= 10) + (self.depth >= 30))
        elif self.depth >= 15 and r.random() < 0.10:
            aff = [r.choice(list(EAFF))]
        xp *= 1 + 0.5 * len(aff)
        if 'fast' in aff:
            fl += ' fast'
        e = dict(name=pre + (' '.join(a.title() for a in aff) + ' ' if aff else '') + ('Champion ' if champ else '') + n, gl=gl,
                 hp=int(hp * sc), mhp=int(hp * sc), dmg=max(1, int(dm * sc)), xp=int(xp * sc), x=x, y=y, fl=fl, slow=0, dots=[],
                 champ=champ or boss or bool(aff), boss=boss, awake=False, aff=aff, bk=bk, phase=1, tele=None, cd=3, add=add, told=False)
        if 'shielded' in aff:
            e['shield'] = int(e['mhp'] * 0.4)
        self.en.append(e)
        return e

    def free_near(self, x, y, r=2):
        spots = [(x + dx, y + dy) for dx in range(-r, r + 1) for dy in range(-r, r + 1)
                 if self.g[y + dy][x + dx] not in '#E' and not self.enemy_at(x + dx, y + dy) and (x + dx, y + dy) != (self.px, self.py)]
        return self.rng.choice(spots) if spots else None

    def summon(self, e, n):
        mine = sum(1 for o in self.en if o.get('owner') == id(e))
        for _ in range(min(n, 6 - mine)):
            p = self.free_near(e['x'], e['y'])
            if p:
                m = self.spawn(p[0], p[1], self.rng, add=True)
                m['owner'], m['awake'] = id(e), True

    def affix_tick(self, e):
        """Per-turn behaviour of affixed enemies. Returns True if the enemy used its action."""
        t = self.turn + id(e) % 7
        if 'mender' in e['aff'] and t % 3 == 0:
            for o in self.en:
                if o is not e and self.near(o, e, 25) and o['hp'] < o['mhp']:
                    o['hp'] = min(o['mhp'], o['hp'] + max(1, int(o['mhp'] * 0.15)))
        if 'summoner' in e['aff'] and t % 6 == 0:
            self.summon(e, 1)
        if 'teleporter' in e['aff'] and t % 5 == 0 and max(abs(e['x'] - self.px), abs(e['y'] - self.py)) > 3:
            p = self.free_near(self.px, self.py, 1)
            if p:
                e['x'], e['y'] = p
                self.say(f'{e["name"]} blinks next to you!')
                return True
        return False

    def boss_tiles(self, e, kind):
        floor = lambda x, y: 0 <= x < W and 0 <= y < H and self.g[y][x] not in '#E'
        tiles = set()
        if kind == 'slam':
            tiles = {(e['x'] + dx, e['y'] + dy) for dx in range(-2, 3) for dy in range(-2, 3)}
        elif kind == 'volley':
            cs = [(self.px, self.py)] + [(self.px + self.rng.randint(-3, 3), self.py + self.rng.randint(-3, 3)) for _ in range(2 + e['phase'])]
            tiles = {(cx + dx, cy + dy) for cx, cy in cs for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        elif kind == 'nova':
            tiles = {(e['x'] + dx, e['y'] + dy) for dx in range(-4, 5) for dy in range(-4, 5) if 3 <= max(abs(dx), abs(dy)) <= 4}
        else:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                x, y = e['x'] + dx, e['y'] + dy
                while floor(x, y) and abs(x - e['x']) + abs(y - e['y']) <= 12:
                    tiles.add((x, y))
                    x, y = x + dx, y + dy
        return {t for t in tiles if floor(*t)}

    def boss_act(self, e):
        """Phases at 66%/33% life, telegraphed attacks that resolve two turns later. True = skip normal move/attack."""
        frac = e['hp'] / max(1, e['mhp'])
        ph = 1 + (frac < 0.66) + (frac < 0.33)
        if ph > e['phase']:
            e['phase'] = ph
            e['dmg'] = int(e['dmg'] * 1.2)
            self.say(f'{e["name"]} ENRAGES! (phase {ph})')
            self.summon(e, 2 + ph)
        kind = e['bk']['tele']
        if e['tele']:
            e['tele']['t'] -= 1
            if e['tele']['t'] <= 0:
                if (self.px, self.py) in e['tele']['tiles']:
                    self.say(f'{e["name"]}\'s {kind} hits you!')
                    self.hurt(e, e['tele']['mult'])
                e['tele'] = None
            return kind == 'slam'
        e['cd'] -= 1
        if e['cd'] <= 0 and max(abs(e['x'] - self.px), abs(e['y'] - self.py)) <= 12:
            e['cd'] = max(3, 6 - e['phase'])
            e['tele'] = dict(tiles=self.boss_tiles(e, kind), t=2, mult={'slam': 3.0, 'volley': 2.5, 'nova': 3.0, 'cross': 2.5}[kind])
            self.say(f'{e["name"]} prepares a {kind}! Get out of the red.')
            if kind == 'cross' and e['phase'] > 1:
                self.summon(e, 1)
            if kind == 'nova' and e['phase'] > 1:
                p = self.free_near(self.px, self.py, 2)
                if p:
                    e['x'], e['y'] = p
        return False

    def enemy_at(self, x, y):
        return next((e for e in self.en if e['x'] == x and e['y'] == y), None)

    # ---- loot
    def apply_filter(self, it):
        """True if the filter consumed the item (auto-salvaged or hidden). Legendary+ and uniques are never filtered."""
        act = self.filter.get(it['rarity'], 'keep')
        if act == 'keep':
            return False
        if act == 'salvage':
            sc, es = self.salvage_value(it)
            self.res['scrap'] += sc
            self.res['essence'] += es
            self.fscrap += sc
        self.fcount += 1
        return True

    def sweep(self):
        n = sc0 = 0
        for i in range(len(self.pack) - 1, -1, -1):
            it = self.pack[i]
            act = self.filter.get(it['rarity'], 'keep')
            if act == 'salvage':
                sc0 += self.salvage_value(it)[0]
                self.salvage(i)
                n += 1
            elif act == 'hide':
                self.pack.pop(i)
                n += 1
        return n, sc0

    def drop(self, x, y, bonus):
        find = 1 + self.st('find') / 100
        roll = self.rng.random()
        if roll < 0.12 * find:
            it = dict(slot='gem', skill=self.rng.choice(list(SKILLS)), rarity='magic')
        else:
            it = self.make_item(self.depth, bonus, find)
            if self.apply_filter(it):
                return
        self.items.setdefault((x, y), []).append(it)

    def roll_affixes(self, slot, rar, ilvl, sub=None):
        r = self.rng
        n = {'normal': 0, 'magic': r.randint(1, 2), 'rare': r.randint(3, 4), 'legend': r.randint(5, 6), 'mythic': r.randint(6, 7)}[rar]
        aff, used = [], set()
        sc = (1 + 0.08 * ilvl) * (1.5 ** ((ilvl - 1) // 10)) * (1.4 if rar == 'mythic' else 1)
        if slot == 'weapon':
            aff.append(('weapon', int((2 + r.randint(0, 2)) * sc * (1.7 if sub == '2h' else 1))))
        if slot == 'offhand':
            aff.append(('armor', int((3 + r.randint(0, 2)) * sc)) if sub == 'shield' else ('mana', int((6 + r.randint(0, 6)) * sc)))
        if slot in ARMOR_SLOTS:
            aff.append(('armor', int((ARMOR_BASE[slot] + r.randint(0, 3)) * sc)))
        for _ in range(n):
            a = r.choice(AFFIXES)
            if a[0] in used:
                continue
            used.add(a[0])
            aff.append((a[0], max(1, int(r.uniform(a[2], a[3]) * sc))))
        return aff

    def make_item(self, ilvl, bonus, find=1):
        r = self.rng
        x = r.random() / (find * (1 + bonus * 0.4)) ** 0.5
        rar = 'mythic' if x < 0.0015 and ilvl >= 6 else 'legend' if x < 0.012 else 'rare' if x < 0.10 else 'magic' if x < 0.40 else 'normal'
        slot = r.choice(['weapon', 'weapon', 'offhand', 'armor', 'head', 'hands', 'legs', 'boots', 'sash', 'charm'])
        extra = {}
        if slot == 'weapon':
            base = r.choice(BASES['weapon'] + WEAPON_2H)
            extra['hands'] = '2h' if base in WEAPON_2H else '1h'
        else:
            base = r.choice(BASES[slot])
            if slot == 'offhand':
                extra['kind'] = 'focus' if base in OFFHAND_FOCUS else 'shield'
        aff = self.roll_affixes(slot, rar, ilvl, extra.get('hands') or extra.get('kind'))
        name = base if rar == 'normal' else f'{r.choice(PRE)} {base}' if rar == 'magic' else \
            f'{r.choice(RARE_A)}{r.choice(RARE_B).lower()} {base}' if rar == 'rare' else \
            f'★ {r.choice(RARE_A)}{r.choice(RARE_B).lower()}, the {base}' if rar == 'legend' else f'☀ Mythic {r.choice(RARE_A)}{r.choice(RARE_B).lower()} {base}'
        it = dict(slot=slot, rarity=rar, name=name, aff=aff, ilvl=ilvl, **extra,
                  sockets=[None] * r.randint(1 if rar in ('rare', 'legend', 'mythic') else 0, SOCKET_MAX[rar]))
        if rar in ('legend', 'mythic'):
            it['power'], it['rank'] = r.choice(LEGEND_POWERS), 2 if rar == 'mythic' else 1
        return it

    # ---- bag economy: salvage, reroll (refits to current depth), ascend legend -> mythic, consumables, chests
    def salvage_value(self, it):
        k = 1 + it.get('ilvl', 1) / 10
        return int(SALVAGE[it['rarity']] * k), int(ESS.get(it['rarity'], 0) * k)

    def reroll_cost(self, it):
        if it['rarity'] == 'normal':
            return None
        k = 1 + self.depth / 10
        return int(REROLL_SCRAP[it['rarity']] * k), REROLL_ESS.get(it['rarity'], 0)

    def salvage(self, i):
        it = self.pack.pop(i)
        for rk in it.get('sockets', []):
            if rk:
                self.runes[rk] = self.runes.get(rk, 0) + 1
        sc, es = self.salvage_value(it)
        self.res['scrap'] += sc
        self.res['essence'] += es
        self.say(f'Salvaged {it["name"]}: +{sc} scrap' + (f' +{es} essence' if es else ''))

    def pay(self, scrap, ess):
        if self.res['scrap'] < scrap or self.res['essence'] < ess:
            self.say(f'Need {scrap} scrap' + (f' + {ess} essence' if ess else ''))
            return False
        self.res['scrap'] -= scrap
        self.res['essence'] -= ess
        return True

    def reroll(self, it):
        cost = self.reroll_cost(it)
        if not cost:
            self.say('Normal gear is not worth it')
            return False
        if not self.pay(*cost):
            return False
        if it['rarity'] == 'unique':
            u = next(u for u in UNIQUES if u['name'] == it['name'])
            sc = (1 + 0.08 * self.depth) * (1.5 ** ((self.depth - 1) // 10))
            it['aff'] = [(k, max(1, int(v * sc))) for k, v in u['base'].items()]
        else:
            it['aff'] = self.roll_affixes(it['slot'], it['rarity'], self.depth, it.get('hands') or it.get('kind'))
        it['ilvl'] = self.depth
        self.say(f'Reforged {it["name"]} for depth {self.depth}')
        return True

    def ascend(self, it):
        if it['rarity'] != 'legend':
            self.say('Only legendary gear ascends')
            return False
        k = 1 + self.depth / 10
        if not self.pay(int(400 * k), 40):
            return False
        it['rarity'], it['rank'] = 'mythic', 2
        it['name'] = '☀ Mythic ' + it['name'][2:]
        it['ilvl'] = self.depth
        it['aff'] = self.roll_affixes(it['slot'], 'mythic', self.depth, it.get('hands') or it.get('kind'))
        it.setdefault('sockets', [])
        while len(it['sockets']) < 3:
            it['sockets'].append(None)
        self.say(f'ASCENDED: {it["name"]}')
        return True

    def new_rune(self, bonus=0):
        t = 1 + self.depth // 10 + (1 if self.rng.random() < 0.2 + bonus else 0)
        return f'{self.rng.choice(list(RUNES))}:{t}'

    def fuse(self, rk):
        t, n = rune_split(rk)
        if self.runes.get(rk, 0) < 3:
            self.say(f'Need 3 {rune_name(rk)} to fuse')
            return False
        self.runes[rk] -= 3
        up = f'{t}:{n + 1}'
        self.runes[up] = self.runes.get(up, 0) + 1
        self.say(f'Fused -> {rune_name(up)}')
        return True

    def socket_cost(self, it):
        n = len(it.get('sockets', []))
        return int(100 * (1 + self.depth / 10) * 2 ** n), 5 * 2 ** n

    def add_socket(self, it):
        if len(it.setdefault('sockets', [])) >= 6:
            self.say('Six sockets is the limit')
            return False
        if not self.pay(*self.socket_cost(it)):
            return False
        it['sockets'].append(None)
        self.say(f'Socket added ({len(it["sockets"])})')
        return True

    def unequip(self, slot):
        it = self.equip[slot]
        if it:
            self.pack.append(it)
            self.equip[slot] = None
            self.hp = min(self.hp, self.st('hp'))

    def use_cons(self, kind):
        if self.cons.get(kind, 0) <= 0:
            self.say(f'No {CONS[kind][0]}')
            return False
        if kind != 'map' and self.potion_cd > 0:
            self.say(f'Potion sickness ({self.potion_cd})')
            return False
        mh, mm = self.st('hp'), self.st('mana')
        if kind == 'hp':
            self.hp = min(mh, self.hp + int(mh * 0.4))
        elif kind == 'mp':
            self.mana = min(mm, self.mana + int(mm * 0.6))
        elif kind == 'rejuv':
            self.hp = min(mh, self.hp + mh // 2)
            self.mana = min(mm, self.mana + mm // 2)
        else:
            self.seen = [[True] * W for _ in range(H)]
            for e in self.en:
                e['awake'] = False
        self.cons[kind] -= 1
        if kind != 'map':
            self.potion_cd = 6
        self.say(f'Used {CONS[kind][0]}')
        return True

    def open_chest(self, x, y):
        if self.keys <= 0:
            self.say('Locked chest. Needs a key (champions and bosses carry them).')
            return False
        self.keys -= 1
        del self.chests[(x, y)]
        for _ in range(self.rng.randint(2, 3)):
            it = self.make_item(self.depth, 3, 1 + self.st('find') / 100)
            if not self.apply_filter(it):
                self.items.setdefault((x, y), []).append(it)
        if self.rng.random() < 0.08:
            self.drop_unique(x, y)
        if self.rng.random() < 0.5:
            self.items.setdefault((x, y), []).append(dict(slot='cons', kind=self.rng.choice(['rejuv', 'hp', 'mp', 'map']), rarity='magic'))
        self.items.setdefault((x, y), []).append(dict(slot='rune', rune=self.new_rune(0.3), rarity='legend'))
        self.res['scrap'] += 5 * self.depth
        self.say('The chest bursts open!')
        return True

    def make_unique(self):
        have = {i['name'] for i in self.pack} | {i['name'] for i in self.equip.values() if i}
        u = self.rng.choice([u for u in UNIQUES if u['name'] not in have] or UNIQUES)
        sc = (1 + 0.08 * self.depth) * (1.5 ** ((self.depth - 1) // 10))
        extra = {'hands': u['hands']} if 'hands' in u else {}
        return dict(slot=u['slot'], rarity='unique', name=u['name'], aff=[(k, max(1, int(v * sc))) for k, v in u['base'].items()],
                    ilvl=self.depth, power=u['power'], rank=1, sockets=[None] * 2, **extra)

    def drop_unique(self, x, y):
        self.items.setdefault((x, y), []).append(self.make_unique())
        self.say('A UNIQUE drops!')

    def aff_text(self, stat, v):
        for a in AFFIXES:
            if a[0] == stat:
                return a[1].format(v).replace('+-', '-')
        return ELABEL.get(stat, stat + ' {}').format(v).replace('+-', '-')

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
            elif it['slot'] == 'cons':
                self.cons[it['kind']] = self.cons.get(it['kind'], 0) + 1
                self.say(f'Picked up {CONS[it["kind"]][0]}')
            elif it['slot'] == 'rune':
                self.runes[it['rune']] = self.runes.get(it['rune'], 0) + 1
                self.say(f'Picked up {rune_name(it["rune"])} rune')
            elif it['slot'] == 'key':
                self.keys += 1
                self.say('Picked up a Dungeon Key')
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
                if not e['told'] and (e['aff'] or e['boss']):
                    e['told'] = True
                    if e['boss']:
                        self.say(f'{e["name"]}: {e["bk"]["info"]}. Phases at 66% and 33%.')
                    else:
                        self.say(f'{e["name"]}: ' + '; '.join(EAFF[a] for a in e['aff']))

    # ---- combat
    def calc(self, base, tags, melee_weapon=False):
        s = self.stats()
        tags = set(tags) | self.extra_tags
        d = base + (s['weapon'] * 0.6 if melee_weapon else 0)
        pct = s.get('dmg_pct', 0) + sum(s.get(t + '_pct', 0) for t in tags) + self.ms.get('sk_dmg', 0)
        if 'pact' in self.buffs:
            pct += 50 + self.pact_extra
        d *= max(0.1, 1 + pct / 100) * (1 + s.get('more_dmg', 0) / 100)
        crit = self.rng.random() * 100 < 5 + s.get('crit', 0) + self.ms.get('sk_crit', 0)
        if crit:
            d *= 2
        return max(1, int(d)), crit

    def hit(self, e, dmg, crit=False, src=''):
        if e['hp'] <= 0:
            return 0
        if e['slow'] > 0 and self.ms.get('shatter'):
            dmg = int(dmg * (1 + self.ms['shatter'] / 100))
        if e.get('shield', 0) > 0:
            ab = min(e['shield'], dmg)
            e['shield'] -= ab
            dmg -= ab
            if dmg <= 0:
                e['awake'] = True
                self.say(f'{src}{e["name"]} shield absorbs {ab}')
                if self.fx is not None:
                    self.fx.append(('absorb', e))
                return 0
        self.last_dmg = dmg
        e['hp'] -= dmg
        e['awake'] = True
        if 'thorned' in e['aff'] and max(abs(e['x'] - self.px), abs(e['y'] - self.py)) <= 2:
            th = max(1, int(dmg * 0.15))
            self.hp -= th
            self.say(f'Thorns -{th}')
        lc = self.st('leech') + self.ms.get('sk_leech', 0)
        if lc:
            self.hp = min(self.st('hp'), self.hp + max(0, int(dmg * lc / 100)))
        self.say(f'{src}{e["name"]} -{dmg}{"!" if crit else ""}' + (' (dies)' if e['hp'] <= 0 else ''))
        if self.fx is not None:
            self.fx.append(('dmg', e, dmg, crit))
        if e['hp'] > 0 and self.ms:
            if self.ms.get('sk_burn'):
                e['dots'].append((max(1, int(dmg * self.ms['sk_burn'] / 100)), 3))
            if self.ms.get('sk_slow'):
                e['slow'] = max(e['slow'], self.ms['sk_slow'])
        if e['hp'] <= 0:
            self.kill(e)
        return dmg

    def near(self, a, b, r2=5):
        return (a['x'] - b['x']) ** 2 + (a['y'] - b['y']) ** 2 <= r2

    def kill(self, e):
        if e in self.en:
            self.en.remove(e)
        if self.fx is not None:
            self.fx.append(('die', e))
        if self.cur:
            self.train(self.cur, 2)
        pw = self.powers()
        if 'blood_chalice' in pw:
            self.mana = min(self.st('mana'), self.mana + 2 * pw['blood_chalice'])
        if 'kill_streak' in pw:
            self.streak, self.streak_t = min(10, self.streak + 1), 6
        if self.ms.get('bl_reset'):
            self.flag_reset = True
        if self.ms.get('fb_explode') and not self._boom:
            self._boom = True
            try:
                dmg = max(1, int(self.last_dmg * self.ms['fb_explode'] / 100))
                for o in [o for o in self.en if self.near(o, e)]:
                    self.hit(o, dmg, False, 'Blast: ')
            finally:
                self._boom = False
        if 'explosive' in e['aff'] and max(abs(e['x'] - self.px), abs(e['y'] - self.py)) <= 2:
            self.say(f'{e["name"]} explodes!')
            self.hurt(e, 2.0)
        if e.get('add'):
            self.gain_xp(e['xp'])
            return
        if e.get('spread') and e['dots']:
            for o in [o for o in self.en if self.near(o, e)]:
                o['dots'] += list(e['dots'])
                o['spread'], o['awake'] = True, True
        self.gain_xp(e['xp'])
        r = self.rng
        self.res['scrap'] += int((1 + self.depth * 0.6) * (5 if e['boss'] else 2 if e['champ'] else 1) * (1 if r.random() < 0.6 else 0))
        if e['champ']:
            self.res['essence'] += (6 + self.depth // 5) if e['boss'] else (1 + self.depth // 12)
        nk = 2 if e['boss'] else 1 if e['champ'] and r.random() < 0.6 else 1 if r.random() < 0.02 else 0
        for _ in range(nk):
            self.items.setdefault((e['x'], e['y']), []).append(dict(slot='key', rarity='rare'))
        for _ in range(3 if e['boss'] else 1 if (e['champ'] and r.random() < 0.5) or r.random() < 0.06 else 0):
            self.items.setdefault((e['x'], e['y']), []).append(dict(slot='rune', rune=self.new_rune(0.1), rarity='legend'))
        if r.random() < 0.12:
            k = r.choices(['hp', 'mp', 'rejuv', 'map'], [45, 35, 8, 12])[0]
            self.items.setdefault((e['x'], e['y']), []).append(dict(slot='cons', kind=k, rarity='magic'))
        if e['boss'] and self.rng.random() < 0.6 or e['champ'] and self.rng.random() < 0.03 or self.rng.random() < 0.003:
            self.drop_unique(e['x'], e['y'])
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

    def nearest(self, rng, skip=()):
        rng += self.ms.get('sk_range', 0)
        c = [e for e in self.en if e not in skip and (e['x'], e['y']) in self.vis and (e['x'] - self.px) ** 2 + (e['y'] - self.py) ** 2 <= rng * rng]
        return min(c, key=lambda e: (e['x'] - self.px) ** 2 + (e['y'] - self.py) ** 2) if c else None

    def adjacent(self):
        return [e for e in self.en if max(abs(e['x'] - self.px), abs(e['y'] - self.py)) == 1]

    # ---- powers (legendary / mythic / unique) feed the same mods the mastery grids use
    def powers(self):
        out = {}
        for it in self.equip.values():
            if it and it.get('power'):
                out[it['power']] = out.get(it['power'], 0) + it.get('rank', 1)
        return out

    def cast_mods(self, key, idx):
        tags = SKILLS[key]['tags']
        m = dict(self.mstats(key))
        add = lambda k, v: m.__setitem__(k, m.get(k, 0) + v)
        for it in self.equip.values():
            for rk in (it or {}).get('sockets', []):
                if rk:
                    d = RUNES[rune_split(rk)[0]]
                    if d['kind'] == 'tag' and (d['tag'] == 'all' or d['tag'] in tags):
                        add(d['stat'], rune_val(rk))
        for p, r in self.powers().items():
            if p == 'cinder_heart' and 'fire' in tags:
                add('fb_explode', 30 * r)
            elif p == 'storm_mantle' and 'chain' in tags:
                add('sk_chain', 2 * r)
            elif p == 'frost_tyrant' and 'cold' in tags:
                m['sk_slow'] = max(m.get('sk_slow', 0), 2 + r)
                add('shatter', 25 * r)
            elif p == 'plague_doctor' and 'poison' in tags:
                m['spread'] = 1
                add('dur', 2 * r)
            elif p == 'echo_ring':
                add('sk_echo', 15 * r)
            elif p == 'whirl_boots' and 'melee' in tags:
                add('sk_radius', r)
            elif p == 'overflow_stone' and self.mana >= 0.9 * self.st('mana'):
                add('sk_dmg', 40 * r)
            elif p == 'last_stand' and self.hp < 0.35 * self.st('hp'):
                add('sk_dmg', 60 * r)
                add('sk_leech', 10 * r)
            elif p == 'prime_charm' and idx == 0:
                add('sk_dmg', 40 * r)
                add('sk_cost', 2 * r)
            elif p == 'inferno' and 'fire' in tags:
                add('sk_burn', 60)
                add('sk_cd', 9)
            elif p == 'kill_streak':
                add('sk_dmg', 10 * self.streak)
        return m

    def eff_cost(self, key):
        idx = self.slots.index(key) if key in self.slots else -1
        return max(0, SKILLS[key]['cost'] - self.cast_mods(key, idx).get('sk_cost', 0))

    def cast(self, idx, free=False):
        if idx >= len(self.slots) or not self.slots[idx]:
            return False
        key = self.slots[idx]
        sk = SKILLS[key]
        if self.cd.get(key, 0) > 0 and not free:
            self.say(f'{sk["name"]} cooling ({self.cd[key]})')
            return False
        ms = self.cast_mods(key, idx)
        pw = self.powers()
        cost = 0 if free else max(0, sk['cost'] - ms.get('sk_cost', 0))
        hpcost = 0
        if self.mana < cost:
            if 'mana_to_life' in pw and self.hp > (cost - self.mana) * 2 + 1:
                hpcost = (cost - self.mana) * 2
            else:
                self.say('Not enough mana')
                return False
        self.ms, self.cur, self.flag_reset = ms, key, False
        self.extra_tags = set(SKILLS[self.slots[(idx + 1) % len(self.slots)]]['tags']) if 'skill_fusion' in pw else set()
        ok = False
        try:
            ok = getattr(self, 'sk_' + key)(sk)
            if ok:
                if hpcost:
                    self.hp -= hpcost
                    self.mana = 0
                else:
                    self.mana -= cost
                self.cd[key] = 0 if self.flag_reset else max(0, sk['cd'] - ms.get('sk_cd', 0))
                self.train(key, 1)
                if self.rng.random() * 100 < ms.get('sk_echo', 0):
                    self.say('Echo!')
                    getattr(self, 'sk_' + key)(sk)
        finally:
            self.ms, self.cur, self.extra_tags = {}, None, frozenset()
        if ok and not free and idx == 0 and 'double_slot' in pw and len(self.slots) > 1 and self.rng.random() < 0.4:
            self.say('Twinned!')
            self.cast(1, free=True)
        return ok

    def mp(self, k):
        return self.ms.get(k, 0)

    def sk_whirlwind(self, sk):
        rr = 1 + self.mp('sk_radius')
        adj = [e for e in self.en if max(abs(e['x'] - self.px), abs(e['y'] - self.py)) <= rr]
        if not adj:
            self.say('Nothing adjacent')
            return False
        for _ in range(2 if self.mp('ww_twice') else 1):
            for e in adj:
                if e not in self.en:
                    continue
                d, c = self.calc(sk['base'], sk['tags'], True)
                self.hit(e, d, c, 'Whirl: ')
                if self.mp('ww_heal'):
                    mh = self.st('hp')
                    self.hp = min(mh, self.hp + max(1, int(mh * self.mp('ww_heal') / 100)))
                if self.mp('ww_bleed') and e in self.en:
                    e['dots'].append((max(1, int(d * self.mp('ww_bleed') / 100)), 4))
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
        if self.mp('fb_twin'):
            o = self.nearest(sk['rng'], skip=(e,))
            if o:
                self.hit(o, int(d * 0.7), False, 'Twin: ')
        if self.mp('fb_splash'):
            for o in [o for o in self.en if o is not e and self.near(o, e, 2)]:
                self.hit(o, int(d * 0.6), False, 'Splash: ')
        return True

    def sk_frost_nova(self, sk):
        r2 = (2 + self.mp('sk_radius')) ** 2 + 1
        hit = [e for e in self.en if (e['x'] - self.px) ** 2 + (e['y'] - self.py) ** 2 <= r2]
        if not hit:
            self.say('Nothing in range')
            return False
        for e in hit:
            d, c = self.calc(sk['base'], sk['tags'])
            self.hit(e, d, c, 'Nova: ')
            if e in self.en:
                e['slow'] = max(e['slow'], 3)
            if self.mp('fn_mana'):
                self.mana = min(self.st('mana'), self.mana + self.mp('fn_mana'))
        if self.mp('fn_pulse'):
            r3 = (3 + self.mp('sk_radius')) ** 2 + 1
            for e in [e for e in self.en if (e['x'] - self.px) ** 2 + (e['y'] - self.py) ** 2 <= r3]:
                d, c = self.calc(sk['base'], sk['tags'])
                self.hit(e, int(d * 0.6), c, 'Pulse: ')
        return True

    def sk_blink(self, sk):
        dx, dy = self.face
        x, y = self.px, self.py
        path = []
        for _ in range(5 + self.mp('bl_range')):
            nx, ny = x + dx, y + dy
            if self.g[ny][nx] in '#E' or self.enemy_at(nx, ny):
                break
            x, y = nx, ny
            path.append((x, y))
        if not path:
            self.say('Blocked')
            return False
        start = (self.px, self.py)
        self.px, self.py = x, y
        if self.mp('bl_trail'):
            done = set()
            for tx, ty in [start] + path[:-1]:
                for e in [e for e in self.en if max(abs(e['x'] - tx), abs(e['y'] - ty)) <= 1 and id(e) not in done]:
                    done.add(id(e))
                    d, c = self.calc(sk['base'], sk['tags'], True)
                    self.hit(e, int(d * self.mp('bl_trail') / 100), c, 'Trail: ')
        for e in self.adjacent():
            d, c = self.calc(sk['base'], sk['tags'], True)
            self.hit(e, d, c, 'Blink: ')
        return True

    def sk_chain_lightning(self, sk):
        e = self.nearest(sk['rng'])
        if not e:
            self.say('No target')
            return False
        allm = self.mp('cl_all')
        jumps = 40 if allm else 4 + self.mp('sk_chain')
        factor = 0.92 if allm else 1.2 if self.mp('cl_ramp') else 0.8
        jr2 = 36 if allm else 16
        done, mult = [], 1.0
        for _ in range(jumps):
            if not e:
                break
            d, c = self.calc(sk['base'], sk['tags'])
            done.append(e)
            self.hit(e, int(d * mult), c, 'Arc: ')
            if e in self.en and self.mp('cl_slow'):
                e['slow'] = max(e['slow'], self.mp('cl_slow'))
            mult *= factor
            cand = [o for o in self.en if o not in done and self.near(o, e, jr2)]
            e = min(cand, key=lambda o: (o['x'] - e['x']) ** 2 + (o['y'] - e['y']) ** 2) if cand else None
        return True

    def sk_bone_spear(self, sk):
        t = self.nearest(sk['rng'])
        if not t:
            self.say('No target')
            return False
        dx, dy = t['x'] - self.px, t['y'] - self.py
        n = max(1, abs(dx), abs(dy))
        hit, k = set(), 0
        for i in range(1, sk['rng'] + self.mp('sk_range') + 1):
            x, y = self.px + round(dx * i / n), self.py + round(dy * i / n)
            if self.g[y][x] in '#E':
                break
            e = self.enemy_at(x, y)
            if e and id(e) not in hit:
                hit.add(id(e))
                d, c = self.calc(sk['base'], sk['tags'])
                self.hit(e, int(d * (1 + self.mp('bs_ramp') / 100 * k)), c, 'Spear: ')
                k += 1
                ex = self.mp('bs_exec')
                if ex and e in self.en and e['hp'] < e['mhp'] * ex / 100:
                    self.hit(e, e['hp'], False, 'Rend: ')
        if self.mp('bs_fan'):
            rng2 = sk['rng'] + self.mp('sk_range')
            others = sorted([o for o in self.en if id(o) not in hit and (o['x'], o['y']) in self.vis and
                             (o['x'] - self.px) ** 2 + (o['y'] - self.py) ** 2 <= rng2 * rng2],
                            key=lambda o: (o['x'] - self.px) ** 2 + (o['y'] - self.py) ** 2)[:self.mp('bs_fan')]
            for o in others:
                d, c = self.calc(sk['base'], sk['tags'])
                self.hit(o, int(d * 0.8), c, 'Barrage: ')
        return True

    def sk_poison_cloud(self, sk):
        t = self.nearest(sk['rng'])
        if not t:
            self.say('No target')
            return False
        r2 = (2 + self.mp('sk_radius')) ** 2 + 1
        dur = 5 + self.mp('dur') + self.mp('pc_long')
        for e in [e for e in self.en if self.near(e, t, r2)]:
            d, _ = self.calc(sk['base'], sk['tags'])
            e['dots'].append((d, dur))
            e['awake'] = True
            if self.mp('spread') or self.mp('pc_spread'):
                e['spread'] = True
        self.say('Poison cloud blooms')
        return True

    def sk_soul_siphon(self, sk):
        e = self.nearest(sk['rng'])
        if not e:
            self.say('No target')
            return False
        d, c = self.calc(sk['base'], sk['tags'])
        mh = self.st('hp')
        got = self.hit(e, d, c, 'Siphon: ')
        self.hp = min(mh, self.hp + int(got * (0.4 + self.mp('ss_heal') / 100)))
        if self.mp('ss_mana'):
            self.mana = min(self.st('mana'), self.mana + self.mp('ss_mana'))
        if self.mp('ss_twin'):
            o = self.nearest(sk['rng'], skip=(e,))
            if o:
                got = self.hit(o, int(d * 0.7), False, 'Twin siphon: ')
                self.hp = min(mh, self.hp + int(got * (0.4 + self.mp('ss_heal') / 100)))
        return True

    def sk_blood_pact(self, sk):
        cost = int(self.st('hp') * (0.06 if self.mp('bp_cheap') else 0.12))
        if self.hp <= cost + 1:
            self.say('Too weak for the pact')
            return False
        self.hp -= cost
        self.mana = min(self.st('mana'), self.mana + 20)
        self.buffs['pact'] = 6 + self.mp('bp_long')
        self.pact_extra = self.mp('bp_power')
        self.say(f'Blood Pact: +{50 + self.pact_extra}% damage')
        return True

    # ---- movement & turn
    def step(self, dx, dy):
        self.face = (dx, dy)
        nx, ny = self.px + dx, self.py + dy
        if self.g[ny][nx] == '#':
            return False
        if (nx, ny) in self.chests:
            return self.open_chest(nx, ny)
        if (nx, ny) in self.npcs:
            self.bump_npc((nx, ny))
            return True
        e = self.enemy_at(nx, ny)
        if e:
            d, c = self.calc(0, {'phys', 'melee'}, True)
            self.hit(e, d, c, 'You: ')
        else:
            self.px, self.py = nx, ny
            self.pickup()
            t = self.g[ny][nx]
            if t == 'E':
                self.travel('N' if ny == 0 else 'S' if ny == H - 1 else 'W' if nx == 0 else 'E')
            elif t == 'F':
                self.rest()
        return True

    def descend(self):
        t = self.g[self.py][self.px]
        if t == '>':
            self.enter(self.zpos, self.floor + 1)
        elif t == 'D':
            self.enter(self.zpos, 1)
        elif t == '<':
            if self.floor > 1:
                self.enter(self.zpos, self.floor - 1)
            else:
                self.enter(self.zpos, 0, 'D')
        elif t == 'F':
            self.rest()
            return False
        else:
            self.say('Nothing to use here. Leave a zone through the gaps in the trees.')
            return False
        self.save()
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
        self.potion_cd = max(0, self.potion_cd - 1)
        if self.streak_t > 0:
            self.streak_t -= 1
            if not self.streak_t:
                self.streak = 0
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
        if self.hp <= 0 and 'deathless' in self.powers() and not self.phoenix:
            self.phoenix = True
            self.hp = self.st('hp') // 2
            self.say('REBIRTH! Flames scour the area.')
            for o in [o for o in self.en if self.near(o, dict(x=self.px, y=self.py), 13)]:
                self.hit(o, max(1, self.st('hp') // 2), False, 'Rebirth: ')
        if self.hp <= 0:
            self.dead = True

    def hurt(self, e, mult=1.0):
        a = self.stats().get('armor', 0)
        d = max(1, int(e['dmg'] * mult * (1 - a / (a + 30 + 8 * self.depth))))
        self.hp -= d
        if 'vampiric' in e['aff']:
            e['hp'] = min(e['mhp'], e['hp'] + d // 2)
        if 'draining' in e['aff']:
            self.mana = max(0, self.mana - max(1, self.st('mana') // 20))
        self.say(f'{e["name"]} hits you -{d}')
        if self.fx is not None:
            self.fx.append(('hurt', d))

    def enemy_act(self, e):
        if e['boss']:
            if self.boss_act(e):
                return
        elif e['aff'] and self.affix_tick(e):
            return
        dx, dy = self.px - e['x'], self.py - e['y']
        dist = max(abs(dx), abs(dy))
        if dist == 1:
            self.hurt(e)
        elif 'ranged' in e['fl'] and dist <= 6 and self.los(e['x'], e['y'], self.px, self.py):
            self.hurt(e, 0.8)
        elif dist <= 16:
            sx, sy = (dx > 0) - (dx < 0), (dy > 0) - (dy < 0)
            for mx, my in ([(sx, sy), (sx, 0), (0, sy)] if abs(dx) > abs(dy) else [(sx, sy), (0, sy), (sx, 0)]):
                if (mx or my) and self.g[e['y'] + my][e['x'] + mx] not in '#E' and not self.enemy_at(e['x'] + mx, e['y'] + my) \
                        and (e['x'] + mx, e['y'] + my) != (self.px, self.py):
                    e['x'] += mx
                    e['y'] += my
                    break

    # ---- passive tree
    def locked(self, tree, alloc, p):
        return any(e in alloc for e in tree.n[p]['excl'])

    def frontier(self, alloc=None, key=None):
        tr, out = tree_of(key), set()
        alloc = self.alloc if alloc is None else alloc
        for a in alloc:
            for p in tr.n[a]['adj']:
                if p not in alloc and not self.locked(tr, alloc, p):
                    out.add(p)
        return out

    def take(self, p):
        if self.points > 0 and p in self.frontier():
            self.alloc.add(p)
            self.points -= 1
            self.hp = min(self.hp, self.st('hp'))
            return True
        return False

    def untake(self, alloc, p, key=None):
        """Free respec of one node: allowed if everything else stays connected to the origin."""
        if p == (0, 0) or p not in alloc:
            return False
        tr = tree_of(key)
        rest = alloc - {p}
        seen, todo = {(0, 0)}, [(0, 0)]
        while todo:
            for q in tr.n[todo.pop()]['adj']:
                if q in rest and q not in seen:
                    seen.add(q)
                    todo.append(q)
        if seen != rest:
            return False
        alloc.discard(p)
        return True

    def respec(self, key=None):
        alloc = self.mas(key)['alloc'] if key else self.alloc
        n = len(alloc) - 1
        alloc.clear()
        alloc.add((0, 0))
        if key:
            self.mas(key)['points'] += n
        else:
            self.points += n
            self.hp = min(self.hp, self.st('hp'))
        return n

    def take_skill(self, key, p):
        m = self.mas(key)
        if m['points'] > 0 and p in self.frontier(m['alloc'], key):
            m['alloc'].add(p)
            m['points'] -= 1
            return True
        return False

    def equip_key(self, it):
        # where an item goes: 1h weapons dual-wield into the free off-hand, offhand/2h exclude each other
        sl = it['slot']
        if sl == 'weapon' and it.get('hands', '1h') == '1h':
            main, off = self.equip['weapon'], self.equip['offhand']
            if main and main.get('hands', '1h') == '1h' and not off:
                return 'offhand'
        return sl

    def equip_item(self, i):
        it = self.pack[i]
        key = self.equip_key(it)
        old = self.equip[key]
        self.equip[key] = it
        self.pack.pop(i)
        if old:
            self.pack.append(old)
        # two-hander clears the off-hand; an off-hand item evicts a worn two-hander
        main, off = self.equip['weapon'], self.equip['offhand']
        if key == 'weapon' and it.get('hands') == '2h' and off:
            self.pack.append(off)
            self.equip['offhand'] = None
            self.say(f'{off["name"]} unequipped (two-handed)')
        elif key == 'offhand' and main and main.get('hands') == '2h':
            self.pack.append(main)
            self.equip['weapon'] = None
            self.say(f'{main["name"]} unequipped (off-hand in use)')
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
SPECIAL = {'>': '▼', '<': '▲', 'D': '∩', 'F': '♨'}
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
            tr = g.ter[y][x]
            if t == '#':
                ch, col = {'T': '♣', 'r': '▲', '~': '≈'}.get(tr, '▓'), cp(1)
            elif t == 'E':
                ch, col = '↑' if y == 0 else '↓' if y == H - 1 else '←' if x == 0 else '→', cp(6, True)
            elif t in SPECIAL:
                ch, col = SPECIAL[t], cp(2, True) if t == 'F' else cp(4, True)
            else:
                ch, col = '"' if tr == 'f' else '·', cp(1)
            put(win, sy + my0, sx + mx0, ch, col if v else curses.A_DIM)
    for (x, y), its in g.items.items():
        if (x, y) in g.vis and inside(y - cy0, x - cx0):
            it = its[-1]
            put(win, y - cy0 + my0, x - cx0 + mx0, {'gem': '◈', 'cons': '!', 'key': '⚷', 'rune': '◇'}.get(it['slot'], '◆'), cp(RCOL[it['rarity']], True))
    for (x, y) in g.chests:
        if g.seen[y][x] and inside(y - cy0, x - cx0):
            put(win, y - cy0 + my0, x - cx0 + mx0, '▣', cp(4, True))
    for (x, y) in g.npcs:
        if (x, y) in g.vis and inside(y - cy0, x - cx0):
            put(win, y - cy0 + my0, x - cx0 + mx0, '&', cp(3, True))
    for e in g.en:
        if e['tele']:
            for (x, y) in e['tele']['tiles']:
                if g.seen[y][x] and inside(y - cy0, x - cx0):
                    put(win, y - cy0 + my0, x - cx0 + mx0, '▓' if e['tele']['t'] <= 1 else '▒', cp(2, True))
    for e in g.en:
        if (e['x'], e['y']) in g.vis and inside(e['y'] - cy0, e['x'] - cx0):
            col = cp(5, True) if e.get('shield', 0) > 0 else cp(2, True) if e['champ'] else cp(3 if e['slow'] else 2)
            put(win, e['y'] - cy0 + my0, e['x'] - cx0 + mx0, e['gl'], col)
    put(win, g.py - cy0 + my0, g.px - cx0 + mx0, '@', cp(5, True))
    bar = lambda v, m, n: '█' * int(n * max(0, v) / max(1, m)) + '░' * (n - int(n * max(0, v) / max(1, m)))
    put(win, 0, 0, f'♥{g.hp}/{s["hp"]} {bar(g.hp, s["hp"], 10)}', cp(2, True))
    put(win, 1, 0, f'✦{g.mana}/{s["mana"]} {bar(g.mana, s["mana"], 10)}', cp(5))
    hud = f'Lv{g.lvl} {g.where()}' + (f' ✚{g.points}' if g.points else '')
    put(win, 0, max(0, w - len(hud) - 1), hud, cp(4, True))
    put(win, 1, w - 22, f'xp {g.xp}/{int(18 * g.lvl ** 1.5)}  {getattr(g, "clock", "")}', curses.A_DIM)
    put(win, 2, w - PANEL if touch else w - 22, f'⚙{g.res["scrap"]} ✧{g.res["essence"]} ⚷{g.keys}', curses.A_DIM)
    nlog = 2 if touch else 3
    for i, m in enumerate(g.log[-nlog:]):
        put(win, h - nlog - (0 if touch else 2) + i, 0, m, curses.A_DIM if i < nlog - 1 else 0)
    if touch:
        y0 = h - 2 - 9
        for r, row in enumerate(PAD):
            for c, (lab, key) in enumerate(row):
                button(win, btns, y0 + 3 * r, 1 + 6 * c, 3, 6, [lab], key, curses.A_DIM if key != ord('.') else 0)
        button(win, btns, 2, 1, 3, 9, [f'HP x{g.cons.get("hp", 0)}'], ord('p'), cp(2, True) if g.cons.get('hp') and not g.potion_cd else curses.A_DIM)
        button(win, btns, 2, 10, 3, 9, [f'MP x{g.cons.get("mp", 0)}'], ord('o'), cp(5, True) if g.cons.get('mp') and not g.potion_cd else curses.A_DIM)
        button(win, btns, 2, 19, 3, 7, ['Map'], ord('M'), curses.A_DIM)
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
            on_stairs = key == ord('>') and g.g[g.py][g.px] in '><DF'
            button(win, btns, y1 + 8, w - PANEL + 5 * i, 3, 5, [lab], key, cp(4, True) if on_stairs else curses.A_DIM)
    else:
        sb = ''
        for i, k in enumerate(g.slots):
            sk = SKILLS[k]
            c = g.cd.get(k, 0)
            sb += f'{i + 1}:{sk["name"][:9]}{"(" + str(c) + ")" if c else "":<3}{g.eff_cost(k)} '
        put(win, h - 2, 0, sb, cp(7))
        put(win, h - 1, 0, 'hjklyubn move 1-4 skill i bag K skills t tree p/o potions > stairs', curses.A_DIM)
    win.refresh()


KEYS = {ord('h'): (-1, 0), ord('l'): (1, 0), ord('k'): (0, -1), ord('j'): (0, 1), curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0),
        curses.KEY_UP: (0, -1), curses.KEY_DOWN: (0, 1), ord('a'): (-1, 0), ord('d'): (1, 0), ord('w'): (0, -1), ord('s'): (0, 1),
        ord('y'): (-1, -1), ord('u'): (1, -1), ord('b'): (-1, 1), ord('n'): (1, 1)}


def rune_effect(g, rk):
    d = RUNES[rune_split(rk)[0]]
    txt = g.aff_text(d['stat'], rune_val(rk))
    return txt if d['kind'] == 'stat' else f'{d["tag"]} skills: {txt}'


def item_lines(g, it):
    if it['slot'] == 'gem':
        sk = SKILLS[it['skill']]
        return [(f'Skill gem: {sk["name"]}', cp(7, True)), (sk['desc'], 0), ('Tags: ' + ' '.join(sorted(sk['tags'])), curses.A_DIM)]
    out = [(it['name'], cp(RCOL[it['rarity']], True)), (f'{it["rarity"]} {ITEM_SUB.get(it.get("hands") or it.get("kind"), SLOTNAME[it["slot"]])} ilvl {it.get("ilvl", 1)}', curses.A_DIM)]
    out += [('  ' + g.aff_text(k, v), 0) for k, v in it['aff']]
    for rk in it.get('sockets', []):
        if rk:
            d = RUNES[rune_split(rk)[0]]
            out.append((f'  ◇ {rune_name(rk)}: ' + rune_effect(g, rk), cp(7)))
        else:
            out.append(('  ○ empty socket', curses.A_DIM))
    if it.get('power'):
        nm, fn = POWER_TEXT[it['power']]
        out.append((f'{"☀" if it["rarity"] == "mythic" else "★"} {nm}' + (' II' if it.get('rank', 1) > 1 else ''), cp(RCOL[it['rarity']], True)))
        out.append(('  ' + fn(it.get('rank', 1)), 0))
    return out


def scroll_top(sel, avail, n):
    return max(0, min(sel - avail + 1, n - avail)) if sel >= avail else 0


ITEM_SUB = {'2h': 'Two-hand weapon', '1h': 'One-hand weapon', 'shield': 'Shield', 'focus': 'Focus'}
TABS = [('Worn', 'worn'), ('Weap', 'weapon'), ('Armor', 'armor'), ('Amulet', 'charm'), ('Items', 'cons'), ('Keys', 'key'), ('Runes', 'rune'), ('Res', 'res')]
PAGE = 16


def bag_entries(g, tab):
    kind = TABS[tab][1]
    dim = curses.A_DIM
    if kind == 'worn':
        return [dict(kind='gear', worn=True, slot=sl, it=it, label=it['name'], attr=cp(RCOL[it['rarity']], True))
                for sl, it in g.equip.items() if it]
    if kind == 'rune':
        ks = sorted([k for k, n in g.runes.items() if n > 0], key=lambda k: (-rune_split(k)[1], k))
        return [dict(kind='rune', key=k, label=f'{rune_name(k)} x{g.runes[k]}', attr=cp(7, True),
                     lines=[(rune_name(k) + ' rune', cp(7, True)), (rune_effect(g, k), 0), (f'You have {g.runes[k]}', dim),
                            ('3 of the same fuse into 1 of the next tier.' + ('' if g.runes[k] >= 3 else ' (need 3)'), dim),
                            ('Socket them into gear from the Socket button.', dim)]) for k in ks]
    if kind in SLOTNAME:
        grp = TAB_GROUP.get(kind, (kind,))
        return [dict(kind='gear', idx=i, it=it, label=it['name'], attr=cp(RCOL[it['rarity']], True))
                for i, it in enumerate(g.pack) if it['slot'] in grp]
    if kind == 'cons':
        return [dict(kind='cons', key=k, label=f'{CONS[k][0]} x{g.cons.get(k, 0)}', attr=cp(4, True) if g.cons.get(k) else dim,
                     lines=[(CONS[k][0], cp(4, True)), (CONS[k][1], 0), (f'You have {g.cons.get(k, 0)}. Main screen: p = HP, o = MP', dim)])
                for k in CONS]
    if kind == 'key':
        return [dict(kind='key', label=f'Key x{g.keys}', attr=cp(4, True) if g.keys else dim,
                     lines=[('Dungeon Key', cp(4, True)), ('Walk into a locked chest (▣) to open it.', 0), ('Chests hold 2-3 better items.', dim),
                            ('Champions and bosses carry keys.', dim), (f'You have {g.keys}', dim)])]
    return [dict(kind='res', label=f'Scrap x{g.res["scrap"]}', attr=cp(1, True),
                 lines=[('Scrap', cp(1, True)), ('From kills and salvage.', 0), ('Pays for Reroll (refits gear to this depth) and Ascend.', dim), (f'You have {g.res["scrap"]}', dim)]),
            dict(kind='res', label=f'Essence x{g.res["essence"]}', attr=cp(6, True),
                 lines=[('Essence', cp(6, True)), ('From champions, bosses, legendary+ salvage.', 0), ('Needed for rerolling legendary+ gear and Ascend (40).', dim), (f'You have {g.res["essence"]}', dim)])]


FMODES = ['keep', 'salvage', 'hide']
FNAME = {'keep': 'KEEP', 'salvage': 'AUTO-SALVAGE', 'hide': 'HIDE'}
FDESC = {'keep': 'Drops on the floor for you to pick up.',
         'salvage': 'Never drops. Instantly becomes scrap.',
         'hide': 'Never drops. Gone, no scrap.'}


def menu_filter(win, g):
    armed = False
    while True:
        win.erase()
        h, w = win.getmaxyx()
        btns = []
        put(win, 0, 0, 'LOOT FILTER   tap a rarity to cycle. Legendary, mythic, unique, gems, keys, potions are never filtered.', cp(4, True))
        rows = [('normal', 'Normal'), ('magic', 'Magic'), ('rare', 'Rare')]
        for i, (r, lab) in enumerate(rows):
            act = g.filter.get(r, 'keep')
            button(win, btns, 2 + 4 * i, 1, 4, w // 2 - 2, [f'{lab}: {FNAME[act]}', FDESC[act][:w // 2 - 6]],
                   ord(r[0]), cp(RCOL[r], True) if act == 'keep' else curses.A_DIM)
        n = sum(1 for it in g.pack if g.filter.get(it['rarity'], 'keep') != 'keep')
        put(win, 2, w // 2 + 1, f'{n} item(s) in your bag match a clearing rule.')
        put(win, 3, w // 2 + 1, 'Sweep applies the rules to the bag now.' if not armed else 'Press Sweep again to confirm.', cp(4, True) if armed else curses.A_DIM)
        button(win, btns, 5, w // 2 + 1, 3, 16, ['Sweep now'], ord('s'), cp(2, True) if armed else curses.A_DIM)
        put(win, 9, w // 2 + 1, 'Changes apply to future drops at once.', curses.A_DIM)
        put(win, h - 4, 0, g.log[-1] if g.log else '', 0)
        button(win, btns, h - 3, 0, 3, w, ['Back'], 27, curses.A_DIM)
        win.refresh()
        c = getin(win, btns)
        if c == -1 or isinstance(c, tuple):
            continue
        if c != ord('s'):
            armed = False
        if c in (27, ord('q'), ord('f')):
            return
        for r, _ in rows:
            if c == ord(r[0]):
                g.filter[r] = FMODES[(FMODES.index(g.filter.get(r, 'keep')) + 1) % 3]
        if c == ord('s'):
            if not n:
                g.say('Nothing to sweep')
            elif not armed:
                armed = True
            else:
                armed = False
                k, sc = g.sweep()
                g.say(f'Swept {k} items (+{sc} scrap)')


def menu_socket(win, g, it):
    ssel, rsel, last_tap = 0, 0, None
    while True:
        win.erase()
        h, w = win.getmaxyx()
        half = w // 2
        btns = []
        socks = it.setdefault('sockets', [])
        ssel = min(ssel, max(0, len(socks) - 1))
        put(win, 0, 0, it['name'] + '   (tap a socket, tap a rune twice to insert)', cp(RCOL[it['rarity']], True))
        if socks:
            sw = min(16, w // len(socks))
            for i, rk in enumerate(socks):
                a = cp(7, True) if rk else curses.A_DIM
                if i == ssel:
                    a |= curses.A_REVERSE
                button(win, btns, 1, i * sw, 3, sw, [(rune_name(rk) if rk else 'empty')[:sw - 2]], 3000 + i, a)
        else:
            put(win, 2, 0, 'No sockets. Use Add socket.', curses.A_DIM)
        runes = sorted([(k, n) for k, n in g.runes.items() if n > 0], key=lambda kv: (-rune_split(kv[0])[1], kv[0]))
        nr = len(runes)
        rsel = min(rsel, max(0, nr - 1))
        avail = max(2, (h - 9) // 2)
        top = scroll_top(rsel, avail, nr)
        put(win, 4, 0, f'Runes ({nr} kinds)', curses.A_DIM)
        for i in range(top, min(nr, top + avail)):
            y = 5 + 2 * (i - top)
            k, n = runes[i]
            put(win, y, 0, ('>' if i == rsel else ' ') + f'{rune_name(k)} x{n}', cp(7, i == rsel))
            btns.append((y, 0, 2, half, 4000 + i))
        y = 5
        if socks and socks[ssel]:
            put(win, y, half + 1, f'In socket: {rune_name(socks[ssel])}', cp(7, True))
            put(win, y + 1, half + 1, rune_effect(g, socks[ssel]))
            y += 3
        if nr:
            put(win, y, half + 1, f'Selected: {rune_name(runes[rsel][0])}', cp(4, True))
            put(win, y + 1, half + 1, rune_effect(g, runes[rsel][0]))
        sc, es = g.socket_cost(it)
        put(win, h - 5, half + 1, f'Add socket: {sc} scrap + {es} ess', curses.A_DIM)
        put(win, h - 4, 0, g.log[-1] if g.log else '')
        defs = [('↑', ord('k')), ('↓', ord('j')), ('Insert', 10), ('Remove', ord('x')), ('Add socket', ord('a')), ('Back', 27)]
        bw = w // len(defs)
        for i, (lab, key) in enumerate(defs):
            button(win, btns, h - 3, i * bw, 3, bw, [lab], key, curses.A_DIM)
        win.refresh()
        c = getin(win, btns)
        if c == -1 or isinstance(c, tuple):
            continue
        if 3000 <= c < 3100:
            ssel = c - 3000
            continue
        if 4000 <= c < 4100:
            i = c - 4000
            if i == last_tap:
                c = 10
            else:
                rsel = last_tap = i
                continue
        if c in (27, ord('q')):
            return
        last_tap = None
        if c in (curses.KEY_DOWN, ord('j')) and nr:
            rsel = (rsel + 1) % nr
        elif c in (curses.KEY_UP, ord('k')) and nr:
            rsel = (rsel - 1) % nr
        elif c in (curses.KEY_LEFT, ord('h')) and socks:
            ssel = (ssel - 1) % len(socks)
        elif c in (curses.KEY_RIGHT, ord('l')) and socks:
            ssel = (ssel + 1) % len(socks)
        elif c in (10, 13) and socks and nr:
            rk, old = runes[rsel][0], socks[ssel]
            g.runes[rk] -= 1
            if old:
                g.runes[old] = g.runes.get(old, 0) + 1
            socks[ssel] = rk
            g.hp = min(g.hp, g.st('hp'))
        elif c == ord('x') and socks and socks[ssel]:
            g.runes[socks[ssel]] = g.runes.get(socks[ssel], 0) + 1
            socks[ssel] = None
            g.hp = min(g.hp, g.st('hp'))
        elif c == ord('a'):
            g.add_socket(it)


def menu_inv(win, g):
    tab, sel, last_tap, armed = 0, 0, None, None
    while True:
        win.erase()
        h, w = win.getmaxyx()
        half = w // 2
        ents = bag_entries(g, tab)
        n = len(ents)
        sel = min(sel, max(0, n - 1))
        page, pages = sel // PAGE, max(1, (n + PAGE - 1) // PAGE)
        btns = []
        tw = w // len(TABS)
        for i, (lab, kind) in enumerate(TABS):
            cnt = sum(1 for it in g.pack if it['slot'] in TAB_GROUP.get(kind, (kind,))) if kind in SLOTNAME else sum(1 for v in g.equip.values() if v) if kind == 'worn' else ''
            button(win, btns, 0, i * tw, 3, tw, [f'{lab} {cnt}'.strip()], 1000 + i, cp(4, True) if i == tab else curses.A_DIM)
        ch = max(1, min(3, (h - 7) // 4))
        cw = half // 4
        for sl in range(PAGE):
            gi = page * PAGE + sl
            y, x = 3 + (sl // 4) * ch, (sl % 4) * cw
            e = ents[gi] if gi < n else None
            a = (e['attr'] if e else curses.A_DIM) | (curses.A_REVERSE if gi == sel and e else 0)
            label = (e['label'] if e else '·')[:cw - 2]
            if ch >= 2:
                box(win, y, x, ch, cw, [label], a)
            else:
                put(win, y, x, label.center(cw - 1), a)
            btns.append((y, x, ch, cw, 2000 + sl))
        put(win, h - 4, 0, f'Page {page + 1}/{pages}  {n} slots', curses.A_DIM)
        if g.log:
            put(win, h - 4, half, g.log[-1], 0)
        e = ents[sel] if n else None
        y = 3
        if e:
            lines = e['lines'] if 'lines' in e else item_lines(g, e['it'])
            for t, at in lines[:h - 12]:
                put(win, y, half + 1, t[:w - half - 2], at)
                y += 1
            if e['kind'] == 'gear':
                it = e['it']
                sc, es = g.salvage_value(it)
                rc = g.reroll_cost(it)
                y = max(y + 1, h - 11)
                if not e.get('worn'):
                    put(win, y, half + 1, f'Salvage +{sc} scrap' + (f' +{es} ess' if es else ''), curses.A_DIM)
                if rc:
                    put(win, y + 1, half + 1, f'Reroll {rc[0]} scrap' + (f' + {rc[1]} ess' if rc[1] else '') + ' (refits to depth)', curses.A_DIM)
                if it['rarity'] == 'legend':
                    k = 1 + g.depth / 10
                    put(win, y + 2, half + 1, f'Ascend {int(400 * k)} scrap + 40 ess -> mythic', curses.A_DIM)
                eq = g.equip[g.equip_key(it)]
                if not e.get('worn'):
                    put(win, y + 3, half + 1, 'Equipped: ' + (eq['name'] if eq else '-'), cp(RCOL[eq['rarity']]) if eq else curses.A_DIM)
        bw = w // 7
        defs = [('Pg◀', ord(',')), ('Pg▶', ord('.'))]
        if e and e['kind'] == 'gear' and e.get('worn'):
            defs += [('Unequip', 10), ('Socket', ord('o')), ('Reroll', ord('r')), ('Ascend', ord('a'))]
        elif e and e['kind'] == 'gear':
            defs += [('Equip', 10), ('Socket', ord('o')), ('Salvage', ord('v')), ('Reroll', ord('r')), ('Ascend', ord('a'))]
        elif e and e['kind'] == 'cons':
            defs += [('Use', 10)]
        elif e and e['kind'] == 'rune':
            defs += [('Fuse', 10)]
        defs += [('Filter', ord('f')), ('Back', 27)]
        bw = w // len(defs)
        for i, (lab, key) in enumerate(defs):
            button(win, btns, h - 3, i * bw, 3, bw, [lab], key, curses.A_DIM)
        win.refresh()
        c = getin(win, btns)
        if c == -1 or isinstance(c, tuple):
            continue
        if 1000 <= c < 1000 + len(TABS):
            tab, sel, last_tap, armed = c - 1000, 0, None, None
            continue
        if 2000 <= c < 2000 + PAGE:
            gi = page * PAGE + (c - 2000)
            if gi < n:
                if last_tap == gi:
                    c = 10
                else:
                    last_tap, sel, armed = gi, gi, None
                    continue
            else:
                continue
        if c in (27, ord('q'), ord('i')):
            return
        if c == ord('f'):
            menu_filter(win, g)
            continue
        if c in (curses.KEY_LEFT, ord('h')):
            sel = max(0, sel - 1)
        elif c in (curses.KEY_RIGHT, ord('l')):
            sel = min(max(0, n - 1), sel + 1)
        elif c in (curses.KEY_UP, ord('k')):
            sel = max(0, sel - 4)
        elif c in (curses.KEY_DOWN, ord('j')):
            sel = min(max(0, n - 1), sel + 4)
        elif c == ord(','):
            sel = max(0, sel - PAGE)
        elif c == ord('.'):
            sel = min(max(0, n - 1), sel + PAGE)
        elif e and c in (10, 13):
            last_tap = None
            if e['kind'] == 'gear' and e.get('worn'):
                g.unequip(e['slot'])
            elif e['kind'] == 'gear':
                g.equip_item(e['idx'])
            elif e['kind'] == 'cons':
                g.use_cons(e['key'])
            elif e['kind'] == 'rune':
                g.fuse(e['key'])
        elif e and e['kind'] == 'gear' and c == ord('o'):
            menu_socket(win, g, e['it'])
        elif e and e['kind'] == 'gear' and not (e.get('worn') and c == ord('v')) and c in (ord('v'), ord('r'), ord('a')):
            it = e['it']
            if it['rarity'] in ('rare', 'legend', 'mythic', 'unique') and armed != (c, sel):
                armed = (c, sel)
                g.say(f'Press {chr(c).upper()} / the same button again to confirm on {it["name"]}')
                continue
            armed = None
            if c == ord('v'):
                g.salvage(e['idx'])
            elif c == ord('r'):
                g.reroll(it)
            else:
                g.ascend(it)


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


def edge_cells(ya, xa, yb, xb):
    """Cells of a line between two nodes: one glyph per row (steep) or per column (shallow), a terminal cell being ~1x2."""
    dx, dy = xb - xa, yb - ya
    slash = '╲' if dx * dy > 0 else '╱'
    out = []
    if abs(dy) * 2 >= abs(dx):
        n = abs(dy)
        xs = [round(xa + dx * i / n) for i in range(n + 1)] if n else [xa]
        for i in range(1, n):
            out.append((ya + (i if dy > 0 else -i), xs[i], '│' if xs[i - 1] == xs[i] == xs[i + 1] else slash))
    else:
        n = abs(dx)
        ys = [round(ya + dy * i / n) for i in range(n + 1)]
        for i in range(1, n):
            out.append((ys[i], xa + (i if dx > 0 else -i), '─' if ys[i - 1] == ys[i] == ys[i + 1] else slash))
    return out


def menu_tree(win, g, key=None):
    tr = tree_of(key)
    cur = (0, 0)
    armed = False
    zoom = 1   # 1 = 2x1 cells per grid step (whole shape), 2 = 4x2 (readable)
    kglyph = {'minor': '○', 'notable': '◈', 'key': '★', 'gate': '◆', 'origin': '◉'}
    while True:
        win.erase()
        h, w = win.getmaxyx()
        if key:
            m = g.mas(key)
            alloc, pts, take = m['alloc'], m['points'], lambda p: g.take_skill(key, p)
            title = f'{SKILLS[key]["name"].upper()} MASTERY lv{m["lvl"]} ({m["xp"]}/{int(6 * (m["lvl"] + 1) ** 1.5)})'
        else:
            alloc, pts, take, title = g.alloc, g.points, g.take, 'CLASS PATHS'
        put(win, 0, 0, f'{title}  points:{pts}  tap a node to focus, tap it again to take', cp(4, True))
        fr = g.frontier(alloc, key)
        cx, cy = cur
        ox, oy = w // 2, (h - 8) // 2 + 1
        top, bot = 1, h - 8
        sxs, sys_ = 2 * zoom, zoom
        scr = lambda p: (oy + (p[1] - cy) * sys_, ox + (p[0] - cx) * sxs)
        for a, b in tr.edges:
            (ya, xa), (yb, xb) = scr(a), scr(b)
            if max(ya, yb) < top or min(ya, yb) > bot or max(xa, xb) < 0 or min(xa, xb) > w - 1:
                continue
            at = cp(3) if a in alloc and b in alloc else curses.A_DIM
            for y, x, ch in edge_cells(ya, xa, yb, xb):
                if top <= y <= bot and 0 <= x < w - 1:
                    put(win, y, x, ch, at)
        for p, nd in tr.n.items():
            y, x = scr(p)
            if not (top <= y <= bot and 0 <= x < w - 1):
                continue
            col = CLS_COL[nd['cls']] if nd['cls'] is not None else 1
            if p in alloc:
                ch, a = '◉', cp(3, True)
            elif p in fr:
                ch, a = kglyph[nd['kind']], cp(col, True)
            elif g.locked(tr, alloc, p):
                ch, a = '✕', cp(2) | curses.A_DIM
            else:
                ch, a = kglyph[nd['kind']], curses.A_DIM
            if p == cur:
                a |= curses.A_REVERSE
            put(win, y, x, ch, a)
        n = tr.n[cur]
        shut = [tr.n[e]['name'] for e in n['excl'] if e in alloc]
        state = 'taken' if cur in alloc else 'available' if cur in fr else f'closed by {", ".join(shut)}' if shut else 'unreachable (take the path to it first)'
        cn = f' · {CLASSES[n["cls"]][0]}' if not key and n['cls'] is not None else ''
        put(win, h - 6, 0, f'{n["name"]} [{n["kind"]}{cn}] {state}' + ('   Reset again to confirm (free)' if armed else ''), cp(4, True))
        put(win, h - 5, 0, ', '.join(g.aff_text(k, v) for k, v in n['stats'].items()))
        if n['excl'] and cur not in alloc:
            put(win, h - 7, 0, 'Taking this closes: ' + ', '.join(tr.n[e]['name'] for e in sorted(n['excl'])), cp(2))
        btns = menu_bar(win, [('←', ord('h')), ('↑', ord('k')), ('↓', ord('j')), ('→', ord('l')), ('Take', 10), ('Untake', ord('x')),
                              ('Zoom', ord('z')), ('Reset' if not armed else 'SURE?', ord('r')), ('Back', 27)])
        win.refresh()
        c = getin(win, btns)
        if c != ord('r') and c != -1:
            armed = False
        if c == ord('z'):
            zoom = 3 - zoom
            continue
        if c == ord('r'):
            if armed:
                n = g.respec(key)
                g.say(f'Respec: {n} points refunded')
            armed = not armed
            continue
        if c == ord('x'):
            if g.untake(alloc, cur, key):
                if key:
                    g.mas(key)['points'] += 1
                else:
                    g.points += 1
                    g.hp = min(g.hp, g.st('hp'))
            continue
        if isinstance(c, tuple):
            ty, tx = c[1], c[2]
            if 1 <= ty < h - 7:
                wx, wy = cx + (tx - ox) / sxs, cy + (ty - oy) / sys_
                near = min(tr.n, key=lambda p: (p[0] - wx) ** 2 + (p[1] - wy) ** 2)
                if (near[0] - wx) ** 2 + (near[1] - wy) ** 2 <= 2.5:
                    if near == cur:
                        if not take(cur):
                            g.say('Cannot take that')
                    else:
                        cur = near
            continue
        if c in (27, ord('q'), ord('t')):
            return
        if c in KEYS:
            dx, dy = KEYS[c]
            best, bs = None, 1e9
            for p in tr.n:
                vx, vy = p[0] - cx, p[1] - cy
                dot = vx * dx + vy * dy
                if dot <= 0:
                    continue
                nn = math.hypot(dx, dy)
                perp = abs(vx * dy - vy * dx) / nn
                sc = math.hypot(vx, vy) + 2 * perp
                if sc < bs:
                    best, bs = p, sc
            if best:
                cur = best
        elif c in (10, 13):
            if not take(cur):
                g.say('Cannot take that' + (' - closed by another choice' if g.locked(tr, alloc, cur) else ''))


def menu_world(win, g):
    while True:
        win.erase()
        h, w = win.getmaxyx()
        ch = 3 if h >= ZH * 3 + 8 else 2
        cw = 6
        ox, oy = max(0, (w - ZW * cw) // 2), 2
        put(win, 0, 0, 'WORLD MAP   tap to close', cp(4, True))
        known = set(g.visited)
        for pos in g.visited:
            for d in g.zones[pos]['links']:
                known.add((pos[0] + DIRS[d][0], pos[1] + DIRS[d][1]))
        for pos, z in g.zones.items():
            if pos not in known:
                continue
            cy_, cx_ = oy + pos[1] * ch + ch // 2, ox + pos[0] * cw + 1
            seen_ = pos in g.visited
            if pos == g.zpos:
                lab, a = ' @', cp(5, True)
            elif not seen_:
                lab, a = ' ?', curses.A_DIM
            elif z['kind'] == 'camp':
                lab, a = ' C', cp(3, True)
            else:
                lab, a = f'{z["level"]:>2}', cp(1)
            put(win, cy_, cx_, lab, a)
            if seen_ and z['dungeon']:
                put(win, cy_, cx_ + 2, 'D', cp(2, True))
            for d, (sx, sy) in (('E', (cx_ + 3, cy_)), ('S', (cx_ + 1, cy_ + 1))):
                if d in z['links'] and (seen_ or (pos[0] + DIRS[d][0], pos[1] + DIRS[d][1]) in g.visited):
                    put(win, sy, sx, '──' if d == 'E' else '│', curses.A_DIM)
        z = g.zone
        put(win, oy + ZH * ch + 1, 0, f'{z["name"]} (lvl {z["level"]})' + (f' - {z["dungeon"]["name"]}, {z["dungeon"]["floors"]} floors' if z['dungeon'] else ''), cp(4, True))
        put(win, oy + ZH * ch + 2, 0, '@ you   C camp (safe, rest at the fire)   D dungeon   numbers = zone level', curses.A_DIM)
        win.refresh()
        c = getin(win, [])
        if c != -1:
            return


def run(win):
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    for i, c in enumerate([curses.COLOR_WHITE, curses.COLOR_RED, curses.COLOR_GREEN, curses.COLOR_YELLOW, curses.COLOR_BLUE,
                           curses.COLOR_MAGENTA, curses.COLOR_CYAN], 1):
        curses.init_pair(i, c, -1)
    # the phone's nav bar overlays the bottom rows; GF_MARGIN (set by glyphfall-touch) keeps the UI above it
    scr, margin = win, int(os.environ.get('GF_MARGIN', '0'))

    def mkwin():
        h, w = scr.getmaxyx()
        ww = scr.derwin(max(12, h - margin), w, 0, 0) if margin else scr
        ww.keypad(True)
        ww.timeout(20000)
        return ww

    win = mkwin()
    curses.mouseinterval(0)
    curses.mousemask(curses.BUTTON1_PRESSED | curses.BUTTON1_CLICKED | curses.BUTTON1_RELEASED)
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
        if margin and win.getmaxyx() != (max(12, scr.getmaxyx()[0] - margin), scr.getmaxyx()[1]):
            scr.clear()
            win = mkwin()
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
        elif c in (ord('p'), ord('o')):
            used = g.use_cons('hp' if c == ord('p') else 'mp')
        elif c == ord('i'):
            menu_inv(win, g)
        elif c == ord('K'):
            menu_skills(win, g)
        elif c == ord('t'):
            menu_tree(win, g)
        elif c == ord('M'):
            menu_world(win, g)
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

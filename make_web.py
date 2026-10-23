#!/usr/bin/env python3
"""Build the browser (pygbag/WASM) variant of glyphfall into ./web.

The browser cannot block, so every function that waits for a key is turned into a coroutine
(getin/getch seeds, then every caller, transitively) and every call to one gets an `await`.
The desktop sources are not touched.
"""
import ast
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'web')
SEEDS = {'getin', 'getch'}
FILES = {'glyphfall.py': set(), 'glyphfall_gui.py': {'fn'}}   # file -> extra awaited call names


def call_name(c):
    f = c.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


def asyncify(trees, extra):
    names = set(SEEDS)
    while True:
        grown = False
        for fname, tree in trees.items():
            for fn in ast.walk(tree):
                if isinstance(fn, ast.FunctionDef) and fn.name not in names:
                    calls = {call_name(c) for c in ast.walk(fn) if isinstance(c, ast.Call)}
                    if calls & (names | extra[fname]):
                        names.add(fn.name)
                        grown = True
        if not grown:
            return names


def rewrite(src, tree, names, extra):
    lines = [l.encode() for l in src.splitlines(keepends=True)]
    edits = []   # (line, col, text_to_insert, chars_to_remove)
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name in names:
            edits.append((n.lineno, n.col_offset, b'async ', 0))
        elif isinstance(n, ast.Call) and call_name(n) in names | extra:
            edits.append((n.lineno, n.col_offset, b'await ', 0))
    for ln, col, txt, _ in sorted(edits, reverse=True):
        l = lines[ln - 1]
        lines[ln - 1] = l[:col] + txt + l[col:]
    return b''.join(lines).decode()


def sub(src, old, new, count=1):
    if src.count(old) != count:
        sys.exit(f'patch target not found {src.count(old)}x (want {count}): {old[:60]!r}')
    return src.replace(old, new)


def main():
    srcs = {f: open(os.path.join(HERE, f), encoding='utf8').read() for f in FILES}
    trees = {f: ast.parse(s) for f, s in srcs.items()}
    names = asyncify(trees, FILES)
    out = {f: rewrite(srcs[f], trees[f], names, FILES[f]) for f in FILES}

    gl = out['glyphfall.py']
    gl = sub(gl, "SAVE = os.path.expanduser('~/.local/share/glyphfall/save.json')",
             "SAVE = ('/data/data/glyphfall/save.json' if sys.platform == 'emscripten'   # pygbag persists /data in IndexedDB\n        else os.path.expanduser('~/.local/share/glyphfall/save.json'))")

    gui = out['glyphfall_gui.py']
    gui = sub(gui, 'import curses\n', 'import curses\nimport asyncio\n')
    gui = sub(gui, "hits = glob.glob(f'/usr/share/fonts/**/{name}', recursive=True)",
              "hits = glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), name))")
    gui = sub(gui, """            e = pygame.event.wait(int(min(rem, 0.25) * 1000) + 1)
            if e.type == pygame.NOEVENT:
                continue
""", """            pend = self.__dict__.setdefault('pend', [])
            if not pend:
                await asyncio.sleep(0.016)
                pend.extend(pygame.event.get())
                if not pend:
                    continue
            e = pend.pop(0)
""")
    gui = sub(gui, "self.screen = pygame.display.set_mode((w, h))", "self.screen = pygame.display.set_mode((w, h), pygame.SCALED)")
    gui = sub(gui, "win = os.environ.get('GF_WINDOW')", "win = os.environ.get('GF_WINDOW') or '1170x540'")
    gui = sub(gui, "            self.clock.tick(60)\n", "            self.clock.tick(60)\n            await asyncio.sleep(0)\n")
    gui = sub(gui, "    await App().run()", "    asyncio.run(App().run())")

    os.makedirs(OUT, exist_ok=True)
    for f, s in (('glyphfall.py', gl), ('main.py', gui)):
        open(os.path.join(OUT, f), 'w', encoding='utf8').write(s)
        compile(s, f, 'exec')
    shutil.copy(os.path.join(HERE, 'web_curses.py'), os.path.join(OUT, 'curses.py'))
    for font in ('DejaVuSansMono.ttf', 'DejaVuSans.ttf'):
        shutil.copy('/usr/share/fonts/dejavu/' + font, OUT)
    print('async:', ', '.join(sorted(names)))


main()

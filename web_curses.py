"""Constants-only curses stand-in for the browser build (the GUI draws its own grid)."""
A_BOLD, A_DIM, A_REVERSE = 0x200000, 0x100000, 0x40000
BUTTON1_PRESSED, BUTTON1_CLICKED = 0x2, 0x4
KEY_DOWN, KEY_UP, KEY_LEFT, KEY_RIGHT, KEY_MOUSE = 258, 259, 260, 261, 409
COLOR_BLACK, COLOR_RED, COLOR_GREEN, COLOR_YELLOW, COLOR_BLUE, COLOR_MAGENTA, COLOR_CYAN, COLOR_WHITE = range(8)


class error(Exception):
    pass

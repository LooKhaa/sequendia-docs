#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
coucou-fedora 3.5 — « l'île » pour agents IA (Hermes…), pensée pour Fedora + GNOME + Wayland.

Inspiré du principe de https://github.com/Louis-CFM/coucou mais réécrit de zéro, en un seul fichier.
Le nom « Coucou » et Mochi appartiennent à leur auteur : donne ton propre nom/personnage à ta version.

L'île reste RÉTRACTÉE en petite encoche sous la barre GNOME ; un clic, une notification ou une demande
d'approbation la déploie (ressorts, particules, sons synthétisés), puis elle se rétracte seule.

IA LOCALE (Ollama, ex. Qwen) pour : questions, résumé/traduction du presse-papiers, bilan, brief, priorités.
« BONJOUR ! » : résumé du matin (Thunderbird + agendas Google + actus + tâches) lu à voix haute ; micro pour parler à Qwen.
PROFILS HERMES : état d'avancement, questions ciblées (@profil …), Mochi à la couleur du profil.
HERMES : approbations de commandes (plugin) + suivi du Kanban.   kDrive : dossier local synchronisé.

COMMANDES : (rien) lance l'île · prompt (barre magique, à lier à un raccourci) · demo · doctor · init-config
            install-hermes · install-autostart · ask "texte" · remind 10m "pâtes" · focus [min] · todo "texte"
            calm [breath|eye] · watch <commande…> · bonjour · mic · toggle · quit · status
CONFIG    : ~/.config/coucou-fedora/config.toml      EXTENSIONS : ~/.config/coucou-fedora/plugins/*.py (`setup(core, cfg)`)
SÉCURITÉ  : socket dans $XDG_RUNTIME_DIR (ton utilisateur uniquement). Réseau : Ollama local, Open-Meteo (si ville renseignée),
            pochette d'album, commandes locales nmcli/tailscale.
"""
from __future__ import annotations

import argparse
import collections
import colorsys
import configparser
import datetime as dt
import email
import email.policy
import email.utils
import hashlib
import html
import json
import math
import os
import pathlib
import random
import re
import shutil
import socket
import sqlite3
import socketserver
import struct
import subprocess
import sys
import threading
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
import xml.etree.ElementTree as ET
import zoneinfo

VERSION = "3.5"
APP = "coucou-fedora"
HOME = pathlib.Path.home()
CONF_DIR = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / APP
DATA_DIR = pathlib.Path(os.environ.get("XDG_DATA_HOME", HOME / ".local/share")) / APP
CACHE_DIR = pathlib.Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / APP
RUNTIME = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR") or f"/tmp/{APP}-{os.getuid()}")
SOCK = pathlib.Path(os.environ.get("COUCOU_SOCK") or RUNTIME / "coucou-fedora.sock")

# ════════════════════════════════════════════════════════════════════════════
#  1. CONFIGURATION PAR DÉFAUT (`init-config` l'écrit dans ~/.config/coucou-fedora/config.toml)
# ════════════════════════════════════════════════════════════════════════════
DEFAULT_TOML = r'''
# ───────────────────────── Île ─────────────────────────
[island]
backend          = "x11"    # "x11" = XWayland (seul moyen de se placer en haut sous GNOME) | "auto"
y_offset         = 32       # px depuis le haut : 32 = juste sous la barre GNOME (ajuste selon ton échelle)
x_offset         = 0
monitor          = "primary"
width_open       = 520
width_mini       = 96
hover_open       = true     # s'ouvre au survol (après hover_delay) ; sinon clic uniquement
hover_delay      = 0.35
auto_close_after = 6        # secondes avant de se rétracter quand on ne la touche plus
toast_seconds    = 5
max_sessions     = 4

[theme]
font     = "Sans"
bg       = "#050507"        # noir presque pur : l'île se fond dans la barre GNOME
surface  = "#14171f"
surface2 = "#1d222d"
text     = "#eef1f6"
dim      = "#8a93a6"
accent   = "#7aa2ff"
ok       = "#4fd6a0"
warn     = "#ffb454"
danger   = "#ff6b7d"
mochi    = "#ffd3e4"

# Sons synthétisés par le programme (rien à installer). Remplacer un son : [sounds.files] approval = "/chemin/son.wav"
[sounds]
enabled = true
volume  = 0.55
hover   = true              # petit « tic » au survol des boutons
player  = ["pw-play", "{file}"]
[sounds.files]

# ───────────────────────── Approbations ─────────────────────────
[approvals]
ask_tools          = ["Bash", "Write", "Edit", "MultiEdit", "NotebookEdit"]
timeout_seconds    = 90
on_timeout         = "ask"
gnome_notification = true

# Radar de risque : score 0-100 par commande
[radar]
enabled = true
hold_at = 70
hold_seconds = 1.2
deny_at = 0

[[radar.rules]]
name = "rm sur / ou ~"
pattern = '\brm\s+(-\S+\s+)*(/|~|\$HOME)(\s|$)'
score = 100
[[radar.rules]]
name = "écriture disque brut"
pattern = '\bdd\s+.*of=/dev/|\bmkfs(\.\w+)?\b|>\s*/dev/(sd|nvme|vd)'
score = 100
[[radar.rules]]
name = "fork bomb"
pattern = ':\(\)\s*\{'
score = 100
[[radar.rules]]
name = "SELinux désactivé"
pattern = '\bsetenforce\s+0|SELINUX=(disabled|permissive)'
score = 85
[[radar.rules]]
name = "réseau vers shell"
pattern = '(curl|wget)[^|;]*\|\s*(sudo\s+)?(ba|z|da)?sh\b'
score = 90
[[radar.rules]]
name = "push forcé"
pattern = '\bgit\s+push\b.*(--force|\s-f\b)'
score = 75
[[radar.rules]]
name = "retrait de paquets"
pattern = '\bdnf5?\s+(remove|erase|autoremove)\b|\brpm\s+-e\b|\brpm-ostree\s+(uninstall|reset)'
score = 70
[[radar.rules]]
name = "secrets"
pattern = '\.ssh/|\.gnupg|\.aws/|id_(rsa|ed25519)|\.env\b|credentials|\.kube/config'
score = 70
[[radar.rules]]
name = "rm récursif/forcé"
pattern = '\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*'
score = 70
[[radar.rules]]
name = "git destructif"
pattern = '\bgit\s+(reset\s+--hard|clean\s+-\w*f)'
score = 65
[[radar.rules]]
name = "sudo"
pattern = '\bsudo\b'
score = 60
[[radar.rules]]
name = "pare-feu / services"
pattern = '\bfirewall-cmd\b.*--(remove|reload)|\bsystemctl\s+(stop|disable|mask)\b'
score = 55
[[radar.rules]]
name = "permissions larges"
pattern = '\bchmod\s+(-R\s+)?[0-7]*777|\bchown\s+-R'
score = 55
[[radar.rules]]
name = "kill"
pattern = '\b(pkill|killall)\b|\bkill\s+-9'
score = 40

# Verrou-parachute : session verrouillée = demandes refusées
[lock]
enabled              = true
decision_when_locked = "deny"
summary_on_return    = true

# ───────────────────────── Musique (Tidal via MPRIS) ─────────────────────────
[music]
enabled               = true
player_match          = "tidal"
mpris_name            = ""
poll_ms               = 1000
toast_on_track_change = true

# DJ Mochi : baisse la musique quand un agent te réclame
[ducking]
enabled       = true
level         = 30
match         = ["tidal"]
restore_delay = 2.0

# ───────────────────────── Dépôt kDrive = dossier local synchronisé par l'appli kDrive ─────────────────────────
[depot]
enabled            = true
folder             = "/home/luca/kDrive/Coucou_depot"
copy_dropped       = true            # glisser un fichier sur l'île le copie dans le dépôt
journal_copy       = true            # le carnet de bord du jour est copié dans <dépôt>/Journal
screenshot_dirs    = ["~/Images/Captures d'écran", "~/Pictures/Screenshots"]

[journal]
enabled = true
dir     = "~/.local/share/coucou-fedora/journal"

# ───────────────────────── IA locale : Ollama ─────────────────────────
[ollama]
enabled         = true
url             = "http://127.0.0.1:11434"
model           = ""                 # vide = détecte un modèle dont le nom contient model_match
model_match     = "qwen"
keep_alive      = "30m"
think           = false              # désactive le « raisonnement » des modèles Qwen3 (réponses plus rapides)
temperature     = 0.4
timeout_seconds = 180
system          = "Tu es Coucou, un assistant local. Réponds en français, de façon brève et directe, sans préambule, sauf demande contraire."

[[ollama.prompts]]
label  = "Idée du jour"
prompt = "Propose-moi une idée de petit projet ou d'amélioration à faire aujourd'hui sur mon ordinateur, en 3 lignes."

[[ollama.clip_actions]]
label  = "Résumer"
prompt = "Résume ce texte en 3 lignes :\n\n{clip}"
[[ollama.clip_actions]]
label  = "Traduire"
prompt = "Traduis ce texte (en français s'il est dans une autre langue, sinon en anglais). Donne uniquement la traduction :\n\n{clip}"
[[ollama.clip_actions]]
label  = "Corriger"
prompt = "Corrige l'orthographe et la grammaire de ce texte. Donne uniquement le texte corrigé :\n\n{clip}"
[[ollama.clip_actions]]
label  = "Reformuler"
prompt = "Reformule ce texte de façon claire et polie. Donne uniquement la version reformulée :\n\n{clip}"
[[ollama.clip_actions]]
label  = "Expliquer"
prompt = "Explique simplement ce texte ou ce code :\n\n{clip}"

# ───────────────────────── Hermes : approbations (plugin) + suivi Kanban ─────────────────────────
[hermes]
enabled             = true
kanban              = true
kanban_poll_seconds = 3
home                = "~/.hermes"
bin                 = ""             # chemin de la commande hermes (vide = détection automatique)

# ───────────────────────── Fonctions du quotidien ─────────────────────────
[focus]
minutes = [25, 45]
dnd     = true

[timers]
presets_minutes = [5, 10, 15]

[health]
battery_warn = 15
battery_ok   = 20

[network]
enabled = true

[clipboard]
enabled       = true         # historique du presse-papiers (en mémoire seulement, jamais écrit sur disque) — modifiable dans l'onglet Outils
guard         = true         # garde-secrets : détecte une clé API / un jeton copié et efface le presse-papiers après guard_seconds
guard_seconds = 30
max_items     = 8
max_chars     = 2000

[inhibit]
enabled = true

[stats]
enabled = true

[wellness]                   # pause yeux 20-20-20, respiration guidée, rappel d'hydratation
eye_break     = true
eye_minutes   = 20
eye_seconds   = 20
water         = true
water_minutes = 60
breath_seconds = 60

[calls]                      # mode appel automatique : micro utilisé par une appli → silence + musique en pause
enabled     = true
dnd         = true
pause_music = true
ignore      = ["speech-dispatcher", "coucou"]

[weather]                    # météo Open-Meteo (sans clé). Renseigne ta ville pour l'activer.
enabled = true
city    = ""
refresh_minutes = 30

# ───────────────────────── Bonjour ! : résumé du matin ─────────────────────────
[bonjour]
enabled        = true
autoplay_voice = false       # lit le résumé à voix haute dès qu'il est prêt
nudge          = true        # propose le résumé une fois chaque matin
agenda_days    = 2           # aujourd'hui + demain

[bonjour.mail]               # Thunderbird (lecture des boîtes de réception locales)
enabled     = true
hours       = 48
profile_dir = ""             # vide = profil par défaut détecté (~/.thunderbird, Flatpak, snap)
max_mails   = 15
tail_mb     = 6

# Agendas Google : Paramètres de l'agenda → « Intégrer l'agenda » → « Adresse secrète au format iCal ». Un bloc par agenda :
# [[bonjour.calendars]]
# name = "Perso"
# url  = "https://calendar.google.com/calendar/ical/.../private-.../basic.ics"

[[bonjour.feeds]]
category = "monde"
url      = "https://www.franceinfo.fr/monde.rss"
[[bonjour.feeds]]
category = "france"
url      = "https://www.franceinfo.fr/france.rss"
[[bonjour.feeds]]
category = "france"
url      = "https://www.franceinfo.fr/politique.rss"
[[bonjour.feeds]]
category = "tech"
url      = "https://www.franceinfo.fr/internet.rss"
[[bonjour.feeds]]
category = "tech"
url      = "https://www.numerama.com/feed/"
[[bonjour.feeds]]
category = "sport"
url      = "https://www.franceinfo.fr/sports.rss"

# ───────────────────────── Voix : lecture du résumé + micro ─────────────────────────
[voice]
lang                 = "fr"
wyoming_tts          = "127.0.0.1:10200"   # Piper en conteneur (protocole Wyoming) — ignoré s'il ne répond pas
wyoming_voice        = ""
piper_bin            = "piper"
piper_model          = ""                  # chemin d'un modèle .onnx pour Piper local (facultatif)
espeak_voice         = "fr"                # repli : espeak-ng (voix robotique)
rate                 = 165
wyoming_stt          = "127.0.0.1:10300"   # Whisper en conteneur (protocole Wyoming)
faster_whisper_model = "small"             # utilisé si le module faster-whisper est installé
whisper_cpp_bin      = "whisper-cli"
whisper_cpp_model    = ""
max_seconds          = 60

# Actions rapides (onglet Outils). kind : shell | dark_mode | night_light | open_depot
[[actions]]
label = "Verrouiller"
kind  = "shell"
cmd   = ["loginctl", "lock-session"]
[[actions]]
label = "Mode sombre"
kind  = "dark_mode"
[[actions]]
label = "Lumière nocturne"
kind  = "night_light"
[[actions]]
label = "Dépôt"
kind  = "open_depot"
[[actions]]
label = "Tidal"
kind  = "shell"
cmd   = ["flatpak", "run", "com.mastermindzh.tidal-hifi"]
'''


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_config(path: pathlib.Path | None = None) -> dict:
    cfg = tomllib.loads(DEFAULT_TOML)
    p = path or CONF_DIR / "config.toml"
    if p.exists():
        try:
            cfg = deep_merge(cfg, tomllib.loads(p.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"[coucou] config invalide ({p}) : {e} — valeurs par défaut utilisées", file=sys.stderr)
    return cfg


# ════════════════════════════════════════════════════════════════════════════
#  2. OUTILS GÉNÉRAUX
# ════════════════════════════════════════════════════════════════════════════
def short(s, n=90):
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def run(cmd: list[str], timeout: float = 3.0) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout
    except Exception:
        return ""


def parse_dur(s: str) -> int:
    m = re.fullmatch(r"(\d+)\s*([smh]?)", s.strip().lower())
    if not m:
        raise ValueError(f"durée invalide : {s!r} (ex. 90s, 10m, 1h)")
    return int(m[1]) * {"s": 1, "m": 60, "h": 3600, "": 60}[m[2]]


def fmt_time(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


# ---- Sons synthétisés : petit moteur (oscillateurs, bruit filtré, cloches, réverbération) ----------------
SR = 32000
TWO_PI = 2 * math.pi


def _tone(f, dur, g=1.0, kind="soft", glide=None, dec=5.0, att=0.004, vib=0.0):
    n = int(dur * SR)
    out, ph = [0.0] * n, 0.0
    for i in range(n):
        fr = f if glide is None else f + (glide - f) * (i / n)
        if vib:
            fr *= 1 + vib * math.sin(TWO_PI * 6 * i / SR)
        ph += TWO_PI * fr / SR
        if kind == "sine":
            s = math.sin(ph)
        elif kind == "tri":
            s = (2 / math.pi) * math.asin(math.sin(ph))
        else:
            s = math.sin(ph) + 0.28 * math.sin(2 * ph) + 0.1 * math.sin(3 * ph)
        out[i] = g * s * min(1.0, i / (att * SR)) * math.exp(-dec * i / n)
    return out


def _bell(f, dur, g=1.0):
    n = int(dur * SR)
    out = [0.0] * n
    for mult, amp, dec in ((1, 1.0, 1.0), (2.0, 0.40, 1.5), (2.76, 0.20, 2.2), (5.4, 0.08, 3.2)):
        w, k = TWO_PI * f * mult / SR, 7.0 * dec / dur
        for i in range(n):
            out[i] += g * amp * math.sin(w * i) * min(1.0, i / (0.004 * SR)) * math.exp(-k * i / SR)
    return out


def _noise(dur, g, lo, hi, shape=1.0):
    """Bruit filtré dont la fréquence de coupure glisse de lo à hi (effet « swoosh »)."""
    n, y = int(dur * SR), 0.0
    rnd = random.Random(7)
    out = [0.0] * n
    for i in range(n):
        fc = lo + (hi - lo) * (i / n)
        a = 1 - math.exp(-TWO_PI * fc / SR)
        y += a * (rnd.uniform(-1, 1) - y)
        out[i] = g * y * (math.sin(math.pi * i / n) ** shape) * 2.2
    return out


def _mix(parts):
    total = max(int(st * SR) + len(b) for st, b in parts)
    buf = [0.0] * total
    for st, b in parts:
        i0 = int(st * SR)
        for i, v in enumerate(b):
            buf[i0 + i] += v
    return buf


def _reverb(buf, mix=0.22):
    tail = int(0.5 * SR)
    src = buf + [0.0] * tail
    out = list(src)
    for delay, fb in ((0.0297, 0.52), (0.0371, 0.47), (0.0411, 0.43), (0.0537, 0.38)):
        d = int(delay * SR)
        comb = list(src)
        for i in range(d, len(comb)):
            comb[i] += fb * comb[i - d]
        for i in range(len(out)):
            out[i] += mix * 0.5 * comb[i]
    return out


def _seq(notes, kind="bell", step=0.07, dur=0.8, g=0.7):
    return _mix([(i * step, _bell(f, dur, g) if kind == "bell" else _tone(f, dur, g, "soft", dec=4)) for i, f in enumerate(notes)])


SOUNDS = {   # nom → (fabrique, niveau relatif)
    "open": (lambda: _reverb(_mix([(0, _noise(.30, .16, 180, 1500, 1.4)), (.01, _tone(392, .34, .55, "sine", glide=523, dec=3.0, att=.035)),
                                    (.06, _tone(587, .36, .38, "sine", glide=784, dec=3.2, att=.04)), (.15, _bell(1175, .5, .16))]), .28), 0.75),
    "close": (lambda: _reverb(_mix([(0, _noise(.26, .12, 1500, 180, 1.4)), (0, _tone(784, .26, .45, "sine", glide=440, dec=3.4, att=.03)),
                                     (.05, _tone(523, .3, .3, "sine", glide=330, dec=3.6, att=.03))]), .22), 0.6),
    "hover": (lambda: _tone(2100, .03, .3, "sine", dec=8), 0.28),
    "click": (lambda: _mix([(0, _tone(1000, .05, .5, "sine", glide=640, dec=7)), (0, _tone(2600, .015, .25, "sine", dec=8))]), 0.6),
    "tick": (lambda: _tone(1500, .04, .4, "sine", dec=8), 0.4),
    "on": (lambda: _mix([(0, _tone(620, .07, .5, "soft", dec=5)), (.06, _tone(930, .11, .5, "soft", dec=5))]), 0.7),
    "off": (lambda: _mix([(0, _tone(930, .07, .5, "soft", dec=5)), (.06, _tone(620, .11, .5, "soft", dec=5))]), 0.6),
    "pop": (lambda: _mix([(0, _tone(480, .08, .6, "soft", glide=980, dec=5)), (.05, _tone(1900, .03, .3, "sine", dec=7))]), 0.75),
    "approval": (lambda: _reverb(_mix([(0, _bell(784, .7, .8)), (.12, _bell(1175, .9, .7))]), .25), 0.9),
    "danger": (lambda: _mix([(0, _tone(196, .55, .7, "soft", vib=.02, dec=3)), (0, _tone(208, .55, .6, "soft", dec=3)),
                             (.3, _tone(196, .55, .7, "soft", vib=.02, dec=3)), (.3, _tone(208, .55, .6, "soft", dec=3))]), 1.0),
    "allow": (lambda: _mix([(0, _tone(1046, .09, .5, "tri", dec=6)), (.06, _tone(1318, .09, .5, "tri", dec=6)), (.12, _tone(1568, .2, .6, "tri", dec=5))]), 0.8),
    "deny": (lambda: _tone(392, .24, .6, "soft", glide=262, dec=4), 0.8),
    "finish": (lambda: _reverb(_seq([523, 659, 784, 1046, 1318], "bell", .07, .9, .7), .3), 0.95),
    "done": (lambda: _mix([(0, _tone(740, .09, .6, "soft", glide=1100, dec=5)), (.07, _bell(1760, .35, .45))]), 0.8),
    "timer": (lambda: _reverb(_mix([(0, _bell(784, .6, 1)), (.28, _bell(784, .6, 1)), (.56, _bell(784, .8, 1))]), .2), 0.95),
    "focus": (lambda: _reverb(_mix([(0, _tone(392, .9, .5, "soft", dec=2.5)), (.18, _tone(587, 1.0, .5, "soft", dec=2.5))]), .3), 0.8),
    "battery": (lambda: _seq([659, 523, 440], "tone", .13, .5, .8), 0.9),
    "drop": (lambda: _mix([(0, _tone(130, .14, .9, "soft", glide=60, dec=5)), (.05, _bell(1046, .5, .5))]), 0.85),
    "upload": (lambda: _mix([(0, _bell(784, .35, .8)), (.08, _bell(1175, .5, .8))]), 0.8),
    "error": (lambda: _mix([(0, _tone(175, .3, .7, "soft", dec=4)), (.14, _tone(147, .4, .7, "soft", dec=4))]), 0.85),
    "msg": (lambda: _reverb(_mix([(0, _bell(1318, .4, .6)), (.09, _bell(1760, .5, .6))]), .2), 0.75),
    "call_on": (lambda: _mix([(0, _tone(523, .09, .5, "soft", dec=5)), (.1, _tone(784, .14, .5, "soft", dec=5))]), 0.7),
    "call_off": (lambda: _mix([(0, _tone(784, .09, .5, "soft", dec=5)), (.1, _tone(523, .14, .5, "soft", dec=5))]), 0.7),
    "inhale": (lambda: _mix([(0, _noise(1.4, .22, 250, 1200, .6)), (0, _tone(220, 1.4, .25, "sine", glide=330, dec=1.2, att=.3))]), 0.55),
    "exhale": (lambda: _mix([(0, _noise(1.6, .2, 1200, 250, .6)), (0, _tone(330, 1.6, .25, "sine", glide=200, dec=1.2, att=.3))]), 0.55),
}


def synth_wav(path: pathlib.Path, buf, vol: float) -> None:
    scale = vol / (max(map(abs, buf)) or 1.0) * 0.92
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(SR)
        wf.writeframes(struct.pack(f"<{len(buf)}h", *[int(max(-1.0, min(1.0, x * scale)) * 32767) for x in buf]))


def sound_path(name: str, vol: float) -> pathlib.Path:
    return CACHE_DIR / "sounds" / f"{name}-v35-{int(vol * 100)}.wav"


def ensure_sounds(vol: float) -> None:
    for name, (fn, level) in SOUNDS.items():
        p = sound_path(name, vol)
        if not p.exists():
            try:
                synth_wav(p, fn(), vol * level)
            except Exception as e:
                print(f"[coucou] son {name} non généré : {e}", file=sys.stderr)


# ════════════════════════════════════════════════════════════════════════════
#  3. BRIQUES MÉTIER (sans interface graphique)
# ════════════════════════════════════════════════════════════════════════════
SECRET_RX = [re.compile(p) for p in (
    r"sk-[A-Za-z0-9_\-]{20,}", r"ghp_[A-Za-z0-9]{30,}", r"github_pat_[A-Za-z0-9_]{30,}", r"AKIA[0-9A-Z]{16}", r"AIza[0-9A-Za-z_\-]{35}",
    r"xox[baprs]-[A-Za-z0-9-]{10,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{10,}")]


def calc(expr: str):
    """Calcul sûr (pas d'eval) : + - * / // % ** parenthèses, virgules françaises, « 20% de 150 »."""
    import ast
    import operator as op
    e = expr.replace(",", ".").replace("^", "**").replace("×", "*").replace("÷", "/").strip()
    m = re.fullmatch(r"([\d.]+)\s*%\s*de\s*([\d.]+)", e, re.I)
    if m:
        v = round(float(m[1]) / 100 * float(m[2]), 6)
        return int(v) if v.is_integer() else v
    ops = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv, ast.FloorDiv: op.floordiv, ast.Mod: op.mod,
           ast.Pow: op.pow, ast.USub: op.neg, ast.UAdd: op.pos}

    def ev(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in ops:
            a, b = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(b) > 100:
                raise ValueError
            return ops[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in ops:
            return ops[type(n.op)](ev(n.operand))
        raise ValueError
    try:
        v = ev(ast.parse(e, mode="eval").body)
    except Exception:
        return None
    return int(v) if isinstance(v, float) and v.is_integer() and abs(v) < 1e15 else round(v, 6)


WMO = {0: ("Dégagé", "sun"), 1: ("Plutôt dégagé", "sun"), 2: ("Nuageux par endroits", "cloud"), 3: ("Couvert", "cloud"), 45: ("Brouillard", "fog"),
       48: ("Brouillard givrant", "fog"), 51: ("Bruine", "rain"), 53: ("Bruine", "rain"), 55: ("Bruine forte", "rain"), 61: ("Pluie faible", "rain"),
       63: ("Pluie", "rain"), 65: ("Forte pluie", "rain"), 66: ("Pluie verglaçante", "rain"), 67: ("Pluie verglaçante", "rain"), 71: ("Neige faible", "snow"),
       73: ("Neige", "snow"), 75: ("Forte neige", "snow"), 77: ("Grésil", "snow"), 80: ("Averses", "rain"), 81: ("Averses", "rain"),
       82: ("Fortes averses", "rain"), 85: ("Averses de neige", "snow"), 86: ("Averses de neige", "snow"), 95: ("Orage", "storm"),
       96: ("Orage et grêle", "storm"), 99: ("Orage et grêle", "storm")}


class Radar:
    def __init__(self, cfg: dict):
        self.c = cfg["radar"]
        self.rules = []
        for r in list(self.c.get("rules", [])) + list(self.c.get("extra_rules", [])):
            try:
                self.rules.append((re.compile(r["pattern"], re.I), int(r.get("score", 50)), r.get("name", "?")))
            except (re.error, KeyError, ValueError) as e:
                print(f"[coucou] règle radar ignorée ({r!r}) : {e}", file=sys.stderr)

    def score(self, text: str) -> tuple[int, list[str]]:
        if not self.c.get("enabled", True):
            return 0, []
        hits = sorted(((sc, n) for rx, sc, n in self.rules if rx.search(text or "")), reverse=True)
        return (hits[0][0], [n for _, n in hits[:3]]) if hits else (0, [])


class Journal:
    def __init__(self, cfg: dict):
        self.on = cfg["journal"].get("enabled", True)
        self.dir = pathlib.Path(os.path.expanduser(cfg["journal"]["dir"]))

    def append(self, md: str) -> pathlib.Path | None:
        if not self.on:
            return None
        self.dir.mkdir(parents=True, exist_ok=True)
        p = self.dir / f"{dt.date.today().isoformat()}.md"
        with open(p, "a", encoding="utf-8") as f:
            f.write(md)
        return p

    def write_turn(self, s: dict) -> pathlib.Path | None:
        tools = ", ".join(f"{k}×{v}" for k, v in s["tools"].most_common()) or "—"
        risk = f" (risque max {s['maxrisk']} : {s['maxlabel']})" if s["maxrisk"] else ""
        return self.append(f"\n## {dt.datetime.now():%H:%M} · {s['agent']} · {s['label']}\n- outils : {tools}\n"
                           f"- fichiers : {', '.join(sorted(s['files'])[:12]) or '—'}\n"
                           f"- approbations : {s['ok']} accordée(s), {s['no']} refusée(s){risk}\n- dernier message : {s['text'] or '—'}\n")


class KDrive:
    """Dépôt kDrive = un dossier LOCAL que l'appli kDrive synchronise (aucun accès réseau ici)."""

    def __init__(self, cfg: dict, core: "Core"):
        self.c, self.core = cfg["depot"], core
        self._timer: threading.Timer | None = None

    def root(self) -> pathlib.Path:
        return pathlib.Path(os.path.expanduser(self.c["folder"]))

    def available(self) -> bool:
        return bool(self.c.get("enabled")) and self.root().is_dir()

    def upload(self, local: str, sub: str = "") -> None:
        threading.Thread(target=self._upload, args=(local, sub), daemon=True).start()

    def _free_name(self, d: pathlib.Path, name: str) -> pathlib.Path:
        p = d / name
        if not p.exists():
            return p
        stem, suf = os.path.splitext(name)
        return d / f"{stem}-{dt.datetime.now():%H%M%S}{suf}"

    def _upload(self, local: str, sub: str = "", overwrite: bool = False) -> bool:
        name = os.path.basename(local.rstrip("/"))
        if not self.c.get("enabled"):
            return False
        try:
            d = self.root() / sub if sub else self.root()
            d.mkdir(parents=True, exist_ok=True)
            dest = d / name if (overwrite or not (d / name).exists()) else self._free_name(d, name)
            if os.path.isdir(local):
                shutil.copytree(local, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(local, dest)
        except OSError as e:
            self.core.set_kdrive(f"Dépôt impossible : {short(e, 60)}", "danger")
            self.core.play("error"); self.core.fx("shake")
            return False
        self.core.set_kdrive(f"✓ {name} déposé dans kDrive", "ok")
        self.core.toast(f"☁ {short(name, 30)} déposé dans kDrive", "ok")
        self.core.play("drop"); self.core.fx("sparkle")
        return True

    def save_text(self, text: str, sub: str = "Notes", prefix: str = "note") -> pathlib.Path | None:
        try:
            d = self.root() / sub
            d.mkdir(parents=True, exist_ok=True)
            p = d / f"{prefix}-{dt.datetime.now():%Y%m%d-%H%M%S}.md"
            p.write_text(text.strip() + "\n", encoding="utf-8")
        except OSError as e:
            self.core.set_kdrive(f"Enregistrement impossible : {short(e, 60)}", "danger")
            return None
        self.core.set_kdrive(f"✓ {p.name} enregistré dans kDrive", "ok")
        self.core.toast("☁ Note enregistrée dans kDrive", "ok"); self.core.play("drop")
        return p

    def schedule_journal_upload(self, path, delay: float = 15.0) -> None:
        if not (path and self.c.get("enabled") and self.c.get("journal_copy")):
            return
        if self._timer:
            self._timer.cancel()
        self._timer = threading.Timer(delay, self._upload, args=(str(path), "Journal", True))
        self._timer.daemon = True
        self._timer.start()

    def last_screenshot(self) -> str | None:
        best = None
        for d in self.c.get("screenshot_dirs", []):
            p = pathlib.Path(os.path.expanduser(d))
            if p.is_dir():
                for f in p.iterdir():
                    if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") and (best is None or f.stat().st_mtime > best.stat().st_mtime):
                        best = f
        return str(best) if best else None


class ThinkFilter:
    """Retire les blocs <think>…</think> d'un flux de texte (modèles Qwen3 « raisonneurs »)."""

    def __init__(self):
        self.buf, self.inside = "", False

    def feed(self, s: str) -> str:
        self.buf += s
        out = ""
        while True:
            if self.inside:
                j = self.buf.find("</think>")
                if j < 0:
                    self.buf = self.buf[-7:]
                    return out
                self.buf, self.inside = self.buf[j + 8:], False
            else:
                j = self.buf.find("<think>")
                if j < 0:
                    keep = max((k for k in range(1, 7) if "<think>".startswith(self.buf[-k:])), default=0)
                    out += self.buf[: len(self.buf) - keep]
                    self.buf = self.buf[len(self.buf) - keep:]
                    return out
                out, self.buf, self.inside = out + self.buf[:j], self.buf[j + 7:], True

    def flush(self) -> str:
        out = "" if self.inside else self.buf
        self.buf = ""
        return out


class Ollama:
    """IA locale : client de l'API Ollama (réponses en flux)."""

    def __init__(self, cfg: dict):
        self.c = cfg["ollama"]
        self._model: str | None = None

    def _req(self, path: str, body: dict | None = None) -> urllib.request.Request:
        return urllib.request.Request(self.c["url"].rstrip("/") + path, data=json.dumps(body).encode() if body is not None else None,
                                      headers={"Content-Type": "application/json"})

    def models(self) -> list[str]:
        with urllib.request.urlopen(self._req("/api/tags"), timeout=3) as r:
            return [m["name"] for m in json.load(r).get("models", [])]

    def model(self) -> str:
        if self.c.get("model"):
            return self.c["model"]
        if self._model:
            return self._model
        names = self.models()
        if not names:
            raise RuntimeError("aucun modèle installé dans Ollama (ollama pull …)")
        m = (self.c.get("model_match") or "").lower()
        self._model = next((n for n in names if m and m in n.lower()), names[0])
        return self._model

    def ping(self) -> tuple[bool, str]:
        try:
            names = self.models()
            return True, f"{len(names)} modèle(s) · utilisé : {self.model()}"
        except Exception as e:
            return False, short(e, 80)

    def ask(self, prompt: str, system: str | None = None, on_text=None) -> str:
        msgs = [{"role": "system", "content": system or self.c.get("system", "")}, {"role": "user", "content": prompt}]
        body = {"model": self.model(), "messages": msgs, "stream": True, "keep_alive": self.c["keep_alive"],
                "options": {"temperature": self.c["temperature"]}}
        if self.c.get("think") is False:
            body["think"] = False
        try:
            return self._stream(body, on_text)
        except urllib.error.HTTPError as e:
            if e.code == 400 and "think" in body:
                body.pop("think")
                return self._stream(body, on_text)
            raise

    def _stream(self, body: dict, on_text) -> str:
        flt, full = ThinkFilter(), ""
        with urllib.request.urlopen(self._req("/api/chat", body), timeout=self.c["timeout_seconds"]) as r:
            for line in r:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("error"):
                    raise RuntimeError(d["error"])
                chunk = flt.feed(d.get("message", {}).get("content", ""))
                if chunk:
                    full += chunk
                    if on_text:
                        on_text(full)
                if d.get("done"):
                    break
        tail = flt.flush()
        if tail:
            full += tail
            if on_text:
                on_text(full)
        return full.strip()


class Kanban:
    """Lecture seule du tableau Kanban de Hermes (SQLite ~/.hermes/kanban.db)."""
    ORDER = ["todo", "ready", "running", "blocked", "done"]
    MAP = {"todo": "todo", "backlog": "todo", "triage": "todo", "pending": "todo", "ready": "ready", "queued": "ready",
           "running": "running", "in_progress": "running", "claimed": "running", "doing": "running", "active": "running",
           "blocked": "blocked", "done": "done", "completed": "done", "complete": "done", "archived": "done", "closed": "done"}

    def __init__(self, cfg: dict):
        self.c = cfg["hermes"]

    def db_path(self) -> pathlib.Path:
        home = pathlib.Path(os.path.expanduser(self.c.get("home", "~/.hermes")))
        try:
            slug = (home / "kanban" / "current").read_text().strip()
            if slug and slug != "default" and (home / "kanban" / "boards" / slug / "kanban.db").exists():
                return home / "kanban" / "boards" / slug / "kanban.db"
        except OSError:
            pass
        return home / "kanban.db"

    def read(self) -> dict:
        p = self.db_path()
        if not p.exists():
            return {"ok": False, "error": "Kanban non initialisé (hermes kanban init)", "counts": {}, "active": [], "total": 0, "tasks": {}}
        try:
            con = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=1.0)
            try:
                cols = [r[1] for r in con.execute("PRAGMA table_info(tasks)")]
                if not cols:
                    raise sqlite3.OperationalError("table tasks absente")
                pick = lambda *names: next((n for n in names if n in cols), None)
                idc, tc, sc, ac = pick("id", "task_id") or "rowid", pick("title", "name", "summary", "description"), pick("status", "state", "lane", "column"), pick("assignee", "profile", "owner")
                if not sc:
                    raise sqlite3.OperationalError("colonne de statut introuvable")
                q = f"SELECT {idc}, {tc or idc}, {sc}, {ac or 'NULL'} FROM tasks ORDER BY rowid DESC LIMIT 300"
                rows = con.execute(q).fetchall()
            finally:
                con.close()
        except sqlite3.Error as e:
            return {"ok": False, "error": f"Kanban illisible : {short(e, 60)}", "counts": {}, "active": [], "total": 0, "tasks": {}}
        counts, tasks, active = collections.Counter(), {}, []
        by_who, current = collections.defaultdict(collections.Counter), {}
        for tid, title, st, who in rows:
            s = self.MAP.get(str(st).lower().replace(" ", "_").replace("-", "_"), "todo")
            counts[s] += 1
            tasks[str(tid)] = {"title": short(title, 60), "status": s}
            if who:
                by_who[str(who).lower()][s] += 1
                if s == "running":
                    current.setdefault(str(who).lower(), short(title, 60))
            if s in ("running", "blocked", "ready"):
                active.append({"id": str(tid), "title": short(title, 60), "status": s, "who": who or ""})
        rank = {"blocked": 0, "running": 1, "ready": 2}
        active.sort(key=lambda t: rank[t["status"]])
        return {"ok": True, "error": "", "counts": dict(counts), "active": active[:5], "total": sum(counts.values()), "tasks": tasks,
                "by_who": {k: dict(v) for k, v in by_who.items()}, "current": current}


def profile_color(cfg: dict, name: str):
    """Couleur de Mochi pour un profil Hermes (None = rose par défaut). Personnalisable : [hermes.profile_colors]."""
    custom = (cfg["hermes"].get("profile_colors") or {}).get(name)
    if custom:
        return hexrgb(custom)
    if not name or name == "default":
        return None
    hue = int(hashlib.md5(name.encode()).hexdigest()[:6], 16) % 360
    return colorsys.hls_to_rgb(hue / 360, 0.74, 0.70)


_EMOJI_RX = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200d]")


def speech_clean(text: str) -> str:
    t = re.sub(r"https?://\S+", "", text)
    t = _EMOJI_RX.sub("", t)
    t = re.sub(r"[*_`#>•▸▌→⚡\[\]]", " ", t)
    return re.sub(r"[ \t]+", " ", t).strip()


def strip_html(s: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s or "")).split())


class Thunderbird:
    """Lit les mails récents dans les dossiers « Boîte de réception » locaux de Thunderbird (fichiers mbox)."""
    ROOTS = ("~/.thunderbird", "~/.var/app/org.mozilla.Thunderbird/.thunderbird", "~/snap/thunderbird/common/.thunderbird")

    def __init__(self, cfg: dict):
        self.c = cfg["bonjour"]["mail"]

    def profiles(self) -> list[pathlib.Path]:
        if self.c.get("profile_dir"):
            p = pathlib.Path(os.path.expanduser(self.c["profile_dir"]))
            return [p] if p.is_dir() else []
        out: list[pathlib.Path] = []
        for root in self.ROOTS:
            base = pathlib.Path(os.path.expanduser(root))
            ini, cands = base / "profiles.ini", []
            if ini.exists():
                cp = configparser.RawConfigParser()
                try:
                    cp.read(ini, encoding="utf-8")
                except configparser.Error:
                    continue
                inst, dflt, rest = [], [], []
                for sec in cp.sections():
                    if sec.startswith("Install") and cp.has_option(sec, "Default"):
                        inst.append((cp.get(sec, "Default"), True))
                    elif sec.startswith("Profile") and cp.has_option(sec, "Path"):
                        item = (cp.get(sec, "Path"), cp.get(sec, "IsRelative", fallback="1") == "1")
                        (dflt if cp.get(sec, "Default", fallback="0") == "1" else rest).append(item)
                for path, rel in inst + dflt + rest:
                    d = base / path if rel else pathlib.Path(path)
                    if d.is_dir() and d not in out:
                        out.append(d)
            elif base.is_dir():
                out += [d for d in base.iterdir() if (d / "prefs.js").exists() and d not in out]
        return out

    def inbox_files(self, prof: pathlib.Path) -> list[tuple[str, pathlib.Path]]:
        files = []
        for sub in ("ImapMail", "Mail"):
            d = prof / sub
            if d.is_dir():
                for srv in d.iterdir():
                    if srv.is_dir():
                        files += [(srv.name, f) for f in srv.iterdir() if f.is_file() and f.name.lower() == "inbox"]
        return files

    def info(self) -> str | None:
        profs = self.profiles()
        if not profs:
            return None
        return f"profil {profs[0].name} · {len(self.inbox_files(profs[0]))} boîte(s) de réception"

    def recent(self, hours: int | None = None, limit: int | None = None) -> list[dict]:
        hours, limit = hours or int(self.c["hours"]), limit or int(self.c["max_mails"])
        cutoff, msgs = time.time() - hours * 3600, []
        for prof in self.profiles()[:1]:
            for acct, f in self.inbox_files(prof):
                try:
                    msgs += self._scan(f, acct, cutoff)
                except OSError:
                    pass
        msgs.sort(key=lambda m: -m["ts"])
        return msgs[:limit]

    def _scan(self, f: pathlib.Path, acct: str, cutoff: float) -> list[dict]:
        size, tail = f.stat().st_size, int(float(self.c["tail_mb"]) * 1024 * 1024)
        with open(f, "rb") as fh:
            partial = size > tail
            if partial:
                fh.seek(size - tail)
            data = fh.read()
        parts = re.split(rb"(?m)^From \S+ +\w{3} \w{3} +\d", data)
        if partial or len(parts) > 1:
            parts = parts[1:]
        out, old_streak = [], 0
        for piece in reversed(parts):
            try:
                msg = email.message_from_bytes(piece.split(b"\n", 1)[1] if b"\n" in piece else piece, policy=email.policy.default)
                d = email.utils.parsedate_to_datetime(str(msg["date"]))
                ts = (d if d.tzinfo else d.astimezone()).timestamp()
            except Exception:
                continue
            if ts < cutoff:
                old_streak += 1
                if old_streak > 80:
                    break
                continue
            old_streak = 0
            try:
                flags = int(str(msg.get("X-Mozilla-Status", "0000")), 16)
            except ValueError:
                flags = 0
            if flags & 0x0008:
                continue
            name, addr = email.utils.parseaddr(str(msg["from"] or ""))
            snippet = ""
            try:
                body = msg.get_body(preferencelist=("plain", "html"))
                snippet = short(strip_html(body.get_content()) if body else "", 280)
            except Exception:
                pass
            out.append({"from": name or addr, "subject": str(msg["subject"] or "(sans objet)"), "ts": ts, "unread": not flags & 1,
                        "snippet": snippet, "account": acct})
        return out


_WD = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def _ics_props(block: str) -> dict:
    props: dict = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        head, _, val = line.partition(":")
        parts = head.split(";")
        params = {}
        for p in parts[1:]:
            k, _, v = p.partition("=")
            params[k.upper()] = v.strip('"')
        props.setdefault(parts[0].upper(), []).append((params, val))
    return props


def _ics_dt(params: dict, val: str):
    v = val.strip()
    if params.get("VALUE") == "DATE" or re.fullmatch(r"\d{8}", v):
        return dt.date(int(v[:4]), int(v[4:6]), int(v[6:8]))
    m = re.fullmatch(r"(\d{8})T(\d{6})(Z?)", v)
    if not m:
        return None
    naive = dt.datetime.strptime(m[1] + m[2], "%Y%m%d%H%M%S")
    if m[3]:
        return naive.replace(tzinfo=dt.timezone.utc)
    if params.get("TZID"):
        try:
            return naive.replace(tzinfo=zoneinfo.ZoneInfo(params["TZID"]))
        except Exception:
            pass
    return naive.astimezone()


def _nth_weekday(year: int, month: int, wd: int, n: int):
    if n > 0:
        d = dt.date(year, month, 1)
        d += dt.timedelta(days=(wd - d.weekday()) % 7 + 7 * (n - 1))
    else:
        nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
        d = nxt - dt.timedelta(days=1)
        d -= dt.timedelta(days=(d.weekday() - wd) % 7 + 7 * (-n - 1))
    return d if d.month == month else None


def _occurrences(start, rule: dict, until_day: dt.date, cap: int = 4000):
    """Génère les dates de début d'une série (RRULE usuelles : DAILY/WEEKLY/MONTHLY/YEARLY, INTERVAL, COUNT, UNTIL, BYDAY, BYMONTHDAY)."""
    freq, interval = rule.get("FREQ", "").upper(), max(1, int(rule.get("INTERVAL", "1")))
    count = int(rule["COUNT"]) if "COUNT" in rule else None
    until = _ics_dt({}, rule["UNTIL"]) if "UNTIL" in rule else None
    until_day = min(until_day, (until.date() if isinstance(until, dt.datetime) else until)) if until else until_day
    sd = start.date() if isinstance(start, dt.datetime) else start
    byday = [b for b in rule.get("BYDAY", "").split(",") if b]
    bymd = [int(x) for x in rule.get("BYMONTHDAY", "").split(",") if x]
    n = 0

    def make(day):
        return dt.datetime.combine(day, start.timetz()) if isinstance(start, dt.datetime) else day
    k = 0
    while k < cap:
        days: list[dt.date] = []
        if freq == "DAILY":
            days = [sd + dt.timedelta(days=interval * k)]
        elif freq == "WEEKLY":
            ws = sd - dt.timedelta(days=sd.weekday()) + dt.timedelta(weeks=interval * k)
            wds = sorted(_WD[re.sub(r"[+-]?\d+", "", b)] for b in byday if re.sub(r"[+-]?\d+", "", b) in _WD) or [sd.weekday()]
            days = [ws + dt.timedelta(days=w) for w in wds]
        elif freq in ("MONTHLY", "YEARLY"):
            mi = (sd.month - 1) + (interval * k if freq == "MONTHLY" else 0)
            y, mo = sd.year + mi // 12 + (interval * k if freq == "YEARLY" else 0), mi % 12 + 1
            if byday:
                for b in byday:
                    m_ = re.fullmatch(r"([+-]?\d+)?([A-Z]{2})", b)
                    if m_ and m_[2] in _WD:
                        d_ = _nth_weekday(y, mo, _WD[m_[2]], int(m_[1] or 1))
                        if d_:
                            days.append(d_)
            else:
                for dd in (bymd or [sd.day]):
                    try:
                        days.append(dt.date(y, mo, dd))
                    except ValueError:
                        pass
        else:
            return
        if not days or min(days) > until_day:
            return
        for d in sorted(days):
            if d < sd:
                continue
            if d > until_day or (count is not None and n >= count):
                return
            n += 1
            yield make(d)
        k += 1


def parse_ics(text: str, win_start: dt.datetime, win_end: dt.datetime, cal: str = "") -> list[dict]:
    text = re.sub(r"\r?\n[ \t]", "", text)
    events, overrides = [], {}
    for blk in re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", text, re.S):
        p = _ics_props(blk)
        if "DTSTART" not in p or (p.get("STATUS", [({}, "")])[0][1].upper() == "CANCELLED"):
            continue
        st = _ics_dt(*p["DTSTART"][0])
        if st is None:
            continue
        allday = not isinstance(st, dt.datetime)
        if "DTEND" in p:
            en = _ics_dt(*p["DTEND"][0])
            dur = (en - st) if en is not None and isinstance(en, type(st)) else dt.timedelta(days=1 if allday else 0)
        elif "DURATION" in p:
            m = re.fullmatch(r"P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?)?", p["DURATION"][0][1])
            dur = dt.timedelta(weeks=int(m[1] or 0), days=int(m[2] or 0), hours=int(m[3] or 0), minutes=int(m[4] or 0)) if m else dt.timedelta(0)
        else:
            dur = dt.timedelta(days=1) if allday else dt.timedelta(0)
        ev = {"uid": p.get("UID", [({}, "")])[0][1], "start": st, "dur": dur, "allday": allday,
              "title": strip_html(p.get("SUMMARY", [({}, "(sans titre)")])[0][1].replace("\\,", ",").replace("\\n", " ")),
              "loc": p.get("LOCATION", [({}, "")])[0][1].replace("\\,", ","), "cal": cal,
              "rrule": dict(kv.split("=", 1) for kv in p["RRULE"][0][1].split(";") if "=" in kv) if "RRULE" in p else None,
              "ex": [_ics_dt(pa, v2) for pa, v in p.get("EXDATE", []) for v2 in v.split(",")]}
        if "RECURRENCE-ID" in p:
            rid = _ics_dt(*p["RECURRENCE-ID"][0])
            overrides[(ev["uid"], _norm_key(rid))] = ev
        events.append(ev)
    out = []
    ws_d, we_d = win_start.date(), win_end.date()

    def keep(start, dur, ev):
        if ev["allday"]:
            sd = start
            return sd < we_d and sd + dur > ws_d
        s = start.astimezone()
        return s < win_end and s + dur > win_start - dt.timedelta(minutes=1)

    def push(start, dur, ev):
        if ev["allday"]:
            out.append(dict(ev, start=start, end=start + dur))
        else:
            s = start.astimezone()
            out.append(dict(ev, start=s, end=s + dur))
    for ev in events:
        if ev["rrule"]:
            exs = {_norm_key(x) for x in ev["ex"] if x is not None}
            for occ in _occurrences(ev["start"], ev["rrule"], we_d + dt.timedelta(days=1)):
                key = _norm_key(occ)
                if key in exs or (ev["uid"], key) in overrides:
                    continue
                if keep(occ, ev["dur"], ev):
                    push(occ, ev["dur"], ev)
        elif keep(ev["start"], ev["dur"], ev):
            push(ev["start"], ev["dur"], ev)
    out.sort(key=lambda e: (e["start"] if isinstance(e["start"], dt.datetime) else dt.datetime.combine(e["start"], dt.time.min).astimezone()))
    return out


def _norm_key(d) -> str:
    if isinstance(d, dt.datetime):
        return d.astimezone(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    return d.strftime("%Y%m%d") if d else ""


class Calendars:
    """Agendas Google via leur « adresse secrète au format iCal » (aucune connexion à un compte)."""

    def __init__(self, cfg: dict):
        self.c = cfg["bonjour"]
        self._cache: dict = {}

    def count(self) -> int:
        return len(self.c.get("calendars", []))

    def _fetch(self, cal: dict) -> str:
        if cal.get("file"):
            return pathlib.Path(os.path.expanduser(cal["file"])).read_text(encoding="utf-8", errors="replace")
        hit = self._cache.get(cal["url"])
        if hit and time.time() - hit[0] < 600:
            return hit[1]
        req = urllib.request.Request(cal["url"], headers={"User-Agent": "coucou-fedora"})
        with urllib.request.urlopen(req, timeout=12) as r:
            txt = r.read().decode("utf-8", errors="replace")
        self._cache[cal["url"]] = (time.time(), txt)
        return txt

    def events(self) -> tuple[list[dict], list[str]]:
        start = dt.datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        end, out, errs = start + dt.timedelta(days=int(self.c.get("agenda_days", 2))), [], []
        for cal in self.c.get("calendars", []):
            try:
                out += parse_ics(self._fetch(cal), start, end, cal.get("name", "Agenda"))
            except Exception as e:
                errs.append(f"{cal.get('name', 'Agenda')} : {short(e, 50)}")

        def key(e):
            s = e["start"]
            return s if isinstance(s, dt.datetime) else dt.datetime.combine(s, dt.time.min).astimezone()
        out.sort(key=key)
        return out, errs


def fetch_feed(url: str, limit: int = 8) -> list[dict]:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (coucou-fedora)"})
    with urllib.request.urlopen(req, timeout=10) as r:
        root = ET.fromstring(r.read())
    items = []
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue
        g = lambda *names: next((strip_html("".join(c.itertext())) for c in el if c.tag.split("}")[-1] in names and "".join(c.itertext()).strip()), "")
        title = g("title")
        if title:
            items.append({"title": short(title, 140), "desc": short(g("description", "summary", "content"), 220)})
        if len(items) >= limit:
            break
    return items


# ---- protocole Wyoming (Whisper / Piper en conteneur, ex. pour Home Assistant) -------------------------
def _wy_send(f, typ: str, data: dict | None = None, payload: bytes = b"") -> None:
    hdr: dict = {"type": typ}
    if data:
        hdr["data"] = data
    if payload:
        hdr["payload_length"] = len(payload)
    f.write((json.dumps(hdr) + "\n").encode() + payload)
    f.flush()


def _wy_read(f):
    line = f.readline()
    if not line:
        return None
    hdr = json.loads(line)
    data = dict(hdr.get("data") or {})
    if hdr.get("data_length"):
        data.update(json.loads(f.read(hdr["data_length"])))
    payload = f.read(hdr["payload_length"]) if hdr.get("payload_length") else b""
    return hdr["type"], data, payload


def _wy_connect(addr: str, timeout: float = 2.0):
    host, _, port = addr.rpartition(":")
    s = socket.create_connection((host or "127.0.0.1", int(port)), timeout=timeout)
    s.settimeout(60)
    return s, s.makefile("rwb")


def wyoming_up(addr: str) -> bool:
    try:
        s, _ = _wy_connect(addr, 0.6)
        s.close()
        return True
    except (OSError, ValueError):
        return False


class Speaker:
    """Synthèse vocale : Wyoming/Piper (conteneur) → piper local → espeak-ng → speech-dispatcher."""

    def __init__(self, cfg: dict):
        self.c = cfg["voice"]
        self.proc: subprocess.Popen | None = None
        self.stop_flag = False

    def engines(self) -> list[str]:
        out = []
        if self.c.get("wyoming_tts") and wyoming_up(self.c["wyoming_tts"]):
            out.append("wyoming")
        if self.c.get("piper_model") and shutil.which(self.c.get("piper_bin", "piper")):
            out.append("piper")
        if shutil.which("espeak-ng"):
            out.append("espeak-ng")
        if shutil.which("spd-say"):
            out.append("speech-dispatcher")
        return out

    def stop(self) -> None:
        self.stop_flag = True
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def say(self, text: str) -> None:
        self.stop_flag = False
        text = speech_clean(text)
        chunks = [c.strip() for c in re.split(r"(?<=[.!?:])\s+|\n+", text) if c.strip()]
        merged, cur = [], ""
        for c in chunks:
            if len(cur) + len(c) < 260:
                cur = f"{cur} {c}".strip()
            else:
                merged.append(cur); cur = c
        merged += [cur] if cur else []
        engines = self.engines()
        if not engines:
            raise RuntimeError("aucune voix : installe espeak-ng (sudo dnf install espeak-ng) ou lance un conteneur Piper (Wyoming)")
        for part in merged:
            if self.stop_flag:
                return
            last_err = None
            for eng in engines:
                try:
                    getattr(self, "_" + eng.replace("-", "_"))(part)
                    last_err = None
                    break
                except Exception as e:
                    last_err = e
            if last_err:
                raise RuntimeError(str(last_err))

    def _play_wav(self, path: str) -> None:
        self.proc = subprocess.Popen(["pw-play", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.proc.wait()

    def _wyoming(self, text: str) -> None:
        s, f = _wy_connect(self.c["wyoming_tts"])
        try:
            voice = {"name": self.c["wyoming_voice"]} if self.c.get("wyoming_voice") else None
            _wy_send(f, "synthesize", {"text": text, **({"voice": voice} if voice else {})})
            pcm, fmt = b"", {"rate": 22050, "width": 2, "channels": 1}
            while True:
                ev = _wy_read(f)
                if ev is None or ev[0] == "audio-stop":
                    break
                if ev[0] in ("audio-start", "audio-chunk"):
                    fmt.update({k: ev[1][k] for k in ("rate", "width", "channels") if k in ev[1]})
                    pcm += ev[2]
        finally:
            s.close()
        path = CACHE_DIR / "voice" / "tts.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(fmt["channels"]); wf.setsampwidth(fmt["width"]); wf.setframerate(fmt["rate"]); wf.writeframes(pcm)
        self._play_wav(str(path))

    def _piper(self, text: str) -> None:
        path = CACHE_DIR / "voice" / "tts.wav"
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([self.c.get("piper_bin", "piper"), "--model", self.c["piper_model"], "--output_file", str(path)], input=text.encode(),
                       capture_output=True, timeout=60, check=True)
        self._play_wav(str(path))

    def _espeak_ng(self, text: str) -> None:
        self.proc = subprocess.Popen(["espeak-ng", "-v", self.c.get("espeak_voice", "fr"), "-s", str(self.c.get("rate", 165)), text],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.proc.wait()

    def _speech_dispatcher(self, text: str) -> None:
        self.proc = subprocess.Popen(["spd-say", "-w", "-l", self.c.get("lang", "fr"), text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.proc.wait()


class Voice:
    """Enregistrement du micro (PipeWire) et transcription locale (Wyoming Whisper → faster-whisper → whisper.cpp)."""

    def __init__(self, cfg: dict):
        self.c = cfg["voice"]
        self.proc: subprocess.Popen | None = None
        self.path = CACHE_DIR / "voice" / "rec.wav"
        self._fw = None

    def engines(self) -> list[str]:
        out = []
        if self.c.get("wyoming_stt") and wyoming_up(self.c["wyoming_stt"]):
            out.append("wyoming")
        try:
            import importlib.util as iu
            if iu.find_spec("faster_whisper"):
                out.append("faster-whisper")
        except (ImportError, ValueError):
            pass
        if self.c.get("whisper_cpp_model") and shutil.which(self.c.get("whisper_cpp_bin", "whisper-cli")):
            out.append("whisper.cpp")
        return out

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.unlink(missing_ok=True)
        if shutil.which("pw-record"):
            cmd = ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16", str(self.path)]
        elif shutil.which("parecord"):
            cmd = ["parecord", "--rate=16000", "--channels=1", "--file-format=wav", str(self.path)]
        else:
            raise RuntimeError("pw-record introuvable (sudo dnf install pipewire-utils)")
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def stop(self) -> pathlib.Path | None:
        p, self.proc = self.proc, None
        if p and p.poll() is None:
            p.send_signal(2)
            try:
                p.wait(4)
            except subprocess.TimeoutExpired:
                p.kill()
        return self.path if self.path.exists() and self.path.stat().st_size > 3000 else None

    def transcribe(self, path: pathlib.Path) -> str:
        errs = []
        for eng in self.engines():
            try:
                return getattr(self, "_" + eng.replace("-", "_").replace(".", "_"))(path).strip()
            except Exception as e:
                errs.append(f"{eng}: {short(e, 60)}")
        raise RuntimeError("aucun moteur de transcription disponible" + (" (" + " ; ".join(errs) + ")" if errs else "")
                           + " — lance ton conteneur Whisper (Wyoming) ou installe faster-whisper")

    def _wyoming(self, path: pathlib.Path) -> str:
        with wave.open(str(path), "rb") as wf:
            fmt = {"rate": wf.getframerate(), "width": wf.getsampwidth(), "channels": wf.getnchannels()}
            frames = wf.readframes(wf.getnframes())
        s, f = _wy_connect(self.c["wyoming_stt"])
        try:
            _wy_send(f, "transcribe", {"language": self.c.get("lang", "fr")})
            _wy_send(f, "audio-start", fmt)
            step = fmt["rate"] * fmt["width"] * fmt["channels"] // 4
            for i in range(0, len(frames), step):
                _wy_send(f, "audio-chunk", fmt, frames[i:i + step])
            _wy_send(f, "audio-stop")
            while True:
                ev = _wy_read(f)
                if ev is None:
                    raise RuntimeError("connexion fermée sans transcription")
                if ev[0] == "transcript":
                    return ev[1].get("text", "")
        finally:
            s.close()

    def _faster_whisper(self, path: pathlib.Path) -> str:
        if self._fw is None:
            from faster_whisper import WhisperModel
            self._fw = WhisperModel(self.c.get("faster_whisper_model", "small"), device="cpu", compute_type="int8")
        segs, _ = self._fw.transcribe(str(path), language=self.c.get("lang", "fr"), vad_filter=True)
        return " ".join(s.text for s in segs)

    def _whisper_cpp(self, path: pathlib.Path) -> str:
        r = subprocess.run([self.c.get("whisper_cpp_bin", "whisper-cli"), "-m", os.path.expanduser(self.c["whisper_cpp_model"]), "-f", str(path),
                            "-l", self.c.get("lang", "fr"), "-nt", "-np"], capture_output=True, text=True, timeout=180)
        return r.stdout


class Ducker:
    def __init__(self, cfg: dict):
        self.c = cfg["ducking"]
        self.saved: dict[int, int] = {}
        self.lock = threading.Lock()

    def inputs(self) -> list[tuple[int, int, str]]:
        try:
            data = json.loads(run(["pactl", "--format=json", "list", "sink-inputs"]))
        except Exception:
            return []
        res = []
        for it in data:
            props = it.get("properties", {})
            name = props.get("application.name") or props.get("application.process.binary") or "?"
            blob = " ".join(str(props.get(k, "")) for k in ("application.name", "application.process.binary", "media.name")).lower()
            if self.c.get("match") != ["*"] and not any(m.lower() in blob for m in self.c.get("match", [])):
                continue
            vol = it.get("volume", {})
            first = next(iter(vol.values()), {}) if isinstance(vol, dict) else {}
            try:
                pct = int(float(str(first.get("value_percent", "100%")).rstrip("%")))
            except ValueError:
                pct = 100
            res.append((int(it["index"]), pct, name))
        return res

    @staticmethod
    def _set(idx: int, pct: int) -> None:
        run(["pactl", "set-sink-input-volume", str(idx), f"{pct}%"])

    def duck(self) -> None:
        if not self.c.get("enabled"):
            return
        with self.lock:
            for idx, pct, _ in self.inputs():
                if idx not in self.saved:
                    self.saved[idx] = pct
                    self._set(idx, min(pct, int(self.c["level"])))

    def restore(self) -> None:
        with self.lock:
            for idx, pct in self.saved.items():
                self._set(idx, pct)
            self.saved.clear()


class Approval:
    def __init__(self, agent, sid, tool, summary, score, labels):
        self.id = uuid.uuid4().hex[:8]
        self.agent, self.sid, self.tool, self.summary, self.score, self.labels = agent, sid, tool, summary, score, labels
        self.event = threading.Event()
        self.decision: str | None = None
        self.reason = ""


class Core:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.lock = threading.RLock()
        self.sessions: "collections.OrderedDict[tuple, dict]" = collections.OrderedDict()
        self.approvals: list[Approval] = []
        self.session_allow: set[tuple] = set()
        self.toast_msg: tuple[str, str, float] | None = None
        self.kdrive_msg = ("", "info", 0.0)
        self.ai: dict = {"state": "idle", "title": "", "text": "", "t": 0.0}
        self.ai_gen = 0
        self.todos: list = self._load_todos()
        self.jobs: dict = {}
        self.kanban: dict = {"ok": False, "error": "lecture en cours…", "counts": {}, "active": [], "total": 0}
        self._kb_prev: dict | None = None
        self.weather: dict = {}
        self._geo = None
        self.calm: dict | None = None
        self.in_call, self._call_prev_dnd, self._call_paused, self._call_on_since, self._call_off_since = False, False, False, 0.0, 0.0
        self.secret_clear_at = 0.0
        self.fx_queue: list = []
        self.ollama_state: tuple[bool, str] = (False, "…")
        self.prefs: dict = self._load_prefs()
        self.profiles: list = []
        self.briefing: dict = {"state": "idle", "sections": [], "t0": 0.0, "date": "", "label": ""}
        self.mic: dict = {"state": "idle", "t0": 0.0, "msg": ""}
        self.speaking, self.speaking_section, self._bj_gen, self._bj_speak = False, -1, 0, None
        self.voice, self.speaker = Voice(cfg), Speaker(cfg)
        self.mail_reader, self.calendars = Thunderbird(cfg), Calendars(cfg)
        self.voice_info: dict = {"tts": [], "stt": [], "tb": None, "cals": 0, "feeds": 0}
        self.suggest_tab: str | None = None
        w = cfg["wellness"]
        self._eye_due = time.time() + float(w["eye_minutes"]) * 60
        self._water_due = time.time() + float(w["water_minutes"]) * 60
        self.locked = False
        self.denied_while_locked = 0
        self.music: dict = {}
        self.sys: dict = {}
        self.timers: list[dict] = []
        self.focus: dict | None = None
        self.dnd = False
        self.clips: "collections.deque[str]" = collections.deque(maxlen=int(cfg["clipboard"]["max_items"]))
        self.audit: "collections.deque[dict]" = collections.deque(maxlen=6)
        self.stats = self._load_stats()
        self.drop_pending = 0
        self.inhibited = False
        self.on_change = lambda: None
        self.ui_handler = lambda cmd, arg=None: None
        self.set_inhibit = lambda on: None
        self.radar, self.journal = Radar(cfg), Journal(cfg)
        self.kdrive, self.ollama, self.kanban_reader, self.ducker = KDrive(cfg, self), Ollama(cfg), Kanban(cfg), Ducker(cfg)
        self._ducked = False
        self._restore_timer: threading.Timer | None = None
        self._bat_alerted = False
        self._drop_busy = False
        self._bg_started = False

    # ---- bases ---------------------------------------------------------------
    def toast(self, text: str, kind: str = "info") -> None:
        self.toast_msg = (text, kind, time.time() + float(self.cfg["island"]["toast_seconds"]))
        self.on_change()

    def set_kdrive(self, text: str, kind: str) -> None:
        self.kdrive_msg = (text, kind, time.time() + 30)
        self.on_change()

    def play(self, kind: str) -> None:
        s = self.cfg["sounds"]
        if not s.get("enabled"):
            return
        f = (s.get("files") or {}).get(kind) or str(sound_path(kind, float(s.get("volume", 0.55))))
        f = os.path.expanduser(f)
        if os.path.exists(f):
            try:
                subprocess.Popen([a.replace("{file}", f) for a in s["player"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass

    def _session(self, agent: str, sid: str, p: dict) -> dict:
        s = self.sessions.get((agent, sid))
        if s is None:
            cwd = p.get("cwd") or ""
            s = {"agent": agent, "id": sid, "cwd": cwd, "label": os.path.basename(cwd.rstrip("/")) or sid[:6], "state": "idle", "tool": "",
                 "text": "", "started": time.time(), "updated": time.time(), "tools": collections.Counter(), "files": set(), "ok": 0, "no": 0,
                 "maxrisk": 0, "maxlabel": "", "dirty": False, "profile": p.get("profile") or ""}
            self.sessions[(agent, sid)] = s
        elif p.get("cwd") and not s["cwd"]:
            s["cwd"], s["label"] = p["cwd"], os.path.basename(p["cwd"].rstrip("/")) or s["label"]
        return s

    # ---- statistiques & audit --------------------------------------------------
    def _stats_path(self) -> pathlib.Path:
        return DATA_DIR / "stats.json"

    def _load_stats(self) -> dict:
        today = dt.date.today().isoformat()
        try:
            d = json.loads(self._stats_path().read_text())
            if d.get("date") == today:
                return d
        except Exception:
            pass
        return {"date": today, "tasks": 0, "ok": 0, "no": 0, "work": 0}

    def save_stats(self) -> None:
        if self.cfg["stats"].get("enabled"):
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                self._stats_path().write_text(json.dumps(self.stats))
            except OSError:
                pass

    def log_decision(self, agent, tool, summary, score, decision) -> None:
        rec = {"ts": time.time(), "agent": agent, "tool": tool, "summary": short(summary, 160), "score": score, "decision": decision}
        self.audit.appendleft(rec)
        if decision in ("allow", "always"):
            self.stats["ok"] += 1
        elif decision == "deny":
            self.stats["no"] += 1
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(DATA_DIR / "audit.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # ---- événements ------------------------------------------------------------
    def handle_event(self, agent: str, p: dict) -> None:
        ev = p.get("hook_event_name", "")
        sid = str(p.get("session_id") or p.get("task_id") or "default")
        ti = p.get("tool_input") or {}
        finished = None
        with self.lock:
            s = self._session(agent, sid, p)
            s["updated"] = time.time()
            if ev == "SessionStart":
                s["state"] = "idle"
            elif ev == "UserPromptSubmit":
                s["state"], s["text"] = "working", short(p.get("prompt"))
            elif ev in ("PreToolUse", "PostToolUse"):
                s["state"], s["tool"] = "working", p.get("tool_name", "")
                fp = (ti.get("file_path") or ti.get("path")) if isinstance(ti, dict) else None
                if fp:
                    s["files"].add(os.path.basename(str(fp)))
                if ev == "PostToolUse":
                    s["tools"][s["tool"] or "?"] += 1
                    s["dirty"] = True
            elif ev == "Notification":
                s["state"], s["text"] = "waiting", short(p.get("message"))
            elif ev == "AssistantText":
                s["text"] = short(p.get("text"))
            elif ev in ("Stop", "SessionEnd"):
                s["state"] = "done"
                if s["dirty"]:
                    finished = dict(s, tools=collections.Counter(s["tools"]), files=set(s["files"]))
                    s["tools"].clear(); s["files"].clear(); s["ok"] = s["no"] = s["maxrisk"] = 0; s["maxlabel"] = ""; s["dirty"] = False
        if finished:
            self.stats["tasks"] += 1
            self.toast(f"✔ {finished['agent']} a terminé · {finished['label']}", "ok")
            self.play("finish")
            self.fx("confetti")
            self.kdrive.schedule_journal_upload(self.journal.write_turn(finished))
        else:
            self.on_change()

    # ---- approbations ----------------------------------------------------------
    def request_approval(self, agent: str, p: dict, timeout: float | None = None) -> dict:
        cfg_a = self.cfg["approvals"]
        timeout = float(timeout or cfg_a["timeout_seconds"])
        tool, ti = p.get("tool_name", "?"), p.get("tool_input") or {}
        summary = str((ti.get("command") or ti.get("file_path") or ti.get("path") or p.get("description") or json.dumps(ti, ensure_ascii=False)) if isinstance(ti, dict) else ti)
        score, labels = self.radar.score(summary)
        sid = str(p.get("session_id") or p.get("task_id") or "default")
        with self.lock:
            s = self._session(agent, sid, p)
            if score > s["maxrisk"]:
                s["maxrisk"], s["maxlabel"] = score, labels[0]
            locked = self.locked and self.cfg["lock"].get("enabled", True)

        def done(decision, reason):
            self.log_decision(agent, tool, summary, score, decision)
            return {"decision": decision, "reason": reason}
        if locked:
            self.denied_while_locked += 1
            return done(self.cfg["lock"]["decision_when_locked"], "Écran verrouillé : personne devant l'ordinateur.")
        deny_at = int(self.cfg["radar"].get("deny_at", 0))
        if deny_at and score >= deny_at:
            return done("deny", f"Refusé par le radar de risque ({', '.join(labels)}).")
        hold_at = int(self.cfg["radar"].get("hold_at", 70))
        if (agent, tool) in self.session_allow and score < hold_at:
            with self.lock:
                s["ok"] += 1
            return done("allow", "Autorisé pour la session.")
        ap = Approval(agent, sid, tool, summary, score, labels)
        with self.lock:
            self.approvals.append(ap)
            s["state"] = "waiting"
        self.play("danger" if score >= hold_at else "approval")
        self._after_change()
        if cfg_a.get("gnome_notification"):
            threading.Thread(target=self._notify_thread, args=(ap, timeout), daemon=True).start()
        ap.event.wait(timeout)
        with self.lock:
            if ap in self.approvals:
                self.approvals.remove(ap)
            if ap.decision is None:
                ap.decision, ap.reason = cfg_a.get("on_timeout", "ask"), "Pas de réponse à temps."
            s["state"] = "working"
        self._after_change()
        return done(ap.decision, ap.reason)

    def resolve(self, ap_id: str, decision: str, reason: str = "") -> None:
        with self.lock:
            ap = next((a for a in self.approvals if a.id == ap_id), None)
            if ap is None or ap.decision is not None:
                return
            ap.decision = decision
            ap.reason = reason or {"allow": "Autorisé depuis l'île.", "always": "Autorisé pour la session depuis l'île.", "deny": "Refusé depuis l'île."}.get(decision, "")
            s = self.sessions.get((ap.agent, ap.sid))
            if s is not None:
                s["ok" if decision in ("allow", "always") else "no"] += 1
            if decision == "always":
                self.session_allow.add((ap.agent, ap.tool))
            if ap in self.approvals:
                self.approvals.remove(ap)
        ap.event.set()
        self.play("deny" if decision == "deny" else "allow")
        self._after_change()

    def _notify_thread(self, ap: Approval, timeout: float) -> None:
        if not shutil.which("notify-send"):
            return
        cmd = ["notify-send", "--app-name=Coucou", "--urgency=critical", "--wait", "-A", "deny=Refuser"]
        if ap.score < int(self.cfg["radar"].get("hold_at", 70)):
            cmd += ["-A", "allow=Autoriser"]
        risk = f"\nRisque {ap.score} : {', '.join(ap.labels)}" if ap.score else ""
        cmd += [f"{ap.agent} demande : {ap.tool}", short(ap.summary, 200) + risk]
        out = run(cmd, timeout + 5).strip()
        if out in ("allow", "deny"):
            self.resolve(ap.id, out)

    def set_locked(self, locked: bool) -> None:
        pending = []
        with self.lock:
            self.locked = locked
            if locked and self.cfg["lock"].get("enabled", True):
                pending = [a.id for a in self.approvals]
        for ap_id in pending:
            self.denied_while_locked += 1
            self.resolve(ap_id, self.cfg["lock"]["decision_when_locked"], "Écran verrouillé.")
        if not locked:
            n, self.denied_while_locked = self.denied_while_locked, 0
            if n and self.cfg["lock"].get("summary_on_return", True):
                self.toast(f"🔒 {n} demande(s) traitée(s) pendant ton absence", "warn")

    def _after_change(self) -> None:
        with self.lock:
            pending = len(self.approvals)
        if pending and not self._ducked:
            self._ducked = True
            if self._restore_timer:
                self._restore_timer.cancel()
            threading.Thread(target=self.ducker.duck, daemon=True).start()
        elif not pending and self._ducked:
            self._ducked = False
            self._restore_timer = threading.Timer(float(self.cfg["ducking"]["restore_delay"]), self.ducker.restore)
            self._restore_timer.daemon = True
            self._restore_timer.start()
        self.on_change()

    # ---- préférences mémorisées (réglages cliqués dans l'île) --------------------------------
    def _prefs_path(self) -> pathlib.Path:
        return DATA_DIR / "prefs.json"

    def _write_prefs(self, p: dict) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._prefs_path().write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _load_prefs(self) -> dict:
        try:
            p = json.loads(self._prefs_path().read_text(encoding="utf-8"))
        except Exception:
            p = {}
        if not p.get("migrated35"):                      # v3.5 : on débloque l'historique du presse-papiers
            p["clipboard.enabled"], p["migrated35"] = True, True
            self._write_prefs(p)
        for k, v in p.items():
            if "." in k:
                sec, key = k.split(".", 1)
                if isinstance(self.cfg.get(sec), dict):
                    self.cfg[sec][key] = v
        return p

    def set_pref(self, sec: str, key: str, val) -> None:
        self.cfg[sec][key] = val
        self.prefs[f"{sec}.{key}"] = val
        self._write_prefs(self.prefs)
        self.play("on" if val else "off")
        self.on_change()

    # ---- profils Hermes ----------------------------------------------------------------------------
    def profile_color(self, name: str):
        return profile_color(self.cfg, name)

    def _hermes_home(self) -> pathlib.Path:
        return pathlib.Path(os.path.expanduser(self.cfg["hermes"].get("home", "~/.hermes")))

    def _proc_profiles(self) -> dict:
        found: dict = {}
        me = os.getpid()
        for d in pathlib.Path("/proc").iterdir():
            if not d.name.isdigit() or int(d.name) == me:
                continue
            try:
                args = (d / "cmdline").read_bytes().split(b"\0")
                args = [a.decode("utf-8", "replace") for a in args if a]
                if not args or not any("hermes" in a for a in args[:3]) or any("coucou-fedora" in a for a in args[:3]):
                    continue
                name = None
                for i, a in enumerate(args):
                    if a in ("-p", "--profile") and i + 1 < len(args):
                        name = args[i + 1]
                if name is None:
                    env = (d / "environ").read_bytes().split(b"\0")
                    hh = next((e.decode()[12:] for e in env if e.startswith(b"HERMES_HOME=")), "")
                    name = os.path.basename(hh.rstrip("/")) if "/profiles/" in hh else "default"
                found[name] = found.get(name, 0) + 1
            except (OSError, ValueError):
                continue
        return found

    def _last_activity(self, name: str) -> float:
        base = self._hermes_home() if name == "default" else self._hermes_home() / "profiles" / name
        best = 0.0
        for rel in ("sessions", "state.db", "state.db-wal", "logs"):
            p = base / rel
            try:
                if p.is_dir():
                    with os.scandir(p) as it:
                        for n, e in enumerate(it):
                            best = max(best, e.stat().st_mtime)
                            if n > 300:
                                break
                elif p.exists():
                    best = max(best, p.stat().st_mtime)
            except OSError:
                pass
        return best

    def _poll_profiles(self) -> None:
        home = self._hermes_home()
        names = []
        if home.is_dir():
            names.append("default")
            pd = home / "profiles"
            if pd.is_dir():
                names += sorted(d.name for d in pd.iterdir() if d.is_dir())
        procs, now, kb = self._proc_profiles(), time.time(), self.kanban
        live = {}
        with self.lock:
            for s in self.sessions.values():
                if s["agent"] == "hermes" and s.get("profile") and s["state"] in ("working", "waiting") and now - s["updated"] < 120:
                    live.setdefault(s["profile"], s)
        out = []
        for n in names:
            who = (kb.get("by_who") or {}).get(n.lower(), {})
            cur = (kb.get("current") or {}).get(n.lower(), "")
            last = self._last_activity(n)
            ls = live.get(n)
            if ls:
                state, detail = "working", (ls["tool"] or ls["text"] or "en cours")
            elif who.get("running"):
                state, detail = "working", cur or "tâche Kanban en cours"
            elif procs.get(n):
                state, detail = "open", "session ouverte"
            else:
                state, detail = "idle", ""
            if state != "working" and last:
                ago = now - last
                detail = (detail + " · " if detail else "") + ("actif à l'instant" if ago < 90 else f"dernière activité il y a {fmt_time(ago)}" if ago < 3600 else
                                                           f"dernière activité il y a {int(ago // 3600)} h" if ago < 86400 else f"inactif depuis {int(ago // 86400)} j")
            out.append({"name": n, "color": self.profile_color(n), "state": state, "detail": detail, "tasks": dict(who), "current": cur, "procs": procs.get(n, 0)})
        out.sort(key=lambda p: ({"working": 0, "open": 1, "idle": 2}[p["state"]], p["name"]))
        self.profiles = out

    def profile_summary(self, name: str) -> str:
        p = next((p for p in self.profiles if p["name"].lower() == name.lower()), None)
        if not p:
            return f"Profil « {name} » introuvable"
        t = p["tasks"]
        tasks = ", ".join(f"{n} {k}" for k, n in t.items()) if t else "aucune tâche Kanban"
        return f"{p['name']} : {'travaille' if p['state'] == 'working' else 'ouvert' if p['state'] == 'open' else 'inactif'} · {p['detail'] or '—'} · {tasks}"

    def _tint(self):
        with self.lock:
            best = max((s for s in self.sessions.values() if s["agent"] == "hermes" and s.get("profile") and s["state"] in ("working", "waiting")),
                       key=lambda s: s["updated"], default=None)
        if self.ai.get("state") in ("busy", "stream") and self.ai.get("color"):
            return self.ai["color"]
        return self.profile_color(best["profile"]) if best else None

    def ask_profile(self, name: str, question: str) -> None:
        exe = self.cfg["hermes"].get("bin") or shutil.which("hermes") or str(HOME / ".local/bin/hermes")
        color = self.profile_color(name)
        self.ai_gen += 1
        gen, t0 = self.ai_gen, time.time()
        title = f"{name} ← {short(question, 34)}"
        self.ai = {"state": "busy", "title": title, "text": "", "t": t0, "color": color}
        self.play("tick")
        self.on_change()

        def work():
            cmd = [exe] + ([] if name == "default" else ["-p", name]) + ["chat", "-Q", "-q", question]
            text = ""
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
                killer = threading.Timer(300, p.kill)
                killer.start()
                for line in p.stdout:
                    text += re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", line)
                    if gen == self.ai_gen:
                        self.ai = {"state": "stream", "title": title, "text": text.strip(), "t": t0, "color": color}
                        self.on_change()
                p.wait()
                killer.cancel()
                if gen == self.ai_gen:
                    self.ai = {"state": "done", "title": title, "text": text.strip() or "(réponse vide)", "t": time.time(), "color": color}
                    self.play("msg")
            except Exception as e:
                if gen == self.ai_gen:
                    self.ai = {"state": "error", "title": title, "text": f"Hermes injoignable : {short(e, 100)}", "t": time.time(), "color": color}
                    self.play("error")
            self.on_change()
        threading.Thread(target=work, daemon=True).start()

    # ---- « Bonjour ! » : résumé du matin (Thunderbird + agendas + actus + tâches, piloté par Qwen) -----------
    def _bj_set(self, gen: int, key: str, text: str | None = None, state: str | None = None) -> None:
        if gen != self._bj_gen:
            return
        with self.lock:
            for s in self.briefing["sections"]:
                if s["key"] == key:
                    if text is not None:
                        s["text"] = text
                    if state:
                        s["state"] = state
        self.on_change()

    def bonjour(self, speak: bool | None = None) -> None:
        if self.briefing["state"] == "running":
            return
        self._bj_gen += 1
        gen = self._bj_gen
        days = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
        months = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre")
        today = dt.date.today()
        meta = (("meteo", "Météo", "🌤"), ("agenda", "Agenda", "📅"), ("mails", "Mails des 48 h", "✉"), ("taches", "Tâches", "✅"), ("actus", "Actus", "📰"), ("plan", "Plan du jour", "🧭"))
        self.briefing = {"state": "running", "t0": time.time(), "date": today.isoformat(), "label": f"{days[today.weekday()]} {today.day} {months[today.month - 1]}",
                         "sections": [{"key": k, "title": t, "icon": i, "state": "pending", "text": ""} for k, t, i in meta]}
        self._bj_speak = speak
        self.play("open")
        self.on_change()
        threading.Thread(target=self._bj_run, args=(gen,), daemon=True).start()

    def _bj_run(self, gen: int) -> None:
        res: dict = {}
        b = self.cfg["bonjour"]

        def collect(name, fn):
            try:
                res[name] = fn()
            except Exception as e:
                res[name] = e
        jobs = []
        if b["mail"].get("enabled"):
            jobs.append(threading.Thread(target=collect, args=("mails", self.mail_reader.recent), daemon=True))
        jobs.append(threading.Thread(target=collect, args=("agenda", self.calendars.events), daemon=True))
        jobs.append(threading.Thread(target=collect, args=("feeds", self._collect_feeds), daemon=True))
        for j in jobs:
            j.start()
        # météo
        self._bj_set(gen, "meteo", state="busy")
        if not self.weather.get("ok") and self.cfg["weather"].get("city"):
            self._refresh_weather()
        w = self.weather
        self._bj_set(gen, "meteo", f"{w['label']}, {w['temp']:.0f} °C à {w['city']} (min {w['tmin']:.0f}°, max {w['tmax']:.0f}°), pluie {w['rain']} %" if w.get("ok")
                     else "Météo indisponible (renseigne ta ville dans [weather] city).", "done")
        for j in jobs:
            j.join(30)
        # agenda (liste exacte, sans IA)
        self._bj_set(gen, "agenda", state="busy")
        ag = res.get("agenda")
        if isinstance(ag, Exception) or ag is None:
            agenda_txt = f"Agendas indisponibles : {short(ag, 60)}"
        else:
            evs, errs = ag
            if not self.calendars.count():
                agenda_txt = "Aucun agenda configuré : ajoute tes adresses iCal Google dans [[bonjour.calendars]]."
            else:
                today, lines = dt.date.today(), []
                for day in (today, today + dt.timedelta(days=1)):
                    day_ev = [e for e in evs if (e["start"].date() if isinstance(e["start"], dt.datetime) else e["start"]) == day]
                    if day_ev:
                        lines.append("Aujourd'hui :" if day == today else "Demain :")
                        for e in day_ev:
                            when = "Toute la journée" if e["allday"] else f"{e['start']:%H:%M}–{e['end']:%H:%M}"
                            lines.append(f"• {when}  {e['title']}" + (f"  ({e['cal']})" if len(self.calendars.c["calendars"]) > 1 else "") + (f"  📍 {short(e['loc'], 30)}" if e["loc"] else ""))
                agenda_txt = "\n".join(lines) if lines else "Rien de prévu aujourd'hui ni demain."
                if errs:
                    agenda_txt += "\n⚠ " + " ; ".join(errs)
        self._bj_set(gen, "agenda", agenda_txt, "done")
        # tâches (liste exacte)
        todo = [t["text"] for t in self.todos if not t["done"]]
        blocked = self.kanban.get("counts", {}).get("blocked", 0) if self.kanban.get("ok") else 0
        tt = "\n".join("• " + t for t in todo[:8]) if todo else "Aucune tâche en attente 🎉"
        if blocked:
            tt += f"\n⛔ {blocked} tâche(s) Kanban Hermes bloquée(s)"
        self._bj_set(gen, "taches", tt, "done")
        # mails (résumé par Qwen)
        self._bj_set(gen, "mails", state="busy")
        mails = res.get("mails")
        if not b["mail"].get("enabled"):
            self._bj_set(gen, "mails", "Lecture des mails désactivée.", "done")
        elif isinstance(mails, Exception):
            self._bj_set(gen, "mails", f"Lecture Thunderbird impossible : {short(mails, 70)}", "error")
        elif not mails:
            info = self.mail_reader.info()
            self._bj_set(gen, "mails", "Aucun mail trouvé sur les 48 dernières heures." if info else "Profil Thunderbird introuvable (voir [bonjour.mail] profile_dir).", "done")
        else:
            digest = "\n".join(f"- {'[NON LU] ' if m['unread'] else ''}De {m['from']} : « {m['subject']} » — {m['snippet']}" for m in mails[:int(b["mail"]["max_mails"])])
            self._bj_llm(gen, "mails", "Voici mes mails des dernières 48 h. Garde uniquement ceux qui comptent (ignore publicités et newsletters sans intérêt). "
                         "Écris au maximum 6 lignes, une par mail, au format : « Expéditeur — résumé en 10 mots maximum — ⚡ action à faire » (n'écris l'action que s'il y en a une). "
                         "S'il y a quelque chose d'urgent, ajoute à la fin une ligne « 🔥 Urgent : … ».\n\n" + digest)
        # actus (choix + résumé par Qwen)
        self._bj_set(gen, "actus", state="busy")
        feeds = res.get("feeds")
        if isinstance(feeds, Exception) or not feeds or not any(feeds.values()):
            self._bj_set(gen, "actus", "Actualités indisponibles (aucun flux n'a répondu).", "error")
        else:
            cat = {"monde": "MONDE", "france": "FRANCE", "tech": "IA / TECH", "sport": "SPORT"}
            block = "\n\n".join(f"== {cat.get(k, k.upper())} ==\n" + "\n".join(f"- {i['title']} — {i['desc']}" for i in v[:7]) for k, v in feeds.items() if v)
            self._bj_llm(gen, "actus", "Voici des titres d'actualité du jour par catégorie. Choisis les plus importants : 1 info MONDE, 2 infos FRANCE, 1 info IA/TECH, 1 info SPORT. "
                         "Pour chacune, écris une ligne : emoji (🌍, 🇫🇷, 🇫🇷, 🤖, ⚽) + titre court + une phrase de contexte. Base-toi uniquement sur ce qui est fourni, n'invente rien. "
                         "Si une catégorie est vide, saute-la.\n\n" + block)
        # plan du jour (Qwen synthétise)
        self._bj_set(gen, "plan", state="busy")
        sec = {s["key"]: s["text"] for s in self.briefing["sections"]}
        self._bj_llm(gen, "plan", "Propose-moi un plan de journée très concret en 4 puces maximum, à partir de ces informations. Sois motivant et bref.\n"
                     f"MÉTÉO : {sec.get('meteo')}\nAGENDA :\n{sec.get('agenda')}\nTÂCHES :\n{sec.get('taches')}\nMAILS :\n{sec.get('mails')}")
        if gen != self._bj_gen:
            return
        with self.lock:
            self.briefing["state"] = "done"
        self.play("finish")
        self.fx("confetti")
        self.on_change()
        if self._bj_speak or (self._bj_speak is None and self.cfg["bonjour"].get("autoplay_voice")):
            self.speak_briefing()

    def _bj_llm(self, gen: int, key: str, prompt: str) -> None:
        try:
            res = self.ollama.ask(prompt, None, lambda t: self._bj_set(gen, key, t.strip(), "busy"))
            self._bj_set(gen, key, res or "(rien à signaler)", "done")
        except Exception as e:
            self._bj_set(gen, key, f"Qwen indisponible : {short(e, 70)}", "error")

    def _collect_feeds(self) -> dict:
        out: dict = {}
        for f in self.cfg["bonjour"].get("feeds", []):
            try:
                out.setdefault(f["category"], []).extend(fetch_feed(f["url"]))
            except Exception:
                out.setdefault(f["category"], [])
        return out

    def briefing_text(self) -> str:
        b = self.briefing
        return f"# Bonjour ! — {b.get('label', '')}\n\n" + "\n\n".join(f"## {s['icon']} {s['title']}\n{s['text']}" for s in b["sections"] if s["text"])

    def save_briefing(self) -> None:
        if self.briefing["sections"]:
            self.kdrive.save_text(self.briefing_text(), "Notes", "bonjour")

    # ---- voix : lecture du résumé & micro ----------------------------------------------------------------------
    def speak_briefing(self) -> None:
        b = self.briefing
        chunks = [(-1, f"Bonjour ! Voici ton résumé du {b.get('label', 'jour')}.")]
        for i, s in enumerate(b["sections"]):
            if s["state"] == "done" and s["text"] and not s["text"].startswith(("Aucun agenda configuré", "Météo indisponible")):
                chunks.append((i, f"{s['title']}. {s['text']}"))
        self.speak_chunks(chunks)

    def speak_chunks(self, chunks: list) -> None:
        if self.speaking:
            return

        def work():
            self.speaking = True
            paused = self.music.get("status") == "Playing"
            if paused:
                self.ui_handler("music", "Pause")
            self.on_change()
            try:
                for idx, txt in chunks:
                    self.speaking_section = idx
                    self.on_change()
                    self.speaker.say(txt)
                    if self.speaker.stop_flag:
                        break
            except Exception as e:
                self.toast(f"Voix : {short(e, 80)}", "danger")
                self.play("error")
            finally:
                self.speaking, self.speaking_section = False, -1
                if paused:
                    self.ui_handler("music", "Play")
                self.on_change()
        threading.Thread(target=work, daemon=True).start()

    def toggle_speak(self) -> None:
        if self.speaking:
            self.speaker.stop()
        elif self.briefing["state"] != "idle":
            self.speak_briefing()

    def mic_toggle(self) -> None:
        st = self.mic["state"]
        if st == "rec":
            return self._mic_stop()
        if st == "transcribing":
            return
        try:
            self.voice.start()
        except Exception as e:
            self.mic = {"state": "error", "t0": time.time(), "msg": short(e, 120)}
            self.toast(f"Micro : {short(e, 60)}", "danger")
            return self.on_change()
        self.mic = {"state": "rec", "t0": time.time(), "msg": ""}
        self.play("call_on")
        self.on_change()

    def _mic_stop(self) -> None:
        path = self.voice.stop()
        self.mic = {"state": "transcribing", "t0": time.time(), "msg": ""}
        self.play("call_off")
        self.on_change()

        def work():
            if path is None:
                self.mic = {"state": "idle", "t0": 0.0, "msg": ""}
                self.toast("Je n'ai rien entendu", "warn")
                return self.on_change()
            try:
                text = self.voice.transcribe(path)
            except Exception as e:
                self.mic = {"state": "error", "t0": time.time(), "msg": short(e, 200)}
                self.play("error")
                return self.on_change()
            self.mic = {"state": "idle", "t0": 0.0, "msg": ""}
            if not text:
                self.toast("Je n'ai rien compris", "warn")
                return self.on_change()
            try:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                with open(DATA_DIR / "voice_notes.md", "a", encoding="utf-8") as f:
                    f.write(f"- {dt.datetime.now():%Y-%m-%d %H:%M} — {text}\n")
            except OSError:
                pass
            self.toast(f"🎤 « {short(text, 44)} »", "info")
            self.magic(text)
        threading.Thread(target=work, daemon=True).start()

    def _probe_sources(self) -> None:
        b = self.cfg["bonjour"]
        self.voice_info = {"tts": self.speaker.engines(), "stt": self.voice.engines(), "tb": self.mail_reader.info() if b["mail"].get("enabled") else "désactivé",
                           "cals": self.calendars.count(), "feeds": len(b.get("feeds", []))}
        self.on_change()

    def _nudge(self) -> None:
        b, today = self.cfg["bonjour"], dt.date.today().isoformat()
        if b.get("enabled") and b.get("nudge") and self.prefs.get("nudged") != today and 5 <= dt.datetime.now().hour < 12 \
                and self.briefing.get("date") != today and not self.locked:
            self.prefs["nudged"] = today
            self._write_prefs(self.prefs)
            self.suggest_tab = "Bonjour"
            self.toast("☀ Bonjour ! Ton résumé du matin t'attend", "info")
            self.play("msg")

    def _mic_watchdog(self, now: float) -> None:
        if self.mic["state"] == "rec" and now - self.mic["t0"] > float(self.cfg["voice"].get("max_seconds", 60)):
            self._mic_stop()

    # ---- effets visuels & IA locale (Ollama) ---------------------------------------
    def fx(self, kind: str, **kw) -> None:
        self.fx_queue.append((kind, kw))

    def ai_run(self, title: str, prompt: str, system: str | None = None) -> None:
        if not self.cfg["ollama"].get("enabled"):
            self.toast("IA locale désactivée ([ollama] enabled)", "warn")
            return
        self.ai_gen += 1
        gen, t0 = self.ai_gen, time.time()
        self.ai = {"state": "busy", "title": title, "text": "", "t": t0}
        self.play("tick")
        self.on_change()

        def work():
            def upd(text):
                if gen == self.ai_gen:
                    self.ai = {"state": "stream", "title": title, "text": text, "t": t0}
                    self.on_change()
            try:
                res = self.ollama.ask(prompt, system, upd)
                if gen == self.ai_gen:
                    self.ai = {"state": "done", "title": title, "text": res or "(réponse vide)", "t": time.time()}
                    self.play("msg")
            except Exception as e:
                if gen == self.ai_gen:
                    self.ai = {"state": "error", "title": title, "text": f"Ollama injoignable : {short(e, 120)}", "t": time.time()}
                    self.play("error")
            self.on_change()
        threading.Thread(target=work, daemon=True).start()

    def ai_clear(self) -> None:
        self.ai_gen += 1
        self.ai = {"state": "idle", "title": "", "text": "", "t": 0.0}
        self.on_change()

    def ai_clip(self, tpl: str, label: str) -> None:
        self.ui_handler("clip_ai", (tpl, label))

    def ai_recap(self) -> None:
        try:
            j = (self.journal.dir / f"{dt.date.today().isoformat()}.md").read_text(encoding="utf-8")[-5000:]
        except OSError:
            j = ""
        st, done = self.stats, [t["text"] for t in self.todos if t["done"]][:10]
        self.ai_run("Bilan du jour", f"Voici mon activité du jour.\nStatistiques : {st['tasks']} tâches d'agents terminées, {st['ok']} commandes autorisées, "
                    f"{st['no']} refusées, {fmt_time(st['work'])} de travail des agents.\nTâches cochées : {', '.join(done) or 'aucune'}.\n"
                    f"Journal des agents :\n{j or '(vide)'}\n\nFais un bilan chaleureux et concret de ma journée en 5 lignes maximum.")

    def ai_brief(self) -> None:
        w, kb, parts = self.weather, self.kanban, []
        if w.get("ok"):
            parts.append(f"Météo à {w['city']} : {w['label']}, {w['temp']:.0f} °C (min {w['tmin']:.0f}, max {w['tmax']:.0f}), pluie {w['rain']}%.")
        todo = [t["text"] for t in self.todos if not t["done"]][:10]
        parts.append("Tâches à faire : " + ("; ".join(todo) if todo else "aucune") + ".")
        if kb.get("ok"):
            parts.append("Kanban Hermes : " + ", ".join(f"{k}={v}" for k, v in kb["counts"].items()) + ".")
        self.ai_run("Brief du matin", "Fais-moi un brief du matin motivant en 4 lignes maximum à partir de ceci.\n" + "\n".join(parts))

    def ai_prioritize(self) -> None:
        todo = [t["text"] for t in self.todos if not t["done"]]
        if not todo:
            self.toast("Aucune tâche à prioriser", "warn")
            return
        self.ai_run("Priorités", "Classe ces tâches de la plus à la moins prioritaire, avec une courte raison (une ligne chacune) :\n- " + "\n- ".join(todo))

    def save_ai_note(self) -> None:
        if self.ai["text"]:
            self.kdrive.save_text(f"# {self.ai['title']}\n\n{self.ai['text']}", "Notes", "ia")

    # ---- barre magique (raccourci `coucou-fedora prompt`) -----------------------------
    def magic(self, text: str) -> None:
        t = text.strip()
        if not t:
            return
        low = t.lower()
        m = re.match(r"^(todo|tâche|tache|\+)\s*:?\s+(.+)$", t, re.I)
        if m:
            return self.add_todo(m[2])
        m = re.match(r"^(rappel|rappelle|timer|minuteur|dans)\s+(\d+\s*[smh]?)\s*(?:pour|de|:)?\s*(.*)$", t, re.I)
        if m:
            try:
                return self.add_timer(parse_dur(m[2]), m[3] or f"Minuteur {m[2].strip()}")
            except ValueError:
                pass
        m = re.fullmatch(r"focus(?:\s+(\d+))?", low)
        if m:
            return self.start_focus(float(m[1] or 25))
        m = re.match(r"^@(\S+)\s*(.*)$", t)
        if m:
            return self.ask_profile(m[1], m[2].strip()) if m[2].strip() else self.toast(short(self.profile_summary(m[1]), 70), "info")
        if low in ("bonjour", "bonjour !", "résumé du matin", "resume du matin"):
            return self.bonjour()
        if low in ("lis", "lis le résumé", "lire", "stop"):
            return self.toggle_speak()
        if low in ("micro", "mic"):
            return self.mic_toggle()
        if low in ("bilan", "bilan du jour"):
            return self.ai_recap()
        if low in ("brief", "brief du matin"):
            return self.ai_brief()
        if low in ("respire", "respirer", "pause"):
            return self.start_calm("breath")
        if t.startswith("=") or (re.fullmatch(r"[\d\s.,+\-*/()%^×÷]+(?:\s*de\s*[\d.,]+)?", t) and re.search(r"\d\s*[+\-*/^%×÷]", t)):
            res = calc(t.lstrip("= "))
            if res is not None:
                self.toast(f"= {res}", "ok")
                self.ui_handler("copy", str(res))
                return self.play("done")
        self.ai_run(short(t, 40), t)

    # ---- tâches (todo) ---------------------------------------------------------------
    def _todo_path(self) -> pathlib.Path:
        return DATA_DIR / "todo.json"

    def _load_todos(self) -> list:
        try:
            return json.loads(self._todo_path().read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_todos(self) -> None:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._todo_path().write_text(json.dumps(self.todos, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def add_todo(self, text: str) -> None:
        with self.lock:
            self.todos.append({"id": uuid.uuid4().hex[:6], "text": short(text, 120), "done": False, "ts": time.time()})
            self._save_todos()
        self.toast(f"✓ Ajouté : {short(text, 40)}", "ok")
        self.play("on")

    def toggle_todo(self, tid: str) -> None:
        with self.lock:
            for t in self.todos:
                if t["id"] == tid:
                    t["done"] = not t["done"]
                    self.play("done" if t["done"] else "off")
            self._save_todos()
        self.on_change()

    def delete_todo(self, tid: str) -> None:
        with self.lock:
            self.todos = [t for t in self.todos if t["id"] != tid]
            self._save_todos()
        self.play("close")
        self.on_change()

    def clear_done(self) -> None:
        with self.lock:
            self.todos = [t for t in self.todos if not t["done"]]
            self._save_todos()
        self.play("close")
        self.on_change()

    # ---- commandes longues surveillées (`coucou-fedora watch …`) ------------------------
    def job_start(self, jid: str, label: str) -> None:
        with self.lock:
            self.jobs[jid] = {"id": jid, "label": short(label, 50), "start": time.time(), "end": None, "code": None}
        self.play("tick")
        self.on_change()

    def job_end(self, jid: str, code: int) -> None:
        with self.lock:
            j = self.jobs.get(jid)
            if not j:
                return
            j["end"], j["code"] = time.time(), code
            label, dur = j["label"], j["end"] - j["start"]
        self.toast(f"{'✔' if code == 0 else '✖'} {label} · {fmt_time(dur)}", "ok" if code == 0 else "danger")
        self.play("finish" if code == 0 else "error")
        self.fx("confetti" if code == 0 else "shake")

    # ---- bien-être : pause yeux, respiration, eau ---------------------------------------
    def start_calm(self, kind: str = "breath", seconds: float | None = None) -> None:
        w = self.cfg["wellness"]
        dur = seconds or (w["eye_seconds"] if kind == "eye" else w["breath_seconds"])
        with self.lock:
            self.calm = {"kind": kind, "start": time.time(), "dur": float(dur)}
        self.play("focus")
        self.on_change()

    def end_calm(self, finished: bool = False) -> None:
        with self.lock:
            was, self.calm = self.calm, None
        if was and finished:
            self.play("finish")
            self.toast("Pause terminée — merci !", "ok")
            self.fx("sparkle")
        elif was:
            self.play("close")
        self.on_change()

    def _wellness_tick(self, now: float) -> None:
        w = self.cfg["wellness"]
        if self.calm:
            if now >= self.calm["start"] + self.calm["dur"]:
                self.end_calm(True)
            return
        if w.get("eye_break") and now >= self._eye_due and not self.focus and not self.in_call:
            self._eye_due = now + float(w["eye_minutes"]) * 60 + float(w["eye_seconds"])
            self.start_calm("eye")
        if w.get("water") and now >= self._water_due:
            self._water_due = now + float(w["water_minutes"]) * 60
            if not self.in_call:
                self.toast("💧 Pense à boire un verre d'eau", "info")
                self.play("msg")

    # ---- mode appel automatique ---------------------------------------------------------------
    def _check_call(self, now: float) -> None:
        c = self.cfg["calls"]
        if not c.get("enabled"):
            return
        try:
            data = json.loads(run(["pactl", "--format=json", "list", "source-outputs"]))
        except ValueError:
            data = []
        active = False
        for it in data:
            props = it.get("properties", {})
            blob = " ".join(str(props.get(k, "")) for k in ("application.name", "application.process.binary", "media.name")).lower()
            if it.get("corked") or any(i.lower() in blob for i in c.get("ignore", [])):
                continue
            active = True
        if active:
            self._call_off_since = 0.0
            self._call_on_since = self._call_on_since or now
            if not self.in_call and now - self._call_on_since >= 4:
                self.in_call, self._call_prev_dnd = True, self.dnd
                if c.get("dnd"):
                    self.set_dnd(True)
                if c.get("pause_music") and self.music.get("status") == "Playing":
                    self._call_paused = True
                    self.ui_handler("music", "Pause")
                self.play("call_on")
                self.toast("🎙 Appel détecté · silence activé", "info")
        else:
            self._call_on_since = 0.0
            if self.in_call:
                self._call_off_since = self._call_off_since or now
                if now - self._call_off_since >= 6:
                    self.in_call = False
                    if c.get("dnd") and not self.focus:
                        self.set_dnd(self._call_prev_dnd)
                    if self._call_paused:
                        self._call_paused = False
                        self.ui_handler("music", "Play")
                    self.play("call_off")
                    self.toast("Appel terminé", "info")

    # ---- météo (Open-Meteo, sans clé) ---------------------------------------------------------------
    def _refresh_weather(self) -> None:
        wc = self.cfg["weather"]
        city = (wc.get("city") or "").strip()
        if not (wc.get("enabled") and city):
            return
        try:
            if not self._geo or self._geo[0] != city:
                with urllib.request.urlopen("https://geocoding-api.open-meteo.com/v1/search?name=" + urllib.parse.quote(city) + "&count=1&language=fr", timeout=6) as r:
                    res = json.load(r)["results"][0]
                self._geo = (city, res["latitude"], res["longitude"], res.get("name", city))
            _, lat, lon, name = self._geo
            url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,weather_code,is_day"
                   "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&timezone=auto&forecast_days=1")
            with urllib.request.urlopen(url, timeout=6) as r:
                d = json.load(r)
            label, icon = WMO.get(int(d["current"]["weather_code"]), ("—", "cloud"))
            self.weather = {"ok": True, "city": name, "temp": d["current"]["temperature_2m"], "label": label, "icon": icon,
                            "night": not d["current"].get("is_day", 1), "tmin": d["daily"]["temperature_2m_min"][0],
                            "tmax": d["daily"]["temperature_2m_max"][0], "rain": d["daily"]["precipitation_probability_max"][0] or 0}
        except Exception as e:
            self.weather = {"ok": False, "error": short(e, 60)}
        self.on_change()

    # ---- actions rapides ----------------------------------------------------------------------------------
    def run_action(self, idx: int) -> None:
        a = self.cfg.get("actions", [])[idx]
        kind = a.get("kind", "shell")

        def work():
            if kind == "shell":
                subprocess.Popen(a["cmd"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            elif kind == "dark_mode":
                dark = "dark" in run(["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"])
                run(["gsettings", "set", "org.gnome.desktop.interface", "color-scheme", "default" if dark else "prefer-dark"])
                self.toast("☀ Mode clair" if dark else "🌙 Mode sombre", "info")
            elif kind == "night_light":
                key = ["org.gnome.settings-daemon.plugins.color", "night-light-enabled"]
                on = run(["gsettings", "get", *key]).strip() == "true"
                run(["gsettings", "set", *key, "false" if on else "true"])
                self.toast("Lumière nocturne " + ("coupée" if on else "activée"), "info")
            elif kind == "open_depot":
                self.open_folder(str(self.kdrive.root()))
        try:
            threading.Thread(target=work, daemon=True).start()
            self.play("click")
        except (OSError, KeyError) as e:
            self.toast(f"Action impossible : {short(e, 40)}", "danger")

    # ---- garde-secrets du presse-papiers ----------------------------------------------------------------
    def on_clipboard(self, text: str) -> bool:
        c = self.cfg["clipboard"]
        if c.get("guard") and text and any(rx.search(text) for rx in SECRET_RX):
            self.secret_clear_at = time.time() + float(c["guard_seconds"])
            self.toast(f"🔐 Secret copié — effacement dans {int(c['guard_seconds'])} s", "warn")
            self.play("danger")
            return True
        self.add_clip(text)
        return False

    # ---- Kanban Hermes ---------------------------------------------------------------------------------------
    def _poll_kanban(self) -> None:
        if not self.cfg["hermes"].get("kanban"):
            return
        res, prev = self.kanban_reader.read(), self._kb_prev
        if res["ok"] and prev is not None:
            for tid, t in res["tasks"].items():
                p = prev.get(tid)
                if p is None or p["status"] == t["status"]:
                    continue
                if t["status"] == "done":
                    self.toast(f"✅ Kanban : {t['title']}", "ok"); self.play("finish"); self.fx("confetti")
                elif t["status"] == "blocked":
                    self.toast(f"⛔ Kanban bloqué : {t['title']}", "warn"); self.play("error")
                elif t["status"] == "running":
                    self.toast(f"▶ Kanban démarré : {t['title']}", "info"); self.play("tick")
        if res["ok"]:
            self._kb_prev = res["tasks"]
        self.kanban = {k: v for k, v in res.items() if k != "tasks"}

    def _ping_ollama(self) -> None:
        self.ollama_state = self.ollama.ping() if self.cfg["ollama"].get("enabled") else (False, "désactivé")

    # ---- minuteurs, focus, silence ----------------------------------------------
    def add_timer(self, seconds: float, label: str = "Minuteur") -> None:
        with self.lock:
            self.timers.append({"id": uuid.uuid4().hex[:6], "label": label, "end": time.time() + seconds, "total": seconds})
        self.toast(f"⏱ {label} · {fmt_time(seconds)}", "info")

    def cancel_timer(self, tid: str) -> None:
        with self.lock:
            self.timers = [t for t in self.timers if t["id"] != tid]
        self.on_change()

    def set_dnd(self, on: bool) -> None:
        run(["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", "false" if on else "true"])
        self.dnd = on
        self.on_change()

    def start_focus(self, minutes: float) -> None:
        with self.lock:
            self.focus = {"end": time.time() + minutes * 60, "total": minutes * 60, "prev_dnd": self.dnd}
        if self.cfg["focus"].get("dnd"):
            self.set_dnd(True)
        self.play("focus")
        self.toast(f"🎯 Focus {int(minutes)} min · notifications coupées", "ok")

    def stop_focus(self, finished: bool = False) -> None:
        with self.lock:
            f, self.focus = self.focus, None
        if f and self.cfg["focus"].get("dnd"):
            self.set_dnd(f["prev_dnd"])
        if finished:
            self.play("timer")
            self.toast("🎯 Focus terminé — fais une pause !", "ok")
        self.on_change()

    def set_volume(self, pct: int) -> None:
        self.sys["vol"] = pct
        threading.Thread(target=run, args=(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"],), daemon=True).start()

    def toggle_mute(self) -> None:
        self.sys["mute"] = not self.sys.get("mute", False)
        threading.Thread(target=run, args=(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],), daemon=True).start()

    def add_clip(self, text: str) -> None:
        c = self.cfg["clipboard"]
        if c.get("enabled") and text and len(text) <= int(c["max_chars"]) and (not self.clips or self.clips[0] != text):
            self.clips.appendleft(text)
            self.on_change()

    @staticmethod
    def open_folder(path: str) -> None:
        if path and os.path.isdir(path):
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---- tâche de fond (1 Hz) ------------------------------------------------------
    def start_background(self) -> None:
        if self._bg_started:
            return
        self._bg_started = True
        self.dnd = run(["gsettings", "get", "org.gnome.desktop.notifications", "show-banners"]).strip() == "false"
        threading.Thread(target=ensure_sounds, args=(float(self.cfg["sounds"].get("volume", 0.55)),), daemon=True).start()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        n, kb_every = 0, max(1, int(self.cfg["hermes"].get("kanban_poll_seconds", 3)))
        wmin = max(1, int(self.cfg["weather"].get("refresh_minutes", 30))) * 60
        while True:
            time.sleep(1.0)
            n += 1
            now = time.time()
            try:
                self._tick_timers()
                self._wellness_tick(now)
                if n % 2 == 0:
                    self.sys.update(self.read_sys())
                    self._check_battery()
                    self._update_inhibit()
                    self._check_call(now)
                if n % kb_every == 0:
                    self._poll_kanban()
                if n % 30 == 1 and self.cfg["network"].get("enabled"):
                    threading.Thread(target=lambda: self.sys.update(self.read_net()), daemon=True).start()
                if n == 3 or n % wmin == 0:
                    threading.Thread(target=self._refresh_weather, daemon=True).start()
                if n % 20 == 2:
                    threading.Thread(target=self._ping_ollama, daemon=True).start()
                if n % 30 == 0:
                    self.save_stats()
                if n % 3 == 0:
                    self._poll_profiles()
                self._mic_watchdog(now)
                if n % 60 == 5:
                    self._nudge()
                if n % 60 == 1:
                    threading.Thread(target=self._probe_sources, daemon=True).start()
                with self.lock:
                    self.jobs = {k: j for k, j in self.jobs.items() if j["end"] is None or now - j["end"] < 90}
            except Exception as e:
                print("[coucou] tâche de fond :", e, file=sys.stderr)
            self.on_change()

    def _tick_timers(self) -> None:
        now, expired = time.time(), []
        with self.lock:
            expired = [t for t in self.timers if t["end"] <= now]
            self.timers = [t for t in self.timers if t["end"] > now]
            f = self.focus
        for t in expired:
            self.play("timer")
            self.toast(f"⏰ {t['label']}", "warn")
            if shutil.which("notify-send"):
                subprocess.Popen(["notify-send", "--app-name=Coucou", "--urgency=critical", f"⏰ {t['label']}", "Le minuteur est terminé."])
        if f and f["end"] <= now:
            self.stop_focus(finished=True)

    def working(self) -> bool:
        now = time.time()
        with self.lock:
            return any(s["state"] == "working" and now - s["updated"] < 120 for s in self.sessions.values())

    def _update_inhibit(self) -> None:
        w = self.working()
        if w:
            self.stats["work"] += 2
        want = w and self.cfg["inhibit"].get("enabled", True)
        if want != self.inhibited:
            self.inhibited = want
            try:
                self.set_inhibit(want)
            except Exception as e:
                print("[coucou] anti-veille :", e, file=sys.stderr)

    def read_sys(self) -> dict:
        s: dict = {}
        bats = sorted(pathlib.Path("/sys/class/power_supply").glob("BAT*"))
        if bats:
            try:
                s["bat"], s["bat_state"] = int((bats[0] / "capacity").read_text()), (bats[0] / "status").read_text().strip()
            except (OSError, ValueError):
                pass
        try:
            mem = {l.split(":")[0]: int(l.split()[1]) for l in open("/proc/meminfo")}
            s["ram"] = round(100 * (1 - mem["MemAvailable"] / mem["MemTotal"]))
        except (OSError, KeyError, ValueError):
            pass
        temps = []
        for z in pathlib.Path("/sys/class/thermal").glob("thermal_zone*/temp"):
            try:
                v = int(z.read_text()) / 1000
                if 0 < v < 130:
                    temps.append(v)
            except (OSError, ValueError):
                pass
        if temps:
            s["temp"] = max(temps)
        if not getattr(self, "_vol_busy", False):
            m = re.search(r"(\d+)%", run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"]))
            if m:
                s["vol"] = int(m[1])
            s["mute"] = "yes" in run(["pactl", "get-sink-mute", "@DEFAULT_SINK@"])
        return s

    def read_net(self) -> dict:
        r: dict = {"wifi": None, "tailscale": None}
        for line in run(["nmcli", "-t", "-f", "ACTIVE,SSID", "dev", "wifi"]).splitlines():
            if line.startswith("yes:"):
                r["wifi"] = line[4:] or "?"
        if shutil.which("tailscale"):
            try:
                r["tailscale"] = json.loads(run(["tailscale", "status", "--json"], 4)).get("BackendState") == "Running"
            except ValueError:
                r["tailscale"] = False
        return r

    def _check_battery(self) -> None:
        bat, state = self.sys.get("bat"), self.sys.get("bat_state")
        h = self.cfg["health"]
        if bat is None:
            return
        if state == "Discharging" and bat <= int(h["battery_warn"]) and not self._bat_alerted:
            self._bat_alerted = True
            self.play("battery")
            self.toast(f"🔋 Batterie faible : {bat}% — branche le chargeur", "danger")
        elif state != "Discharging" or bat >= int(h["battery_ok"]):
            self._bat_alerted = False

    # ---- vue pour l'interface -----------------------------------------------------
    def snapshot(self) -> dict:
        now = time.time()
        with self.lock:
            for k in [k for k, s in self.sessions.items() if now - s["updated"] > 4 * 3600]:
                del self.sessions[k]
            sessions = sorted((dict(s) for s in self.sessions.values()), key=lambda s: -s["updated"])
            aps = [dict(id=a.id, agent=a.agent, tool=a.tool, summary=a.summary, score=a.score, labels=list(a.labels)) for a in self.approvals]
            toast = self.toast_msg if self.toast_msg and self.toast_msg[2] > now else None
            kd = self.kdrive_msg if self.kdrive_msg[2] > now else ("", "info", 0)
            timers = [dict(t) for t in self.timers]
            focus = dict(self.focus) if self.focus else None
            todos, jobs = [dict(t) for t in self.todos], [dict(j) for j in self.jobs.values()]
            calm = dict(self.calm) if self.calm else None
        return {"now": now, "sessions": sessions, "approvals": aps, "toast": toast, "kdrive": kd, "ai": dict(self.ai),
                "locked": self.locked, "music": dict(self.music), "sys": dict(self.sys), "timers": timers, "focus": focus,
                "dnd": self.dnd, "clips": list(self.clips), "audit": list(self.audit), "stats": dict(self.stats),
                "inhibited": self.inhibited, "todos": todos, "jobs": jobs, "kanban": dict(self.kanban), "weather": dict(self.weather),
                "calm": calm, "in_call": self.in_call, "secret_left": max(0.0, self.secret_clear_at - now) if self.secret_clear_at else 0.0,
                "ollama": self.ollama_state, "depot_ok": self.kdrive.available(), "profiles": [dict(p) for p in self.profiles], "tint": self._tint(),
                "briefing": json.loads(json.dumps(self.briefing)), "mic": dict(self.mic), "speaking": self.speaking,
                "speaking_section": self.speaking_section, "voice_info": dict(self.voice_info)}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        try:
            msg = json.loads(self.rfile.readline(1 << 20).decode("utf-8"))
        except Exception:
            return
        core: Core = self.server.core  # type: ignore[attr-defined]
        op, agent, payload = msg.get("op", "event"), str(msg.get("agent", "agent")), msg.get("payload") or {}
        try:
            if op == "event":
                core.handle_event(agent, payload); reply = {"ok": True}
            elif op == "approve":
                core.handle_event(agent, dict(payload, hook_event_name="PreToolUse"))
                reply = core.request_approval(agent, payload, msg.get("timeout"))
            elif op in ("toggle", "quit"):
                core.ui_handler(op); reply = {"ok": True}
            elif op == "timer":
                core.add_timer(float(msg["seconds"]), str(msg.get("label") or "Minuteur")); reply = {"ok": True}
            elif op == "focus":
                core.start_focus(float(msg.get("minutes", 25))); reply = {"ok": True}
            elif op == "magic":
                core.magic(str(msg.get("text", ""))); reply = {"ok": True}
            elif op == "job_start":
                core.job_start(str(msg["id"]), str(msg.get("label", "commande"))); reply = {"ok": True}
            elif op == "job_end":
                core.job_end(str(msg["id"]), int(msg.get("code", 0))); reply = {"ok": True}
            elif op == "mic":
                core.mic_toggle(); reply = {"ok": True}
            elif op == "bonjour":
                core.bonjour(msg.get("speak")); reply = {"ok": True}
            elif op == "calm":
                core.start_calm(str(msg.get("kind", "breath"))); reply = {"ok": True}
            elif op == "status":
                snap = core.snapshot()
                reply = {"sessions": [{k: s[k] for k in ("agent", "label", "state", "tool")} for s in snap["sessions"]],
                         "approvals": snap["approvals"], "locked": snap["locked"], "music": snap["music"], "sys": snap["sys"],
                         "todos": snap["todos"], "kanban": snap["kanban"], "ai": snap["ai"]}
            elif op == "resolve":
                decision = str(msg.get("decision", "deny"))
                if decision not in ("allow", "deny", "always"):
                    raise ValueError("Décision invalide")
                core.resolve(str(msg.get("id", "")), decision, "Décision depuis Android")
                reply = {"ok": True}
            elif op == "ask_profile":
                profile = str(msg.get("profile", "default") or "default")
                if len(profile) > 80 or any(c in profile for c in "\r\n/\\"):
                    raise ValueError("Profil invalide")
                core.ask_profile(profile, str(msg.get("text", "")))
                reply = {"ok": True}
            else:
                reply = {"error": "op inconnue"}
        except Exception as e:
            reply = {"error": str(e)}
        try:
            self.wfile.write((json.dumps(reply, ensure_ascii=False) + "\n").encode("utf-8"))
        except OSError:
            pass


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def send(msg: dict, wait: bool = False, timeout: float = 2.0) -> dict | None:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(str(SOCK))
        s.sendall((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8")) if buf.strip() else {}
    except (OSError, ValueError):
        return None
    finally:
        s.close()


def start_server(core: Core) -> Server:
    SOCK.parent.mkdir(parents=True, exist_ok=True)
    if SOCK.exists():
        if send({"op": "status"}) is not None:
            raise SystemExit("coucou-fedora tourne déjà.")
        SOCK.unlink()
    srv = Server(str(SOCK), Handler)
    os.chmod(SOCK, 0o600)
    srv.core = core  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def load_user_plugins(core: Core, cfg: dict) -> None:
    import importlib.util
    for f in sorted((CONF_DIR / "plugins").glob("*.py")):
        try:
            spec = importlib.util.spec_from_file_location(f"coucou_plugin_{f.stem}", f)
            mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            if hasattr(mod, "setup"):
                mod.setup(core, cfg)
            print(f"[coucou] extension chargée : {f.name}")
        except Exception as e:
            print(f"[coucou] extension {f.name} ignorée : {e}", file=sys.stderr)


# ════════════════════════════════════════════════════════════════════════════
#  4. D-BUS GNOME : musique (MPRIS), verrouillage, anti-veille
# ════════════════════════════════════════════════════════════════════════════
class Mpris:
    PFX = "org.mpris.MediaPlayer2."

    def __init__(self, cfg: dict):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib, self.c = Gio, GLib, cfg["music"]
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.name: str | None = None

    def _call(self, dest, path, iface, method, params=None, rtype=None):
        return self.bus.call_sync(dest, path, iface, method, params, rtype, self.Gio.DBusCallFlags.NONE, 500, None)

    def pick(self) -> str | None:
        r = self._call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames", None, self.GLib.VariantType("(as)"))
        names = [n for n in r.unpack()[0] if n.startswith(self.PFX)]
        if self.c.get("mpris_name") in names:
            return self.c["mpris_name"]
        m = (self.c.get("player_match") or "").lower()
        return next((n for n in names if m and m in n.lower()), names[0] if names else None)

    def poll(self) -> dict:
        try:
            self.name = self.pick()
            if not self.name:
                return {}
            r = self._call(self.name, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "GetAll",
                           self.GLib.Variant("(s)", (self.PFX + "Player",)), self.GLib.VariantType("(a{sv})"))
            props = r.unpack()[0]
            meta = props.get("Metadata", {})
            artist = meta.get("xesam:artist", "")
            return {"name": self.name, "status": props.get("PlaybackStatus", ""), "title": str(meta.get("xesam:title", "")),
                    "album": str(meta.get("xesam:album", "")), "artist": ", ".join(artist) if isinstance(artist, list) else str(artist),
                    "art": str(meta.get("mpris:artUrl", "")), "length": int(meta.get("mpris:length", 0) or 0) / 1e6,
                    "pos": int(props.get("Position", 0) or 0) / 1e6, "t": time.time()}
        except Exception:
            return {}

    def command(self, method: str) -> None:
        if self.name:
            try:
                self._call(self.name, "/org/mpris/MediaPlayer2", self.PFX + "Player", method)
            except Exception:
                pass


class LockWatcher:
    def __init__(self, core: Core):
        from gi.repository import Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.bus.signal_subscribe("org.gnome.ScreenSaver", "org.gnome.ScreenSaver", "ActiveChanged", "/org/gnome/ScreenSaver",
                                  None, Gio.DBusSignalFlags.NONE, lambda *a: core.set_locked(bool(a[5].unpack()[0])))
        try:
            r = self.bus.call_sync("org.gnome.ScreenSaver", "/org/gnome/ScreenSaver", "org.gnome.ScreenSaver", "GetActive",
                                   None, GLib.VariantType("(b)"), Gio.DBusCallFlags.NONE, 500, None)
            core.set_locked(bool(r.unpack()[0]))
        except Exception:
            pass


class Inhibitor:
    """Empêche la veille/le verrouillage automatique (org.gnome.SessionManager) tant qu'un agent travaille."""

    def __init__(self):
        from gi.repository import Gio, GLib
        self.Gio, self.GLib = Gio, GLib
        self.bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.cookie: int | None = None

    def set(self, on: bool) -> None:
        sm = ("org.gnome.SessionManager", "/org/gnome/SessionManager", "org.gnome.SessionManager")
        if on and self.cookie is None:
            r = self.bus.call_sync(*sm, "Inhibit", self.GLib.Variant("(susu)", ("coucou-fedora", 0, "Un agent IA travaille", 12)),
                                   self.GLib.VariantType("(u)"), self.Gio.DBusCallFlags.NONE, 1000, None)
            self.cookie = r.unpack()[0]
        elif not on and self.cookie is not None:
            self.bus.call_sync(*sm, "Uninhibit", self.GLib.Variant("(u)", (self.cookie,)), None, self.Gio.DBusCallFlags.NONE, 1000, None)
            self.cookie = None


# ════════════════════════════════════════════════════════════════════════════
#  5. INTERFACE GTK3 — encoche animée (ressorts, particules, survols), dessinée avec Cairo
# ════════════════════════════════════════════════════════════════════════════
def hexrgb(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


class Spring:
    """Ressort amorti : donne aux tailles un rebond naturel (comme une encoche qui « respire »)."""

    def __init__(self, v: float):
        self.pos = self.target = float(v)
        self.vel = 0.0

    def step(self, dt: float, target: float | None = None, k: float = 300.0, d: float = 24.0) -> float:
        if target is not None:
            self.target = float(target)
        n = max(1, int(dt / 0.008))
        h = dt / n
        for _ in range(n):
            self.vel += (k * (self.target - self.pos) - d * self.vel) * h
            self.pos += self.vel * h
        return self.pos

    @property
    def settled(self) -> bool:
        return abs(self.target - self.pos) < 0.4 and abs(self.vel) < 0.8


def smooth(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def ease_out_back(x: float) -> float:
    x = max(0.0, min(1.0, x))
    c1, c3 = 1.4, 2.4
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def run_gui(cfg: dict, core: Core) -> None:
    if cfg["island"].get("backend", "x11") == "x11":
        os.environ["GDK_BACKEND"] = "x11"
    import contextlib
    import gi
    gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
    gi.require_version("Pango", "1.0"); gi.require_version("PangoCairo", "1.0"); gi.require_version("GdkPixbuf", "2.0")
    import cairo
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango, PangoCairo

    T = {k: hexrgb(v) for k, v in cfg["theme"].items() if k != "font"}
    FONT, IC, TAU, EAR = cfg["theme"].get("font", "Sans"), cfg["island"], 2 * math.pi, 12
    KIND = {"info": T["accent"], "ok": T["ok"], "warn": T["warn"], "danger": T["danger"]}
    STATE = {"working": T["accent"], "waiting": T["warn"], "done": T["ok"], "idle": T["dim"]}
    KB = {"todo": T["dim"], "ready": T["accent"], "running": T["warn"], "blocked": T["danger"], "done": T["ok"]}
    KB_LABEL = {"todo": "à faire", "ready": "prêt", "running": "en cours", "blocked": "bloqué", "done": "fait"}
    CONFETTI = [T["accent"], T["ok"], T["warn"], T["danger"], T["mochi"], (0.8, 0.6, 1.0)]

    def shape(cr, w, h, ear, r):
        cr.new_path(); cr.move_to(-ear, 0); cr.line_to(w + ear, 0)
        cr.arc_negative(w + ear, ear, ear, -math.pi / 2, math.pi)
        cr.line_to(w, h - r); cr.arc(w - r, h - r, r, 0, math.pi / 2); cr.line_to(r, h); cr.arc(r, h - r, r, math.pi / 2, math.pi)
        cr.line_to(0, ear); cr.arc_negative(-ear, ear, ear, 0, -math.pi / 2); cr.close_path()

    def rr(cr, x, y, w, h, r):
        r = max(0.1, min(r, w / 2, h / 2))
        cr.new_sub_path(); cr.arc(x + w - r, y + r, r, -math.pi / 2, 0); cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi); cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi); cr.close_path()

    def layout(cr, s, size, bold=False, mono=False, w=None, lines=1, align="l"):
        lay = PangoCairo.create_layout(cr)
        lay.set_font_description(Pango.FontDescription(f"{'Monospace' if mono else FONT} {'Bold ' if bold else ''}{size}"))
        lay.set_text(str(s), -1)
        if w:
            lay.set_width(int(w * Pango.SCALE)); lay.set_ellipsize(Pango.EllipsizeMode.END); lay.set_height(-lines)
            lay.set_wrap(Pango.WrapMode.WORD_CHAR)
            lay.set_alignment({"l": Pango.Alignment.LEFT, "c": Pango.Alignment.CENTER, "r": Pango.Alignment.RIGHT}[align])
        return lay

    def text(cr, s, x, y, size=11, color=None, bold=False, w=None, lines=1, align="l", mono=False):
        lay = layout(cr, s, size, bold, mono, w, lines, align)
        cr.set_source_rgb(*(color or T["text"])); cr.move_to(x, y); PangoCairo.show_layout(cr, lay)
        return lay.get_pixel_size()[1]

    def tw(cr, s, size=10, bold=False):
        return layout(cr, s, size, bold).get_pixel_size()[0]

    def star(cr, x, y, s):
        cr.move_to(x, y - s); cr.curve_to(x, y - s * .2, x + s * .2, y, x + s, y); cr.curve_to(x + s * .2, y, x, y + s * .2, x, y + s)
        cr.curve_to(x, y + s * .2, x - s * .2, y, x - s, y); cr.curve_to(x - s * .2, y, x, y - s * .2, x, y - s); cr.fill()

    def heart(cr, x, y, s):
        cr.move_to(x, y + s * .9); cr.curve_to(x - s * 1.4, y - s * .2, x - s * .6, y - s * 1.1, x, y - s * .4)
        cr.curve_to(x + s * .6, y - s * 1.1, x + s * 1.4, y - s * .2, x, y + s * .9); cr.fill()

    def weather_icon(cr, kind, cx, cy, s, now, night):
        def cloud(ox=0.0, oy=0.0, col=(0.85, 0.88, 0.95)):
            cr.set_source_rgb(*col)
            for dx, dy, r in ((-.28, .05, .22), (0, -.08, .3), (.3, .06, .2)):
                cr.arc(cx + ox + dx * s, cy + oy + dy * s, r * s, 0, TAU); cr.fill()
            rr(cr, cx + ox - .46 * s, cy + oy + .05 * s, .92 * s, .21 * s, .1 * s); cr.fill()
        if kind == "sun":
            if night:
                cr.set_source_rgb(.95, .93, .75); cr.arc(cx, cy, s * .32, 0, TAU); cr.fill()
                cr.set_source_rgb(*T["bg"]); cr.arc(cx + s * .14, cy - s * .08, s * .28, 0, TAU); cr.fill()
            else:
                cr.set_source_rgb(1.0, .78, .25); cr.arc(cx, cy, s * .26, 0, TAU); cr.fill()
                cr.set_line_width(max(1.5, s * .06)); cr.set_source_rgb(1.0, .78, .25)
                for i in range(8):
                    a = i * TAU / 8 + now * .5
                    cr.move_to(cx + math.cos(a) * s * .36, cy + math.sin(a) * s * .36); cr.line_to(cx + math.cos(a) * s * .5, cy + math.sin(a) * s * .5); cr.stroke()
        elif kind == "fog":
            cr.set_source_rgba(.85, .88, .95, .8); cr.set_line_width(s * .08)
            for i in range(3):
                off = math.sin(now * 1.2 + i) * s * .08
                cr.move_to(cx - s * .4 + off, cy - s * .2 + i * s * .22); cr.line_to(cx + s * .4 + off, cy - s * .2 + i * s * .22); cr.stroke()
        else:
            cloud(math.sin(now * .8) * s * .04, -s * .1, (.7, .72, .8) if kind == "storm" else (.85, .88, .95))
            if kind in ("rain", "storm"):
                cr.set_source_rgb(.45, .7, 1.0); cr.set_line_width(max(1.4, s * .05))
                for i in range(3):
                    p = (now * 1.6 + i / 3) % 1.0
                    x = cx - s * .22 + i * s * .22
                    cr.move_to(x, cy + s * .18 + p * s * .3); cr.line_to(x - s * .04, cy + s * .26 + p * s * .3); cr.stroke()
            if kind == "snow":
                cr.set_source_rgb(1, 1, 1)
                for i in range(3):
                    p = (now * .6 + i / 3) % 1.0
                    cr.arc(cx - s * .22 + i * s * .22 + math.sin(now * 2 + i) * s * .04, cy + s * .2 + p * s * .35, s * .04, 0, TAU); cr.fill()
            if kind == "storm" and int(now * 3) % 4 == 0:
                cr.set_source_rgb(1.0, .9, .3)
                cr.move_to(cx + s * .04, cy + s * .12); cr.line_to(cx - s * .1, cy + s * .34); cr.line_to(cx, cy + s * .34); cr.line_to(cx - s * .06, cy + s * .52)
                cr.line_to(cx + s * .12, cy + s * .26); cr.line_to(cx + s * .02, cy + s * .26); cr.close_path(); cr.fill()

    class Island(Gtk.Window):
        TABS = ("Bonjour", "Agents", "Musique", "IA", "Tâches", "Outils", "Système")

        def __init__(self):
            super().__init__()
            self.set_title("Coucou"); self.set_decorated(False); self.set_app_paintable(True)
            self.set_type_hint(Gdk.WindowTypeHint.DOCK); self.set_keep_above(True); self.stick()
            self.set_skip_taskbar_hint(True); self.set_skip_pager_hint(True)
            self.set_accept_focus(False); self.set_focus_on_map(False)
            vis = self.get_screen().get_rgba_visual()
            if vis:
                self.set_visual(vis)
            self.WMAX, self.HMAX = int(IC["width_open"]), 760
            try:
                d_ = Gdk.Display.get_default()
                g_ = (d_.get_primary_monitor() or d_.get_monitor(0)).get_geometry()
                self.HMAX = int(max(420, min(820, g_.height - int(IC["y_offset"]) - 36)))
            except Exception:
                pass
            self.WWIN = self.WMAX + 2 * EAR
            self.mini_w, self.MINI_H, self.PEEK = int(IC["width_mini"]), 18, (350, 48)
            self.set_default_size(self.WWIN, self.HMAX)
            self.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                            | Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK | Gdk.EventMask.SCROLL_MASK)
            for sig, cb in (("draw", self.on_draw), ("button-press-event", self.on_press), ("button-release-event", self.on_release),
                            ("motion-notify-event", self.on_motion), ("enter-notify-event", self.on_enter),
                            ("leave-notify-event", self.on_leave), ("scroll-event", self.on_scroll), ("drag-data-received", self.on_drop), ("drag-motion", self.on_drag_motion)):
                self.connect(sig, cb)
            self.drag_dest_set(Gtk.DestDefaults.ALL, [Gtk.TargetEntry.new("text/uri-list", 0, 0)], Gdk.DragAction.COPY)
            self.sw, self.sh, self.ind, self.squish = Spring(self.mini_w), Spring(self.MINI_H), Spring(0), Spring(0)
            self.a = {"mini": 1.0, "peek": 0.0, "open": 0.0}
            self.mode, self.tab, self.tab_t, self.open_t = "mini", "Agents", 0.0, 0.0
            self.pinned, self.open_until, self.block_hover_until = False, 0.0, 0.0
            self.hover, self.hover_t0, self.ptr, self.hot = False, 0.0, None, None
            self.hits: list = []
            self.accept_hits, self.holding, self.drag, self.pressed = False, None, None, None
            self.snap, self.snap_t, self.dirty, self.now = core.snapshot(), 0.0, True, time.time()
            self.last_t, self.last_draw, self.last_hover_snd = time.time(), 0.0, 0.0
            self.need_open, self.x0, self.ri = 340, 0.0, 0
            self.shape_ok, self.last_rect = None, None
            self.anim: dict = {}
            self.hv: dict = {}
            self.ripples: list = []
            self.parts: list = []
            self.shake_until, self.cursor_pointer = 0.0, False
            self.scroll_y = self.scroll_t = self.max_scroll = self.hy = 0.0
            self.body_clip, self.profile_open = None, None
            self.blink_at, self.blink_until = time.time() + 3, 0.0
            self.prev_aps, self.prev_ai, self.prev_mode, self.calm_seg = 0, "idle", "mini", -1
            self.art_cache: dict = {}
            self.music_key = None
            self.cx, self.top = 960, int(IC["y_offset"])
            self.mpris = None
            if cfg["music"].get("enabled"):
                try:
                    self.mpris = Mpris(cfg)
                except Exception as e:
                    print("[coucou] MPRIS indisponible :", e, file=sys.stderr)
            core.on_change = lambda: setattr(self, "dirty", True)
            core.ui_handler = lambda cmd, arg=None: GLib.idle_add(self.on_cmd, cmd, arg)
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).connect("owner-change", self.on_clip)
            self.place()
            self.show()
            GLib.timeout_add(16, self.tick)
            if self.mpris:
                GLib.timeout_add(int(cfg["music"]["poll_ms"]), self.poll_music)

        # ---------- placement & forme ----------
        def place(self):
            try:
                d = Gdk.Display.get_default()
                mon = d.get_primary_monitor() if str(IC["monitor"]) == "primary" else d.get_monitor(int(IC["monitor"]))
                g = (mon or d.get_monitor(0)).get_geometry()
                self.cx, self.top = g.x + g.width // 2 + int(IC["x_offset"]), g.y + int(IC["y_offset"])
            except Exception as e:
                print("[coucou] écran :", e, file=sys.stderr)
            self.move(self.cx - self.WWIN // 2, self.top)

        def set_shape(self, x, w, h):
            gw = self.get_window()
            if gw is None:
                return None
            try:
                gw.input_shape_combine_region(cairo.Region(cairo.RectangleInt(int(x), 0, int(w), int(h))), 0, 0)
                return True
            except Exception:
                return False

        def apply_geometry(self, rw, rh):
            ear = min(EAR, rh / 3)
            if self.shape_ok is not False:
                self.shape_ok = self.set_shape((self.WWIN - rw) / 2 - ear, rw + 2 * ear, rh)
            if self.shape_ok is False:
                self.resize(rw + 2 * EAR, rh); self.move(self.cx - (rw + 2 * EAR) // 2, self.top)

        def set_pointer(self, on):
            if on != self.cursor_pointer:
                self.cursor_pointer = on
                try:
                    gw = self.get_window()
                    gw.set_cursor(Gdk.Cursor.new_from_name(Gdk.Display.get_default(), "pointer") if on else None)
                except Exception:
                    pass

        # ---------- commandes & données ----------
        def on_cmd(self, cmd, arg=None):
            if cmd == "toggle":
                self.collapse() if self.mode == "open" else self.open_now(True, pin=True)
            elif cmd == "quit":
                Gtk.main_quit()
            elif cmd == "copy":
                self.copy(str(arg), quiet=True)
            elif cmd == "music":
                self.player(str(arg))
            elif cmd == "clip_ai":
                tpl, label = arg
                txt = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
                if txt:
                    self.set_tab("IA"); self.open_now()
                    core.ai_run(label, tpl.replace("{clip}", txt[:6000]))
                else:
                    core.toast("Le presse-papiers est vide", "warn")
            return False

        def open_now(self, sound=False, pin=False):
            self.open_until = time.time() + float(IC["auto_close_after"])
            self.pinned = self.pinned or pin
            if sound and self.mode != "open":
                core.play("open")
            self.dirty = True

        def collapse(self):
            self.pinned, self.open_until = False, 0.0
            self.block_hover_until = time.time() + 1.2
            self.dirty = True

        def set_tab(self, t):
            if t != self.tab:
                core.play("tick")
            self.tab, self.tab_t = t, time.time()
            self.scroll_t = self.scroll_y = 0.0

        def open_prompt(self, prefill=""):
            env = {k: v for k, v in os.environ.items() if k != "GDK_BACKEND"}
            subprocess.Popen([sys.executable, str(pathlib.Path(__file__).resolve()), "prompt"] + (["--prefill", prefill] if prefill else []), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        def poll_music(self):
            m = self.mpris.poll() if self.mpris else {}
            core.music = m
            key = (m.get("title"), m.get("artist")) if m.get("status") == "Playing" else None
            if key and key != self.music_key and cfg["music"].get("toast_on_track_change"):
                core.toast(f"♪ {m['title']} — {m['artist']}", "info")
            self.music_key = key
            self.dirty = True
            return True

        def player(self, meth):
            if self.mpris:
                self.mpris.command(meth)
                GLib.timeout_add(250, self.poll_music)

        def on_clip(self, cb, _ev):
            if cfg["clipboard"].get("enabled") or cfg["clipboard"].get("guard"):
                cb.request_text(lambda _c, t: core.on_clipboard(t))

        def on_scroll(self, _w, ev):
            if self.mode == "open":
                if ev.direction == Gdk.ScrollDirection.SMOOTH:
                    d = ev.delta_y * 36
                else:
                    d = -36 if ev.direction == Gdk.ScrollDirection.UP else 36
                self.scroll_t = max(0.0, min(self.max_scroll, self.scroll_t + d))
            return True

        def copy(self, t, quiet=False):
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(t, -1)
            if not quiet:
                core.toast("Copié dans le presse-papiers", "ok"); core.play("click")

        def get_art(self, url):
            if not url:
                return None
            if url not in self.art_cache:
                self.art_cache[url] = None
                threading.Thread(target=self._load_art, args=(url,), daemon=True).start()
            return self.art_cache[url]

        def _load_art(self, url):
            try:
                if url.startswith("file://"):
                    path = GLib.filename_from_uri(url)[0]
                else:
                    path = str(CACHE_DIR / "art" / hashlib.sha1(url.encode()).hexdigest())
                    if not os.path.exists(path):
                        os.makedirs(os.path.dirname(path), exist_ok=True)
                        with urllib.request.urlopen(url, timeout=6) as r, open(path, "wb") as f:
                            f.write(r.read(4_000_000))
                self.art_cache[url] = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, 152, 152, True)
                self.dirty = True
            except Exception:
                pass

        # ---------- particules & effets ----------
        def mochi_pos(self):
            return (34.0, 31.0) if self.mode == "open" else (30.0, self.sh.pos / 2 + 1)

        def burst(self, x, y, kind="conf", n=30):
            for _ in range(n):
                a = random.uniform(-math.pi * 0.95, -math.pi * 0.05) if kind != "star" else random.uniform(0, TAU)
                v = random.uniform(120, 330) if kind == "conf" else random.uniform(30, 120)
                self.parts.append({"x": x, "y": y, "vx": math.cos(a) * v, "vy": math.sin(a) * v, "life": random.uniform(.9, 1.6), "max": 1.6, "kind": kind,
                                   "col": random.choice(CONFETTI), "s": random.uniform(2.5, 5.0), "rot": random.uniform(0, TAU), "vr": random.uniform(-9, 9)})

        def poke(self):
            self.squish.vel = -520
            self.burst(*self.mochi_pos(), "heart", 6)
            core.play("pop")

        def process_fx(self):
            while core.fx_queue:
                kind, kw = core.fx_queue.pop(0)
                x, y = kw.get("x"), kw.get("y")
                x, y = (x, y) if x is not None else self.mochi_pos()
                if kind == "confetti":
                    self.burst(x, y, "conf", 38); self.squish.vel = -420
                elif kind == "sparkle":
                    self.burst(x, y, "star", 14)
                elif kind == "shake":
                    self.shake_until = time.time() + 0.45

        # ---------- boucle d'animation ----------
        def tick(self):
            now = time.time()
            dt = min(0.05, max(0.001, now - self.last_t))
            self.last_t, self.now = now, now
            if self.dirty or now - self.snap_t > 0.25:
                self.snap, self.snap_t, self.dirty = core.snapshot(), now, False
            snap, aps = self.snap, self.snap["approvals"]
            self.process_fx()
            if self.hover and IC.get("hover_open", True) and self.mode != "open" and now > self.block_hover_until \
                    and now - self.hover_t0 > float(IC["hover_delay"]):
                self.open_now()
            if self.hover and self.mode == "open":
                self.open_until = now + float(IC["auto_close_after"])
            if len(aps) > self.prev_aps:
                self.set_tab("Agents")
            self.prev_aps = len(aps)
            ai_state = snap["ai"]["state"]
            if ai_state in ("done", "error") and ai_state != self.prev_ai:
                self.set_tab("IA"); self.open_until = now + 3 * float(IC["auto_close_after"])
            self.prev_ai = ai_state
            if aps or snap["calm"] or self.pinned or now < self.open_until:
                mode = "open"
            else:
                mode = "peek" if (snap["toast"] or snap["mic"]["state"] in ("rec", "transcribing")) else "mini"
            if mode == "open" and self.mode != "open":
                self.open_t = now
                if core.suggest_tab:
                    self.set_tab(core.suggest_tab)
                    core.suggest_tab = None
            elif self.mode == "open" and mode != "open":
                core.play("close")
            self.mode = mode
            if mode == "open":
                tgt = (self.WMAX, min(self.HMAX, self.need_open))
            elif mode == "peek":
                tgt = self.PEEK
            else:
                tgt = (self.mini_w, self.MINI_H)
            self.sw.step(dt, tgt[0], 320, 25); self.sh.step(dt, tgt[1], 280, 23); self.squish.step(dt, 0, 260, 12)
            self.scroll_y += (self.scroll_t - self.scroll_y) * min(1.0, dt * 14)
            self.ind.step(dt, self.TABS.index(self.tab) * (self.WMAX - 32) / len(self.TABS), 380, 28)
            moving = not (self.sw.settled and self.sh.settled)
            for k in self.a:
                t = 1.0 if k == mode else 0.0
                self.a[k] += (t - self.a[k]) * min(1.0, dt * 13)
                if abs(t - self.a[k]) < 0.01:
                    self.a[k] = t
                else:
                    moving = True
            rect = (int(self.sw.pos), int(self.sh.pos))
            if rect != self.last_rect or self.shape_ok is None:
                self.apply_geometry(*rect)
                self.last_rect = rect
            if now > self.blink_at:
                self.blink_until, self.blink_at = now + 0.14, now + random.uniform(2.5, 5.5)
            if self.holding and now - self.holding[1] >= self.holding[0]["hold"]:
                hit = self.holding[0]; self.holding = None; hit["cb"](); core.play("allow")
            for p in self.parts:
                p["life"] -= dt
                p["x"] += p["vx"] * dt; p["y"] += p["vy"] * dt; p["rot"] += p["vr"] * dt
                if p["kind"] == "conf":
                    p["vy"] += 620 * dt; p["vx"] *= (1 - 0.8 * dt)
                else:
                    p["vy"] -= 20 * dt if p["kind"] == "heart" else 0
            self.parts = [p for p in self.parts if p["life"] > 0]
            self.ripples = [r for r in self.ripples if now - r[2] < 0.55]
            if core.secret_clear_at and now >= core.secret_clear_at:
                core.secret_clear_at = 0.0
                cb = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
                txt = cb.wait_for_text()
                if txt and any(rx.search(txt) for rx in SECRET_RX):
                    cb.clear(); core.toast("🔐 Presse-papiers effacé", "ok"); core.play("close")
            busy = mode == "open" or snap["music"].get("status") == "Playing" or bool(aps) or core.working() or bool(self.parts)
            interval = 0.016 if (moving or self.parts or self.ripples) else (0.033 if busy else 0.11)
            if now - self.last_draw >= interval:
                self.last_draw = now
                self.queue_draw()
            return True

        # ---------- souris ----------
        def on_enter(self, *_):
            self.hover, self.hover_t0 = True, time.time()

        def on_leave(self, *_):
            self.hover, self.ptr, self.holding, self.hot = False, None, None, None
            self.set_pointer(False)

        def on_drag_motion(self, *_):
            self.hover = True
            self.open_now()
            return False

        def top_hit(self, x, y):
            for h in reversed(self.hits):
                rx, ry, rw_, rh_ = h["r"]
                if rx <= x <= rx + rw_ and ry <= y <= ry + rh_:
                    return h
            return None

        def on_motion(self, _w, ev):
            self.ptr = (ev.x - self.x0, ev.y)
            if self.drag:
                x, _y, w, _h = self.drag["r"]
                self.drag["drag"](max(0.0, min(1.0, (self.ptr[0] - x) / w)))
            h = self.top_hit(*self.ptr)
            hot = h["r"] if h else None
            if hot != self.hot:
                self.hot = hot
                self.set_pointer(hot is not None or self.mode != "open")
                if hot is not None and cfg["sounds"].get("hover", True) and time.time() - self.last_hover_snd > 0.09:
                    self.last_hover_snd = time.time(); core.play("hover")
            return True

        def hit(self, x, y, w, h, cb=None, hold=0.0, drag=None):
            if not self.accept_hits:
                return
            ye = y - self.hy
            if self.body_clip and not (self.body_clip[0] - 6 <= ye + h / 2 <= self.body_clip[1] + 6):
                return
            self.hits.append({"r": (x, ye, w, h), "cb": cb, "hold": hold, "drag": drag})

        def on_press(self, _w, ev):
            if ev.button != 1:
                return True
            x, y = ev.x - self.x0, ev.y
            h = self.top_hit(x, y)
            if h:
                self.pressed = h["r"]
                self.ripples.append((x, y, time.time(), T["accent"]))
                if h["drag"]:
                    self.drag, core._vol_busy = h, True
                    h["drag"](max(0.0, min(1.0, (x - h["r"][0]) / h["r"][2])))
                elif h["hold"]:
                    self.holding = (h, time.time())
                else:
                    core.play("click"); h["cb"]()
                return True
            if self.mode != "open":
                self.open_now(True)
            return True

        def on_release(self, *_):
            self.holding, self.pressed = None, None
            if self.drag:
                self.drag, core._vol_busy = None, False
            return True

        def on_drop(self, _w, _ctx, _x, _y, data, _info, _t):
            if not (cfg["depot"].get("enabled") and cfg["depot"].get("copy_dropped")):
                return
            for uri in data.get_uris() or []:
                try:
                    core.kdrive.upload(GLib.filename_from_uri(uri)[0], "Dépôts")
                except Exception as e:
                    core.set_kdrive(f"Dépôt impossible : {short(e, 50)}", "danger")

        # ---------- éléments de dessin ----------
        def mood(self, snap):
            aps, toast = snap["approvals"], snap["toast"]
            if aps:
                return "danger" if aps[0]["score"] >= int(cfg["radar"].get("hold_at", 70)) else "wait"
            if snap["mic"]["state"] == "rec":
                return "listen"
            if snap["speaking"]:
                return "talk"
            if snap["focus"] or snap["calm"]:
                return "sleep"
            if toast and toast[1] == "ok":
                return "done"
            if toast and toast[1] in ("warn", "danger"):
                return "wait"
            if snap["music"].get("status") == "Playing":
                return "dance"
            return "work" if any(s["state"] == "working" and snap["now"] - s["updated"] < 120 for s in snap["sessions"]) else "idle"

        def mochi(self, cr, cx, cy, s, mood, now, interactive=False, tint=None):
            col = {"wait": T["warn"], "danger": T["danger"], "done": T["ok"], "sleep": (0.62, 0.68, 0.95)}.get(mood, tint or T["mochi"])
            breathe, dy, rot = 1 + 0.025 * math.sin(now * 2.1), 0.0, 0.0
            if mood == "wait":
                dy = -abs(math.sin(now * 6)) * s * 0.10
            elif mood == "dance":
                dy, rot = -abs(math.sin(now * 7)) * s * 0.09, math.sin(now * 7) * 0.10
            elif mood == "danger":
                cx += math.sin(now * 45) * s * 0.025
            elif mood == "listen":
                rot = math.sin(now * 2) * 0.07
            elif mood == "talk":
                dy = -abs(math.sin(now * 5)) * s * 0.03
            if now < self.shake_until:
                cx += math.sin(now * 60) * s * 0.06
            sq = max(-0.25, min(0.25, self.squish.pos * 0.002 + self.sh.vel * 0.0004))
            look = (0.0, 0.0)
            if self.ptr:
                ddx, ddy = self.ptr[0] - cx, self.ptr[1] - cy
                n = max(1.0, math.hypot(ddx, ddy) / 40)
                look = (ddx / n / 40, ddy / n / 40)
            elif mood == "work":
                look = (math.sin(now * 2.2) * 0.8, 0.1)
            else:
                look = (math.sin(now * 0.45) * 0.5, math.sin(now * 0.31) * 0.2)
            cr.save(); cr.translate(cx, cy + dy + s * 0.46 * sq); cr.rotate(rot); cr.scale(breathe * (1 + sq), breathe * (1 - sq))
            if mood in ("wait", "danger", "done") and s >= 28:
                glow = 0.12 + 0.08 * math.sin(now * 5)
                cr.set_source_rgba(*col, glow); cr.arc(0, 0, s * 0.85, 0, TAU); cr.fill()
            cr.set_source_rgb(*col); rr(cr, -s / 2, -s * 0.46, s, s * 0.92, s * 0.42); cr.fill()
            cr.save(); cr.translate(-s * 0.13, -s * 0.28); cr.scale(1, 0.55); cr.set_source_rgba(1, 1, 1, 0.24)
            cr.arc(0, 0, s * 0.2, 0, TAU); cr.fill(); cr.restore()
            er, ey, lw, dark = s * 0.085, -s * 0.04, max(1.0, s * 0.06), (0.10, 0.10, 0.14)
            for sx in (-1, 1):
                ex = sx * s * 0.21
                cr.set_source_rgb(*dark); cr.set_line_width(lw)
                if mood == "sleep":
                    cr.arc(ex, ey, er, 0.2, math.pi - 0.2); cr.stroke()
                elif mood == "done":
                    cr.arc(ex, ey + er * 0.6, er, math.pi + 0.2, TAU - 0.2); cr.stroke()
                else:
                    cr.save(); cr.translate(ex + look[0] * er, ey + look[1] * er)
                    cr.scale(1, 0.15 if now < self.blink_until else (1.25 if mood in ("wait", "listen") else 1.0))
                    cr.arc(0, 0, er * (1.2 if mood in ("wait", "listen") else 1.0), 0, TAU); cr.fill()
                    cr.set_source_rgba(1, 1, 1, 0.9); cr.arc(-er * 0.3, -er * 0.3, er * 0.28, 0, TAU); cr.fill(); cr.restore()
            if s >= 20:
                cr.set_source_rgba(1, 0.4, 0.55, 0.30)
                for sx in (-1, 1):
                    cr.save(); cr.translate(sx * s * 0.31, s * 0.13); cr.scale(1.3, 0.8); cr.arc(0, 0, s * 0.055, 0, TAU); cr.fill(); cr.restore()
                cr.set_source_rgb(*dark); cr.set_line_width(lw * 0.9)
                if mood == "talk":
                    cr.save(); cr.translate(0, s * 0.15); cr.scale(1, 0.4 + 0.9 * abs(math.sin(now * 11))); cr.arc(0, 0, s * 0.07, 0, TAU); cr.fill(); cr.restore()
                elif mood == "listen":
                    cr.arc(0, s * 0.15, s * 0.04, 0, TAU); cr.fill()
                elif mood in ("idle", "dance", "work"):
                    cr.arc(0, s * 0.08, s * 0.07, 0.3, math.pi - 0.3); cr.stroke()
                elif mood == "done":
                    cr.arc(0, s * 0.05, s * 0.12, 0.2, math.pi - 0.2); cr.stroke()
                elif mood == "wait":
                    cr.arc(0, s * 0.17, s * 0.045, 0, TAU); cr.fill()
                elif mood == "danger":
                    cr.arc(0, s * 0.24, s * 0.08, math.pi + 0.3, TAU - 0.3); cr.stroke()
                    for sx in (-1, 1):
                        cr.move_to(sx * s * 0.32, -s * 0.2); cr.line_to(sx * s * 0.10, -s * 0.13); cr.stroke()
                elif mood == "sleep":
                    for i, (zx, zy, zs) in enumerate(((0.32, -0.62, 0.26), (0.5, -0.9, 0.34))):
                        a = 0.4 + 0.6 * max(0.0, math.sin(now * 1.6 - i * 1.1))
                        text(cr, "z", s * zx, s * zy + (1 - a) * 4, s * zs, tuple(c * a + T["bg"][j] * (1 - a) for j, c in enumerate(T["dim"])), True)
            cr.restore()

        def title(self, cr, label, y, pad, w):
            text(cr, label, pad, y, 8.5, T["dim"], True)
            cr.set_source_rgba(1, 1, 1, 0.07); lw_ = tw(cr, label, 8.5, True) + 8
            cr.rectangle(pad + lw_, y + 6, w - 2 * pad - lw_, 1); cr.fill()
            return y + 19

        @contextlib.contextmanager
        def rev(self, cr):
            i = self.ri
            self.ri += 1
            p = ease_out_back((self.now - max(self.open_t, self.tab_t) - 0.05 * i - 0.04) / 0.34)
            if p >= 0.999:
                yield
                return
            cr.push_group(); cr.translate(0, (1 - p) * 14)
            try:
                yield
            finally:
                cr.pop_group_to_source(); cr.paint_with_alpha(max(0.0, min(1.0, p)))

        def hvv(self, key, target):
            v = self.hv.get(key, 0.0)
            v += (target - v) * 0.28
            if len(self.hv) > 400:
                self.hv.clear()
            self.hv[key] = v
            return v

        def chip(self, cr, x, y, label, color, cb, hold=0.0, w=None, h=24, active=False, now=0.0):
            w = w or tw(cr, label, 10, True) + 24
            rect = (x, y - self.hy, w, h)
            hv = self.hvv(rect, 1.0 if self.hot == rect else 0.0)
            pr = 1.0 if self.pressed == rect else 0.0
            sc = 1 + 0.035 * hv - 0.06 * pr
            cr.save(); cr.translate(x + w / 2, y + h / 2); cr.scale(sc, sc); cr.translate(-w / 2, -h / 2)
            cr.set_source_rgba(*color, (0.34 if active else 0.15) + 0.17 * hv); rr(cr, 0, 0, w, h, h / 2); cr.fill()
            if hv > 0.05:
                cr.set_source_rgba(*color, 0.55 * hv); cr.set_line_width(1.1); rr(cr, 0.5, 0.5, w - 1, h - 1, h / 2); cr.stroke()
            if hold and self.holding and self.holding[0]["r"] == rect:
                p = min(1.0, (now - self.holding[1]) / hold)
                cr.set_source_rgba(*color, 0.85); rr(cr, 0, 0, max(h, w * p), h, h / 2); cr.fill()
            text(cr, label, 0, (h - 15) / 2, 10, color if not (hold and self.holding) else T["text"], True, w=w, align="c")
            cr.restore()
            self.hit(x, y, w, h, cb, hold)
            return w

        def flow(self, cr, items, x, y, W, pad, now=0.0, h=24):
            x0 = x
            for label, color, cb in items:
                w = tw(cr, label, 10, True) + 24
                if x + w > W - pad and x > x0:
                    x, y = x0, y + h + 8
                self.chip(cr, x, y, label, color, cb, now=now)
                x += w + 8
            return y + h + 8

        def bar(self, cr, x, y, w, h, frac, color):
            cr.set_source_rgba(1, 1, 1, 0.08); rr(cr, x, y, w, h, h / 2); cr.fill()
            if frac > 0:
                cr.set_source_rgb(*color); rr(cr, x, y, max(h, w * min(1.0, frac)), h, h / 2); cr.fill()

        def switch(self, cr, x, y, on, key, cb):
            v = self.anim.get(key, 1.0 if on else 0.0)
            v += ((1.0 if on else 0.0) - v) * 0.3
            self.anim[key] = v
            cr.set_source_rgba(*T["ok"], 0.25 + 0.55 * v); rr(cr, x, y, 38, 20, 10); cr.fill()
            cr.set_source_rgb(1, 1, 1); cr.arc(x + 10 + 18 * v, y + 10, 7, 0, TAU); cr.fill()
            self.hit(x, y, 38, 20, cb)

        def cnt(self, key, val):
            v = self.anim.get(key, 0.0)
            v += (val - v) * 0.2
            self.anim[key] = v
            return int(round(v))

        # ---------- dessin principal ----------
        def layer(self, cr, alpha, fn):
            if alpha < 0.02:
                return
            cr.push_group(); fn(); cr.pop_group_to_source(); cr.paint_with_alpha(min(1.0, alpha))

        def on_draw(self, _w, cr):
            now, snap = time.time(), self.snap
            self.now = now
            W = self.get_allocated_width() or self.WWIN
            rw, rh = self.sw.pos, self.sh.pos
            self.x0 = (W - rw) / 2
            cr.set_operator(cairo.OPERATOR_SOURCE); cr.set_source_rgba(0, 0, 0, 0); cr.paint(); cr.set_operator(cairo.OPERATOR_OVER)
            cr.translate(self.x0, 0)
            aps = snap["approvals"]
            ear, hold_at = min(EAR, rh / 3), int(cfg["radar"].get("hold_at", 70))
            rad = max(2.0, min(24.0, (rh - ear) / 2, rw / 2))
            shape(cr, rw, rh, ear, rad); cr.set_source_rgb(*T["bg"]); cr.fill_preserve()
            if aps:
                col = T["danger"] if aps[0]["score"] >= hold_at else T["warn"]
                cr.set_source_rgba(*col, 0.35 + 0.4 * (0.5 + 0.5 * math.sin(now * 5))); cr.set_line_width(1.8)
            else:
                cr.set_source_rgba(1, 1, 1, 0.07); cr.set_line_width(1.0)
            cr.stroke()
            shape(cr, rw, rh, ear, rad); cr.clip()
            self.hits, mood, self.ri = [], self.mood(snap), 0
            self.accept_hits = False
            self.layer(cr, self.a["mini"], lambda: self.draw_mini(cr, now, rw, rh, mood))
            self.layer(cr, self.a["peek"], lambda: self.draw_peek(cr, now, rw, rh, mood))
            self.accept_hits = self.a["open"] > 0.7
            self.layer(cr, self.a["open"], lambda: self.draw_open(cr, now, rw, mood))
            for (rx, ry, t0, col) in self.ripples:                       # ondulations au clic
                p = (now - t0) / 0.55
                cr.set_source_rgba(*col, 0.35 * (1 - p)); cr.arc(rx, ry, 6 + 60 * smooth(p), 0, TAU); cr.fill()
            for p in self.parts:                                          # confettis / étincelles / cœurs
                a = max(0.0, min(1.0, p["life"] / 0.5))
                cr.set_source_rgba(*p["col"], a)
                if p["kind"] == "conf":
                    cr.save(); cr.translate(p["x"], p["y"]); cr.rotate(p["rot"]); cr.rectangle(-p["s"], -p["s"] * .5, p["s"] * 2, p["s"]); cr.fill(); cr.restore()
                elif p["kind"] == "star":
                    star(cr, p["x"], p["y"], p["s"] * (0.6 + 0.6 * math.sin(p["life"] * 12) ** 2))
                else:
                    cr.set_source_rgba(1, 0.45, 0.6, a); heart(cr, p["x"], p["y"], p["s"])
            return False

        def draw_mini(self, cr, now, rw, rh, mood):
            snap, cy = self.snap, rh / 2 + 1
            self.mochi(cr, 24, cy, 14, mood, now, tint=snap["tint"])
            ix = rw - 26
            if snap["in_call"]:
                cr.set_source_rgba(*T["danger"], 0.6 + 0.4 * math.sin(now * 4)); cr.arc(ix, cy, 3.2, 0, TAU); cr.fill()
            elif snap["music"].get("status") == "Playing":
                cr.set_source_rgb(*T["accent"])
                for i in range(4):
                    h = 2 + 7 * abs(math.sin(now * (3.5 + i * 1.3) + i))
                    cr.rectangle(ix - 8 + i * 4.5, cy + 4 - h, 2.6, h); cr.fill()
            elif core.working():
                for i in range(3):
                    cr.set_source_rgba(*T["accent"], 0.35 + 0.65 * max(0.0, math.sin(now * 5 - i * 0.9)))
                    cr.arc(ix - 6 + i * 6.5, cy, 2.2, 0, TAU); cr.fill()
            else:
                cr.set_source_rgba(*T["dim"], 0.35 + 0.25 * math.sin(now * 1.4)); cr.arc(ix, cy, 2.2, 0, TAU); cr.fill()

        def draw_peek(self, cr, now, rw, rh, mood):
            t = self.snap["toast"]
            self.mochi(cr, 32, rh / 2 + 1, 30, mood, now, tint=self.snap["tint"])
            msg, kind = (t[0], t[1]) if t else ("Coucou", "info")
            shown = msg[: max(1, int((now - (t[2] - float(IC["toast_seconds"]))) * 55))] if t else msg
            mic = self.snap["mic"]
            if mic["state"] in ("rec", "transcribing") and not t:
                msg, kind = (f"🎤 J'écoute… {fmt_time(now - mic['t0'])}  ·  clique pour arrêter" if mic["state"] == "rec" else "✍ Transcription…"), "danger"
                shown = msg
                cr.set_source_rgba(*T["danger"], 0.25 * (0.5 + 0.5 * math.sin(now * 5))); cr.arc(rw - 20, rh / 2, 6 + 5 * abs(math.sin(now * 3)), 0, TAU); cr.fill()
            cr.set_source_rgb(*KIND.get(kind, T["accent"])); cr.arc(rw - 20, rh / 2, 3.5, 0, TAU); cr.fill()
            text(cr, shown, 58, rh / 2 - 9, 12, T["text"], True, w=rw - 58 - 38)

        def draw_open(self, cr, now, W, mood):
            snap, pad, y = self.snap, 18, 12
            aps = snap["approvals"]
            n_work = sum(1 for s in snap["sessions"] if s["state"] in ("working", "waiting") and now - s["updated"] < 120)
            with self.rev(cr):
                self.mochi(cr, pad + 20, y + 22, 40, mood, now, tint=snap["tint"])
                self.hit(pad, y, 42, 42, self.poke)
                head = (f"{len(aps)} demande(s) en attente" if aps else snap["toast"][0] if snap["toast"] else
                        "Pause bien-être" if snap["calm"] else f"{n_work} agent(s) au travail" if n_work else "Tout est calme")
                text(cr, head, pad + 52, y + 5, 13.5, T["text"], True, w=W - 2 * pad - 176)
                sub = dt.datetime.now().strftime("%H:%M") + ("  ·  🔒 verrouillé" if snap["locked"] else "") + ("  ·  🎯 focus" if snap["focus"] else "") \
                    + ("  ·  🎙 appel" if snap["in_call"] else "") + ("  ·  ☕ anti-veille" if snap["inhibited"] else "")
                text(cr, sub, pad + 52, y + 26, 9.5, T["dim"], w=W - 2 * pad - 176)
                px, cx, mx = W - pad - 60, W - pad - 14, W - pad - 100
                cr.set_source_rgba(*T["accent"], 1.0 if self.pinned else 0.4); cr.set_line_width(1.6)
                cr.arc(px, y + 20, 6, 0, TAU); cr.fill() if self.pinned else cr.stroke()
                self.hit(px - 12, y + 8, 24, 24, lambda: setattr(self, "pinned", not self.pinned))
                cr.set_source_rgba(1, 1, 1, 0.55); cr.set_line_width(2); cr.move_to(cx - 6, y + 23); cr.line_to(cx, y + 17); cr.line_to(cx + 6, y + 23); cr.stroke()
                self.hit(cx - 14, y + 6, 28, 28, self.collapse)
                rec = snap["mic"]["state"] == "rec"
                if rec:
                    cr.set_source_rgba(*T["danger"], 0.3 * (0.5 + 0.5 * math.sin(now * 6))); cr.arc(mx, y + 20, 14 + 3 * math.sin(now * 6), 0, TAU); cr.fill()
                self.draw_mic(cr, mx, y + 20, 18, T["danger"] if rec else T["dim"], 1.0 if rec else 0.85)
                self.hit(mx - 14, y + 6, 28, 28, core.mic_toggle)
            y += 54
            if snap["calm"]:
                y = self.draw_calm(cr, now, W, y, pad)
                self.need_open = int(y + 12)
                return
            with self.rev(cr):
                tabw = (W - 2 * pad) / len(self.TABS)
                for i, t in enumerate(self.TABS):
                    act = t == self.tab
                    text(cr, t, pad + i * tabw, y + 3, 10.5, T["text"] if act else T["dim"], act, w=tabw, align="c")
                    self.hit(pad + i * tabw, y - 4, tabw, 30, lambda tt=t: self.set_tab(tt))
                    badge = len(aps) if t == "Agents" else sum(1 for d in snap["todos"] if not d["done"]) if t == "Tâches" else 0
                    if badge:
                        bx = pad + i * tabw + tabw / 2 + tw(cr, t, 10.5, act) / 2 + 8
                        cr.set_source_rgb(*(T["warn"] if t == "Agents" else T["accent"])); cr.arc(bx, y + 10, 6.5, 0, TAU); cr.fill()
                        text(cr, str(badge), bx - 7, y + 4.5, 8, (0.05, 0.05, 0.08), True, w=14, align="c")
                    if t == "IA" and snap["ai"]["state"] in ("busy", "stream"):
                        cr.set_source_rgb(*T["accent"]); cr.arc(pad + i * tabw + tabw / 2 + 20, y + 10, 2.5 + math.sin(now * 8), 0, TAU); cr.fill()
                cr.set_source_rgba(*T["accent"], 0.95); rr(cr, pad + self.ind.pos + 14, y + 24, tabw - 28, 3, 1.5); cr.fill()
            y += 38
            with self.rev(cr):
                y = self.approvals(cr, now, W, y, pad)
            top = y
            self.scroll_t = max(0.0, min(self.scroll_t, self.max_scroll))
            cr.save()
            cr.rectangle(0, top - 2, W, max(8.0, self.sh.pos - top - 6)); cr.clip()
            cr.translate(0, -self.scroll_y)
            self.hy, self.body_clip = self.scroll_y, (top, max(top + 8, self.sh.pos - 6))
            y = {"Bonjour": self.body_bonjour, "Agents": self.body_agents, "Musique": self.body_music, "IA": self.body_ai, "Tâches": self.body_tasks,
                 "Outils": self.body_tools, "Système": self.body_system}[self.tab](cr, now, W, y, pad)
            self.hy, self.body_clip = 0.0, None
            cr.restore()
            self.need_open = int(y + 12)
            self.max_scroll = max(0.0, self.need_open - self.HMAX)
            if self.max_scroll > 0 and self.sh.pos > top + 40:
                tr_h = self.sh.pos - top - 14
                th = max(24.0, tr_h * (self.HMAX - top) / max(1.0, self.need_open - top))
                ty = top + 4 + (tr_h - th) * (self.scroll_y / self.max_scroll)
                cr.set_source_rgba(1, 1, 1, 0.22); rr(cr, W - 7, ty, 3, th, 1.5); cr.fill()

        def approvals(self, cr, now, W, y, pad):
            aps, hold_at = self.snap["approvals"], int(cfg["radar"].get("hold_at", 70))
            for ap in aps[:2]:
                hi = ap["score"] >= hold_at
                rc = T["danger"] if hi else T["warn"] if ap["score"] >= 40 else T["ok"]
                cw = W - 2 * pad
                cr.set_source_rgb(*T["surface"]); rr(cr, pad, y, cw, 130, 15); cr.fill()
                cr.set_source_rgb(*rc); rr(cr, pad, y + 12, 3.5, 106, 2); cr.fill()
                text(cr, f"{ap['agent']}  ·  {ap['tool']}", pad + 16, y + 9, 10, T["dim"], True)
                cr.set_source_rgba(0, 0, 0, 0.35); rr(cr, pad + 14, y + 28, cw - 28, 42, 9); cr.fill()
                text(cr, short(ap["summary"], 200), pad + 22, y + 33, 10, T["text"], w=cw - 44, lines=2, mono=True)
                self.bar(cr, pad + 16, y + 78, cw - 32, 5, max(ap["score"], 4) / 100, rc)
                text(cr, f"Risque {ap['score']}" + (" · " + ", ".join(ap["labels"]) if ap["labels"] else " · commande ordinaire"), pad + 16, y + 86, 9, rc, w=cw - 32)
                bw, by, bx = (cw - 32 - 16) / 3, y + 104, pad + 16
                self.chip(cr, bx, by, "Refuser", T["danger"], lambda i=ap["id"]: core.resolve(i, "deny"), w=bw, now=now)
                if not hi:
                    self.chip(cr, bx + bw + 8, by, "Toujours", T["accent"], lambda i=ap["id"]: core.resolve(i, "always"), w=bw, now=now)
                self.chip(cr, bx + 2 * (bw + 8), by, "Autoriser" if not hi else "Maintenir…", T["ok"], lambda i=ap["id"]: core.resolve(i, "allow"),
                          hold=float(cfg["radar"].get("hold_seconds", 1.2)) if hi else 0.0, w=bw, now=now)
                y += 140
            if len(aps) > 2:
                text(cr, f"+ {len(aps) - 2} autre(s) en attente", pad, y, 10, T["warn"], True); y += 22
            return y

        # ---------- pause bien-être ----------
        def draw_calm(self, cr, now, W, y, pad):
            c = self.snap["calm"]
            el, left = now - c["start"], max(0.0, c["dur"] - (now - c["start"]))
            cx, cy = W / 2, y + 100
            if c["kind"] == "breath":
                ph = el % 16
                seg, frac = int(ph // 4), (ph % 4) / 4
                k = smooth(frac) if seg == 0 else 1.0 if seg == 1 else 1 - smooth(frac) if seg == 2 else 0.0
                label = ("Inspire", "Retiens", "Expire", "Retiens")[seg]
                if seg != self.calm_seg:
                    self.calm_seg = seg
                    core.play("inhale" if seg == 0 else "exhale" if seg == 2 else "tick")
                r = 34 + 50 * k
                for i, (dr, a) in enumerate(((22, .06), (12, .10), (0, .22))):
                    cr.set_source_rgba(*T["accent"], a); cr.arc(cx, cy, r + dr, 0, TAU); cr.fill()
                cr.set_source_rgba(*T["accent"], .9); cr.set_line_width(2); cr.arc(cx, cy, r, 0, TAU); cr.stroke()
                text(cr, label, cx - 70, cy - 12, 17, T["text"], True, w=140, align="c")
            else:
                self.calm_seg = -1
                cr.set_source_rgba(1, 1, 1, .08); cr.set_line_width(5); cr.arc(cx, cy, 62, 0, TAU); cr.stroke()
                cr.set_source_rgb(*T["ok"]); cr.arc(cx, cy, 62, -math.pi / 2, -math.pi / 2 + TAU * (1 - left / c["dur"])); cr.stroke()
                for i in range(18):
                    a = i * 0.7 + now * 0.15
                    rr_ = 20 + (i * 13 % 36)
                    cr.set_source_rgba(1, 1, 1, 0.25 + 0.25 * math.sin(now * 2 + i)); cr.arc(cx + math.cos(a) * rr_, cy + math.sin(a) * rr_ * 0.8, 1.4, 0, TAU); cr.fill()
                text(cr, "Regarde au loin", cx - 80, cy - 12, 15, T["text"], True, w=160, align="c")
            text(cr, f"{int(left)} s", cx - 40, cy + 98, 11, T["dim"], w=80, align="c")
            yb = cy + 124
            self.chip(cr, cx - 110, yb, "Passer", T["dim"], lambda: core.end_calm(False), w=100)
            if c["kind"] == "breath":
                self.chip(cr, cx + 10, yb, "+1 min", T["accent"], lambda: core.calm.__setitem__("dur", core.calm["dur"] + 60), w=100)
            return yb + 34

        # ---------- onglets ----------
        def body_agents(self, cr, now, W, y, pad):
            snap, cw = self.snap, W - 2 * pad
            sess = [s for s in snap["sessions"] if s["state"] != "done" or now - s["updated"] < 300][: int(IC["max_sessions"])]
            with self.rev(cr):
                y = self.flow(cr, [("☀ Bonjour !", T["warn"], self.start_bonjour), ("🎤 Parler à Qwen", T["ok"], core.mic_toggle)], pad, y, W, pad, now)
            with self.rev(cr):
                y = self.title(cr, "AGENTS", y, pad, W)
                if not sess:
                    text(cr, "Aucun agent actif — lance `hermes` dans un terminal.", pad, y + 2, 10.5, T["dim"], w=cw); y += 28
                for s in sess:
                    c = STATE.get(s["state"], T["dim"])
                    pulse = 0.55 + 0.45 * math.sin(now * 5) if s["state"] == "working" else 1.0
                    pcol = core.profile_color(s["profile"]) if s.get("profile") else None
                    cr.set_source_rgba(*(pcol if (pcol and s["state"] == "working") else c), pulse); cr.arc(pad + 7, y + 13, 4.5, 0, TAU); cr.fill()
                    text(cr, f"{s.get('profile') or s['agent']} · {s['label']}", pad + 22, y + 5, 11, T["text"], True, w=190)
                    text(cr, s["tool"] if s["state"] == "working" and s["tool"] else (s["text"] or s["state"]), pad + 220, y + 6, 10, T["dim"], w=cw - 220 - 20)
                    if s["cwd"]:
                        cr.set_source_rgba(1, 1, 1, 0.35); rr(cr, W - pad - 14, y + 9, 12, 9, 2); cr.fill()
                        self.hit(pad, y, cw, 28, lambda c=s["cwd"]: core.open_folder(c))
                    y += 30
                y += 4
            y = self.section_profiles(cr, now, W, y, pad)
            if snap["jobs"]:
                with self.rev(cr):
                    y = self.title(cr, "COMMANDES SURVEILLÉES", y, pad, W)
                    for j in snap["jobs"][:4]:
                        run_ = j["end"] is None
                        if run_:
                            cr.set_source_rgb(*T["accent"]); cr.set_line_width(2.2); cr.arc(pad + 8, y + 11, 6, now * 6, now * 6 + 4.0); cr.stroke()
                        else:
                            text(cr, "✔" if j["code"] == 0 else "✖", pad + 1, y + 3, 12, T["ok"] if j["code"] == 0 else T["danger"], True)
                        text(cr, j["label"], pad + 24, y + 4, 10.5, T["text"], w=cw - 100, mono=True)
                        text(cr, fmt_time((j["end"] or now) - j["start"]), W - pad - 64, y + 4, 10.5, T["dim"], True, w=64, align="r")
                        y += 26
                    y += 4
            if cfg["hermes"].get("kanban"):
                with self.rev(cr):
                    y = self.title(cr, "KANBAN HERMES", y, pad, W)
                    kb = snap["kanban"]
                    if not kb.get("ok"):
                        text(cr, kb.get("error") or "lecture en cours…", pad, y + 2, 10, T["dim"], w=cw); y += 26
                    else:
                        tot, x = max(1, kb["total"]), pad
                        for st in Kanban.ORDER:
                            n = kb["counts"].get(st, 0)
                            wseg = self.anim.setdefault(f"kb_{st}", 0.0)
                            wseg += (cw * n / tot - wseg) * 0.2
                            self.anim[f"kb_{st}"] = wseg
                            if wseg > 0.5:
                                cr.set_source_rgb(*KB[st]); rr(cr, x, y, max(4, wseg - 2), 8, 4); cr.fill()
                            x += wseg
                        y += 14
                        text(cr, "  ·  ".join(f"{self.cnt('kbn_' + st, kb['counts'].get(st, 0))} {KB_LABEL[st]}" for st in Kanban.ORDER if kb["counts"].get(st)), pad, y, 9.5, T["dim"], w=cw)
                        y += 20
                        for t in kb["active"][:4]:
                            cr.set_source_rgb(*KB[t["status"]]); cr.arc(pad + 5, y + 9, 3.5, 0, TAU); cr.fill()
                            text(cr, t["title"], pad + 16, y + 2, 10.5, T["text"], w=cw - 130)
                            text(cr, (t["who"] + " · " if t["who"] else "") + KB_LABEL[t["status"]], W - pad - 112, y + 3, 9.5, KB[t["status"]], w=112, align="r")
                            y += 22
                    y += 4
            if cfg["stats"].get("enabled"):
                with self.rev(cr):
                    st = snap["stats"]
                    text(cr, f"Aujourd'hui · {self.cnt('st_t', st['tasks'])} tâche(s) · {self.cnt('st_o', st['ok'])} accord(s) · {self.cnt('st_n', st['no'])} refus · agents actifs {fmt_time(st['work'])}",
                         pad, y + 2, 9.5, T["dim"], w=cw)
                    y += 22
            return y

        def body_music(self, cr, now, W, y, pad):
            snap, m, cw = self.snap, self.snap["music"], W - 2 * pad
            with self.rev(cr):
                y = self.title(cr, "MUSIQUE", y, pad, W)
                if m.get("title"):
                    size, art = 84, self.get_art(m.get("art"))
                    bob = math.sin(now * 3) * 1.2 if m.get("status") == "Playing" else 0
                    cr.set_source_rgb(*T["surface"]); rr(cr, pad, y + bob, size, size, 15); cr.fill()
                    if art:
                        cr.save(); rr(cr, pad, y + bob, size, size, 15); cr.clip(); cr.translate(pad, y + bob)
                        cr.scale(size / art.get_width(), size / art.get_height()); Gdk.cairo_set_source_pixbuf(cr, art, 0, 0); cr.paint(); cr.restore()
                    else:
                        text(cr, "♪", pad, y + 22, 30, T["dim"], True, w=size, align="c")
                    tx = pad + size + 16
                    text(cr, m["title"], tx, y + 4, 13.5, T["text"], True, w=W - tx - pad)
                    text(cr, m["artist"], tx, y + 25, 11, T["dim"], w=W - tx - pad)
                    text(cr, m.get("album", ""), tx, y + 43, 9.5, T["dim"], w=W - tx - pad)
                    pos = m.get("pos", 0) + ((now - m.get("t", now)) if m.get("status") == "Playing" else 0)
                    ln = m.get("length") or 0
                    self.bar(cr, tx, y + 68, W - tx - pad - 74, 4, (pos / ln) if ln else 0, T["accent"])
                    text(cr, f"{fmt_time(pos)} / {fmt_time(ln)}", W - pad - 70, y + 62, 9, T["dim"], w=70, align="r")
                    y += size + 14
                    cx, playing = W / 2, m.get("status") == "Playing"
                    for dx, meth, kind in ((-72, "Previous", "prev"), (0, "PlayPause", "play"), (72, "Next", "next")):
                        px, rect = cx + dx, (cx + dx - 24, y - 2, 48, 44)
                        hv = self.hvv(rect, 1.0 if self.hot == rect else 0.0)
                        if kind == "play":
                            cr.set_source_rgba(*T["accent"], 0.9 + 0.1 * hv); cr.arc(px, y + 20, 21 + 2 * hv, 0, TAU); cr.fill(); cr.set_source_rgb(0.07, 0.08, 0.1)
                            if playing:
                                cr.rectangle(px - 7, y + 12, 5, 16); cr.rectangle(px + 2, y + 12, 5, 16)
                            else:
                                cr.move_to(px - 5, y + 11); cr.line_to(px + 9, y + 20); cr.line_to(px - 5, y + 29); cr.close_path()
                        else:
                            d = -1 if kind == "prev" else 1
                            cr.set_source_rgba(*T["text"], 0.75 + 0.25 * hv)
                            for off in (-5, 3):
                                cr.move_to(px + d * (off - 3), y + 12); cr.line_to(px + d * (off + 6), y + 20); cr.line_to(px + d * (off - 3), y + 28); cr.close_path()
                        cr.fill()
                        self.hit(*rect, lambda mm=meth: self.player(mm))
                    y += 54
                else_ = not m.get("title")
                if else_:
                    text(cr, "Aucun lecteur détecté. Lance Tidal (tidal-hifi) et active MPRIS dans ses réglages.", pad, y + 2, 10.5, T["dim"], w=cw, lines=2); y += 42
            with self.rev(cr):
                y = self.title(cr, "VOLUME", y, pad, W)
                vol, mute = snap["sys"].get("vol", 0), snap["sys"].get("mute", False)
                sw_ = cw - 84
                self.bar(cr, pad, y + 9, sw_, 6, 0 if mute else vol / 100, T["dim"] if mute else T["accent"])
                cr.set_source_rgb(1, 1, 1); cr.arc(pad + sw_ * (0 if mute else vol / 100), y + 12, 7, 0, TAU); cr.fill()
                self.hit(pad - 6, y, sw_ + 12, 24, drag=lambda f: core.set_volume(int(f * 100)))
                text(cr, "Muet" if mute else f"{vol}%", W - pad - 70, y + 4, 10.5, T["warn"] if mute else T["text"], True, w=70, align="r")
                self.hit(W - pad - 70, y, 70, 24, core.toggle_mute)
                y += 36
            return y

        def body_ai(self, cr, now, W, y, pad):
            snap, cw, ai = self.snap, W - 2 * pad, self.snap["ai"]
            with self.rev(cr):
                y = self.title(cr, "IA LOCALE (OLLAMA)", y, pad, W)
                ok, info = snap["ollama"]
                cr.set_source_rgb(*(T["ok"] if ok else T["danger"])); cr.arc(pad + 5, y + 8, 3.5, 0, TAU); cr.fill()
                text(cr, info if ok else f"Ollama injoignable ({info or '…'})", pad + 16, y + 2, 9.5, T["dim"], w=cw - 16)
                y += 24
                items = [("✨ Brief du matin", T["accent"], core.ai_brief), ("📝 Bilan du jour", T["accent"], core.ai_recap)]
                items += [(p["label"], T["accent"], lambda p=p: core.ai_run(p["label"], p["prompt"])) for p in cfg["ollama"].get("prompts", [])]
                items.append(("💬 Poser une question…", T["ok"], self.open_prompt))
                y = self.flow(cr, items, pad, y, W, pad, now)
            with self.rev(cr):
                y = self.title(cr, "VOIX", y, pad, W)
                mic, vi = snap["mic"], snap["voice_info"]
                rec = mic["state"] == "rec"
                cx_, cy_ = pad + 26, y + 28
                if rec:
                    for k in range(3):
                        p_ = ((now * 1.2) + k / 3) % 1.0
                        cr.set_source_rgba(*T["danger"], 0.35 * (1 - p_)); cr.arc(cx_, cy_, 22 + 22 * p_, 0, TAU); cr.fill()
                cr.set_source_rgba(*(T["danger"] if rec else T["accent"]), 0.9); cr.arc(cx_, cy_, 24, 0, TAU); cr.fill()
                self.draw_mic(cr, cx_, cy_, 26, (0.06, 0.07, 0.09))
                self.hit(pad, y + 2, 52, 52, core.mic_toggle)
                msg_ = {"idle": "Clique et parle : Qwen te répond par écrit.", "rec": f"J'écoute… {fmt_time(now - mic['t0'])} — clique pour arrêter",
                        "transcribing": "Transcription en cours…", "error": mic.get("msg", "erreur")}[mic["state"]]
                text(cr, msg_, pad + 62, y + 8, 11, T["danger"] if mic["state"] == "error" else T["text"], mic["state"] == "rec", w=cw - 62, lines=3)
                text(cr, "Transcription : " + (", ".join(vi.get("stt", [])) or "aucun moteur détecté"), pad + 62, y + 40, 9, T["dim"] if vi.get("stt") else T["warn"], w=cw - 62)
                y += 66
            with self.rev(cr):
                y = self.title(cr, "SUR LE PRESSE-PAPIERS", y, pad, W)
                y = self.flow(cr, [(c["label"], T["warn"], lambda c=c: core.ai_clip(c["prompt"], c["label"])) for c in cfg["ollama"].get("clip_actions", [])], pad, y, W, pad, now)
            if ai["state"] != "idle":
                with self.rev(cr):
                    streaming = ai["state"] in ("busy", "stream")
                    body = ai["text"] + (" ▌" if streaming and int(now * 2.5) % 2 == 0 else "")
                    lay = layout(cr, body or " ", 10.5, False, False, cw - 28, 10)
                    th = max(18, lay.get_pixel_size()[1]) if ai["text"] else 22
                    ch = th + 62
                    cr.set_source_rgb(*T["surface"]); rr(cr, pad, y, cw, ch, 14); cr.fill()
                    cr.set_source_rgb(*(T["danger"] if ai["state"] == "error" else (ai.get("color") or T["accent"]))); rr(cr, pad, y + 12, 3.5, ch - 24, 2); cr.fill()
                    text(cr, ai["title"], pad + 16, y + 9, 9.5, T["dim"], True, w=cw - 100)
                    if ai["state"] == "busy":
                        cr.set_source_rgb(*T["accent"]); cr.set_line_width(2.2); cr.arc(pad + cw - 20, y + 16, 7, now * 6, now * 6 + 4.0); cr.stroke()
                        text(cr, "Qwen réfléchit…", pad + 16, y + 30, 10.5, T["dim"])
                    else:
                        cr.set_source_rgb(*(T["danger"] if ai["state"] == "error" else T["text"])); cr.move_to(pad + 16, y + 30); PangoCairo.show_layout(cr, lay)
                    if ai["state"] == "done":
                        by, x = y + ch - 34, pad + 16
                        x += self.chip(cr, x, by, "Copier", T["accent"], lambda t=ai["text"]: self.copy(t), h=22, now=now) + 8
                        if cfg["depot"].get("enabled"):
                            x += self.chip(cr, x, by, "☁ Enregistrer", T["ok"], core.save_ai_note, h=22, now=now) + 8
                        self.chip(cr, x, by, "Effacer", T["dim"], core.ai_clear, h=22, now=now)
                    elif ai["state"] == "error":
                        self.chip(cr, pad + 16, y + ch - 34, "Effacer", T["dim"], core.ai_clear, h=22, now=now)
                    y += ch + 8
            return y

        def body_tasks(self, cr, now, W, y, pad):
            snap, cw = self.snap, W - 2 * pad
            todos = sorted(snap["todos"], key=lambda t: (t["done"], t["ts"]))[:7]
            with self.rev(cr):
                y = self.title(cr, "À FAIRE", y, pad, W)
                if not todos:
                    text(cr, "Rien à faire ! Ajoute avec la barre magique : « todo acheter du pain ».", pad, y + 2, 10.5, T["dim"], w=cw, lines=2); y += 38
                for t in todos:
                    k = self.anim.get("chk" + t["id"], 1.0 if t["done"] else 0.0)
                    k += ((1.0 if t["done"] else 0.0) - k) * 0.28
                    self.anim["chk" + t["id"]] = k
                    cx_, cy_ = pad + 11, y + 12
                    cr.set_source_rgba(*T["ok"], 0.25 + 0.75 * k); cr.set_line_width(1.8); cr.arc(cx_, cy_, 8.5, 0, TAU); cr.fill() if k > 0.5 else cr.stroke()
                    if k > 0.05:
                        cr.set_source_rgb(0.05, 0.08, 0.07); cr.set_line_width(2)
                        cr.move_to(cx_ - 4, cy_); cr.line_to(cx_ - 1 * k - 0.5, cy_ + 3.5 * k + 0.5); cr.line_to(cx_ + 4.5 * k - 0.5, cy_ - 3.5 * k); cr.stroke()
                    col = tuple(T["dim"][i] * k + T["text"][i] * (1 - k) for i in range(3))
                    text(cr, t["text"], pad + 30, y + 4, 11, col, w=cw - 70)
                    if k > 0.3:
                        cr.set_source_rgba(*T["dim"], k * 0.9); cr.set_line_width(1); cr.move_to(pad + 30, y + 12); cr.line_to(pad + 30 + min(cw - 70, tw(cr, t["text"], 11) * k), y + 12); cr.stroke()
                    self.hit(pad, y, cw - 30, 26, lambda i=t["id"], d=t["done"], x=cx_, yy=cy_: (core.toggle_todo(i), None if d else self.burst(x, yy, "conf", 18)))
                    cr.set_source_rgba(1, 1, 1, 0.3); cr.set_line_width(1.4)
                    cr.move_to(W - pad - 14, y + 8); cr.line_to(W - pad - 6, y + 16); cr.move_to(W - pad - 6, y + 8); cr.line_to(W - pad - 14, y + 16); cr.stroke()
                    self.hit(W - pad - 22, y, 26, 26, lambda i=t["id"]: core.delete_todo(i))
                    y += 28
                y += 2
                y = self.flow(cr, [("➕ Ajouter…", T["ok"], self.open_prompt), ("🧠 Prioriser (Qwen)", T["accent"], core.ai_prioritize), ("Effacer les faits", T["dim"], core.clear_done)], pad, y, W, pad, now)
            with self.rev(cr):
                y = self.title(cr, "FOCUS & MINUTEURS", y, pad, W)
                f = snap["focus"]
                if f:
                    left = f["end"] - now
                    cr.set_source_rgba(1, 1, 1, 0.1); cr.set_line_width(3.5); cr.arc(pad + 20, y + 20, 15, 0, TAU); cr.stroke()
                    cr.set_source_rgb(*T["accent"]); cr.arc(pad + 20, y + 20, 15, -math.pi / 2, -math.pi / 2 + TAU * (1 - left / f["total"])); cr.stroke()
                    text(cr, fmt_time(left), pad + 46, y + 8, 15, T["text"], True)
                    text(cr, "focus en cours · notifications coupées" if cfg["focus"].get("dnd") else "focus en cours", pad + 46, y + 28, 9.5, T["dim"])
                    self.chip(cr, W - pad - 90, y + 8, "Arrêter", T["danger"], core.stop_focus, w=90)
                    y += 46
                else:
                    y = self.flow(cr, [(f"🎯 Focus {m} min", T["accent"], lambda m=m: core.start_focus(m)) for m in cfg["focus"]["minutes"]]
                                  + [(f"⏱ {m} min", T["warn"], lambda m=m: core.add_timer(m * 60, f"{m} min")) for m in cfg["timers"]["presets_minutes"]], pad, y, W, pad, now)
                for t in snap["timers"][:3]:
                    left = t["end"] - now
                    text(cr, t["label"], pad, y + 2, 10.5, T["text"], w=cw - 110)
                    text(cr, fmt_time(left), W - pad - 100, y + 2, 10.5, T["warn"], True, w=60, align="r")
                    self.bar(cr, pad, y + 20, cw - 36, 3, 1 - left / t["total"], T["warn"])
                    cr.set_source_rgba(1, 1, 1, 0.5); cr.set_line_width(1.6)
                    cr.move_to(W - pad - 12, y + 4); cr.line_to(W - pad - 4, y + 12); cr.move_to(W - pad - 4, y + 4); cr.line_to(W - pad - 12, y + 12); cr.stroke()
                    self.hit(W - pad - 22, y - 2, 24, 24, lambda i=t["id"]: core.cancel_timer(i))
                    y += 28
            return y

        def body_tools(self, cr, now, W, y, pad):
            snap, cw = self.snap, W - 2 * pad
            with self.rev(cr):
                y = self.title(cr, "ACTIONS RAPIDES", y, pad, W)
                y = self.flow(cr, [(a["label"], T["accent"], lambda i=i: core.run_action(i)) for i, a in enumerate(cfg.get("actions", []))], pad, y, W, pad, now)
            with self.rev(cr):
                y = self.title(cr, "CONFORT", y, pad, W)
                text(cr, "Ne pas déranger (GNOME)", pad, y + 2, 11, T["text"]); self.switch(cr, W - pad - 38, y, snap["dnd"], "dnd", lambda: (core.set_dnd(not snap["dnd"]), core.play("off" if snap["dnd"] else "on"))); y += 30
                on = cfg["inhibit"].get("enabled", True)
                text(cr, "Anti-veille pendant les tâches" + ("  · actif" if snap["inhibited"] else ""), pad, y + 2, 11, T["text"])
                self.switch(cr, W - pad - 38, y, on, "inh", lambda: (cfg["inhibit"].__setitem__("enabled", not on), core.play("off" if on else "on"))); y += 30
                con = cfg["calls"].get("enabled", True)
                text(cr, "Mode appel automatique" + ("  · en appel" if snap["in_call"] else ""), pad, y + 2, 11, T["text"])
                self.switch(cr, W - pad - 38, y, con, "call", lambda: (cfg["calls"].__setitem__("enabled", not con), core.play("off" if con else "on"))); y += 32
            with self.rev(cr):
                y = self.title(cr, "BIEN-ÊTRE", y, pad, W)
                w_ = cfg["wellness"]
                nxt = []
                if w_.get("eye_break"):
                    nxt.append(f"pause yeux dans {fmt_time(core._eye_due - now)}")
                if w_.get("water"):
                    nxt.append(f"eau dans {fmt_time(core._water_due - now)}")
                text(cr, "  ·  ".join(nxt) or "rappels désactivés", pad, y + 2, 10, T["dim"], w=cw); y += 22
                y = self.flow(cr, [("👀 Pause yeux", T["ok"], lambda: core.start_calm("eye")), ("🌬 Respirer", T["ok"], lambda: core.start_calm("breath"))], pad, y, W, pad, now)
            with self.rev(cr):
                y = self.title(cr, "DÉPÔT KDRIVE", y, pad, W)
                dep = snap["depot_ok"]
                cr.set_source_rgb(*(T["ok"] if dep else T["danger"])); cr.arc(pad + 5, y + 8, 3.5, 0, TAU); cr.fill()
                kd = snap["kdrive"]
                text(cr, kd[0] if kd[0] else (cfg["depot"]["folder"] if dep else "Dossier introuvable : " + cfg["depot"]["folder"]), pad + 16, y + 2, 9.5, KIND.get(kd[1], T["dim"]) if kd[0] else T["dim"], w=cw - 16)
                y += 24
                y = self.flow(cr, [("📷 Dernière capture", T["accent"], self.send_screenshot), ("Ouvrir le dépôt", T["dim"], lambda: core.open_folder(str(core.kdrive.root())))], pad, y, W, pad, now)
            with self.rev(cr):
                y = self.title(cr, "PRESSE-PAPIERS", y, pad, W)
                con, g = cfg["clipboard"].get("enabled"), cfg["clipboard"].get("guard")
                text(cr, "Historique du presse-papiers", pad, y + 2, 11, T["text"])
                self.switch(cr, W - pad - 38, y, con, "cbh", lambda: core.set_pref("clipboard", "enabled", not con)); y += 30
                text(cr, "Garde-secrets" + (f"  · effacement dans {int(snap['secret_left'])} s" if snap["secret_left"] else ""), pad, y + 2, 11, T["warn"] if snap["secret_left"] else T["text"])
                self.switch(cr, W - pad - 38, y, g, "cbg", lambda: core.set_pref("clipboard", "guard", not g)); y += 32
                if con:
                    for c in snap["clips"][:5]:
                        text(cr, short(c, 58), pad, y + 2, 10, T["text"], w=cw, mono=True)
                        self.hit(pad, y - 2, cw, 22, lambda t=c: self.copy(t)); y += 22
                    if snap["clips"]:
                        y = self.flow(cr, [("Effacer l'historique", T["dim"], lambda: (core.clips.clear(), core.play("close")))], pad, y + 2, W, pad, now)
                    else:
                        text(cr, "Copie du texte : il apparaîtra ici (en mémoire seulement).", pad, y + 2, 10, T["dim"], w=cw); y += 24
            return y

        def draw_mic(self, cr, cx, cy, s, color, alpha=1.0):
            cr.set_source_rgba(*color, alpha)
            rr(cr, cx - s * .2, cy - s * .5, s * .4, s * .66, s * .2); cr.fill()
            cr.set_line_width(max(1.4, s * .09)); cr.arc(cx, cy + s * .02, s * .34, 0.15 * math.pi, 0.85 * math.pi); cr.stroke()
            cr.move_to(cx, cy + s * .36); cr.line_to(cx, cy + s * .55); cr.stroke()

        def text_block(self, cr, s, x, y, w, size=10.5, color=None, lines=8):
            lay = layout(cr, s or " ", size, False, False, w, lines)
            cr.set_source_rgb(*(color or T["text"])); cr.move_to(x, y); PangoCairo.show_layout(cr, lay)
            return max(14, lay.get_pixel_size()[1])

        def start_bonjour(self):
            core.bonjour()
            self.set_tab("Bonjour")

        def body_bonjour(self, cr, now, W, y, pad):
            snap, cw, b, vi = self.snap, W - 2 * pad, self.snap["briefing"], self.snap["voice_info"]
            if b["state"] == "idle":
                with self.rev(cr):
                    bw, bh = cw, 78
                    rect = (pad, y - self.hy, bw, bh)
                    hv = self.hvv(rect, 1.0 if self.hot == rect else 0.0)
                    sc = 1 + 0.02 * hv - 0.03 * (1.0 if self.pressed == rect else 0.0)
                    cr.save(); cr.translate(pad + bw / 2, y + bh / 2); cr.scale(sc, sc); cr.translate(-bw / 2, -bh / 2)
                    g = cairo.LinearGradient(0, 0, bw, 0)
                    g.add_color_stop_rgba(0, *T["warn"], 0.30 + 0.12 * hv); g.add_color_stop_rgba(1, *T["accent"], 0.30 + 0.12 * hv)
                    cr.set_source(g); rr(cr, 0, 0, bw, bh, 22); cr.fill()
                    cr.set_source_rgba(1.0, .78, .25, 1); cr.arc(44, bh / 2, 14, 0, TAU); cr.fill()
                    cr.set_line_width(2.6)
                    for i in range(10):
                        a = i * TAU / 10 + now * .6
                        cr.move_to(44 + math.cos(a) * 20, bh / 2 + math.sin(a) * 20); cr.line_to(44 + math.cos(a) * 28, bh / 2 + math.sin(a) * 28); cr.stroke()
                    text(cr, "Bonjour !", 90, 14, 22, T["text"], True)
                    text(cr, "Mails · agendas · actus · tâches — résumé par Qwen, en local", 90, 46, 10, T["dim"], w=bw - 110)
                    cr.restore()
                    self.hit(pad, y, bw, bh, self.start_bonjour)
                    y += bh + 16
                with self.rev(cr):
                    y = self.title(cr, "SOURCES", y, pad, W)
                    src = [("Thunderbird", vi.get("tb")), ("Agendas Google", f"{vi.get('cals', 0)} agenda(s)" if vi.get("cals") else None),
                           ("Actualités", f"{vi.get('feeds', 0)} flux" if vi.get("feeds") else None), ("Qwen (Ollama)", snap["ollama"][1] if snap["ollama"][0] else None),
                           ("Voix", ", ".join(vi.get("tts", [])) or None), ("Micro (transcription)", ", ".join(vi.get("stt", [])) or None)]
                    for lab, info in src:
                        cr.set_source_rgb(*(T["ok"] if info else T["danger"])); cr.arc(pad + 5, y + 8, 3.5, 0, TAU); cr.fill()
                        text(cr, lab, pad + 16, y + 2, 10.5, T["text"], True, w=150)
                        text(cr, info or "non configuré", pad + 170, y + 3, 9.5, T["dim"] if info else T["warn"], w=cw - 170)
                        y += 22
                    y += 6
                with self.rev(cr):
                    ap_ = cfg["bonjour"].get("autoplay_voice")
                    text(cr, "Lire le résumé à voix haute automatiquement", pad, y + 2, 11, T["text"])
                    self.switch(cr, W - pad - 38, y, ap_, "autov", lambda: core.set_pref("bonjour", "autoplay_voice", not ap_)); y += 30
                    nd = cfg["bonjour"].get("nudge")
                    text(cr, "Me le proposer chaque matin", pad, y + 2, 11, T["text"])
                    self.switch(cr, W - pad - 38, y, nd, "nudge", lambda: core.set_pref("bonjour", "nudge", not nd)); y += 32
                return y
            with self.rev(cr):
                sp = snap["speaking"]
                text(cr, b.get("label", ""), pad, y + 4, 12.5, T["text"], True, w=cw - 20)
                y += 28
                items = [("⏹ Stop" if sp else "🔊 Lire", T["ok"], core.toggle_speak), ("↻ Relancer", T["accent"], core.bonjour),
                         ("Copier", T["dim"], lambda: self.copy(core.briefing_text()))]
                if cfg["depot"].get("enabled"):
                    items.append(("☁ Enregistrer", T["dim"], core.save_briefing))
                y = self.flow(cr, items, pad, y, W, pad, now)
            for i, s in enumerate(b["sections"]):
                with self.rev(cr):
                    col = {"pending": T["dim"], "busy": T["accent"], "done": T["ok"], "error": T["danger"]}[s["state"]]
                    reading = snap["speaking_section"] == i
                    body = s["text"] or ("en attente…" if s["state"] == "pending" else "")
                    if s["state"] == "busy" and int(now * 2.5) % 2 == 0 and s["text"]:
                        body += " ▌"
                    lines = {"meteo": 3, "agenda": 12, "mails": 10, "taches": 9, "actus": 12, "plan": 10}.get(s["key"], 8)
                    lay = layout(cr, body or " ", 10.5, False, False, cw - 32, lines)
                    th = max(16, lay.get_pixel_size()[1]) if body else 16
                    ch = th + 38
                    cr.set_source_rgb(*T["surface"]); rr(cr, pad, y, cw, ch, 14); cr.fill()
                    pulse = 0.55 + 0.45 * math.sin(now * 6) if (reading or s["state"] == "busy") else 1.0
                    cr.set_source_rgba(*col, pulse); rr(cr, pad, y + 12, 3.5, ch - 24, 2); cr.fill()
                    text(cr, f"{s['icon']}  {s['title']}", pad + 16, y + 9, 10.5, T["text"], True, w=cw - 70)
                    if s["state"] == "busy":
                        cr.set_source_rgb(*T["accent"]); cr.set_line_width(2.2); cr.arc(pad + cw - 20, y + 17, 7, now * 6, now * 6 + 4.0); cr.stroke()
                    elif reading:
                        text(cr, "🔊", pad + cw - 34, y + 8, 12, T["ok"])
                    cr.set_source_rgb(*(T["text"] if s["state"] != "pending" else T["dim"])); cr.move_to(pad + 16, y + 30); PangoCairo.show_layout(cr, lay)
                    y += ch + 8
            return y

        def section_profiles(self, cr, now, W, y, pad):
            profs, cw = self.snap["profiles"], W - 2 * pad
            if not profs:
                return y
            with self.rev(cr):
                y = self.title(cr, "PROFILS HERMES", y, pad, W)
            for p in profs[:6]:
                col = tuple(p["color"]) if p["color"] else T["mochi"]
                opened = self.profile_open == p["name"]
                with self.rev(cr):
                    h = 40 + (46 if opened else 0)
                    rect = (pad, y - self.hy, cw, 38)
                    hv = self.hvv(rect, 1.0 if self.hot == rect else 0.0)
                    cr.set_source_rgba(1, 1, 1, 0.04 + 0.05 * hv); rr(cr, pad, y, cw, h - 2, 13); cr.fill()
                    self.hit(pad, y, cw, 38, lambda n=p["name"]: setattr(self, "profile_open", None if self.profile_open == n else n))
                    self.mochi(cr, pad + 22, y + 19, 24, "work" if p["state"] == "working" else "idle", now, tint=col)
                    text(cr, p["name"], pad + 44, y + 5, 11, T["text"], True, w=110)
                    dot = {"working": T["accent"], "open": T["ok"], "idle": T["dim"]}[p["state"]]
                    cr.set_source_rgba(*dot, 0.55 + 0.45 * math.sin(now * 5) if p["state"] == "working" else 1.0); cr.arc(pad + 44 + 4, y + 28, 3, 0, TAU); cr.fill()
                    label = {"working": "travaille", "open": "ouvert", "idle": "inactif"}[p["state"]]
                    text(cr, f"{label}" + (f" · {p['detail']}" if p["detail"] else ""), pad + 54, y + 22, 9, dot if p["state"] != "idle" else T["dim"], w=cw - 54 - 112)
                    self.chip(cr, W - pad - 104, y + 7, "Demander", col, lambda n=p["name"]: self.open_prompt(f"@{n} "), w=92, h=24, now=now)
                    if opened:
                        t = p["tasks"]
                        line = " · ".join(f"{n} {k}" for k, n in t.items()) if t else "aucune tâche Kanban assignée"
                        text(cr, "Kanban : " + line, pad + 14, y + 44, 9.5, T["dim"], w=cw - 28)
                        text(cr, ("En cours : " + p["current"]) if p["current"] else "Rien en cours côté Kanban", pad + 14, y + 60, 9.5, T["text"] if p["current"] else T["dim"], w=cw - 28)
                    y += h + 4
            return y

        def send_screenshot(self):
            p = core.kdrive.last_screenshot()
            core.kdrive.upload(p, "Captures") if p else core.toast("Aucune capture trouvée", "warn")

        def body_system(self, cr, now, W, y, pad):
            snap, s, cw = self.snap, self.snap["sys"], W - 2 * pad
            w = snap["weather"]
            with self.rev(cr):
                y = self.title(cr, "MÉTÉO", y, pad, W)
                if w.get("ok"):
                    cr.set_source_rgb(*T["surface"]); rr(cr, pad, y, cw, 76, 14); cr.fill()
                    weather_icon(cr, w["icon"], pad + 44, y + 40, 54, now, w["night"])
                    text(cr, f"{w['temp']:.0f}°", pad + 88, y + 8, 26, T["text"], True)
                    text(cr, f"{w['label']} · {w['city']}", pad + 88, y + 44, 10.5, T["dim"], w=cw - 100)
                    text(cr, f"min {w['tmin']:.0f}° · max {w['tmax']:.0f}° · pluie {w['rain']}%", pad + 88, y + 59, 9.5, T["dim"], w=cw - 100)
                    y += 86
                else:
                    text(cr, w.get("error") or ("Renseigne ta ville : [weather] city = \"…\" dans la config." if not cfg["weather"].get("city") else "chargement…"), pad, y + 2, 10, T["dim"], w=cw, lines=2); y += 34
            with self.rev(cr):
                y = self.title(cr, "SYSTÈME", y, pad, W)
                rows = []
                if "bat" in s:
                    low = s["bat"] <= int(cfg["health"]["battery_warn"])
                    rows.append(("Batterie", s["bat"], f"{s['bat']}%" + (" ⚡" if s.get("bat_state") in ("Charging", "Full") else ""), T["danger"] if low else T["ok"]))
                if "ram" in s:
                    rows.append(("Mémoire", s["ram"], f"{s['ram']}%", T["warn"] if s["ram"] > 85 else T["accent"]))
                if "temp" in s:
                    rows.append(("Température", min(100, s["temp"]), f"{s['temp']:.0f} °C", T["danger"] if s["temp"] > 85 else T["accent"]))
                for lab, pct, val, c in rows:
                    text(cr, lab, pad, y + 1, 10.5, T["text"], w=100)
                    self.bar(cr, pad + 110, y + 7, cw - 110 - 64, 6, self.anim.setdefault("b" + lab, 0.0) + 0, c)
                    self.anim["b" + lab] += (pct / 100 - self.anim["b" + lab]) * 0.15
                    text(cr, val, W - pad - 60, y + 1, 10.5, T["text"], True, w=60, align="r")
                    y += 26
                if not rows:
                    text(cr, "Pas de capteurs détectés.", pad, y + 2, 10.5, T["dim"]); y += 26
                if cfg["network"].get("enabled"):
                    x = pad
                    for lab, ok_, detail in (("Wi-Fi", bool(s.get("wifi")), s.get("wifi") or "déconnecté"),
                                             ("Tailscale", bool(s.get("tailscale")), "connecté" if s.get("tailscale") else ("éteint" if s.get("tailscale") is False else "absent"))):
                        x += self.chip(cr, x, y, f"{lab} · {short(detail, 18)}", T["ok"] if ok_ else T["dim"], lambda: None, active=ok_) + 8
                    y += 34
            with self.rev(cr):
                y = self.title(cr, "DERNIÈRES DÉCISIONS", y, pad, W)
                if not snap["audit"]:
                    text(cr, "Aucune demande d'approbation pour l'instant.", pad, y + 2, 10, T["dim"], w=cw); y += 24
                for a in snap["audit"][:5]:
                    good = a["decision"] in ("allow", "always")
                    text(cr, "✓" if good else "✗" if a["decision"] == "deny" else "?", pad, y + 2, 11, T["ok"] if good else T["danger"], True)
                    text(cr, dt.datetime.fromtimestamp(a["ts"]).strftime("%H:%M"), pad + 18, y + 3, 9, T["dim"])
                    text(cr, f"{a['tool']} · {a['summary']}", pad + 56, y + 3, 10, T["text"], w=cw - 56 - 40, mono=True)
                    sc = a["score"]
                    text(cr, str(sc), W - pad - 30, y + 3, 10, T["danger"] if sc >= 70 else T["warn"] if sc >= 40 else T["dim"], True, w=30, align="r")
                    y += 22
                y += 4
            return y

    import signal
    win = Island()
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, lambda: Gtk.main_quit() or False)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, lambda: Gtk.main_quit() or False)
    try:
        core.set_inhibit = Inhibitor().set
    except Exception as e:
        print("[coucou] anti-veille indisponible :", e, file=sys.stderr)
    if cfg["lock"].get("enabled", True):
        try:
            win.lockwatch = LockWatcher(core)
        except Exception as e:
            print("[coucou] verrou-parachute indisponible :", e, file=sys.stderr)
    core.start_background()
    Gtk.main()

# ════════════════════════════════════════════════════════════════════════════
#  6. PLUGIN HERMES (écrit par `install-hermes`, tourne DANS Hermes)
# ════════════════════════════════════════════════════════════════════════════
HERMES_PLUGIN_YAML = '''name: coucou-fedora
version: "1.0"
description: Relaie l'activité de Hermes vers l'île coucou-fedora et y affiche les demandes d'approbation.
'''

HERMES_PLUGIN_INIT = r'''"""Plugin Hermes → coucou-fedora (généré). Ne bloque jamais l'agent si l'île est éteinte."""
import json, os, socket, threading

SOCK = os.environ.get("COUCOU_SOCK") or os.path.join(
    os.environ.get("XDG_RUNTIME_DIR") or "/tmp/coucou-fedora-%d" % os.getuid(), "coucou-fedora.sock")
WAIT = float(os.environ.get("COUCOU_APPROVAL_WAIT", "110"))


def _send(msg, wait=False, timeout=2.0):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(SOCK)
        s.sendall((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        if not wait:
            return None
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
        return json.loads(buf.decode("utf-8")) if buf.strip() else None
    finally:
        s.close()


def _profile():
    h = os.environ.get("HERMES_HOME", "")
    return os.path.basename(h.rstrip("/")) if "/profiles/" in h else "default"


def _fire(event, **fields):
    def run():
        try:
            _send({"op": "event", "agent": "hermes", "payload": dict(fields, hook_event_name=event, profile=_profile())})
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def _sid(kw):
    return kw.get("session_id") or kw.get("task_id") or "hermes"


def _on_session_start(**kw):
    _fire("SessionStart", session_id=_sid(kw), model=kw.get("model", ""))


def _on_pre_tool(tool_name="", args=None, **kw):
    _fire("PreToolUse", session_id=_sid(kw), tool_name=tool_name, tool_input=args if isinstance(args, dict) else {})


def _on_post_tool(tool_name="", args=None, **kw):
    _fire("PostToolUse", session_id=_sid(kw), tool_name=tool_name, tool_input=args if isinstance(args, dict) else {})


def _on_llm_done(assistant_response="", **kw):
    _fire("AssistantText", session_id=_sid(kw), text=(assistant_response or "")[:300])


def _on_session_end(**kw):
    _fire("Stop", session_id=_sid(kw))


def _present(request):
    """Transport d'approbation : affiche la demande sur l'île et renvoie la décision."""
    command = getattr(request, "command", None) or getattr(request, "display_text", None) or str(request)
    desc = getattr(request, "description", "") or ""
    try:
        reply = _send({"op": "approve", "agent": "hermes", "timeout": WAIT,
                       "payload": {"profile": _profile(), "session_id": str(getattr(request, "session_key", "") or "hermes"), "tool_name": "terminal",
                                   "tool_input": {"command": str(command)}, "description": str(desc)}},
                      wait=True, timeout=WAIT + 5)
    except (OSError, ValueError):
        reply = None
    decision = (reply or {}).get("decision")
    if decision == "allow":
        return request.respond("once")
    if decision == "always":
        return request.respond("session")
    if decision == "deny":
        return request.respond("deny")
    # île éteinte / pas de réponse / « ask » : on lève → Hermes applique transport_fallback
    raise RuntimeError("île coucou-fedora : pas de décision (%s)" % (decision or "injoignable"))


def register(ctx):
    for name, fn in (("on_session_start", _on_session_start), ("pre_tool_call", _on_pre_tool), ("post_tool_call", _on_post_tool),
                     ("post_llm_call", _on_llm_done), ("on_session_end", _on_session_end)):
        try:
            ctx.register_hook(name, fn)
        except Exception:
            pass
    if hasattr(ctx, "register_approval_transport"):
        ctx.register_approval_transport("coucou-fedora", _present)
'''


# ════════════════════════════════════════════════════════════════════════════
#  6. COMMANDES
# ════════════════════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════════════════════
#  7. COMMANDES
# ════════════════════════════════════════════════════════════════════════════
def self_cmd() -> str:
    return f'"{pathlib.Path(__file__).resolve()}"'


def cmd_run(args) -> None:
    cfg = load_config()
    core = Core(cfg)
    start_server(core)
    load_user_plugins(core, cfg)
    print(f"[coucou] île prête · socket {SOCK}")
    try:
        run_gui(cfg, core)
    except (ImportError, ValueError) as e:
        raise SystemExit(f"GTK3 / PyGObject introuvable ({e}).\nsudo dnf install python3-gobject python3-cairo gtk3")
    finally:
        core.ducker.restore()
        if core.focus:
            core.stop_focus()
        core.save_stats()
        try:
            SOCK.unlink()
        except OSError:
            pass


def cmd_hook(args) -> None:
    """Appelé par Claude Code : lit le JSON du hook sur stdin, parle à l'île, répond au format Claude Code."""
    cfg = load_config()
    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    wait = args.wait and payload.get("hook_event_name") == "PreToolUse"
    if not wait:
        send({"op": "event", "agent": args.agent, "payload": payload}, timeout=1.5)
        return
    timeout = float(cfg["approvals"]["timeout_seconds"])
    reply = send({"op": "approve", "agent": args.agent, "payload": payload, "timeout": timeout}, wait=True, timeout=timeout + 5)
    decision = (reply or {}).get("decision")
    if decision in ("allow", "always", "deny"):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny" if decision == "deny" else "allow",
                                                 "permissionDecisionReason": reply.get("reason", "")}}, ensure_ascii=False))

def _backup(p: pathlib.Path) -> pathlib.Path | None:
    if p.exists():
        b = p.with_name(p.name + f".bak-{dt.datetime.now():%Y%m%d-%H%M%S-%f}")
        shutil.copy2(p, b)
        return b
    return None


def cmd_install_claude(args) -> None:
    cfg = load_config()
    path = pathlib.Path(args.settings).expanduser()
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    hooks = data.setdefault("hooks", {})
    marker = " hook --agent claude"
    timeout = int(cfg["approvals"]["timeout_seconds"]) + 15
    plan = [("SessionStart", None, False), ("UserPromptSubmit", None, False), ("PreToolUse", "|".join(cfg["approvals"]["ask_tools"]), True),
            ("PostToolUse", None, False), ("Notification", None, False), ("Stop", None, False), ("SessionEnd", None, False)]
    for ev, matcher, wait in plan:
        hooks[ev] = [e for e in hooks.get(ev, []) if not any(marker in h.get("command", "") for h in e.get("hooks", []))]
        if not args.remove:
            entry: dict = {"hooks": [{"type": "command", "command": self_cmd() + marker + (" --wait" if wait else ""), "timeout": timeout if wait else 5}]}
            if matcher:
                entry["matcher"] = matcher
            hooks[ev].append(entry)
        if not hooks[ev]:
            del hooks[ev]
    if not hooks:
        del data["hooks"]
    b = _backup(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(("Hooks retirés de " if args.remove else "Hooks installés dans ") + str(path) + (f"  (sauvegarde : {b})" if b else ""))
    if not args.remove:
        print("Redémarre Claude Code pour qu'il relise ses réglages.")


def cmd_install_hermes(args) -> None:
    home = pathlib.Path(args.home).expanduser()
    d = home / "plugins" / "coucou-fedora"
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.yaml").write_text(HERMES_PLUGIN_YAML, encoding="utf-8")
    (d / "__init__.py").write_text(HERMES_PLUGIN_INIT, encoding="utf-8")
    print(f"Plugin écrit dans {d}\n\nIl reste 2 étapes côté Hermes :\n  1) hermes plugins enable coucou-fedora\n"
          f"  2) dans {home}/config.yaml, ajoute (ou fusionne) :\n\nsecurity:\n  approval:\n    transport: coucou-fedora\n    transport_fallback: builtin\n\n"
          "Puis redémarre Hermes. Avec transport_fallback: builtin, si l'île est éteinte Hermes te demande normalement dans son terminal.")


def cmd_install_autostart(args) -> None:
    p = pathlib.Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "autostart" / "coucou-fedora.desktop"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"[Desktop Entry]\nType=Application\nName=Coucou Fedora\nExec={self_cmd()}\nX-GNOME-Autostart-enabled=true\nNoDisplay=true\n", encoding="utf-8")
    print("Démarrage automatique installé :", p)


def cmd_init_config(args) -> None:
    p = CONF_DIR / "config.toml"
    if p.exists() and not args.force:
        raise SystemExit(f"{p} existe déjà (utilise --force pour l'écraser).")
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    (CONF_DIR / "plugins").mkdir(exist_ok=True)
    p.write_text(DEFAULT_TOML.lstrip(), encoding="utf-8")
    print("Configuration écrite :", p)


def cmd_ask(args) -> None:
    prev = [0]

    def cb(t: str) -> None:
        sys.stdout.write(t[prev[0]:]); sys.stdout.flush(); prev[0] = len(t)
    try:
        Ollama(load_config()).ask(" ".join(args.prompt), on_text=cb)
        print()
    except Exception as e:
        raise SystemExit(f"Ollama injoignable : {e}")


def cmd_simple(op):
    def run_(args) -> None:
        r = send({"op": op})
        if r is None:
            raise SystemExit("L'île n'est pas lancée.")
        if op == "status":
            print(json.dumps(r, indent=2, ensure_ascii=False))
    return run_


def cmd_remind(args) -> None:
    try:
        sec = parse_dur(args.duration)
    except ValueError as e:
        raise SystemExit(str(e))
    if send({"op": "timer", "seconds": sec, "label": " ".join(args.label) or f"Minuteur {args.duration}"}) is None:
        raise SystemExit("L'île n'est pas lancée.")
    print(f"Minuteur de {fmt_time(sec)} lancé.")


def cmd_focus(args) -> None:
    if send({"op": "focus", "minutes": args.minutes}) is None:
        raise SystemExit("L'île n'est pas lancée.")
    print(f"Focus de {args.minutes} min lancé.")


def cmd_todo(args) -> None:
    if send({"op": "magic", "text": "todo " + " ".join(args.text)}) is None:
        raise SystemExit("L'île n'est pas lancée.")


def cmd_calm(args) -> None:
    if send({"op": "calm", "kind": args.kind}) is None:
        raise SystemExit("L'île n'est pas lancée.")


def cmd_watch(args) -> None:
    """coucou-fedora watch <commande…> : lance la commande et prévient l'île (son + confettis) à la fin."""
    cmd = args.cmd[1:] if args.cmd and args.cmd[0] == "--" else args.cmd
    if not cmd:
        raise SystemExit("Usage : coucou-fedora watch <commande…>   ex. : coucou-fedora watch make -j8")
    jid = uuid.uuid4().hex[:8]
    send({"op": "job_start", "id": jid, "label": " ".join(cmd)}, timeout=1.5)
    try:
        code = subprocess.call(cmd)
    except FileNotFoundError:
        print(f"commande introuvable : {cmd[0]}", file=sys.stderr)
        code = 127
    except KeyboardInterrupt:
        code = 130
    send({"op": "job_end", "id": jid, "code": code}, timeout=1.5)
    sys.exit(code)


def cmd_bonjour(args) -> None:
    if send({"op": "bonjour", "speak": True if args.speak else None}) is None:
        raise SystemExit("L'île n'est pas lancée.")
    print("Résumé « Bonjour ! » lancé.")


def cmd_mic(args) -> None:
    if send({"op": "mic"}) is None:
        raise SystemExit("L'île n'est pas lancée.")


def cmd_prompt(args) -> None:
    """Barre magique : petite fenêtre de saisie. Lie `coucou-fedora prompt` à un raccourci clavier GNOME."""
    try:
        import gi
        gi.require_version("Gtk", "3.0"); gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk
    except (ImportError, ValueError) as e:
        raise SystemExit(f"GTK3 introuvable ({e})")
    css = Gtk.CssProvider()
    css.load_from_data(b"""window { background: transparent; }
        .card { background: #0b0c10; border-radius: 20px; border: 1px solid rgba(255,255,255,0.14); padding: 6px; }
        entry { background: transparent; color: #eef1f6; font-size: 18px; border: none; box-shadow: none; padding: 12px 16px; caret-color: #7aa2ff; }
        .hint { color: #8a93a6; font-size: 11px; padding: 0 18px 12px 18px; }""")
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    win = Gtk.Window(title="Coucou")
    win.set_decorated(False); win.set_default_size(660, 84); win.set_position(Gtk.WindowPosition.CENTER); win.set_keep_above(True); win.set_app_paintable(True)
    vis = win.get_screen().get_rgba_visual()
    if vis:
        win.set_visual(vis)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
    box.get_style_context().add_class("card")
    entry = Gtk.Entry()
    entry.set_placeholder_text("Demande à Qwen, ou : @profil question · todo … · rappel 10m … · = 12*7 · bonjour · focus 25")
    hint = Gtk.Label(label="Entrée : envoyer   ·   Échap : fermer", xalign=0)
    hint.get_style_context().add_class("hint")
    box.pack_start(entry, False, False, 0)
    box.pack_start(hint, False, False, 0)
    win.add(box)

    def submit(_e):
        t = entry.get_text().strip()
        if t and send({"op": "magic", "text": t}) is None:
            print("L'île n'est pas lancée.", file=sys.stderr)
        Gtk.main_quit()
    entry.connect("activate", submit)
    win.connect("key-press-event", lambda w, e: Gtk.main_quit() if e.keyval == Gdk.KEY_Escape else False)
    win.connect("focus-out-event", lambda *a: Gtk.main_quit())
    win.connect("destroy", lambda *a: Gtk.main_quit())
    if getattr(args, "prefill", ""):
        entry.set_text(args.prefill); entry.set_position(-1)
    win.show_all(); win.present(); entry.grab_focus()
    Gtk.main()


def cmd_demo(args) -> None:
    if send({"op": "status"}) is None:
        raise SystemExit("Lance d'abord l'île (`coucou-fedora`) dans un autre terminal.")
    base = {"session_id": "demo-1", "cwd": str(HOME)}
    send({"op": "event", "agent": "hermes", "payload": dict(base, hook_event_name="UserPromptSubmit", prompt="Ajoute un test pour le parseur")})
    send({"op": "magic", "text": "todo Démo : tester Coucou"})
    send({"op": "job_start", "id": "demo-job", "label": "make -j8"})
    time.sleep(3)
    send({"op": "job_end", "id": "demo-job", "code": 0})
    time.sleep(2)
    for cmd in ("npm test", "sudo dnf remove firefox"):
        threading.Thread(target=send, kwargs=dict(msg={"op": "approve", "agent": "hermes", "timeout": 25,
                         "payload": dict(base, tool_name="terminal", tool_input={"command": cmd})}, wait=True, timeout=40), daemon=True).start()
        time.sleep(0.4)
    print("Démo envoyée : une commande surveillée, une tâche, puis deux demandes (une banale, une risquée) pendant 25 s.")
    time.sleep(27)


def cmd_doctor(args) -> None:
    cfg = load_config()
    ok = lambda b: "✓" if b else "✗"
    print(f"coucou-fedora {VERSION} · session {os.environ.get('XDG_SESSION_TYPE', '?')} · {os.environ.get('XDG_CURRENT_DESKTOP', '?')}")
    print(f" {ok(shutil.which('Xwayland'))} Xwayland")
    gtk = True
    try:
        import gi
        gi.require_version("Gtk", "3.0"); gi.require_version("PangoCairo", "1.0"); gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import Gtk  # noqa: F401
        import cairo  # noqa: F401
    except Exception as e:
        gtk = False
        print("   détail :", short(e, 100))
    print(f" {ok(gtk)} GTK3 + PyGObject + Cairo + GdkPixbuf")
    for tool, hint in (("pactl", "volume / ducking / détection d'appel"), ("pw-play", "sons"), ("notify-send", "notifications"), ("gsettings", "Ne pas déranger, mode sombre"),
                       ("nmcli", "Wi-Fi"), ("tailscale", "Tailscale (optionnel)"), ("xdg-open", "ouvrir dossiers"), ("loginctl", "action Verrouiller")):
        print(f" {ok(shutil.which(tool))} {tool}  ({hint})")
    dep = KDrive(cfg, Core(cfg))
    print(f" {ok(dep.available())} dépôt kDrive : {cfg['depot']['folder']}")
    if gtk:
        try:
            m = Mpris(cfg).poll()
            print(f" {ok(bool(m))} lecteur MPRIS : {m.get('name', 'aucun')}  ({m.get('status', '')} {m.get('title', '')})")
        except Exception as e:
            print(" ✗ D-Bus :", short(e, 80))
    ins = Ducker(dict(cfg, ducking=dict(cfg["ducking"], match=["*"]))).inputs() if shutil.which("pactl") else []
    print(" Applis audio actives ([ducking].match) :", ", ".join(sorted({n for _, _, n in ins})) or "aucune")
    o, why = Ollama(cfg).ping()
    print(f" {ok(o)} Ollama {cfg['ollama']['url']}  ({why})")
    kb = Kanban(cfg).read()
    print(f" {ok(kb['ok'])} Kanban Hermes : " + (f"{kb['total']} tâche(s) {kb['counts']}" if kb["ok"] else kb["error"]))
    print(f" {ok((HOME / '.hermes/plugins/coucou-fedora/__init__.py').exists())} plugin Hermes installé (approbations)")
    vi = {"tts": Speaker(cfg).engines(), "stt": Voice(cfg).engines()}
    print(f" {ok(vi['tts'])} voix (lecture du résumé) : {', '.join(vi['tts']) or 'aucune → sudo dnf install espeak-ng'}")
    print(f" {ok(vi['stt'])} transcription (micro) : {', '.join(vi['stt']) or 'aucun moteur → Whisper Wyoming, faster-whisper ou whisper.cpp'}")
    print(f" {ok(shutil.which('pw-record') or shutil.which('parecord'))} enregistrement micro (pw-record)")
    tb = Thunderbird(cfg)
    print(f" {ok(tb.info())} Thunderbird : {tb.info() or 'profil introuvable'}")
    print(f" {ok(Calendars(cfg).count())} agendas Google : {Calendars(cfg).count()} configuré(s)")
    for f in cfg["bonjour"].get("feeds", []):
        try:
            n = len(fetch_feed(f["url"], 3)); print(f" {ok(n)} flux {f['category']} : {f['url']} ({n} article(s))")
        except Exception as e:
            print(f" ✗ flux {f['category']} : {f['url']} ({short(e, 50)})")
    print(f" {ok(bool(cfg['weather'].get('city')))} météo : ville = « {cfg['weather'].get('city') or 'non renseignée'} »")
    print(f" {ok(send({'op': 'status'}) is not None)} île en cours d'exécution")


def main() -> None:
    ap = argparse.ArgumentParser(prog=APP, description="Île de contrôle d'agents IA pour Fedora/GNOME/Wayland")
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("run").set_defaults(fn=cmd_run)
    h = sub.add_parser("hook"); h.add_argument("--agent", default="claude"); h.add_argument("--wait", action="store_true"); h.set_defaults(fn=cmd_hook)
    c = sub.add_parser("install-claude"); c.add_argument("--remove", action="store_true"); c.add_argument("--settings", default="~/.claude/settings.json"); c.set_defaults(fn=cmd_install_claude)
    hh = sub.add_parser("install-hermes"); hh.add_argument("--home", default=os.environ.get("HERMES_HOME", "~/.hermes")); hh.set_defaults(fn=cmd_install_hermes)
    sub.add_parser("install-autostart").set_defaults(fn=cmd_install_autostart)
    ic = sub.add_parser("init-config"); ic.add_argument("--force", action="store_true"); ic.set_defaults(fn=cmd_init_config)
    a = sub.add_parser("ask"); a.add_argument("prompt", nargs="+"); a.set_defaults(fn=cmd_ask)
    r = sub.add_parser("remind"); r.add_argument("duration"); r.add_argument("label", nargs="*"); r.set_defaults(fn=cmd_remind)
    f = sub.add_parser("focus"); f.add_argument("minutes", nargs="?", type=float, default=25); f.set_defaults(fn=cmd_focus)
    t = sub.add_parser("todo"); t.add_argument("text", nargs="+"); t.set_defaults(fn=cmd_todo)
    cm = sub.add_parser("calm"); cm.add_argument("kind", nargs="?", choices=["breath", "eye"], default="breath"); cm.set_defaults(fn=cmd_calm)
    w = sub.add_parser("watch"); w.add_argument("cmd", nargs=argparse.REMAINDER); w.set_defaults(fn=cmd_watch)
    pr = sub.add_parser("prompt"); pr.add_argument("--prefill", default=""); pr.set_defaults(fn=cmd_prompt)
    bj = sub.add_parser("bonjour"); bj.add_argument("--speak", action="store_true"); bj.set_defaults(fn=cmd_bonjour)
    sub.add_parser("mic").set_defaults(fn=cmd_mic)
    for op in ("toggle", "quit", "status"):
        sub.add_parser(op).set_defaults(fn=cmd_simple(op))
    sub.add_parser("demo").set_defaults(fn=cmd_demo)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    args = ap.parse_args()
    (args.fn if args.cmd else cmd_run)(args)


if __name__ == "__main__":
    main()

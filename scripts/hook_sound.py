#!/usr/bin/env python3
"""Звуковое оповещение для хуков Claude Code.

Идея: хук Stop срабатывает после КАЖДОГО хода, а при работе под /goal ходов много. Скрипт ждёт паузу
и играет сигнал только если за это время новых ходов не было, то есть работа действительно закончилась.

Подключение (settings.json, см. settings.example.json):
  Stop                -> скрипт запоминает метку и запускает отложенную проверку в фоне, сам выходит сразу
  UserPromptSubmit    -> обновляет метку: новый запрос отменяет ожидающий сигнал
  Notification        -> сразу играет сигнал «агент ждёт вас» (запрос разрешения и т.п.)

Проверка без звука: python hook_sound.py --self-test
Сухой запуск с вашими данными: echo {"hook_event_name":"Stop","session_id":"x"} | python hook_sound.py --dry-run
Переменные: HOOK_SOUND_DELAY (секунды ожидания, по умолчанию 20), HOOK_SOUND_STATE_DIR (папка меток).
Скрипт всегда завершается с кодом 0 и не блокирует Claude Code.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEFAULT_DELAY = 20.0


def state_dir() -> Path:
    base = os.environ.get("HOOK_SOUND_STATE_DIR")
    path = Path(base) if base else Path(tempfile.gettempdir()) / "claude_hook_sound"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _token_file(session: str) -> Path:
    safe = "".join(c for c in session if c.isalnum() or c in "-_") or "default"
    return state_dir() / f"{safe}.token"


def touch_token(session: str) -> str:
    """Записывает новую метку сессии и возвращает её."""
    token = str(time.time_ns())
    _token_file(session).write_text(token, encoding="utf-8")
    return token


def is_latest(session: str, token: str) -> bool:
    try:
        return _token_file(session).read_text(encoding="utf-8").strip() == token
    except OSError:
        return False


def wait_and_maybe_play(session: str, token: str, delay: float, dry_run: bool = False) -> bool:
    """Ждёт delay секунд; если метка не обновилась, играет сигнал «готово». Возвращает True, если сигнал сыгран."""
    time.sleep(delay)
    if not is_latest(session, token):
        if dry_run:
            print("SKIP: после этого хода были новые события, работа продолжается")
        return False
    play("done", dry_run)
    return True


def play(kind: str, dry_run: bool = False) -> None:
    """kind: done (работа закончена) или attention (агент ждёт вас)."""
    if dry_run:
        print(f"PLAY: {kind}")
        return
    try:
        if sys.platform == "win32":
            import winsound

            notes = [(880, 140), (1320, 220)] if kind == "done" else [(660, 120), (660, 120), (990, 200)]
            for freq, ms in notes:
                winsound.Beep(freq, ms)
        elif sys.platform == "darwin":
            subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff" if kind == "done" else "/System/Library/Sounds/Ping.aiff"],
                           check=False)
        else:
            sample = "/usr/share/sounds/freedesktop/stereo/complete.oga" if kind == "done" else "/usr/share/sounds/freedesktop/stereo/bell.oga"
            if Path(sample).is_file():
                subprocess.run(["paplay", sample], check=False)
            else:
                sys.stderr.write("\a")
    except Exception:
        pass  # звук необязателен; хук не должен ломать работу


def _spawn_waiter(session: str, token: str, delay: float) -> None:
    cmd = [sys.executable, str(Path(__file__).resolve()), "--wait", token, "--session", session, "--delay", str(delay)]
    kwargs: dict = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def handle_event(event: str, session: str, delay: float, dry_run: bool) -> None:
    if event == "Stop":
        token = touch_token(session)
        if dry_run:
            wait_and_maybe_play(session, token, 0.0, dry_run=True)  # в сухом запуске новых ходов нет, сигнал сыграет
        else:
            _spawn_waiter(session, token, delay)
    elif event == "UserPromptSubmit":
        touch_token(session)
    elif event == "Notification":
        play("attention", dry_run)


def self_test() -> int:
    """Два хода подряд: сигнал должен сыграть только после последнего."""
    os.environ["HOOK_SOUND_STATE_DIR"] = tempfile.mkdtemp(prefix="hook_sound_test_")
    session = "selftest"
    first = touch_token(session)
    second = touch_token(session)  # второй ход начался до истечения ожидания первого
    r1 = wait_and_maybe_play(session, first, 0.05, dry_run=True)
    r2 = wait_and_maybe_play(session, second, 0.05, dry_run=True)
    ok = (r1, r2) == (False, True)
    print("self-test:", "OK" if ok else f"ОШИБКА {(r1, r2)}")
    return 0 if ok else 1


def main() -> int:
    p = argparse.ArgumentParser(description="Звуковой хук Claude Code")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="не играть звук, печатать решение")
    p.add_argument("--event", default=None, help="имя события, если его нет в JSON на стандартном вводе")
    p.add_argument("--wait", default=None, help="служебный режим: отложенная проверка метки")
    p.add_argument("--session", default="default")
    p.add_argument("--delay", type=float, default=float(os.environ.get("HOOK_SOUND_DELAY", DEFAULT_DELAY)))
    args = p.parse_args()

    if args.self_test:
        return self_test()
    if args.wait:
        wait_and_maybe_play(args.session, args.wait, args.delay)
        return 0

    payload: dict = {}
    if not sys.stdin.isatty():
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except json.JSONDecodeError:
            payload = {}
    event = args.event or payload.get("hook_event_name", "Stop")
    session = str(payload.get("session_id", args.session))
    handle_event(event, session, args.delay, args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # хук не должен падать и блокировать работу
        sys.exit(0)

# Examples — strong random sources for security values, plus
# weak random in non-security contexts (which must NOT trip).
import os
import random
import secrets


def make_session_token():
    return secrets.token_urlsafe(32)


def make_password():
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    return "".join(secrets.choice(alphabet) for _ in range(16))


def make_api_key():
    return secrets.token_hex(32)


def make_nonce():
    return os.urandom(16)


def make_csrf_token():
    return secrets.token_urlsafe(24)


def make_password_reset_code():
    return secrets.randbelow(900000) + 100000


def random_iv_for_aes():
    return os.urandom(16)


def via_systemrandom_token():
    rng = random.SystemRandom()
    return rng.randint(0, 2 ** 64)


# === Non-security uses of random — these must NOT trip ===
def shuffle_deck(deck):
    random.shuffle(deck)
    return deck


def random_color_for_chart():
    return (random.random(), random.random(), random.random())


def pick_demo_word(words):
    return random.choice(words)


def monte_carlo_pi(n):
    inside = 0
    for _ in range(n):
        x, y = random.random(), random.random()
        if x * x + y * y <= 1.0:
            inside += 1
    return 4 * inside / n


# Audited legacy path with explicit suppression.
def legacy_demo_token():
    # Only used in seeded reproducibility tests, never on the wire.
    return random.randint(0, 99)  # weak-random-ok — fixture-only

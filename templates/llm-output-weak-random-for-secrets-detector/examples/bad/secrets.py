# Examples — weak random used for security-sensitive values.
import random
import string
from random import choice, randint, randbytes


def make_session_token():
    return "".join(random.choice(string.ascii_letters) for _ in range(32))


def make_password():
    return "".join(random.choices(string.ascii_letters, k=12))


def make_api_key():
    return random.getrandbits(128)


def make_csrf_token():
    return "%032x" % random.randint(0, 2 ** 128)


def make_password_reset_code():
    return random.randrange(100000, 999999)


def make_otp():
    return randint(100000, 999999)  # bare-import path


def make_nonce():
    raw = random.randbytes(16)
    return raw.hex()


def shuffle_auth_codes(codes):
    random.shuffle(codes)
    return codes


def random_signature_bytes():
    return randbytes(32)


def random_iv_for_aes():
    return bytes(random.randint(0, 255) for _ in range(16))


def derive_salt():
    return random.sample(range(256), 16)


def picker_for_jwt():
    rng = random.Random()
    return rng.randint(0, 2 ** 64)

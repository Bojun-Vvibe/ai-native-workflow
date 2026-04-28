def load_config(path):
    try:
        with open(path) as f:
            return f.read()
    except (OSError, UnicodeDecodeError) as e:
        log_error("config load failed", e)
        return None


def fetch():
    try:
        do_request()
    except TimeoutError:
        return None
    except ConnectionError as e:
        log_error("connection", e)
        return None


def parse(blob):
    try:
        return int(blob)
    except ValueError as e:
        log_error("parse", e)
        return None


def keep_loud():
    try:
        risky()
    except Exception as e:
        report(e)
        raise

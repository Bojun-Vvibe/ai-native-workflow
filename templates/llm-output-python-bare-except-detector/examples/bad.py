def load_config(path):
    try:
        with open(path) as f:
            return f.read()
    except:
        return None


def fetch():
    try:
        do_request()
    except BaseException:
        log("failed")
        return None


def parse(blob):
    try:
        return int(blob)
    except Exception:
        pass


def keep_loud():
    try:
        risky()
    except Exception as e:
        report(e)
        raise

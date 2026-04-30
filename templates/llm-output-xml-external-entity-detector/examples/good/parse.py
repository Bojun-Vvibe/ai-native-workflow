# Examples — safe XML parsing.
import defusedxml.ElementTree as ET
import defusedxml.minidom as minidom
import defusedxml.lxml
import lxml.etree


def parse_config(path):
    return ET.parse(path)


def parse_payload(blob):
    return ET.fromstring(blob)


def parse_minidom(path):
    return minidom.parse(path)


def parse_with_defused_lxml(path):
    return defusedxml.lxml.parse(path)


def parse_lxml_hardened(path):
    parser = lxml.etree.XMLParser(
        resolve_entities=False, no_network=True, dtd_validation=False
    )
    return lxml.etree.parse(path, parser)


# Comments mentioning ET.parse(x) and lxml.etree.parse(y) should not trip.
TEMPLATE = "Use ET.parse(path) only via defusedxml."


# A line below has the suppression marker for an audited usage.
def legacy_loader(path):
    import xml.etree.ElementTree as RawET
    return RawET.parse(path)  # xxe-ok — internal-only callers, audited 2026-Q1

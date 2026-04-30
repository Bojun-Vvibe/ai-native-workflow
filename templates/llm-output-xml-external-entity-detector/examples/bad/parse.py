# Examples — bad XML parsing surfaces.
import xml.etree.ElementTree as ET
from xml.dom import minidom, pulldom
import xml.sax
import xml.parsers.expat
import lxml.etree


def parse_config(path):
    return ET.parse(path)


def parse_string_payload(blob):
    return ET.fromstring(blob)


def stream_parse(path):
    for ev, el in ET.iterparse(path):
        yield ev, el


def parse_with_minidom(path):
    return minidom.parse(path)


def parse_with_pulldom_string(blob):
    return pulldom.parseString(blob)


def parse_with_sax(path, handler):
    return xml.sax.parse(path, handler)


def make_expat():
    return xml.parsers.expat.ParserCreate()


def parse_lxml(path):
    return lxml.etree.parse(path)


def parse_lxml_string(blob):
    return lxml.etree.fromstring(blob)


def parse_lxml_xml(blob):
    return lxml.etree.XML(blob)


def parse_lxml_iter(path):
    return lxml.etree.iterparse(path)


def make_sax_parser():
    return xml.sax.make_parser()


def parse_sax_string(blob, handler):
    return xml.sax.parseString(blob, handler)

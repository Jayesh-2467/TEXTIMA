# coding=utf-8

# use the backport on Python 2 and the standard library on Python 3
import configparser
import re
from collections import defaultdict

from six import string_types


def strtobool(val):
    """
    Based on strtobools from distutils.util.

    Convert a string representation of truth to true (1) or false (0).

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()

    if val in ("y", "yes", "t", "true", "on", "1"):
        return True
    elif val in ("n", "no", "f", "false", "off", "0"):
        return False
    else:
        raise ValueError(f"Invalid truth value {val!r}")


def coerce_value(value):
    """
    Try coercing values to numbers or booleans.
    """
    if not isinstance(value, string_types):
        return value

    if re.match(r"^[0-9]+$", value):
        return int(value)

    if re.match(r"^[.0-9]+$", value):
        try:
            return float(value)
        except ValueError:
            return value

    if re.match(r"^(true|false|yes|no)$", value, flags=re.IGNORECASE):
        return bool(strtobool(value))

    return value


class CoerceInterpolation(configparser.Interpolation):
    """
    Coerce values and strip quotes from strings.
    """

    def before_read(self, parser, section, option, value):
        if not isinstance(value, string_types):
            return value

        coerced_value = coerce_value(value)

        if isinstance(coerced_value, string_types):
            return coerced_value.strip("\"'")

        return coerced_value


class StripQuotesInterpolation(configparser.Interpolation):
    """
    Strip quotes from strings.
    """

    def before_read(self, parser, section, option, value):
        if not isinstance(value, string_types):
            return value

        return value.strip("\"'")


class SimpleConfigParser(configparser.ConfigParser):
    """
    A ConfigParser that:

    - strips quotes from strings ('"value"' becomes 'value')
    - doesn't transform option strings ('OPTION' remains upper-case)
    - doesn't support weird '%' interpolation
    - allows empty values ('value =' is ok)
    - coerces numbers and booleans ('true' → True)
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_no_value", True)
        kwargs.setdefault("interpolation", CoerceInterpolation())

        super(SimpleConfigParser, self).__init__(*args, **kwargs)

    def optionxform(self, option_string):
        return option_string


class Tini(object):
    """
    Easily parse simple ini files.
    """

    def __init__(self, filenames=None, f=None, defaults=None, **kwargs):
        self.defaults = defaultdict(dict, **(defaults if defaults else {}))

        self.parser = SimpleConfigParser(**kwargs)

        if filenames and f:
            raise ValueError("filenames and f may not both be specified")

        if filenames:
            if isinstance(filenames, string_types):
                filenames = [filenames]

            self.parser.read(filenames)
        elif f:
            self.parser.read_file(f)
        else:
            raise ValueError("either filenames or f must be specified")

        # We do this here instead of in SimpleConfigParser because we want to
        # support defaults that pertain to a specific section.
        sections = list(dict(self.parser._sections).keys()) + list(self.defaults.keys())

        self.items = {}

        for section in sections:
            if section in self.parser._sections:
                self.items[section] = dict(
                    self.defaults[section], **dict(self.parser._sections[section])
                )
            else:
                self.items[section] = self.defaults[section]

    def __getattr__(self, name):
        return self.items[name]

#!/usr/bin/env python3
# coding: ascii
# pygame - Python Game Library
# Copyright (C) 2000-2003  Pete Shinners
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Library General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Library General Public License for more details.
#
# You should have received a copy of the GNU Library General Public
# License along with this library; if not, write to the Free
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
# Pete Shinners
# pete@shinners.org
"""sysfont, used in the font module to find system fonts"""

import os
import sys
from os.path import basename, dirname, exists, join, splitext

PY_MAJOR_VERSION = sys.version_info[0]

def geterror():
    return sys.exc_info()[1]

# Python 3
if PY_MAJOR_VERSION >= 3:
    long_ = int
    xrange_ = range
    from io import StringIO
    from io import BytesIO
    unichr_ = chr
    unicode_ = str
    bytes_ = bytes
    raw_input_ = input
    imap_ = map

    # Represent escaped bytes and strings in a portable way.
    #
    # as_bytes: Allow a Python 3.x string to represent a bytes object.
    #   e.g.: as_bytes("a\x01\b") == b"a\x01b" # Python 3.x
    #         as_bytes("a\x01\b") == "a\x01b"  # Python 2.x
    # as_unicode: Allow a Python "r" string to represent a unicode string.
    #   e.g.: as_unicode(r"Bo\u00F6tes") == u"Bo\u00F6tes" # Python 2.x
    #         as_unicode(r"Bo\u00F6tes") == "Bo\u00F6tes"  # Python 3.x
    def as_bytes(string):
        """ '<binary literal>' => b'<binary literal>' """
        return string.encode('latin-1', 'strict')

    def as_unicode(rstring):
        """ r'<Unicode literal>' => '<Unicode literal>' """
        return rstring.encode('ascii', 'strict').decode('unicode_escape',
                                                        'strict')

# Python 2
else:
    long_ = long
    xrange_ = xrange
    from cStringIO import StringIO
    BytesIO = StringIO
    unichr_ = unichr
    unicode_ = unicode
    bytes_ = str
    raw_input_ = raw_input
    from itertools import imap as imap_

    # Represent escaped bytes and strings in a portable way.
    #
    # as_bytes: Allow a Python 3.x string to represent a bytes object.
    #   e.g.: as_bytes("a\x01\b") == b"a\x01b" # Python 3.x
    #         as_bytes("a\x01\b") == "a\x01b"  # Python 2.x
    # as_unicode: Allow a Python "r" string to represent a unicode string.
    #   e.g.: as_unicode(r"Bo\u00F6tes") == u"Bo\u00F6tes" # Python 2.x
    #         as_unicode(r"Bo\u00F6tes") == "Bo\u00F6tes"  # Python 3.x
    def as_bytes(string):
        """ '<binary literal>' => '<binary literal>' """
        return string

    def as_unicode(rstring):
        """ r'<Unicode literal>' => u'<Unicode literal>' """
        return rstring.decode('unicode_escape', 'strict')


def get_BytesIO():
    return BytesIO


def get_StringIO():
    return StringIO


def ord_(o):
    try:
        return ord(o)
    except TypeError:
        return o

if sys.platform == 'win32':
    filesystem_errors = "replace"
elif PY_MAJOR_VERSION >= 3:
    filesystem_errors = "surrogateescape"
else:
    filesystem_errors = "strict"


def filesystem_encode(u):
    fsencoding = sys.getfilesystemencoding()
    if fsencoding.lower() in ['ascii', 'ansi_x3.4-1968'] and sys.platform.startswith('linux'):
        # Don't believe Linux systems claiming ASCII-only filesystems. In
        # practice, arbitrary bytes are allowed, and most things expect UTF-8.
        fsencoding = 'utf-8'
    return u.encode(fsencoding, filesystem_errors)

if sys.platform == 'darwin':
    import xml.etree.ElementTree as ET


OpenType_extensions = frozenset(('.ttf', '.ttc', '.otf'))
Sysfonts = {}
Sysalias = {}

# Python 3 compatibility
if PY_MAJOR_VERSION >= 3:
    def toascii(raw):
        """convert bytes to ASCII-only string"""
        return raw.decode('ascii', 'ignore')
    if os.name == 'nt':
        import winreg as _winreg
    else:
        import subprocess
else:
    def toascii(raw):
        """return ASCII characters of a given unicode or 8-bit string"""
        return raw.decode('ascii', 'ignore')
    if os.name == 'nt':
        import _winreg
    else:
        import subprocess


def _simplename(name):
    """create simple version of the font name"""
    # return alphanumeric characters of a string (converted to lowercase)
    return ''.join(c.lower() for c in name if c.isalnum())


def _addfont(name, bold, italic, font, fontdict):
    """insert a font and style into the font dictionary"""
    if name not in fontdict:
        fontdict[name] = {}
    fontdict[name][bold, italic] = font


def initsysfonts_win32():
    """initialize fonts dictionary on Windows"""

    fontdir = join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')

    fonts = {}

    # add fonts entered in the registry

    # find valid registry keys containing font information.
    # http://docs.python.org/lib/module-sys.html
    # 0 (VER_PLATFORM_WIN32s)          Win32s on Windows 3.1
    # 1 (VER_PLATFORM_WIN32_WINDOWS)   Windows 95/98/ME
    # 2 (VER_PLATFORM_WIN32_NT)        Windows NT/2000/XP
    # 3 (VER_PLATFORM_WIN32_CE)        Windows CE
    if sys.getwindowsversion()[0] == 1:
        key_name = "SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Fonts"
    else:
        key_name = "SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Fonts"
    key = _winreg.OpenKey(_winreg.HKEY_LOCAL_MACHINE, key_name)

    for i in xrange_(_winreg.QueryInfoKey(key)[1]):
        try:
            # name is the font's name e.g. Times New Roman (TrueType)
            # font is the font's filename e.g. times.ttf
            name, font = _winreg.EnumValue(key, i)[0:2]
        except EnvironmentError:
            break

        # try to handle windows unicode strings for file names with
        # international characters
        if PY_MAJOR_VERSION < 3:
            # here are two documents with some information about it:
            # http://www.python.org/peps/pep-0277.html
            # https://www.microsoft.com/technet/archive/interopmigration/linux/mvc/lintowin.mspx#ECAA
            try:
                font = str(font)
            except UnicodeEncodeError:
                # MBCS is the windows encoding for unicode file names.
                try:
                    font = font.encode('MBCS')
                except UnicodeEncodeError:
                    # no success with str or MBCS encoding... skip this font.
                    continue

        if splitext(font)[1].lower() not in OpenType_extensions:
            continue
        if not dirname(font):
            font = join(fontdir, font)

        _parse_font_entry_win(name, font, fonts)

    return fonts


def _parse_font_entry_win(name, font, fonts):
    """
    Parse out a simpler name and the font style from the initial file name.

    :param name: The font name
    :param font: The font file path
    :param fonts: The pygame font dictionary

    :return: Tuple of (bold, italic, name)
    """
    true_type_suffix = '(TrueType)'
    mods = ('demibold', 'narrow', 'light', 'unicode', 'bt', 'mt')
    if name.endswith(true_type_suffix):
        name = name.rstrip(true_type_suffix).rstrip()
    name = name.lower().split()
    bold = italic = 0
    for mod in mods:
        if mod in name:
            name.remove(mod)
    if 'bold' in name:
        name.remove('bold')
        bold = 1
    if 'italic' in name:
        name.remove('italic')
        italic = 1
    name = ''.join(name)
    name = _simplename(name)

    _addfont(name, bold, italic, font, fonts)


def _add_font_paths(sub_elements, fonts):
    """ Gets each element, checks its tag content,
        if wanted fetches the next value in the iterable
    """
    font_name = None
    bold = False
    italic = False
    for tag in sub_elements:
        if tag.text == "_name":
            font_file_name = next(sub_elements).text
            font_name = splitext(font_file_name)[0]
            if splitext(font_file_name)[1] not in OpenType_extensions:
                break
            bold = "bold" in font_name
            italic = "italic" in font_name
        if tag.text == "path" and font_name is not None:
            font_path = next(sub_elements).text
            _addfont(_simplename(font_name), bold, italic, font_path, fonts)
            break


def _system_profiler_darwin():
    fonts = {}
    flout, _ = subprocess.Popen(
        ' '.join(['system_profiler', '-xml', 'SPFontsDataType']),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=True
    ).communicate()

    for font_node in ET.fromstring(flout).iterfind('./array/dict/array/dict'):
        _add_font_paths(font_node.iter("*"), fonts)

    return fonts


def initsysfonts_darwin():
    """ Read the fonts on MacOS, and OS X.
    """
    # if the X11 binary exists... try and use that.
    #  Not likely to be there on pre 10.4.x ... or MacOS 10.10+
    if exists('/usr/X11/bin/fc-list'):
        fonts = initsysfonts_unix('/usr/X11/bin/fc-list')
    # This fc-list path will work with the X11 from the OS X 10.3 installation
    # disc
    elif exists('/usr/X11R6/bin/fc-list'):
        fonts = initsysfonts_unix('/usr/X11R6/bin/fc-list')
    elif exists('/usr/sbin/system_profiler'):
        try:
            fonts = _system_profiler_darwin()
        except (OSError, ValueError):
            fonts = {}
    else:
        fonts = {}

    return fonts


# read the fonts on unix
def initsysfonts_unix(path="fc-list"):
    """use the fc-list from fontconfig to get a list of fonts"""
    fonts = {}

    try:
        # note, we capture stderr so if fc-list isn't there to stop stderr
        # printing.
        flout, _ = subprocess.Popen('%s : file family style' % path,
                                    shell=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    close_fds=True).communicate()
    except (OSError, ValueError):
        return fonts

    entries = toascii(flout)
    try:
        for entry in entries.split('\n'):

            try:
                _parse_font_entry_unix(entry, fonts)
            except ValueError:
                # try the next one.
                pass

    except ValueError:
        pass

    return fonts


def _parse_font_entry_unix(entry, fonts):
    """
    Parses an entry in the unix font data to add to the pygame font
    dictionary.

    :param entry: A entry from the unix font list.
    :param fonts: The pygame font dictionary to add the parsed font data to.

    """
    filename, family, style = entry.split(':', 2)
    if splitext(filename)[1].lower() in OpenType_extensions:
        bold = 'Bold' in style
        italic = 'Italic' in style
        oblique = 'Oblique' in style
        for name in family.strip().split(','):
            if name:
                break
        else:
            name = splitext(basename(filename))[0]

        _addfont(_simplename(name), bold, italic or oblique,
                 filename, fonts)


def create_aliases():
    """ Map common fonts that are absent from the system to similar fonts
        that are installed in the system
    """
    alias_groups = (
        ('monospace', 'misc-fixed', 'courier', 'couriernew', 'console',
         'fixed', 'mono', 'freemono', 'bitstreamverasansmono',
         'verasansmono', 'monotype', 'lucidaconsole', 'consolas',
         'dejavusansmono', 'liberationmono'),
        ('sans', 'arial', 'helvetica', 'swiss', 'freesans',
         'bitstreamverasans', 'verasans', 'verdana', 'tahoma',
         'calibri', 'gillsans', 'segoeui', 'trebuchetms', 'ubuntu',
         'dejavusans', 'liberationsans'),
        ('serif', 'times', 'freeserif', 'bitstreamveraserif', 'roman',
         'timesroman', 'timesnewroman', 'dutch', 'veraserif',
         'georgia', 'cambria', 'constantia', 'dejavuserif',
         'liberationserif'),
        ('wingdings', 'wingbats'),
    )
    for alias_set in alias_groups:
        for name in alias_set:
            if name in Sysfonts:
                found = Sysfonts[name]
                break
        else:
            continue
        for name in alias_set:
            if name not in Sysfonts:
                Sysalias[name] = found


def initsysfonts():
    """
    Initialise the sysfont module, called once. Locates the installed fonts
    and creates some aliases for common font categories.

    Has different initialisation functions for different platforms.
    """
    if sys.platform == 'win32':
        fonts = initsysfonts_win32()
    elif sys.platform == 'darwin':
        fonts = initsysfonts_darwin()
    else:
        fonts = initsysfonts_unix()
    Sysfonts.update(fonts)
    create_aliases()
    if not Sysfonts:  # dummy so we don't try to reinit
        Sysfonts[None] = None



# the exported functions

def get_fonts():
    """pygame.font.get_fonts() -> list
       get a list of system font names

       Returns the list of all found system fonts. Note that
       the names of the fonts will be all lowercase with spaces
       removed. This is how pygame internally stores the font
       names for matching.
    """
    if not Sysfonts:
        initsysfonts()
    return list(Sysfonts)


def match_font(name, bold=0, italic=0):
    """pygame.font.match_font(name, bold=0, italic=0) -> name
       find the filename for the named system font

       This performs the same font search as the SysFont()
       function, only it returns the path to the TTF file
       that would be loaded. The font name can also be an
       iterable of font names or a string/bytes of comma-separated
       font names to try.

       If no match is found, None is returned.
    """
    if not Sysfonts:
        initsysfonts()

    fontname = None
    if isinstance(name, (str, bytes, unicode_)):
        name = name.split(b',' if str != bytes and isinstance(name, bytes) else ',')

    for single_name in name:
        if str != bytes and isinstance(single_name, bytes):
            single_name = single_name.decode()

        single_name = _simplename(single_name)
        styles = Sysfonts.get(single_name)
        if not styles:
            styles = Sysalias.get(single_name)
        if styles:
            while not fontname:
                fontname = styles.get((bold, italic))
                if italic:
                    italic = 0
                elif bold:
                    bold = 0
                elif not fontname:
                    fontname = list(styles.values())[0]
        if fontname:
            break
    return fontname

if __name__ == '__main__':
    name = sys.argv[1]
    bold = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    italic = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    sys.stdout.write(str(match_font(name, bold, italic)))

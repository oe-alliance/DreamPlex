SUBDIRS = skins fonts plex jellyfin

installdir = $(libdir)/enigma2/python/Plugins/Extensions/DreamPlex

# The sources are installed as plain data rather than with install_PYTHON,
# which would byte-compile them with the Python of the build machine. The
# resulting .pyc carry that interpreter's magic number and are useless on a
# box running a different version, which ignores them and recompiles from the
# .py anyway: dead weight in the package. Enigma2 compiles them on first run.
install_DATA = *.py LICENSE.txt maintainer.info pluginLogoHD.png pluginLogo.png keymap.xml

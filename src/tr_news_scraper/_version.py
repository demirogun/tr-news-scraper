"""The installed tr-news-scraper version (internal).

It lives in its own module, so the http layer can name the version in its User-Agent without
importing the package root, which imports the http layer.
"""

from importlib.metadata import version

__version__ = version("tr-news-scraper")

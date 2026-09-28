"""Verify that an installed specification is complete without running a facility."""
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from design_book import copy_design_book


class References(HTMLParser):
    def __init__(self, path):
        super().__init__()
        self.links, self.ids = [], set()
        self.feed(path.read_text())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if key in attrs:
                self.links.append(attrs[key])


class DesignBookDelivery(unittest.TestCase):
    def test_delivered_pages_and_assets_resolve_outside_checkout(self):
        with tempfile.TemporaryDirectory(prefix='loom docs ') as directory:
            delivered = (Path(directory) / 'installed docs').resolve()
            hashes = copy_design_book(ROOT / 'docs', delivered)
            self.assertIn('loom-design-book.html', hashes)
            pages = {path: References(path) for path in delivered.rglob('*.html')}
            self.assertGreater(len(pages), 1)
            for name, digest in hashes.items():
                self.assertEqual((delivered / name).read_bytes(), (ROOT / 'docs' / name).read_bytes())
                self.assertEqual(digest, hashlib.sha256((delivered / name).read_bytes()).hexdigest())
            for path, refs in pages.items():
                for href in refs.links:
                    url = urlsplit(href)
                    if url.scheme or url.netloc:
                        continue
                    target = (path.parent / unquote(url.path)).resolve() if url.path else path
                    self.assertTrue(target.is_relative_to(delivered), (path, href))
                    self.assertTrue(target.is_file(), (path, href))
                    if url.fragment:
                        self.assertIn(unquote(url.fragment), pages[target].ids, (path, href))

    def test_secondary_page_changes_are_recorded_when_entry_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            (source / 'design-book').mkdir(parents=True)
            (source / 'loom-design-book.html').write_text('unchanged entry')
            chapter = source / 'design-book/contract.html'
            chapter.write_text('original contract')
            first = copy_design_book(source, root / 'first')
            chapter.write_text('revised contract')
            second = copy_design_book(source, root / 'second')
            self.assertEqual(first['loom-design-book.html'], second['loom-design-book.html'])
            self.assertNotEqual(first['design-book/contract.html'], second['design-book/contract.html'])

    def test_frozen_acceptance_includes_every_specification_asset(self):
        frozen = runpy.run_path(str(ROOT / 'tests/go_acceptance/run_frozen.py'))
        captured = set(frozen['sources']())
        expected = {path for path in (ROOT / 'docs/design-book').rglob('*') if path.is_file()}
        expected.add(ROOT / 'docs/loom-design-book.html')
        self.assertTrue(expected <= captured, expected - captured)


if __name__ == '__main__':
    unittest.main()

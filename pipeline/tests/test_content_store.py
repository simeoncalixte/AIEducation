"""Content-addressed blob store round-trips."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from evolvingclass_pipeline.adapters.filesystem_content import (
    FilesystemContentStore,
)


class ContentStoreCase(unittest.TestCase):
    def test_put_get_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FilesystemContentStore(tmp)
            body = {"text": "hi", "n": 1}
            ref = store.put(body)
            self.assertTrue(ref.startswith("sha256:"))
            self.assertEqual(store.get(ref), body)

    def test_same_body_same_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FilesystemContentStore(tmp)
            self.assertEqual(store.put({"a": 1}), store.put({"a": 1}))

    def test_different_bodies_differ(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = FilesystemContentStore(tmp)
            self.assertNotEqual(store.put({"a": 1}), store.put({"a": 2}))


if __name__ == "__main__":
    unittest.main()

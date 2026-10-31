"""Module boundaries, enforced by AST so drift fails loudly."""

import ast
import os
import unittest

PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(PKG, "evolvingclass_pipeline")

STDLIB = {
    "abc", "dataclasses", "enum", "functools", "hashlib", "html", "json",
    "pathlib", "typing",
}


def imports_of(relpath):
    with open(os.path.join(SRC, relpath)) as fh:
        tree = ast.parse(fh.read())
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add((node.module or "").split(".")[0])
    return mods


class BoundaryCase(unittest.TestCase):
    def test_domain_is_stdlib_only(self):
        self.assertLessEqual(imports_of("domain.py"), STDLIB | {"__future__"})

    def test_ports_import_domain_only(self):
        mods = imports_of("ports.py") - STDLIB - {"__future__"}
        self.assertEqual(mods, {"evolvingclass_pipeline"})

    def test_pipeline_and_policy_avoid_io(self):
        for name in ("asset_pipeline.py", "policy.py"):
            mods = imports_of(name) - STDLIB - {"__future__"}
            self.assertEqual(mods, {"evolvingclass_pipeline"}, name)

    def test_agents_avoid_orm_and_filesystem(self):
        mods = imports_of("agents/template_backend.py")
        self.assertLessEqual(mods, STDLIB | {"__future__", "evolvingclass_pipeline"})
        self.assertNotIn("DataModels", mods)


if __name__ == "__main__":
    unittest.main()

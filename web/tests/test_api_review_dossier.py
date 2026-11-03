"""Tests for the JSON proposal-dossier API (SCRUM-178).

Mirrors the /review/<kind>/<id> dossier behavior through
/api/review/<kind>/<id> plus the JSON review actions: the React
proposal dossier drives these endpoints with the same pilot semantics
(staff only, rationales recorded, state transitions audited).
"""

import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "database"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))
sys.path.insert(0, os.path.join(ROOT, "service"))
sys.path.insert(0, os.path.join(ROOT, "web"))

from evolvingclass_web.app import create_app  # noqa: E402
from evolvingclass_web.seed import seed  # noqa: E402


class ApiDossierTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp.close()
        self._tmp = tmp.name
        self.url = f"sqlite:///{tmp.name}"
        self.ids = seed(self.url)
        self.app = create_app(self.url)
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self._tmp)

    def login(self, login_ref):
        return self.client.post("/api/login", json={"login_ref": login_ref})

    def dossier(self, kind, version_id):
        resp = self.client.get(f"/api/review/{kind}/{version_id}")
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["dossier"]

    # -- guards --------------------------------------------------------

    def test_dossier_requires_login_as_json(self):
        resp = self.client.get("/api/review/asset/1")
        self.assertEqual(resp.status_code, 401)
        self.assertIn("error", resp.get_json())

    def test_dossier_forbidden_for_students_as_json(self):
        self.login("sam")
        resp = self.client.get("/api/review/asset/1")
        self.assertEqual(resp.status_code, 403)
        self.assertIn("teachers and admins", resp.get_json()["error"])

    def test_action_forbidden_for_students_as_json(self):
        self.login("sam")
        resp = self.client.post("/api/review/asset/1/approve",
                                json={"rationale": "nope"})
        self.assertEqual(resp.status_code, 403)

    def test_unknown_level_and_version_as_json(self):
        self.login("tess")
        resp = self.client.get("/api/review/scene/1")
        self.assertEqual(resp.status_code, 404)
        resp = self.client.get("/api/review/asset/999999")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("error", resp.get_json())

    # -- asset dossier --------------------------------------------------

    def test_asset_dossier_shows_diff_coverage_reuse_impact(self):
        self.login("tess")
        d = self.dossier("asset", self.ids["asset_draft_id"])
        self.assertEqual(d["kind"], "asset")
        self.assertEqual(d["prior_version_no"], 1)
        fields = {row["field"]: row for row in d["diff"]}
        self.assertIn("content_ref", fields)
        self.assertTrue(fields["content_ref"]["changed"])
        snapshot = d["coverage"]["snapshot_directives"]
        self.assertTrue(any("Cover the three eruption" in s["focus"]
                            for s in snapshot))
        self.assertTrue(any("Rock Samples" in r["title"]
                            for r in d["reuse"]))
        self.assertTrue(any(i["mastery"] == "0.72" for i in d["impact"]))
        self.assertIn("content/volcano-v2.glb", d["content_ref"])

    def test_asset_dossier_shows_usage_refs(self):
        self.login("tess")
        d = self.dossier("asset", self.ids["asset_draft_id"])
        consumers = {(u["consumer"], u["kind"], u["role"]) for u in d["usage"]}
        self.assertIn(("Volcanoes / Eruption", "stage", "centerpiece"),
                      consumers)
        statuses = {u["status"] for u in d["usage"]}
        self.assertIn("draft", statuses)

    def test_asset_dossier_flags_low_impact_with_evidence(self):
        self.login("tess")
        d = self.dossier("asset", self.ids["sediment_live_id"])
        self.assertTrue(d["low_impact"])
        flagged = [i for i in d["impact"] if i["low"]]
        self.assertTrue(flagged)
        row = flagged[0]
        self.assertEqual(row["mastery"], "0.31")
        self.assertEqual(row["sample_size"], 12)
        self.assertEqual(row["cohort"], "Room 1")

    def test_healthy_asset_has_no_flag_but_shows_uncertainty(self):
        self.login("tess")
        d = self.dossier("asset", self.ids["asset_draft_id"])
        self.assertFalse(d["low_impact"])
        uncertainties = {i["uncertainty"] for i in d["impact"]}
        self.assertIn("0.05", uncertainties)

    # -- stage and lesson dossiers --------------------------------------

    def test_stage_dossier_shows_uses_with_impact(self):
        self.login("tess")
        d = self.dossier("stage", self.ids["stage_draft_id"])
        assets = {u["asset"] for u in d["uses"]}
        self.assertIn("Volcano Model", assets)
        self.assertIn("Label the Parts", assets)
        roles = {u["role"] for u in d["uses"]}
        self.assertIn("challenge", roles)
        for u in d["uses"]:
            self.assertIn("mastery", u)

    def test_stage_dossier_shows_goals_and_lesson_context(self):
        self.login("tess")
        d = self.dossier("stage", self.ids["stage_draft_id"])
        self.assertEqual(len(d["goals"]), 1)
        entry = d["goals"][0]
        self.assertEqual(entry["challenge"], "Label the Parts")
        keys = {g["key"] for g in entry["goals"]}
        self.assertEqual(keys, {"crater", "vent", "explain"})
        crater = next(
            g for g in entry["goals"] if g["key"] == "crater")
        self.assertEqual(crater["evaluation"], "deterministic")
        self.assertEqual(crater["rule"]["verb"], "goal-attempted")
        self.assertTrue(crater["models"])
        self.assertTrue(crater["probes"])
        explain = next(
            g for g in entry["goals"] if g["key"] == "explain")
        self.assertEqual(explain["evaluation"], "teacher")
        self.assertTrue(explain["rubric"]["criteria"])
        self.assertTrue(explain["models"])
        self.assertEqual(len(d["lessons"]), 1)
        lesson = d["lessons"][0]
        self.assertEqual(lesson["lesson"], "Volcanoes")
        self.assertEqual(lesson["version_no"], 3)
        self.assertEqual(lesson["scope"], "class default")
        self.assertTrue(lesson["models"])
        self.assertTrue(lesson["composition"])

    def test_lesson_dossier_shows_composition_and_audit(self):
        self.login("tess")
        d = self.dossier("lesson", self.ids["lesson_live_id"])
        stages = {c["stage"] for c in d["composition"]}
        self.assertIn("Eruption", stages)
        actions = {e["action"] for e in d["audit"]["events"]}
        self.assertIn("published", actions)
        rationales = [e["rationale"] for e in d["audit"]["events"]]
        self.assertIn("Live.", rationales)

    # -- actions ---------------------------------------------------------

    def test_approve_then_publish_asset(self):
        self.login("tess")
        vid = self.ids["asset_draft_id"]
        resp = self.client.post(f"/api/review/asset/{vid}/approve",
                                json={"rationale": "good"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["message"], "Approval recorded.")
        self.assertEqual(body["dossier"]["decision"], "approved")
        resp = self.client.post(f"/api/review/asset/{vid}/publish",
                                json={"rationale": "ship"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["message"], "Publication recorded.")
        self.assertEqual(body["dossier"]["status"], "published")
        rationales = [e["rationale"]
                      for e in body["dossier"]["audit"]["events"]]
        self.assertIn("ship", rationales)

    def test_reject_records_decision(self):
        self.login("tess")
        vid = self.ids["challenge_draft_id"]
        resp = self.client.post(f"/api/review/asset/{vid}/reject",
                                json={"rationale": "too hard"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["message"], "Rejection recorded.")
        self.assertEqual(body["dossier"]["decision"], "rejected")
        rationales = [a["rationale"]
                      for a in body["dossier"]["audit"]["approvals"]]
        self.assertIn("too hard", rationales)

    def test_publish_blocked_by_draft_dependency(self):
        self.login("tess")
        vid = self.ids["stage_draft_id"]
        self.client.post(f"/api/review/stage/{vid}/approve",
                         json={"rationale": "ok"})
        resp = self.client.post(f"/api/review/stage/{vid}/publish",
                                json={"rationale": "ship"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "unpublished_dependency")

    def test_edit_updates_rationale(self):
        self.login("tess")
        vid = self.ids["lesson_draft_id"]
        resp = self.client.post(f"/api/review/lesson/{vid}/edit",
                                json={"rationale": "Revised pacing note."})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["message"], "Edit recorded.")
        self.assertEqual(body["dossier"]["rationale"],
                         "Revised pacing note.")

    def test_edit_updates_asset_content_ref(self):
        self.login("tess")
        vid = self.ids["asset_draft_id"]
        resp = self.client.post(
            f"/api/review/asset/{vid}/edit",
            json={"rationale": "New scan.",
                  "content_ref": "content/volcano-v3.glb"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["dossier"]["content_ref"],
                         "content/volcano-v3.glb")

    def test_edit_non_draft_rejected(self):
        self.login("tess")
        vid = self.ids["lesson_live_id"]
        resp = self.client.post(f"/api/review/lesson/{vid}/edit",
                                json={"rationale": "too late"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "not_draft")

    def test_edit_replaces_stage_uses(self):
        self.login("tess")
        vid = self.ids["stage_draft_id"]
        asset = self.ids["asset_draft_id"]
        resp = self.client.post(
            f"/api/review/stage/{vid}/edit",
            json={"rationale": "Solo staging.",
                  "uses": [{"asset_version_id": asset,
                            "role": "solo"}]})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["message"], "Edit recorded.")
        self.assertEqual(
            [(u["asset"], u["role"]) for u in body["dossier"]["uses"]],
            [("Volcano Model", "solo")])

    def test_edit_can_remove_manager_guide(self):
        self.login("tess")
        vid = self.ids["stage_draft_id"]
        uses = self.dossier("stage", vid)["uses"]
        self.assertIn("guide", {u["role"] for u in uses})
        kept = [{"asset_version_id": u["asset_version_id"],
                 "role": u["role"]}
                for u in uses if u["role"] != "guide"]
        resp = self.client.post(f"/api/review/stage/{vid}/edit",
                                json={"uses": kept})
        self.assertEqual(resp.status_code, 200)
        roles = {u["role"]
                 for u in resp.get_json()["dossier"]["uses"]}
        self.assertNotIn("guide", roles)

    def test_edit_replaces_lesson_composition(self):
        self.login("tess")
        vid = self.ids["lesson_draft_id"]
        stage = self.ids["stage_draft_id"]
        resp = self.client.post(
            f"/api/review/lesson/{vid}/edit",
            json={"pins": [{"stage_version_id": stage,
                            "required": False}]})
        self.assertEqual(resp.status_code, 200)
        rows = resp.get_json()["dossier"]["composition"]
        self.assertEqual(
            [(c["stage_version_id"], c["position"], c["required"])
             for c in rows],
            [(stage, 1, False)])

    def test_edit_rejects_bad_structure(self):
        self.login("tess")
        stage = self.ids["stage_draft_id"]
        resp = self.client.post(
            f"/api/review/stage/{stage}/edit",
            json={"uses": [{"asset_version_id": 9999,
                            "role": "prop"}]})
        self.assertEqual(resp.status_code, 404)
        resp = self.client.post(
            f"/api/review/stage/{stage}/edit",
            json={"uses": [{"role": "prop"}]})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "invalid_edit")
        lesson = self.ids["lesson_draft_id"]
        resp = self.client.post(
            f"/api/review/lesson/{lesson}/edit",
            json={"pins": [{"stage_version_id": stage},
                           {"stage_version_id": stage}]})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "invalid_edit")

    def test_rollback_restores_retired_lesson(self):
        self.login("tess")
        vid = self.ids["lesson_retired_id"]
        resp = self.client.post(f"/api/review/lesson/{vid}/rollback",
                                json={"rationale": "v2 pacing off"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["message"], "Rollback recorded.")
        actions = {e["action"] for e in body["dossier"]["audit"]["events"]}
        self.assertIn("rolled_back", actions)

    def test_retire_live_lesson(self):
        self.login("tess")
        vid = self.ids["lesson_live_id"]
        resp = self.client.post(f"/api/review/lesson/{vid}/retire",
                                json={"rationale": "done"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["message"], "Retirement recorded.")
        self.assertEqual(body["dossier"]["status"], "retired")

    def test_revise_drafts_new_version_with_lineage(self):
        self.login("tess")
        vid = self.ids["sediment_live_id"]
        resp = self.client.post(f"/api/review/asset/{vid}/revise",
                                json={"rationale": "coarser grains"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["message"], "Revision drafted.")
        self.assertIn("Revision of v1: coarser grains",
                      body["dossier"]["rationale"])
        self.assertEqual(body["dossier"]["status"], "draft")
        self.assertEqual(body["dossier"]["id"], body["version_id"])

    def test_revise_draft_rejected(self):
        self.login("tess")
        vid = self.ids["asset_draft_id"]
        resp = self.client.post(f"/api/review/asset/{vid}/revise",
                                json={"rationale": "nope"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json()["code"], "not_published")

    def test_retire_audited_with_rationale(self):
        self.login("tess")
        vid = self.ids["sediment_live_id"]
        resp = self.client.post(f"/api/review/asset/{vid}/retire",
                                json={"rationale": "replaced"})
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["dossier"]["status"], "retired")
        rationales = [e["rationale"]
                      for e in body["dossier"]["audit"]["events"]]
        self.assertIn("replaced", rationales)

    def test_publish_asset_finalizes_and_shows_preview(self):
        self.login("tess")
        previews = tempfile.TemporaryDirectory()
        self.addCleanup(previews.cleanup)
        self.app.config["preview_dir"] = previews.name
        vid = self.ids["asset_draft_id"]
        self.client.post(f"/api/review/asset/{vid}/approve",
                         json={"rationale": "good"})
        resp = self.client.post(f"/api/review/asset/{vid}/publish",
                                json={"rationale": "ship"})
        self.assertEqual(resp.status_code, 200)
        refs = [p["storage_ref"]
                for p in resp.get_json()["dossier"]["previews"]]
        self.assertEqual(len(refs), 1)
        self.assertIn("v2_poster.svg", refs[0])
        self.assertTrue(os.path.exists(
            os.path.join(previews.name, refs[0])))

    def test_admin_may_review_dossier(self):
        self.login("ash")
        resp = self.client.get(
            f"/api/review/lesson/{self.ids['lesson_live_id']}")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("dossier", resp.get_json())


if __name__ == "__main__":
    unittest.main()

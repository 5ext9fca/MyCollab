"""F5 read-only workspace aggregations (overview board + dependency graph)."""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from missions import services
from missions.models import Mission

from . import utils


class WorkspaceScenarioMixin:
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="pw")
        self.bob = User.objects.create_user("bob", password="pw")
        self.client = APIClient()
        self.client.force_authenticate(self.alice)

    def _mission(self, actor=None, **kwargs):
        defaults = {"actor": actor or self.alice, "title": "t"}
        defaults.update(kwargs)
        return services.create_mission(**defaults)

    def _complete(self, actor, mission):
        utils.claim(actor, mission)
        utils.submit(actor, mission)
        return utils.review(self.alice, mission, decision="accept")

    @staticmethod
    def _group(body, name):
        for group in body["groups"]:
            milestone = group["milestone"]
            if milestone and milestone["name"] == name:
                return group
        if name is None:
            return body["groups"][-1]
        raise AssertionError(f"group {name} not found")

    def _sample(self):
        """The fixed example from NEW_FUNCTION.md section 10.12."""
        m1 = services.create_milestone(actor=self.alice, name="基础移动")
        m2 = services.create_milestone(actor=self.alice, name="首个可玩版本")
        a = self._mission(title="Dash 程序", milestone_id=m1.id)
        b = self._mission(title="Dash 动画", milestone_id=m1.id)
        self._complete(self.bob, a)
        utils.claim(self.bob, b)
        c = self._mission(title="动画接入", milestone_id=m2.id)
        d = self._mission(title="Dash 测试", milestone_id=m2.id)
        services.add_dependency(
            actor=self.alice,
            mission_id=c.id,
            prerequisite_id=a.id,
            expected_version=Mission.objects.get(pk=c.id).version,
        )
        services.add_dependency(
            actor=self.alice,
            mission_id=c.id,
            prerequisite_id=b.id,
            expected_version=Mission.objects.get(pk=c.id).version,
        )
        services.add_dependency(
            actor=self.alice,
            mission_id=d.id,
            prerequisite_id=c.id,
            expected_version=Mission.objects.get(pk=d.id).version,
        )
        e = self._mission(title="调整脚步音量")
        utils.claim(self.bob, e)
        utils.submit(self.bob, e)
        f = self._mission(title="旧 Dash 方案", milestone_id=m1.id)
        utils.cancel(self.alice, f, reason="方案作废")
        return {
            "m1": m1,
            "m2": m2,
            "a": a,
            "b": b,
            "c": c,
            "d": d,
            "e": e,
            "f": f,
        }


class OverviewTests(WorkspaceScenarioMixin, TestCase):
    def test_groups_include_milestones_and_unassigned(self):
        data = self._sample()
        response = self.client.get("/api/workspace/overview/")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()

        names = sorted(
            group["milestone"]["name"] if group["milestone"] else "未归属"
            for group in body["groups"]
        )
        self.assertEqual(names, sorted(["基础移动", "首个可玩版本", "未归属"]))
        self.assertTrue(body["groups"][-1]["is_unassigned"])
        self.assertEqual(body["columns"], ["Open", "InProgress", "Submitted", "Done", "Cancelled"])

        base = self._group(body, "基础移动")
        # Full milestone scope: A Done, B InProgress, F Cancelled -> 1/2 effective.
        self.assertEqual(base["full_counts"]["effective_total"], 2)
        self.assertEqual(base["full_counts"]["done"], 1)
        self.assertEqual(base["full_counts"]["progress"], 0.5)

    def test_cards_land_in_their_real_status_column(self):
        self._sample()
        body = self.client.get("/api/workspace/overview/").json()
        base = self._group(body, "基础移动")
        self.assertEqual(
            [card["title"] for card in base["columns"]["Done"]], ["Dash 程序"]
        )
        self.assertEqual(
            [card["title"] for card in base["columns"]["InProgress"]], ["Dash 动画"]
        )
        self.assertEqual(
            [card["title"] for card in base["columns"]["Cancelled"]], ["旧 Dash 方案"]
        )

    def test_blocked_stays_in_its_status_column_with_badge(self):
        self._sample()
        body = self.client.get("/api/workspace/overview/").json()
        playable = self._group(body, "首个可玩版本")
        open_titles = [card["title"] for card in playable["columns"]["Open"]]
        self.assertEqual(open_titles, ["动画接入", "Dash 测试"])
        for card in playable["columns"]["Open"]:
            self.assertTrue(card["is_blocked"])
            self.assertGreater(card["blocking_count"], 0)

    def test_summary_counts_match_filters(self):
        self._sample()
        summary = self.client.get("/api/workspace/overview/").json()["summary"]
        self.assertEqual(summary["matched_total"], 6)
        self.assertEqual(summary["submitted"], 1)
        self.assertEqual(summary["done"], 1)
        self.assertEqual(summary["blocked"], 2)

    def test_filters_narrow_cards_but_keep_milestone_totals(self):
        data = self._sample()
        body = self.client.get(
            f"/api/workspace/overview/?milestone={data['m2'].id}&status=Open"
        ).json()
        self.assertEqual(len(body["groups"]), 1)
        group = self._group(body, "首个可玩版本")
        self.assertEqual(group["matched_total"], 2)
        self.assertEqual(group["full_counts"]["effective_total"], 2)
        self.assertEqual(body["summary"]["matched_total"], 2)
        self.assertTrue(body["filters_active"])

    def test_column_limit_reports_loaded_and_total(self):
        data = self._sample()
        body = self.client.get("/api/workspace/overview/?column_limit=1&milestone="
                               f"{data['m2'].id}").json()
        group = self._group(body, "首个可玩版本")
        self.assertEqual(group["matched_counts"]["Open"], 2)
        self.assertEqual(group["loaded"]["Open"], 1)

    def test_revalidation_is_reported_separately(self):
        prerequisite = self._mission(title="前置")
        dependent = self._mission(title="下游")
        self._complete(self.bob, prerequisite)
        services.add_dependency(
            actor=self.alice,
            mission_id=dependent.id,
            prerequisite_id=prerequisite.id,
            expected_version=Mission.objects.get(pk=dependent.id).version,
        )
        self._complete(self.bob, dependent)
        # Reopening the prerequisite makes the Done dependent need a re-check.
        services.reopen_mission(
            actor=self.alice,
            mission_id=prerequisite.id,
            reason="发现回归",
            expected_version=Mission.objects.get(pk=prerequisite.id).version,
        )
        body = self.client.get("/api/workspace/overview/?revalidation=true").json()
        self.assertEqual(body["summary"]["matched_total"], 1)
        dependent_cards = [
            card
            for group in body["groups"]
            for card in group["columns"]["Done"]
        ]
        self.assertEqual([card["title"] for card in dependent_cards], ["下游"])
        self.assertFalse(dependent_cards[0]["is_blocked"])
        self.assertTrue(dependent_cards[0]["requires_revalidation"])

    def test_anonymous_is_rejected(self):
        client = APIClient()
        response = client.get("/api/workspace/overview/")
        self.assertIn(response.status_code, (401, 403))


class GraphTests(WorkspaceScenarioMixin, TestCase):
    def test_graph_edges_follow_prerequisite_to_dependent(self):
        data = self._sample()
        body = self.client.get("/api/workspace/graph/").json()
        by_id = {node["id"]: node for node in body["nodes"]}
        edges = {
            (edge["prerequisite_id"], edge["mission_id"]): edge
            for edge in body["edges"]
        }
        self.assertIn((str(data["a"].id), str(data["c"].id)), edges)
        self.assertIn((str(data["b"].id), str(data["c"].id)), edges)
        self.assertIn((str(data["c"].id), str(data["d"].id)), edges)
        self.assertTrue(edges[(str(data["a"].id), str(data["c"].id))]["is_satisfied"])
        self.assertFalse(edges[(str(data["b"].id), str(data["c"].id))]["is_satisfied"])
        # Cross-milestone edges are flagged, not hidden (A -> C crosses milestones).
        self.assertTrue(edges[(str(data["a"].id), str(data["c"].id))]["cross_milestone"])
        self.assertFalse(edges[(str(data["c"].id), str(data["d"].id))]["cross_milestone"])
        # Isolated missions are still visible.
        self.assertIn(str(data["e"].id), by_id)
        self.assertIn(str(data["f"].id), by_id)

    def test_context_nodes_are_kept_for_filters(self):
        data = self._sample()
        body = self.client.get(
            f"/api/workspace/graph/?milestone={data['m2'].id}"
        ).json()
        meta = body["meta"]
        self.assertEqual(meta["scope"], "team")
        context_titles = [n["title"] for n in body["nodes"] if n["is_context"]]
        # A and B belong to the other milestone but keep the edges visible.
        self.assertIn("Dash 程序", context_titles)
        self.assertIn("Dash 动画", context_titles)
        self.assertGreater(meta["context_count"], 0)
        self.assertEqual(meta["matched_count"], 2)

    def test_focus_expansion_walks_transitive_dependencies(self):
        data = self._sample()
        one_hop = self.client.get(
            f"/api/workspace/graph/?scope=mission&focus={data['a'].id}&expand=one"
            "&context=false"
        ).json()
        one_hop_ids = {node["id"] for node in one_hop["nodes"]}
        self.assertIn(str(data["c"].id), one_hop_ids)
        self.assertNotIn(str(data["d"].id), one_hop_ids)

        all_hops = self.client.get(
            f"/api/workspace/graph/?scope=mission&focus={data['a'].id}&expand=all"
            "&direction=downstream&context=false&depth=5"
        ).json()
        all_ids = {node["id"] for node in all_hops["nodes"]}
        self.assertIn(str(data["d"].id), all_ids)

    def test_scope_and_parent_edges(self):
        data = self._sample()
        body = self.client.get(
            f"/api/workspace/graph/?scope=mission&focus={data['c'].id}&context=false"
        ).json()
        ids = {node["id"] for node in body["nodes"]}
        self.assertIn(str(data["c"].id), ids)
        self.assertIn(str(data["a"].id), ids)
        self.assertIn(str(data["b"].id), ids)
        self.assertEqual(body["meta"]["scope"], "mission")

        child = self._mission(title="子任务", parent_id=data["c"].id)
        with_parent = self.client.get(
            "/api/workspace/graph/?include_parent=true"
        ).json()
        parent_edges = {
            (edge["parent_id"], edge["child_id"]) for edge in with_parent["parent_edges"]
        }
        self.assertIn((str(data["c"].id), str(child.id)), parent_edges)
        # Parent/child edges never masquerade as dependency edges.
        self.assertNotIn(
            (str(data["c"].id), str(child.id)),
            {(e["prerequisite_id"], e["mission_id"]) for e in with_parent["edges"]},
        )

    def test_meta_reports_limits_and_snapshot(self):
        self._sample()
        body = self.client.get("/api/workspace/graph/").json()
        meta = body["meta"]
        self.assertEqual(meta["node_limit"], 200)
        self.assertEqual(meta["edge_limit"], 1000)
        self.assertFalse(meta["nodes_truncated"])
        self.assertFalse(meta["edges_truncated"])
        self.assertFalse(meta["truncated"])
        self.assertTrue(meta["relationships_complete"])
        self.assertEqual(meta["truncation_reasons"], [])
        self.assertTrue(body["revision"])

    def test_revision_is_stable_and_reflects_writes(self):
        data = self._sample()
        first = self.client.get("/api/workspace/overview/").json()["revision"]
        second = self.client.get("/api/workspace/overview/").json()["revision"]
        # Same rows -> same revision; a random per-request id could not do this.
        self.assertEqual(first, second)
        utils.claim(self.bob, data["c"])
        third = self.client.get("/api/workspace/overview/").json()["revision"]
        self.assertNotEqual(first, third)

    def test_graph_revision_changes_with_dependencies(self):
        data = self._sample()
        first = self.client.get("/api/workspace/graph/").json()["revision"]
        extra = self._mission(title="新增下游")
        services.add_dependency(
            actor=self.alice,
            mission_id=extra.id,
            prerequisite_id=data["a"].id,
            expected_version=Mission.objects.get(pk=extra.id).version,
        )
        second = self.client.get("/api/workspace/graph/").json()["revision"]
        self.assertNotEqual(first, second)

    def test_group_declares_count_scopes(self):
        self._sample()
        body = self.client.get("/api/workspace/overview/").json()
        group = self._group(body, "基础移动")
        self.assertEqual(group["full_counts_scope"], "milestone_all_visible")
        self.assertEqual(group["matched_counts_scope"], "active_filters")

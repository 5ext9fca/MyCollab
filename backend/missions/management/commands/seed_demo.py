"""创建演示用样板数据。

`seed_demo` 通过服务层写入一组互相衔接的示例数据（用户、里程碑、任务树、
前置依赖、成果提交与验收），用于本地开发与演示。所有写入都走
`missions.services`，因此会经过状态机与权限校验。

用法：

    python manage.py seed_demo           # 不存在样板数据时创建
    python manage.py seed_demo --reset    # 清空现有任务/里程碑/标签后重建
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from missions import services
from missions.models import (
    Milestone,
    MilestoneEvent,
    Mission,
    MissionDependency,
    MissionEvent,
    MissionSubmission,
    Tag,
)

from accounts.models import User

DEMO_USERNAMES = ["alice", "bob", "carol", "dave", "erin"]
DEMO_PASSWORD = "demo12345"
ROOT_TITLE = "实现角色移动系统"


def _user(username: str, display_name: str) -> User:
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"first_name": display_name, "is_active": True},
    )
    if not user.has_usable_password():
        user.set_password(DEMO_PASSWORD)
        user.save(update_fields=["password"])
    return user


class Command(BaseCommand):
    help = "创建演示用样板数据（用户、里程碑、任务、依赖、成果与验收）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="先删除现有任务、里程碑、标签与样板用户，再重新创建",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            self._reset()

        if Mission.objects.filter(title=ROOT_TITLE).exists():
            self.stdout.write(
                self.style.WARNING("样板数据已存在，跳过创建（使用 --reset 重建）。")
            )
            return

        self._seed()
        self.stdout.write(self.style.SUCCESS("样板数据已创建。"))
        self.stdout.write(
            f"演示账号：{'、'.join(DEMO_USERNAMES)}（密码：{DEMO_PASSWORD}）"
        )

    # -- reset ------------------------------------------------------------- #
    def _reset(self) -> None:
        # Break the protected self-reference before deleting the tree.
        Mission.objects.update(parent=None, current_submission=None)
        # Delete children before parents to satisfy PROTECT/SET_NULL relations.
        MissionSubmission.objects.all().delete()
        MissionDependency.objects.all().delete()
        MissionEvent.objects.all().delete()
        Mission.objects.all().delete()
        MilestoneEvent.objects.all().delete()
        Milestone.objects.all().delete()
        Tag.objects.all().delete()
        User.objects.filter(username__in=DEMO_USERNAMES).delete()
        self.stdout.write("已清空现有样板数据。")

    # -- seed -------------------------------------------------------------- #
    def _seed(self) -> None:
        today = timezone.localdate()
        alice = _user("alice", "Alice")
        bob = _user("bob", "Bob")
        carol = _user("carol", "Carol")
        dave = _user("dave", "Dave")
        erin = _user("erin", "Erin")

        playable = services.create_milestone(
            actor=alice,
            name="首个可玩版本",
            description="完成基础移动与战斗循环，交付内部可玩构建。",
            due_date=today + timedelta(days=14),
        )
        playable = services.transition_milestone(
            actor=alice,
            milestone_id=playable.id,
            status="Active",
            expected_version=playable.version,
        )
        online = services.create_milestone(
            actor=alice,
            name="联机测试版本",
            description="完成房间匹配与基础同步，用于小规模联机测试。",
            due_date=today + timedelta(days=35),
        )

        move = services.create_mission(
            actor=alice,
            title=ROOT_TITLE,
            content="实现角色的移动、跳跃与 Dash，作为后续战斗系统的基础。",
            acceptance_criteria="- 行走、跳跃、Dash 手感符合设计\n- 无穿模与输入丢失",
            tags=["Unity", "Gameplay"],
            type="Feature",
            priority="P1",
            reviewer_id=alice.id,
            milestone_id=playable.id,
        )
        walk = services.create_mission(
            actor=alice,
            title="实现行走与跳跃",
            parent_id=move.id,
            tags=["Gameplay"],
            type="Task",
            priority="P1",
        )
        dash = services.create_mission(
            actor=alice,
            title="实现 Dash",
            parent_id=move.id,
            tags=["Gameplay"],
            type="Task",
            priority="P1",
        )
        services.create_mission(
            actor=alice,
            title="Dash 结束后输入未恢复",
            content="Dash 动画结束时方向键会短暂失灵。",
            parent_id=move.id,
            type="Bug",
            priority="P0",
        )
        tests = services.create_mission(
            actor=alice,
            title="编写移动系统测试",
            parent_id=move.id,
            tags=["Gameplay"],
            type="Task",
            priority="P2",
            reviewer_id=dave.id,
        )
        self._add_dependency(alice, tests, walk)
        self._add_dependency(alice, tests, dash)

        online_feature = services.create_mission(
            actor=alice,
            title="实现基础联机同步",
            content="房间匹配与基础位置同步，为后续联机玩法打基础。",
            tags=["Networking"],
            type="Feature",
            priority="P0",
            reviewer_id=erin.id,
            milestone_id=online.id,
        )
        self._add_dependency(alice, online_feature, dash)

        # A finished task with source / build evidence and an accepted review.
        pipeline = services.create_mission(
            actor=alice,
            title="搭建构建流水线",
            content="接入 CI，产出 Windows 可玩构建。",
            tags=["Build"],
            type="Task",
            priority="P2",
            reviewer_id=dave.id,
        )
        pipeline = services.claim_mission(
            actor=erin, mission_id=pipeline.id, expected_version=pipeline.version
        )
        pipeline = services.submit_mission(
            actor=erin,
            mission_id=pipeline.id,
            description="已接入流水线，Windows 构建成功。",
            verification_description="在目标机器上启动构建，确认可正常进入主菜单。",
            source_references=[
                {
                    "provider": "Git",
                    "repository": "game/engine",
                    "revision": "a1b2c3d",
                    "browse_url": "https://example.com/commit/a1b2c3d",
                }
            ],
            build_references=[
                {
                    "provider": "Jenkins",
                    "build_id": "2026.10.13.1",
                    "platform": "Windows",
                    "source_revision": "a1b2c3d",
                    "artifact_url": "https://example.com/builds/2026.10.13.1",
                    "status": "Succeeded",
                }
            ],
            expected_version=pipeline.version,
        )
        submission = MissionSubmission.objects.get(pk=pipeline.current_submission_id)
        verified_build = submission.build_references.get()
        services.review_mission(
            actor=dave,
            mission_id=pipeline.id,
            submission_id=submission.id,
            decision="accept",
            comment="构建成功，已在目标机器验证。",
            verified_build_reference_id=verified_build.id,
            expected_version=pipeline.version,
        )

        # Let members start working so the board is not all `Open`.
        services.claim_mission(actor=carol, mission_id=walk.id, expected_version=walk.version)
        services.claim_mission(actor=bob, mission_id=dash.id, expected_version=dash.version)

        self.stdout.write(
            f"创建任务 {Mission.objects.count()} 个、里程碑 {Milestone.objects.count()} 个。"
        )

    def _add_dependency(self, actor, mission: Mission, prerequisite: Mission) -> None:
        mission = Mission.objects.get(pk=mission.id)
        services.add_dependency(
            actor=actor,
            mission_id=mission.id,
            prerequisite_id=prerequisite.id,
            expected_version=mission.version,
        )

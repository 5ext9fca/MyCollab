"""创建演示用样板数据。

`seed_demo` 通过服务层写入一组互相衔接的示例数据（用户、里程碑、任务树、
前置依赖、成果提交与验收），用于本地开发与演示。所有写入都走
各业务服务，因此会经过状态机与权限校验；重建清理在同一事务内执行。

用法：

    python manage.py seed_demo           # 不存在样板数据时创建
    python manage.py seed_demo --reset    # 重建演示账号的业务数据，保留账号
"""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from missions import services
from missions.models import (
    Milestone,
    Mission,
    MissionDependency,
    MissionSubmission,
    DesignElement, ProductionTemplate, ProductionBatch, SavedMissionView,
)

from accounts.models import User

DEMO_USERNAMES = ["alice", "bob", "carol", "dave", "erin"]
DEMO_PASSWORD = "demo12345"
ROOT_TITLE = "实现角色移动系统"


def _user(username: str, display_name: str) -> User:
    user, created = User.objects.get_or_create(
        username=username,
        defaults={"first_name": display_name, "is_active": True},
    )
    if created or not user.password or not user.has_usable_password():
        user.set_password(DEMO_PASSWORD)
        user.save(update_fields=["password"])
    return user


class Command(BaseCommand):
    help = "创建全流程演示数据（任务、生产链、日程、个人工作、通知与筛选）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="重建演示账号创建的任务、里程碑、设计与模板，保留账号及其他成员数据",
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
            f"演示账号：{'、'.join(DEMO_USERNAMES)}（新账号或空密码账号：{DEMO_PASSWORD}；已有有效密码保留）"
        )

    # -- reset ------------------------------------------------------------- #
    def _reset(self) -> None:
        demo_users = User.objects.filter(username__in=DEMO_USERNAMES)
        missions = Mission.objects.filter(creator__in=demo_users)
        # 若其他成员依赖演示任务，拒绝重建，避免静默移除其关系。
        if (Mission.objects.exclude(creator__in=demo_users).filter(parent__in=missions).exists()
                or MissionDependency.objects.filter(prerequisite__in=missions)
                    .exclude(mission__in=missions).exists()):
            raise CommandError("其他成员的任务引用了演示任务，无法安全重建。")
        missions.update(parent=None, current_submission=None)
        missions.delete()
        ProductionBatch.objects.filter(created_by__in=demo_users).delete()
        elements = DesignElement.objects.filter(created_by__in=demo_users)
        elements.update(parent=None)
        elements.delete()
        ProductionTemplate.objects.filter(created_by__in=demo_users).delete()
        Milestone.objects.filter(created_by__in=demo_users).delete()
        SavedMissionView.objects.filter(owner__in=demo_users, name__startswith="示例 · ").delete()
        # 保留账号、密码、个人素材、其他筛选和共享标签。
        self.stdout.write("已清理演示账号创建的业务数据，保留账号与其他成员数据。")

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

        # 已验收任务保留源码、构建证据和验收记录。
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

        # 认领任务，展示真实的执行中状态。
        services.claim_mission(actor=carol, mission_id=walk.id, expected_version=walk.version)
        services.claim_mission(actor=bob, mission_id=dash.id, expected_version=dash.version)

        self._extended_scenarios(alice, bob, carol, dave, erin, playable, today)

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

    def _extended_scenarios(self, alice, bob, carol, dave, erin, milestone, today):
        from missions.saved_views import save_view
        from notifications import services as notifications
        from notifications.models import Notification

        def create(title, start=None, end=None, **kwargs):
            return services.create_mission(
                actor=alice, title=title, reviewer_id=alice.pk,
                milestone_id=milestone.pk,
                planned_start_date=today + timedelta(days=start) if start is not None else None,
                planned_end_date=today + timedelta(days=end) if end is not None else None,
                **kwargs,
            )

        def claim(mission, actor=bob):
            mission.refresh_from_db()
            return services.claim_mission(actor=actor, mission_id=mission.pk, expected_version=mission.version)

        def submit(mission, actor=bob):
            mission.refresh_from_db()
            return services.submit_mission(actor=actor, mission_id=mission.pk,
                expected_version=mission.version, description="已完成演示交付，请按验收标准人工核对。",
                verification_description="运行对应场景，核对输入、输出和异常路径。")

        def review(mission, decision="accept"):
            mission.refresh_from_db()
            return services.review_mission(actor=alice, mission_id=mission.pk,
                expected_version=mission.version, submission_id=mission.current_submission_id,
                decision=decision, comment="人工验证通过。" if decision == "accept" else "边界输入仍有问题，请修复后重新提交。")

        # 日期均相对生成当天，分别展示待验收、退回、临期和逾期。
        pending = create("验收手柄输入适配", -3, 1, priority="P1")
        submit(claim(pending))
        returned = create("修复斜坡移动抖动", -5, -1, type="Bug", priority="P0")
        review(submit(claim(returned)), "reject")
        claim(create("补齐移动操作说明", 0, 2, tags=["Documentation"]), carol)
        claim(create("排查低帧率输入丢失", -7, -2, type="Bug", priority="P1"), dave)

        # 前置任务完成后，下游仍须自行执行、提交和验收。
        prerequisite = create("确定输入映射规范", -4, -2)
        ready = claim(create("接入重映射设置界面", 0, 5))
        self._add_dependency(alice, ready, prerequisite)
        review(submit(claim(prerequisite)))

        # 已完成的下游不会自动回退；上游重开后出现需复核提示。
        upstream = create("确认碰撞体规格", -8, -6)
        downstream = create("验证角色碰撞回归", -5, -3)
        self._add_dependency(alice, downstream, upstream)
        review(submit(claim(upstream)))
        review(submit(claim(downstream)))
        upstream.refresh_from_db()
        services.reopen_mission(actor=alice, mission_id=upstream.pk,
            expected_version=upstream.version, reason="碰撞体规格调整，已完成的回归任务需要人工复核。")

        cancelled = create("试验自动寻路替代移动", 1, 6, type="Feature", priority="P3")
        services.cancel_mission(actor=alice, mission_id=cancelled.pk,
            expected_version=cancelled.version, reason="本轮不采用该方案，保留取消记录。")
        create("尚未估期的移动音效", tags=["Audio"])
        create("仅确定交付日的兼容性检查", end=7)

        # 设计树、资产和模板实例化建立真实生产关系，不手工伪造批次。
        design = services.create_design_element(actor=alice, title="角色移动设计",
            content="## 体验目标\n行走、跳跃与 Dash 连贯。\n\n设计条目用于组织说明与资产，不会自动完成任务。")
        asset = services.create_design_element(actor=alice, title="主角移动动画", kind="Asset",
            content="生产链：原画确认 → 动画制作 → 引擎集成。")
        services.update_design_element(actor=alice, element_id=design.pk, expected_version=design.version, changes={"asset_ids": [asset.pk]})
        template = services.create_production_template(actor=alice, name="角色动画标准生产链",
            description="一次生成带前置依赖的任务；模板后续修改不会改写既有批次。",
            steps=[
                {"key": "concept", "title": "原画确认", "tags": ["Art"]},
                {"key": "animation", "title": "动画制作", "tags": ["Animation"], "prerequisite_keys": ["concept"]},
                {"key": "integration", "title": "引擎集成", "tags": ["Unity"], "prerequisite_keys": ["animation"]},
            ])
        batch = services.instantiate_production(actor=alice, element_id=asset.pk,
            expected_version=asset.version, template_id=template.pk,
            template_version=template.version, milestone_id=milestone.pk)
        for index, key in enumerate(("concept", "animation", "integration")):
            task = batch.items.get(step_key=key).mission
            services.update_mission(actor=alice, mission_id=task.pk, expected_version=task.version,
                changes={"planned_start_date": (today + timedelta(days=index * 3)).isoformat(),
                         "planned_end_date": (today + timedelta(days=index * 3 + 2)).isoformat()})
            claim(task, erin)

        # 关注者收到评论；静音用户不收到普通通知，职责通知仍由服务层保障。
        notifications.set_subscription(user=carol, mission_id=pending.pk, mode="Follow", expected_version=0)
        notifications.set_subscription(user=dave, mission_id=pending.pk, mode="Mute", expected_version=0)
        services.create_comment(actor=bob, mission_id=pending.pk,
            content="## 验收提示\n- 已覆盖键盘与手柄\n- 请检查断连重连\n\n外部证据链接仅供演示：[验证说明](https://example.com/demo)。")
        notifications.send_reminders()
        first = Notification.objects.filter(recipient=alice).first()
        if first:
            notifications.mark_read(user=alice, ids=[first.pk])

        for owner, name, visibility, target, filters, window in [
            (alice, "团队阻塞任务", "Team", "Square", {"blocked": True}, None),
            (alice, "需要复核", "Team", "Square", {"revalidation": True}, None),
            (alice, "未来七天计划", "Team", "Gantt", {}, {"mode": "relative", "preset": "next_7_days"}),
            (bob, "我认领的任务", "Private", "Square", {"assignee": "me"}, None),
        ]:
            save_view(actor=owner, data={"name": "示例 · " + name, "visibility": visibility,
                "target": target, "definition": {"filters": filters, "ordering": None,
                    "date_window": window, "zoom": "day" if target == "Gantt" else None}})

        guide = create("示例导览：当前能力与边界", type="Feature", content="""## 推荐体验顺序
1. Alice：个人工作中心查看待验收、临期、逾期和需复核；通知中心查看已读与未读。
2. Bob：查看退回待改和解除阻塞的任务，修复后重新提交；使用私有筛选。
3. 工作台：甘特图查看完整日期、单边日期、未排期和依赖关系。
4. 设计目录：查看角色移动设计、动画资产、模板与生产批次。
5. 任务广场：选择当前页任务，预览批量计划修改，再确认执行。

## 能力边界
- 单团队协作；不提供跨团队项目组合、工时计费或资源容量自动调度。
- 依赖用于阻塞校验和风险提示，不会自动排期或自动完成下游任务。
- 父任务需子任务完成后人工提交；验收与重新打开保留事件历史。
- 构建与源码引用是人工登记的外部证据，示例链接不是实际构建服务。
- 通知在站内展示；到期提醒由命令或外部定时调度触发，不是邮件推送。
- 批量修改只支持计划字段，逐项处理并报告部分失败，不绕过状态机。
- 模板生成任务后保留快照，后续模板修改不自动同步既有任务。
- 素材按用户隔离；本演示不预置上传文件，可自行上传验证权限。
""")
        services.create_comment(actor=carol, mission_id=guide.pk,
            content="这是可操作的样板数据；修改会写入真实本地数据库。重新运行 seed_demo --reset 可恢复场景，日期以重建当天为准。")

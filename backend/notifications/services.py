"""数据库通知与个人订阅写入口；不反向调用任务状态流转。"""
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from accounts.models import User
from common.exceptions import ConflictError, NotFound, ValidationFailure
from missions.models import Mission, MissionDependency
from .models import MissionSubscription, Notification

LABELS = {
    'submitted': '提交成果，等待验收', 'review_rejected': '成果被退回',
    'review_approved': '验收通过', 'review_transferred': '验收已转交',
    'reviewer_changed': '验收者已调整', 'claimed': '任务已认领', 'released': '退出认领',
    'reopened': '任务重新打开', 'cancelled': '任务已取消', 'plan_changed': '计划已调整',
    'comment_created': '新增评论', 'dependency_unblocked': '前置依赖已解除',
    'dependency_revalidation': '前置条件变化，需要复核',
    'due_soon': '任务即将到期', 'overdue': '任务已逾期',
}


def roles(mission):
    return {i for i in (mission.creator_id, mission.assignee_id, mission.reviewer_id) if i}


def deliver(*, mission, actor, kind, source_key, mandatory=(), extra=(), ordinary=True):
    recipients = set()
    if ordinary:
        subscriptions = list(MissionSubscription.objects.filter(mission=mission).values_list('user_id', 'mode'))
        recipients = roles(mission) | {int(i) for i in extra if i} | {i for i, mode in subscriptions if mode == 'Follow'}
        recipients -= {i for i, mode in subscriptions if mode == 'Mute'}
    recipients |= {i for i in mandatory if i}
    if actor:
        recipients.discard(actor.pk)
    ids = list(User.objects.filter(pk__in=recipients, is_active=True).values_list('pk', flat=True))
    # 唯一约束处理并发重复来源，不在外层事务中捕获完整性异常。
    Notification.objects.bulk_create([
        Notification(recipient_id=i, mission=mission, actor=actor, kind=kind,
                     source_key=source_key, payload={'summary': LABELS[kind]}) for i in ids
    ], ignore_conflicts=True)


def from_event(event):
    mission, kind = event.mission, event.action
    mandatory, extra = set(), set()
    if kind == 'updated':
        if not {'priority', 'milestone', 'planned_start_date', 'planned_end_date'} & set(event.payload.get('fields', [])):
            return
        kind = 'plan_changed'
    if kind not in LABELS:
        return
    if kind in ('submitted', 'review_transferred'):
        mandatory.add(mission.reviewer_id)
    if kind == 'review_rejected':
        mandatory.add(mission.assignee_id)
    if kind in ('review_transferred', 'reviewer_changed'):
        extra.add(event.payload.get('from'))
    deliver(mission=mission, actor=event.actor, kind=kind,
            source_key=f'event:{event.pk}:{kind}:{mission.pk}', mandatory=mandatory, extra=extra)


def dependency_snapshot(mission_id):
    ids = set(MissionDependency.objects.filter(prerequisite_id=mission_id).values_list('mission_id', flat=True))
    ids.add(mission_id)
    return {m.pk: (MissionDependency.objects.filter(mission=m).exclude(prerequisite__status='Done').exists(), m.status)
            for m in Mission.objects.filter(pk__in=ids)}


def dependency_changes(before, *, actor, source_event):
    for mission in Mission.objects.filter(pk__in=before):
        old_unresolved, old_status = before[mission.pk]
        unresolved = MissionDependency.objects.filter(mission=mission).exclude(prerequisite__status='Done').exists()
        kind = None
        if old_unresolved and not unresolved:
            kind = 'dependency_unblocked'
        elif unresolved and mission.status == 'Done' and not (old_unresolved and old_status == 'Done'):
            kind = 'dependency_revalidation'
        if kind:
            deliver(mission=mission, actor=actor, kind=kind,
                    source_key=f'event:{source_event.pk}:{kind}:{mission.pk}',
                    mandatory={mission.creator_id, mission.reviewer_id} if kind == 'dependency_revalidation' else ())


@transaction.atomic
def mark_read(*, user, ids):
    rows = list(Notification.objects.select_for_update().filter(recipient=user, pk__in=ids))
    if len(rows) != len(ids):
        raise NotFound('通知不存在。')
    return Notification.objects.filter(pk__in=ids, recipient=user, read_at__isnull=True).update(read_at=timezone.now())


@transaction.atomic
def set_subscription(*, user, mission_id, mode, expected_version):
    from missions.services import _acquire_team_lock
    _acquire_team_lock()
    if not Mission.objects.filter(pk=mission_id).exists():
        raise NotFound('任务不存在。')
    if mode not in ('Follow', 'Mute') or type(expected_version) is not int or expected_version < 0:
        raise ValidationFailure('订阅模式或版本无效。')
    row = MissionSubscription.objects.select_for_update().filter(user=user, mission_id=mission_id).first()
    if (row.version if row else 0) != expected_version:
        raise ConflictError('订阅已变化，请刷新重试。', code='version_conflict')
    if row:
        row.mode, row.version = mode, row.version + 1
        row.save()
    else:
        row = MissionSubscription.objects.create(user=user, mission_id=mission_id, mode=mode)
    return row


def send_reminders():
    from missions.services import _acquire_team_lock
    scanned = added = 0
    today = timezone.localdate()
    candidates = Mission.objects.filter(status__in=['Open', 'InProgress', 'Submitted'],
        planned_end_date__lte=today + timedelta(days=3)).values_list('pk', flat=True)
    for pk in candidates.iterator(chunk_size=200):
        with transaction.atomic():
            _acquire_team_lock()
            mission = Mission.objects.select_for_update().filter(pk=pk).first()
            scanned += 1
            today = timezone.localdate()
            if not mission or mission.status not in ('Open', 'InProgress', 'Submitted') or not mission.planned_end_date:
                continue
            end = mission.planned_end_date
            if end > today + timedelta(days=3):
                continue
            kind = 'overdue' if end < today else 'due_soon'
            key = f'deadline:{pk}:{end.isoformat()}:{kind}'
            before = Notification.objects.filter(source_key=key).count()
            deliver(mission=mission, actor=None, kind=kind, source_key=key, mandatory=roles(mission), ordinary=False)
            added += Notification.objects.filter(source_key=key).count() - before
    return scanned, added

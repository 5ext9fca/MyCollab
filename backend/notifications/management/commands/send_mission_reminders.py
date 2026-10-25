from django.core.management.base import BaseCommand, CommandError
from notifications.services import send_reminders


class Command(BaseCommand):
    help = '发送尚未提醒过的任务到期通知，可安全重复运行'

    def handle(self, *args, **options):
        try:
            scanned, added = send_reminders()
        except Exception as exc:
            raise CommandError(f'日期提醒失败：{exc}') from exc
        self.stdout.write(f'扫描 {scanned} 个任务，新增 {added} 条通知。')

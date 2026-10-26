from django.core.management.base import BaseCommand
from transfers.services import cleanup_transfers


class Command(BaseCommand):
    help = "删除过期的文件直传会话与信令"

    def handle(self, *args, **options):
        self.stdout.write(f"已清理 {cleanup_transfers()} 条过期记录。")

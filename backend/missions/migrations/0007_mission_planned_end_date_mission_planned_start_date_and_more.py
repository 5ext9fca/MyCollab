# 由 Django 6.1.2 生成：新增 Mission 可空计划日期与区间约束。

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('missions', '0006_productiontemplate_productionbatch_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='mission',
            name='planned_end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='mission',
            name='planned_start_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='missionevent',
            name='action',
            field=models.CharField(choices=[('created', '创建'), ('updated', '修改'), ('claimed', '认领'), ('released', '退出'), ('submitted', '提交成果'), ('review_approved', '验收通过'), ('review_rejected', '退回'), ('cancelled', '取消'), ('child_created', '创建子任务'), ('schedule_changed', '修改计划日期'), ('design_element_changed', '修改设计依据'), ('type_changed', '修改类型'), ('priority_changed', '修改优先级'), ('reviewer_changed', '修改验收者'), ('review_transferred', '转交验收'), ('reopened', '重新打开'), ('milestone_changed', '修改里程碑'), ('dependency_added', '添加依赖'), ('dependency_removed', '移除依赖')], max_length=32),
        ),
        migrations.AddConstraint(
            model_name='mission',
            constraint=models.CheckConstraint(condition=models.Q(('planned_start_date__isnull', True), ('planned_end_date__isnull', True), ('planned_start_date__lte', models.F('planned_end_date')), _connector='OR'), name='mission_schedule_order'),
        ),
    ]

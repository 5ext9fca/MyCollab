# 由 Django 6.1.2 生成的设计关联迁移。

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('missions', '0004_remove_mission_result_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='missionevent',
            name='action',
            field=models.CharField(choices=[('created', '创建'), ('updated', '修改'), ('claimed', '认领'), ('released', '退出'), ('submitted', '提交成果'), ('review_approved', '验收通过'), ('review_rejected', '退回'), ('cancelled', '取消'), ('child_created', '创建子任务'), ('design_element_changed', '修改设计依据'), ('type_changed', '修改类型'), ('priority_changed', '修改优先级'), ('reviewer_changed', '修改验收者'), ('review_transferred', '转交验收'), ('reopened', '重新打开'), ('milestone_changed', '修改里程碑'), ('dependency_added', '添加依赖'), ('dependency_removed', '移除依赖')], max_length=32),
        ),
        migrations.CreateModel(
            name='DesignElement',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200)),
                ('content', models.TextField(blank=True)),
                ('kind', models.CharField(choices=[('Design', '设计说明'), ('Asset', '资产')], default='Design', max_length=16)),
                ('version', models.PositiveIntegerField(default=1)),
                ('archived', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='design_elements', to=settings.AUTH_USER_MODEL)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='children', to='missions.designelement')),
            ],
            options={
                'ordering': ['title', 'id'],
            },
        ),
        migrations.AddField(
            model_name='mission',
            name='design_element',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='missions', to='missions.designelement'),
        ),
        migrations.CreateModel(
            name='DesignElementEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=32)),
                ('payload', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('element', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='missions.designelement')),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.AddIndex(
            model_name='designelement',
            index=models.Index(fields=['archived', 'parent'], name='missions_de_archive_6f6866_idx'),
        ),
        migrations.AddConstraint(
            model_name='designelement',
            constraint=models.CheckConstraint(condition=models.Q(('parent', models.F('id')), _negated=True), name='design_parent_not_self'),
        ),
    ]

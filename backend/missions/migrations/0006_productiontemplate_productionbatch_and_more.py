# 资产生产模板、不可变批次快照与步骤映射。

import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('missions', '0005_alter_missionevent_action_designelement_and_more'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ProductionTemplate',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=200)),
                ('description', models.TextField(blank=True)),
                ('steps', models.JSONField(default=list)),
                ('version', models.PositiveIntegerField(default=1)),
                ('archived', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['name', 'id'],
            },
        ),
        migrations.CreateModel(
            name='ProductionBatch',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('template_version', models.PositiveIntegerField()),
                ('template_snapshot', models.JSONField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('asset', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='production_batch', to='missions.designelement')),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='missions.productiontemplate')),
            ],
        ),
        migrations.CreateModel(
            name='ProductionTemplateEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(max_length=32)),
                ('payload', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('template', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='events', to='missions.productiontemplate')),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
        migrations.CreateModel(
            name='ProductionBatchItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('step_key', models.CharField(max_length=50)),
                ('batch', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='missions.productionbatch')),
                ('mission', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='production_item', to='missions.mission')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('batch', 'step_key'), name='production_batch_step_unique')],
            },
        ),
    ]

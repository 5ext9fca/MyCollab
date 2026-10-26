from django.db import migrations


def remove_delegation_requests(apps, schema_editor):
    # 委派执行模型已移至 feature 分支；移除旧请求，避免旧设备继续领取。
    requests = apps.get_model('agent_bridge', 'AssistanceRequest')
    requests.objects.filter(kind__in=['image_generate', 'image_edit', 'code_implement']).delete()
    devices = apps.get_model('agent_bridge', 'AgentDevice')
    for device in devices.objects.all().iterator():
        device.capabilities = [kind for kind in device.capabilities if kind not in ['image_generate', 'image_edit', 'code_implement']]
        device.save(update_fields=['capabilities'])


class Migration(migrations.Migration):
    dependencies = [
        ('agent_bridge', '0005_remove_interactioncommand_interaction_command_dedup_and_more'),
        ('missions', '0013_remove_codeexecution_code_execution_version_unique_and_more'),
    ]
    operations = [migrations.RunPython(remove_delegation_requests, migrations.RunPython.noop)]

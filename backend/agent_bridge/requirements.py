"""需求导出只读取业务快照；不执行 Mission，也不调用模型。"""
from . import protocol
from common.exceptions import ValidationFailure


def snapshot(mission):
    items = list(mission.assets.all().order_by('id'))
    if mission.design_element_id:
        items.append(mission.design_element)
    contexts = [{"id": str(item.pk), "version": item.version, "kind": item.kind,
                 "title": item.title, "content": item.content, "archived": item.archived} for item in items]
    result = {
        "mission": {"id": str(mission.pk), "version": mission.version, "title": mission.title,
                    "content": mission.content, "acceptance_criteria": mission.acceptance_criteria,
                    "type": mission.type, "priority": mission.priority, "status": mission.status},
        "contexts": contexts,
    }
    try:
        protocol.bounded_json(result, protocol.INPUT_LIMIT)
    except protocol.ProtocolError as exc:
        raise ValidationFailure("Mission 与关联说明超出 256 KiB，请精简后导出。") from exc
    return result

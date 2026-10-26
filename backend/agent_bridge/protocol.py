"""无框架依赖的协议校验；本地 Runner 与服务器共用，不包含模型通信。"""

import json
import re

KINDS = ("design_polish", "template_generate", "mission_write", "review_assist")
INPUT_LIMIT = 256 * 1024
RESULT_LIMIT = 128 * 1024
TEXT_LIMIT = 30000


class ProtocolError(ValueError):
    pass


def bounded_json(value, limit):
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError) as exc:
        raise ProtocolError("必须是有效 JSON。") from exc
    if len(encoded) > limit:
        raise ProtocolError("内容超出允许体积。")
    return encoded


def fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ProtocolError("字段缺失、包含未知字段或对象格式不正确。")


def text(value, maximum=TEXT_LIMIT, nonempty=False):
    if not isinstance(value, str) or len(value) > maximum or (nonempty and not value.strip()):
        raise ProtocolError("文本为空、过长或类型错误。")


def strings(value, maximum=30, length=2000):
    if not isinstance(value, list) or len(value) > maximum:
        raise ProtocolError("列表格式或数量错误。")
    for item in value:
        text(item, length, True)


def mission_fields(value):
    text(value["title"], 200, True)
    text(value["content"])
    text(value["acceptance_criteria"])
    if value["type"] not in ("Feature", "Task", "Bug") or value["priority"] not in ("P0", "P1", "P2", "P3"):
        raise ProtocolError("任务类型或优先级无效。")
    strings(value["tags"], 30, 50)


def validate_result(kind, value):
    bounded_json(value, RESULT_LIMIT)
    if kind == "design_polish":
        fields(value, ("title", "content", "summary", "questions"))
        text(value["title"], 200, True)
        text(value["content"])
        text(value["summary"], 4000)
        strings(value["questions"])
    elif kind == "mission_write":
        fields(value, ("title", "content", "acceptance_criteria", "type", "priority", "tags", "questions"))
        mission_fields(value)
        strings(value["questions"])
    elif kind == "template_generate":
        fields(value, ("name", "description", "steps"))
        text(value["name"], 200, True)
        text(value["description"])
        steps = value["steps"]
        if not isinstance(steps, list) or not 1 <= len(steps) <= 30:
            raise ProtocolError("模板必须包含 1–30 步。")
        graph = {}
        for step in steps:
            fields(step, ("key", "title", "content", "acceptance_criteria", "type", "priority", "tags", "prerequisite_keys"))
            mission_fields(step)
            key = step["key"]
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_]{1,50}", key) or key in graph:
                raise ProtocolError("步骤 key 无效或重复。")
            strings(step["prerequisite_keys"], 30, 50)
            if len(set(step["prerequisite_keys"])) != len(step["prerequisite_keys"]):
                raise ProtocolError("前置步骤重复。")
            graph[key] = step["prerequisite_keys"]
        visited, visiting = set(), set()

        def visit(key):
            if key not in graph or key in visiting:
                raise ProtocolError("前置步骤不存在或形成循环。")
            if key in visited:
                return
            visiting.add(key)
            for prerequisite in graph[key]:
                visit(prerequisite)
            visiting.remove(key)
            visited.add(key)

        for key in graph:
            visit(key)
    elif kind == "review_assist":
        fields(value, ("criteria", "missing_materials", "checks", "comment"))
        if not isinstance(value["criteria"], list) or not 1 <= len(value["criteria"]) <= 50:
            raise ProtocolError("验收分析必须包含 1–50 项。")
        for criterion in value["criteria"]:
            fields(criterion, ("criterion", "assessment", "evidence", "unverified"))
            text(criterion["criterion"], 2000, True)
            if criterion["assessment"] not in ("supported", "contradicted", "insufficient"):
                raise ProtocolError("验收判断无效。")
            evidence = criterion["evidence"]
            if not isinstance(evidence, list) or len(evidence) > 30:
                raise ProtocolError("依据列表格式或数量错误。")
            if criterion["assessment"] != "insufficient" and not evidence:
                raise ProtocolError("支持或矛盾判断必须引用已提供的材料。")
            for reference in evidence:
                fields(reference, ("path", "quote"))
                text(reference["path"], 500, True)
                text(reference["quote"], 2000, True)
            strings(criterion["unverified"])
        strings(value["missing_materials"])
        strings(value["checks"])
        text(value["comment"], 10000)
    else:
        raise ProtocolError("不支持的辅助类型。")
    return value


def validate_evidence(kind, value, snapshot):
    """证据必须定位输入 JSON 字段并逐字包含引用，不能用生成的来源冒充已读材料。"""
    if kind != "review_assist":
        return
    for criterion in value["criteria"]:
        for reference in criterion["evidence"]:
            path = reference["path"]
            if not path.startswith("/"):
                raise ProtocolError("证据路径必须是输入 JSON Pointer。")
            node = snapshot
            try:
                for part in path[1:].split("/"):
                    key = part.replace("~1", "/").replace("~0", "~")
                    node = node[int(key)] if isinstance(node, list) else node[key]
            except (KeyError, ValueError, TypeError, IndexError):
                raise ProtocolError("证据引用的输入字段不存在。")
            if not isinstance(node, str) or reference["quote"] not in node:
                raise ProtocolError("证据摘录不在所引用的输入字段中。")

import json
from pathlib import Path


DATASET_DIR = Path(__file__).with_name("datasets")
TASK_FILES = {
    "classification": "classification.jsonl",
    "reply_suggestion": "reply_suggestion.jsonl",
    "knowledge_qa": "knowledge_qa.jsonl",
    "refund": "refund_cases.json",
    "presale": "presale_cases.jsonl",
}


def load_dataset(task: str) -> list[dict]:
    """按任务名加载并校验对应的 JSONL 评测样本。"""
    # 数据集统一用 JSONL：一行就是一条样本，便于手工维护和逐条定位问题。
    file_name = TASK_FILES.get(task)
    if file_name is None:
        raise ValueError(f"unsupported eval task: {task}")

    dataset_path = DATASET_DIR / file_name
    if dataset_path.suffix == ".json":
        cases = json.loads(dataset_path.read_text(encoding="utf-8"))
        if not isinstance(cases, list):
            raise ValueError(f"{task} dataset must be an array")
        for index, case in enumerate(cases, 1):
            validate_case(task, case, index)
        return cases

    cases = []
    with dataset_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            validate_case(task, case, line_number)
            cases.append(case)
    return cases


def load_suite(suite: str) -> dict[str, list[dict]]:
    """加载一个评测套件下的全部任务数据集。"""
    if suite == "core":
        tasks = ("classification", "reply_suggestion", "knowledge_qa")
    elif suite == "refund":
        tasks = ("refund",)
    elif suite == "presale":
        tasks = ("presale",)
    else:
        raise ValueError(f"unsupported eval suite: {suite}")
    return {task: load_dataset(task) for task in tasks}


def validate_case(task: str, case: dict, line_number: int | None = None) -> None:
    """校验单条样本是否满足该任务运行所需的最小结构。"""
    # 先在加载阶段固定样本契约，避免评测跑到一半才因为字段缺失失败。
    label = f"{task}:{line_number}" if line_number is not None else task
    for field in ("id", "input", "expected", "tags"):
        if field not in case:
            raise ValueError(f"{label} missing required field: {field}")

    if not isinstance(case["input"], dict):
        raise ValueError(f"{label} input must be an object")
    if not isinstance(case["expected"], dict):
        raise ValueError(f"{label} expected must be an object")
    if not isinstance(case["tags"], list):
        raise ValueError(f"{label} tags must be a list")

    if task == "classification":
        # 不同任务的期望结构不同，这里只校验各自真正依赖的字段。
        for field in ("problem_type", "priority", "user_sentiment"):
            if field not in case["expected"]:
                raise ValueError(f"{label} expected missing field: {field}")
    elif task == "reply_suggestion":
        for field in ("expected_tools", "forbidden_tools"):
            if field not in case or not isinstance(case[field], list):
                raise ValueError(f"{label} missing list field: {field}")
    elif task == "knowledge_qa":
        if "expected_sources" not in case["expected"]:
            raise ValueError(f"{label} expected missing field: expected_sources")
    elif task == "refund":
        for field in ("expected_intent", "expected_action", "forbidden_claims"):
            if field not in case["expected"]:
                raise ValueError(f"{label} expected missing field: {field}")
        if not isinstance(case.get("required_tools"), list):
            raise ValueError(f"{label} missing list field: required_tools")
    elif task == "presale":
        for field in ("action", "product_sku_ids", "comparison", "forbidden_claims"):
            if field not in case["expected"]:
                raise ValueError(f"{label} expected missing field: {field}")
        if not isinstance(case.get("required_tools"), list):
            raise ValueError(f"{label} missing list field: required_tools")

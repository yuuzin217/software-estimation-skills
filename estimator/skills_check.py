"""Agent Skills の構成検証。

公式の skills-ref がインストールされていれば、それも実行する。
未インストールのときは構成・参照・frontmatterの代替検証だけを行う。
"""

import importlib
import re
from pathlib import Path

MAX_DESCRIPTION = 1024
MAX_COMPATIBILITY = 500
MAX_LINES = 500
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
PATH_RE = re.compile(r"(?<![\w./-])(?:references|scripts|assets)/[A-Za-z0-9_./-]+")


def validate_skills(root: Path) -> list[str]:
    skills_root = root / ".agents" / "skills"
    errors: list[str] = []
    if not skills_root.is_dir():
        return [f"Skillディレクトリがありません: {skills_root}"]
    skill_dirs = [path for path in sorted(skills_root.iterdir()) if path.is_dir()]
    if not skill_dirs:
        return ["Skillが1件もありません。"]
    for skill_dir in skill_dirs:
        errors.extend(_validate_skill(skill_dir))
        errors.extend(_official(skill_dir))
    return errors


def _validate_skill(skill_dir: Path) -> list[str]:
    errors = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return [f"{skill_dir.name}: SKILL.md がありません。"]
    text = skill_md.read_text(encoding="utf-8")
    line_count = text.count("\n") + (0 if text.endswith("\n") else 1)
    if line_count > MAX_LINES:
        errors.append(f"{skill_dir.name}: SKILL.md が {line_count} 行あり、500行を超えています。")
    try:
        frontmatter, _body = _frontmatter(text)
    except ValueError as exc:
        return [f"{skill_dir.name}: {exc}"]
    name = frontmatter.get("name")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        errors.append(f"{skill_dir.name}: name が小文字・数字・ハイフンの規則を満たしません。")
    elif name != skill_dir.name:
        errors.append(f"{skill_dir.name}: ディレクトリ名と name が一致しません。")
    description = frontmatter.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append(f"{skill_dir.name}: description が空です。")
    elif len(description) > MAX_DESCRIPTION:
        errors.append(f"{skill_dir.name}: description が1024文字を超えています。")
    compatibility = frontmatter.get("compatibility")
    if compatibility is not None and (not isinstance(compatibility, str) or len(compatibility) > MAX_COMPATIBILITY):
        errors.append(f"{skill_dir.name}: compatibility が不正です。")
    allowed = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
    extra = set(frontmatter) - allowed
    if extra:
        errors.append(f"{skill_dir.name}: 公式仕様外のfrontmatterです: {', '.join(sorted(extra))}")
    for link in LINK_RE.findall(text):
        if link.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if link.startswith("/"):
            errors.append(f"{skill_dir.name}: 絶対パスの参照は使えません（{link}）。")
            continue
        target = (skill_dir / link).resolve()
        if not target.exists():
            errors.append(f"{skill_dir.name}: 参照先がありません（{link}）。")
    for match in PATH_RE.findall(text):
        if match.endswith("/"):
            continue
        target = skill_dir / match
        if not target.exists():
            errors.append(f"{skill_dir.name}: パスが実在しません（{match}）。")
    return errors


def _frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        raise ValueError("SKILL.md は YAML frontmatter で始めてください。")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise ValueError("frontmatter の終端がありません。")
    raw = text[4:end]
    body = text[end + 5 :]
    return _simple_yaml(raw), body


def _simple_yaml(raw: str) -> dict:
    """このリポジトリのfrontmatterに限った最小パーサー。"""
    data: dict = {}
    current = None
    for line in raw.splitlines():
        if not line.strip():
            continue
        if line.startswith("  ") and current:
            key, value = _split_pair(line.strip())
            data[current][key] = _unquote(value)
            continue
        key, value = _split_pair(line)
        if value == "":
            data[key] = {}
            current = key
        else:
            data[key] = _unquote(value)
            current = None
    return data


def _split_pair(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ValueError(f"YAMLの行を解釈できません: {line}")
    key, value = line.split(":", 1)
    return key.strip(), value.strip()


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _official(skill_dir: Path) -> list[str]:
    try:
        validator = importlib.import_module("skills_ref.validator")
    except ImportError:
        return []
    return [f"{skill_dir.name}: {message}" for message in validator.validate(skill_dir)]

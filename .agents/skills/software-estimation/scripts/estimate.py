#!/usr/bin/env python3
"""見積もり計算の薄いラッパー。

このSkillディレクトリ単体では動かない。リポジトリ全体の estimator パッケージが必要。
"""

import sys
from pathlib import Path


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "estimator" / "__init__.py").is_file():
            return parent
    raise SystemExit(
        "estimator パッケージが見つかりません。software-estimation-skills を展開した状態で実行してください。"
    )


def main() -> int:
    root = _repo_root()
    sys.path.insert(0, str(root))
    from estimator.cli import main as cli_main

    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())

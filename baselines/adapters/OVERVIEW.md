# baselines/adapters/

統一 I/O アダプタの置き場（将来用）。

現在の実装は `baselines/runner/adapters/` にある：
- `rust_mining.py` — Rust バイナリ（comparative_mining）へのアダプタ
- `spmf.py` — SPMF Java ライブラリへのアダプタ

新しい外部ライブラリを追加する場合は `baselines/runner/adapters/` に実装し、
必要に応じてここに薄いラッパを置く。

"""
合成 CICIDS データ生成器。

CICIDS 2017/2018 の構造を模擬し、ATT&CK 技術 ID をアイテムとした
時間ビン × ネットワークセグメント形式のトランザクションデータを生成する。
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Tuple


# --- ATT&CK 技術 ID (整数エンコーディング) ---
# 実際の ATT&CK ID と対応するマッピング
TECHNIQUE_MAP = {
    1: "T1059",   # Command and Scripting Interpreter
    2: "T1071",   # Application Layer Protocol
    3: "T1053",   # Scheduled Task/Job
    4: "T1078",   # Valid Accounts
    5: "T1021",   # Remote Services
    6: "T1055",   # Process Injection
    7: "T1105",   # Ingress Tool Transfer
    8: "T1569",   # System Services
    9: "T1547",   # Boot or Logon Autostart Execution
    10: "T1036",  # Masquerading
    11: "T1027",  # Obfuscated Files or Information
    12: "T1070",  # Indicator Removal
    13: "T1082",  # System Information Discovery
    14: "T1083",  # File and Directory Discovery
    15: "T1057",  # Process Discovery
    16: "T1018",  # Remote System Discovery
    17: "T1560",  # Archive Collected Data
    18: "T1041",  # Exfiltration Over C2 Channel
    19: "T1486",  # Data Encrypted for Impact
    20: "T1498",  # Network Denial of Service
}

# 技術 ID の逆マッピング
REVERSE_TECHNIQUE_MAP = {v: k for k, v in TECHNIQUE_MAP.items()}

# --- 攻撃グループの TTP プロファイル ---
APT_PROFILES = {
    "APT28": {
        "techniques": [1, 2, 4, 6, 7, 10, 11, 13, 14, 18],
        "description": "Fancy Bear - Spear phishing + credential theft + lateral movement",
    },
    "APT29": {
        "techniques": [1, 2, 3, 5, 7, 9, 11, 12, 17, 18],
        "description": "Cozy Bear - Stealthy persistence + data exfiltration",
    },
    "Lazarus": {
        "techniques": [1, 6, 7, 8, 10, 11, 19, 20],
        "description": "Lazarus Group - Destructive malware + ransomware",
    },
}

# --- ネットワークセグメント ---
SEGMENTS = ["DMZ", "Internal", "Server", "IoT"]


def generate_background_traffic(
    n_transactions: int,
    n_techniques: int = 20,
    benign_rate: float = 0.3,
    rng: random.Random = None,
) -> List[List[int]]:
    """バックグラウンドトラフィック（良性 + ノイズ）を生成する。"""
    if rng is None:
        rng = random.Random(42)

    transactions = []
    benign_techniques = [13, 14, 15, 16]  # Discovery は正常でも発生
    for _ in range(n_transactions):
        tx = []
        # 良性トラフィック
        if rng.random() < benign_rate:
            n_items = rng.randint(1, 3)
            tx = rng.sample(benign_techniques, min(n_items, len(benign_techniques)))
        # ランダムノイズ
        if rng.random() < 0.1:
            noise_items = rng.sample(range(1, n_techniques + 1), rng.randint(1, 2))
            tx.extend(noise_items)
        transactions.append(sorted(set(tx)))
    return transactions


def inject_campaign(
    transactions: List[List[int]],
    apt_name: str,
    start_bin: int,
    duration: int,
    intensity: float = 0.8,
    segment_focus: str = "Internal",
    rng: random.Random = None,
) -> Dict:
    """攻撃キャンペーンを注入する。"""
    if rng is None:
        rng = random.Random(42)

    profile = APT_PROFILES[apt_name]
    techniques = profile["techniques"]
    end_bin = min(start_bin + duration, len(transactions))

    injected_count = 0
    for t in range(start_bin, end_bin):
        if rng.random() < intensity:
            # 攻撃技術のサブセットを注入
            n_techs = rng.randint(max(2, len(techniques) // 2), len(techniques))
            attack_techs = rng.sample(techniques, n_techs)
            transactions[t] = sorted(set(transactions[t] + attack_techs))
            injected_count += 1

    return {
        "apt_name": apt_name,
        "start_bin": start_bin,
        "end_bin": end_bin,
        "duration": duration,
        "intensity": intensity,
        "segment": segment_focus,
        "techniques": techniques,
        "injected_count": injected_count,
    }


def generate_synthetic_cicids(
    n_transactions: int = 500,
    seed: int = 42,
) -> Tuple[List[List[int]], Dict]:
    """
    CICIDS 構造を模擬した合成データを生成する。

    Returns:
        transactions: トランザクションのリスト
        ground_truth: 注入したキャンペーンのメタデータ
    """
    rng = random.Random(seed)

    # バックグラウンドトラフィック生成
    transactions = generate_background_traffic(n_transactions, rng=rng)

    campaigns = []

    # Campaign 1: APT28 (t=50-100)
    c1 = inject_campaign(
        transactions, "APT28", start_bin=50, duration=50,
        intensity=0.85, rng=rng,
    )
    campaigns.append(c1)

    # Campaign 2: APT29 (t=150-220)
    c2 = inject_campaign(
        transactions, "APT29", start_bin=150, duration=70,
        intensity=0.75, rng=rng,
    )
    campaigns.append(c2)

    # Campaign 3: Lazarus (t=300-350)
    c3 = inject_campaign(
        transactions, "Lazarus", start_bin=300, duration=50,
        intensity=0.90, rng=rng,
    )
    campaigns.append(c3)

    # Campaign 4: APT28 再攻撃 (t=400-430, 短期・高強度)
    c4 = inject_campaign(
        transactions, "APT28", start_bin=400, duration=30,
        intensity=0.95, rng=rng,
    )
    campaigns.append(c4)

    ground_truth = {
        "n_transactions": n_transactions,
        "seed": seed,
        "technique_map": TECHNIQUE_MAP,
        "apt_profiles": {k: v["techniques"] for k, v in APT_PROFILES.items()},
        "campaigns": campaigns,
    }

    return transactions, ground_truth


def save_transactions(transactions: List[List[int]], path: str) -> None:
    """トランザクションを Apriori-Window 入力形式で保存する。"""
    with open(path, "w", encoding="utf-8") as f:
        for tx in transactions:
            if tx:
                f.write(" ".join(str(item) for item in tx) + "\n")
            else:
                f.write("\n")


def save_ground_truth(ground_truth: Dict, path: str) -> None:
    """グラウンドトゥルースを JSON で保存する。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ground_truth, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    out_dir = Path(__file__).parent / "data"
    out_dir.mkdir(exist_ok=True)

    transactions, gt = generate_synthetic_cicids(n_transactions=500, seed=42)
    save_transactions(transactions, str(out_dir / "synthetic_cicids.txt"))
    save_ground_truth(gt, str(out_dir / "ground_truth.json"))

    print(f"Generated {len(transactions)} transactions")
    print(f"Campaigns: {len(gt['campaigns'])}")
    for c in gt["campaigns"]:
        print(f"  {c['apt_name']}: t={c['start_bin']}-{c['end_bin']}, "
              f"injected={c['injected_count']}")

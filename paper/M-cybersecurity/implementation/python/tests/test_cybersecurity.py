"""
Paper M: Cybersecurity テスト。

合成データ生成、ATT&CK アダプタ、密集パターン検出、
キャンペーン推定、脅威帰属の各コンポーネントをテストする。
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

# テスト対象モジュールへのパス
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "apriori_window_suite" / "python"))

from synthetic_cicids import (
    APT_PROFILES,
    TECHNIQUE_MAP,
    generate_background_traffic,
    generate_synthetic_cicids,
    inject_campaign,
    save_ground_truth,
    save_transactions,
)

from attack_adapter import (
    attribute_campaigns,
    build_item_occurrence_map,
    compute_co_occurrence_timestamps,
    estimate_campaigns,
    find_dense_attack_patterns,
    itemset_to_attack_names,
    load_transactions,
)


# ============================================================
# 合成データ生成テスト
# ============================================================


class TestSyntheticData:
    def test_background_traffic_length(self):
        txs = generate_background_traffic(100)
        assert len(txs) == 100

    def test_background_traffic_items_valid(self):
        txs = generate_background_traffic(200, n_techniques=20)
        for tx in txs:
            for item in tx:
                assert 1 <= item <= 20

    def test_generate_synthetic_cicids_shape(self):
        txs, gt = generate_synthetic_cicids(n_transactions=500, seed=42)
        assert len(txs) == 500
        assert len(gt["campaigns"]) == 4

    def test_campaign_injection_increases_items(self):
        txs = generate_background_traffic(200)
        total_before = sum(len(tx) for tx in txs)
        inject_campaign(txs, "APT28", start_bin=50, duration=50, intensity=1.0)
        total_after = sum(len(tx) for tx in txs)
        assert total_after > total_before

    def test_campaign_ground_truth_metadata(self):
        _, gt = generate_synthetic_cicids(n_transactions=500, seed=123)
        for c in gt["campaigns"]:
            assert "apt_name" in c
            assert "start_bin" in c
            assert "end_bin" in c
        # 少なくとも範囲内のキャンペーンは注入されているはず
        in_range = [c for c in gt["campaigns"] if c["start_bin"] < 500]
        assert any(c["injected_count"] > 0 for c in in_range)

    def test_save_load_roundtrip(self):
        txs, gt = generate_synthetic_cicids(n_transactions=100, seed=99)
        with tempfile.TemporaryDirectory() as tmp:
            tx_path = str(Path(tmp) / "txs.txt")
            gt_path = str(Path(tmp) / "gt.json")
            save_transactions(txs, tx_path)
            save_ground_truth(gt, gt_path)

            loaded = load_transactions(tx_path)
            assert len(loaded) == len(txs)

            with open(gt_path) as f:
                loaded_gt = json.load(f)
            assert loaded_gt["n_transactions"] == 100

    def test_technique_map_completeness(self):
        assert len(TECHNIQUE_MAP) == 20
        for k, v in TECHNIQUE_MAP.items():
            assert isinstance(k, int)
            assert v.startswith("T")

    def test_apt_profiles_valid(self):
        for name, profile in APT_PROFILES.items():
            assert len(profile["techniques"]) >= 5
            for t in profile["techniques"]:
                assert t in TECHNIQUE_MAP


# ============================================================
# アダプタテスト
# ============================================================


class TestAttackAdapter:
    @pytest.fixture
    def sample_transactions(self):
        txs, _ = generate_synthetic_cicids(n_transactions=500, seed=42)
        return txs

    def test_build_item_occurrence_map(self, sample_transactions):
        item_map = build_item_occurrence_map(sample_transactions)
        assert len(item_map) > 0
        for item, tids in item_map.items():
            assert tids == sorted(tids)
            assert len(set(tids)) == len(tids)

    def test_co_occurrence_timestamps(self, sample_transactions):
        item_map = build_item_occurrence_map(sample_transactions)
        # APT28 の技術ペア (1, 2) が共起するはず
        ts = compute_co_occurrence_timestamps((1, 2), item_map)
        assert len(ts) > 0
        assert ts == sorted(ts)

    def test_co_occurrence_empty_for_rare_combo(self, sample_transactions):
        item_map = build_item_occurrence_map(sample_transactions)
        # 存在しないアイテム
        ts = compute_co_occurrence_timestamps((999,), item_map)
        assert ts == []

    def test_itemset_to_attack_names(self):
        names = itemset_to_attack_names((1, 2, 3))
        assert names == ["T1059", "T1071", "T1053"]

    def test_itemset_unknown_item(self):
        names = itemset_to_attack_names((999,))
        assert "Unknown" in names[0]


# ============================================================
# 密集パターン検出テスト
# ============================================================


class TestDensePatternDetection:
    @pytest.fixture
    def dense_results(self):
        txs, _ = generate_synthetic_cicids(n_transactions=500, seed=42)
        return find_dense_attack_patterns(
            txs, window_size=20, threshold=10, max_length=4
        )

    def test_dense_patterns_found(self, dense_results):
        assert len(dense_results) > 0

    def test_dense_patterns_contain_multi_item(self, dense_results):
        multi = {k: v for k, v in dense_results.items() if len(k) >= 2}
        assert len(multi) > 0, "Multi-technique dense patterns should exist"

    def test_dense_intervals_valid(self, dense_results):
        for itemset, intervals in dense_results.items():
            assert len(intervals) > 0
            for s, e in intervals:
                assert s <= e

    def test_dense_patterns_in_campaign_windows(self, dense_results):
        """密集パターンがキャンペーン注入区間に存在するか確認。"""
        campaign_ranges = [(50, 100), (150, 220), (300, 350), (400, 430)]
        multi = {k: v for k, v in dense_results.items() if len(k) >= 2}
        found_in_campaign = False
        for itemset, intervals in multi.items():
            for s, e in intervals:
                for cs, ce in campaign_ranges:
                    if s <= ce and e >= cs:
                        found_in_campaign = True
                        break
        assert found_in_campaign, "Dense patterns should overlap with campaign windows"

    def test_apriori_property_holds(self, dense_results):
        """Apriori 性質: サブセットも密集区間を持つ。"""
        for itemset in dense_results:
            if len(itemset) >= 2:
                for item in itemset:
                    assert (item,) in dense_results, (
                        f"Singleton ({item},) should be in results "
                        f"if superset {itemset} is present"
                    )


# ============================================================
# キャンペーン推定テスト
# ============================================================


class TestCampaignEstimation:
    @pytest.fixture
    def campaigns(self):
        txs, _ = generate_synthetic_cicids(n_transactions=500, seed=42)
        patterns = find_dense_attack_patterns(
            txs, window_size=20, threshold=10, max_length=4
        )
        return estimate_campaigns(patterns, overlap_threshold=0.3)

    def test_campaigns_found(self, campaigns):
        assert len(campaigns) > 0

    def test_campaign_structure(self, campaigns):
        for c in campaigns:
            assert "campaign_id" in c
            assert "techniques" in c
            assert "start" in c
            assert "end" in c
            assert c["start"] <= c["end"]

    def test_campaigns_have_technique_names(self, campaigns):
        for c in campaigns:
            assert "technique_names" in c
            assert len(c["technique_names"]) > 0

    def test_campaigns_sorted_by_start(self, campaigns):
        starts = [c["start"] for c in campaigns]
        assert starts == sorted(starts)


# ============================================================
# 脅威帰属テスト
# ============================================================


class TestThreatAttribution:
    @pytest.fixture
    def attributed(self):
        txs, _ = generate_synthetic_cicids(n_transactions=500, seed=42)
        patterns = find_dense_attack_patterns(
            txs, window_size=20, threshold=10, max_length=4
        )
        campaigns = estimate_campaigns(patterns, overlap_threshold=0.3)
        return attribute_campaigns(campaigns)

    def test_attribution_results_exist(self, attributed):
        assert len(attributed) > 0

    def test_attribution_scores_valid(self, attributed):
        for r in attributed:
            assert "attribution_scores" in r
            for apt, score in r["attribution_scores"].items():
                assert 0.0 <= score <= 1.0

    def test_best_match_exists(self, attributed):
        for r in attributed:
            assert r["best_match"] in APT_PROFILES

    def test_best_score_positive(self, attributed):
        for r in attributed:
            assert r["best_score"] > 0.0

    def test_attribution_matches_injected_apt(self, attributed):
        """少なくとも一つのキャンペーンが注入した APT に帰属されるか。"""
        injected_apts = {"APT28", "APT29", "Lazarus"}
        matched = {r["best_match"] for r in attributed}
        assert len(matched & injected_apts) > 0, (
            f"At least one injected APT should be matched. Got: {matched}"
        )


# ============================================================
# エッジケーステスト
# ============================================================


class TestEdgeCases:
    def test_empty_transactions(self):
        results = find_dense_attack_patterns(
            [[] for _ in range(100)],
            window_size=10, threshold=5, max_length=3
        )
        assert len(results) == 0

    def test_single_item_transactions(self):
        txs = [[1] for _ in range(50)]
        results = find_dense_attack_patterns(
            txs, window_size=10, threshold=5, max_length=3
        )
        # 単体アイテムの密集区間は存在するが multi-item はない
        multi = {k: v for k, v in results.items() if len(k) >= 2}
        assert len(multi) == 0

    def test_small_window(self):
        txs, _ = generate_synthetic_cicids(n_transactions=500, seed=42)
        results = find_dense_attack_patterns(
            txs, window_size=5, threshold=3, max_length=3
        )
        assert len(results) > 0

    def test_high_threshold_reduces_patterns(self):
        txs, _ = generate_synthetic_cicids(n_transactions=500, seed=42)
        r_low = find_dense_attack_patterns(
            txs, window_size=20, threshold=5, max_length=3
        )
        r_high = find_dense_attack_patterns(
            txs, window_size=20, threshold=15, max_length=3
        )
        assert len(r_high) <= len(r_low)

    def test_campaign_estimation_empty(self):
        campaigns = estimate_campaigns({})
        assert campaigns == []

    def test_attribution_empty(self):
        results = attribute_campaigns([])
        assert results == []

"""Content pairing and human-audit failure paths, with explicitly synthetic test ratings."""

from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from collie.contracts import AlertMessage, assert_no_hidden_state
from collie.data.alerts.audit import (
    CRITERIA,
    Rating,
    audit_ratings,
    cohen_kappa,
    default_audit_config,
    review_samples,
)
from collie.data.alerts.bank import load_alert_bank
from collie.data.alerts.controls import (
    VARIANTS,
    ContentVariantSet,
    PromptChannels,
    content_contrast,
    no_alert,
    numeric_history_removed,
    render_content_controls,
)
from tools.build_alert_bank import review_sample

ROOT = Path(__file__).resolve().parents[1]
CONFIG = default_audit_config()


@pytest.fixture
def variants():
    # 五种文本共享一个调用机会, 作为时间戳、词序、长度和触发轨迹测试的基准。
    return render_content_controls(
        AlertMessage("original", 7, "Customer orders may rise next month."),
        trigger_trace=[{"period": 7, "reason": "alert"}],
        wrong_text="Cargo is waiting at the port.",
        true_family="demand_level",
        wrong_family="transit_pause",
        seed=42,
        length_tolerance=CONFIG["length_tolerance"],
    )


def test_content_variants_share_timestamp(variants):
    assert {variants.message(k).period for k in VARIANTS} == {7}
    assert len(variants.trigger_trace_hash) == 64
    assert_no_hidden_state(variants)
    assert content_contrast(variants)[0].period == content_contrast(variants)[1].period


def test_cross_timestamp_contrast_raises(variants):
    # 主动混入另一个时间点的消息, 要求抛异常, 而不是仅打印警告后继续比较。
    messages = {k: variants.message(k) for k in VARIANTS}
    messages["wrong"] = replace(messages["wrong"], period=8)
    with pytest.raises(ValueError, match="cross-timestamp"):
        ContentVariantSet.from_messages(
            messages, dict.fromkeys(VARIANTS, variants.trigger_trace_hash)
        )
    with pytest.raises(TypeError):
        content_contrast(list(messages.values()))


def test_cross_trigger_trace_contrast_raises(variants):
    hashes = dict.fromkeys(VARIANTS, variants.trigger_trace_hash)
    hashes["wrong"] = "a" * 64
    with pytest.raises(ValueError, match="cross-trigger"):
        ContentVariantSet.from_messages({k: variants.message(k) for k in VARIANTS}, hashes)


def test_masked_and_neutral_length_matched(variants):
    texts = dict(variants.texts)
    for key in ("masked", "neutral"):
        assert abs(len(texts[key]) - len(texts["true"])) <= CONFIG["length_tolerance"]
        assert texts[key] != texts["true"]


def test_shuffle_preserves_words(variants):
    texts = dict(variants.texts)
    assert Counter(texts["shuffled"].split()) == Counter(texts["true"].split())
    assert texts["shuffled"] != texts["true"]


def test_controls_are_deterministic(variants):
    recreated = render_content_controls(
        variants.message("true"),
        trigger_trace=[{"period": 7, "reason": "alert"}],
        wrong_text=dict(variants.texts)["wrong"],
        true_family="demand_level",
        wrong_family="transit_pause",
        seed=42,
    )
    assert variants == recreated


def test_separate_history_and_channel_ablations(variants):
    # 分别检查历史消融与告警通道消融, 并确认原始提示对象未被修改。
    channels = PromptChannels(variants.message("true"), ("sales: 40", "inventory: 20"))
    assert numeric_history_removed(channels) == PromptChannels(channels.alert, ())
    assert no_alert(channels) == PromptChannels(None, channels.numeric_history)
    assert channels.numeric_history


def test_mutable_variant_input_rejected(variants):
    with pytest.raises(ValueError):
        replace(variants, texts=list(variants.texts))


@pytest.fixture
def audit_inputs():
    # 评分完全是测试合成数据, 只用于验证统计与校验逻辑, 不能作为 P3/P4 的真实审核结果。
    bank = load_alert_bank(ROOT / "collie/data/alerts/templates")
    samples = review_samples(
        bank, review_sample(bank, CONFIG["render_sample_size"]), CONFIG["render_seed"]
    )
    # Synthetic ratings exist only in tests, never in the human score artifact.
    ratings = tuple(
        Rating(sample, rater, criterion, 4 + i % 2)
        for i, sample in enumerate(samples)
        for rater in CONFIG["raters"]
        for criterion in CRITERIA
    )
    return samples, ratings


def test_every_template_has_two_scores_per_criterion(audit_inputs):
    samples, ratings = audit_inputs
    assert len(samples) == 204
    result = audit_ratings(samples, ratings, CONFIG)
    assert len(result["retained_template_ids"]) == 180
    assert set(result["kappa"].values()) == {1.0}
    with pytest.raises(ValueError, match="missing 1 ratings"):
        audit_ratings(samples, ratings[:-1], CONFIG)


def test_leakage_failure_removes_template(audit_inputs):
    # 只降低其中一位评分者的泄漏分数, 另一位同意也不能阻止模板被剔除。
    samples, ratings = audit_inputs
    ratings = list(ratings)
    index = next(i for i, r in enumerate(ratings) if r.criterion == "no_leakage")
    ratings[index] = replace(ratings[index], score=3)
    result = audit_ratings(samples, ratings, CONFIG)
    removed = samples[ratings[index].sample_id][0].template_id
    assert removed not in result["retained_template_ids"]
    assert result["removals"][0]["template_id"] == removed
    assert result["status"] == "needs_review"


def test_rendered_sample_leakage_removes_base_template(audit_inputs):
    samples, ratings = audit_inputs
    ratings = [
        replace(r, score=1)
        if r.sample_id.startswith("render:") and r.criterion == "no_leakage" and r.rater == "P4"
        else r
        for r in ratings
    ]
    result = audit_ratings(samples, ratings, CONFIG)
    assert len({r["template_id"] for r in result["removals"]}) == 24


def test_low_kappa_selects_120_and_requires_deviation(audit_inputs):
    # 构造系统性分歧以触发缩减; 选出 120 条后仍须记录偏离并完成审核。
    samples, ratings = audit_inputs
    ratings = [replace(r, score=9 - r.score) if r.rater == "P4" else r for r in ratings]
    result = audit_ratings(samples, ratings, CONFIG)
    assert result["fallback_required"] and result["dated_deviation_required"]
    assert len(result["retained_template_ids"]) == 120
    assert len(result["fallback_removed_template_ids"]) == 60
    assert result["status"] == "needs_review"


def test_duplicate_score_and_invalid_score_rejected(audit_inputs):
    samples, ratings = audit_inputs
    with pytest.raises(ValueError, match="duplicate"):
        audit_ratings(samples, ratings + ratings[:1], CONFIG)
    with pytest.raises(ValueError, match="1 to 5"):
        replace(ratings[0], score=True)


def test_kappa_known_table_and_degenerate_case():
    assert cohen_kappa([1, 1, 2, 2], [1, 2, 1, 2]) == 0
    assert cohen_kappa([4, 4], [4, 4]) is None
    assert cohen_kappa([1, 2], [2, 1]) == -1


def test_report_does_not_pass_missing_human_ratings(tmp_path):
    from tools.score_alert_templates import main

    assert main(["--report", "--ratings", str(tmp_path / "missing.csv")]) == 2


def test_blank_sheet_never_counts_as_completed_audit(tmp_path):
    from tools.score_alert_templates import main

    path = tmp_path / "ratings.csv"
    assert main(["--prepare", "--ratings", str(path)]) == 0
    assert main(["--report", "--ratings", str(path)]) == 2
    assert main(["--prepare", "--ratings", str(path)]) == 2  # cannot overwrite scores


def test_stale_rating_sheet_rejected(tmp_path, audit_inputs):
    # 评分表中的文本一旦与当前模板不一致, 旧评分必须失效, 不能沿用到修改后的刺激。
    import csv

    from collie.data.alerts.audit import read_ratings, write_rating_sheet

    samples, _ = audit_inputs
    path = tmp_path / "ratings.csv"
    write_rating_sheet(path, samples, CONFIG["raters"])
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    rows[0]["text"] = "Changed template after review"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="stale"):
        read_ratings(path, samples)


def test_undefined_kappa_never_passes(audit_inputs):
    # 双方始终给相同常数分时, 机会一致率也为 1; 此时 κ 不可定义, 不能报告为完美一致。
    samples, ratings = audit_inputs
    ratings = [replace(r, score=5) for r in ratings]
    result = audit_ratings(samples, ratings, CONFIG | {"status": "confirmed"})
    assert result["undefined_kappa"]
    assert result["status"] == "needs_review"


def test_completed_non_degenerate_audit_can_pass(audit_inputs):
    samples, ratings = audit_inputs
    result = audit_ratings(samples, ratings, CONFIG | {"status": "confirmed"})
    assert result["status"] == "ready"


def test_episode_runner_demo(capsys):
    # 调用真正的 EpisodeRunner 演示, 检查四个条件和各内容对照的配对结果。
    from tools.build_alert_bank import replay_one_seed

    report = replay_one_seed(show_diff=True)
    assert report["episode_runner_replays"] == 19
    assert report["constant_controller_observations_equal_excluding_alert"]
    assert len(report["conditions"]) == 4
    for content_set in report["content_sets"]:
        assert set(content_set["diff"]) == set(VARIANTS)
        assert all(
            not row["timestamp_changed"]
            and not row["exogenous_changed"]
            and not row["trigger_trace_changed"]
            for row in content_set["diff"].values()
        )
    capsys.readouterr()


def test_prepare_defaults_to_stdout_without_creating_files(tmp_path, monkeypatch, capsys):
    # 默认输出只走终端, 防止运行工具时额外修改用户提交清单之外的文件。
    import csv
    import io

    from tools.score_alert_templates import main

    monkeypatch.chdir(tmp_path)
    assert main(["--prepare"]) == 0
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert len(rows) == 2040
    assert all(row["score"] == "" for row in rows)
    assert list(tmp_path.iterdir()) == []


def test_default_report_does_not_need_external_config_or_write_files(tmp_path, monkeypatch, capsys):
    from tools.score_alert_templates import main

    monkeypatch.chdir(tmp_path)
    assert main(["--report"]) == 2
    assert "human ratings missing" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_default_configuration_is_a_fresh_pending_copy():
    first = default_audit_config()
    first["raters"].append("unintended third rater")
    second = default_audit_config()
    assert second["raters"] == ["P3", "P4"]
    assert second["status"] == "pending_team_confirmation"

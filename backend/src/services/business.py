"""同一作业员路线改造前后的配对复测，不涉及库存业务。"""
import math
import random
import numpy as np
from scipy import stats


def metadata():
    return {"name": "拣选路线改造复测", "short": "pick-paired", "tagline": "让同一个人的前后差，回答路线是否缩短。", "client": "北岭履约 · 80 名作业员的流程改善试点组", "workflow": "改善员把两周作业均时直接比较，忽略人员结构和熟练度差异。", "pains": ["不同人员混在前后平均中", "缺失配对无法识别", "改善秒数缺少区间与个体差异"], "upstream": "匿名作业员配对测时 BL_route_retest.csv", "downstream": "流程改善组决定路线方案是否扩大复测",
            "entities": ["配对复测样本", "路线改善核验", "班组复测简报"], "dataset_name": "80 名作业员 · 原路线与新路线配对",
            "columns": [{"key": "operator", "label": "匿名作业员", "type": "string"}, {"key": "team", "label": "试点小组", "type": "string"}, {"key": "before", "label": "原路线/秒", "type": "number"}, {"key": "after", "label": "新路线/秒", "type": "number"}],
            "parameters": [{"key": "team", "label": "试点小组", "type": "select", "default": "全部", "options": [{"value": x, "label": x} for x in ["全部", "一组", "二组", "三组", "四组"]]}, {"key": "confidence", "label": "置信度", "type": "select", "default": "0.95", "options": [{"value": str(x), "label": f"{x*100:g}%"} for x in [.9, .95, .99]]}],
            "workbench_title": "人员配对改善核验", "action_label": "计算配对差与区间", "unit": "秒", "accent": "oklch(47% 0.075 248)", "style": "blueprint",
            "seed_story": ["07:50 改善员导入 BL_route_retest.csv，共 80 人。", "08:10 核对 OP-001 至 OP-080 的前后测时完整。", "08:30 选择全部小组、95% 置信区间。", "08:35 执行配对检验，查看平均节省秒数。", "08:50 打开逐人差值，核对反向改善样本。", "09:10 单独选择四组，比较改善差异。", "09:30 导出班组简报，安排负改善人员的路线走查。"],
            "method": "逐人差值 d=before−after；配对 t=mean(d)/(sd(d)/√n)，自由度 n−1；置信区间由 t 分布给出；标准化配对效应 dz=mean(d)/sd(d)。", "limitations": ["顺序、学习效应可能混入路线效果", "不对个人绩效作评价", "需保持复测订单难度和测时口径一致"]}


def seed_records():
    rng = random.Random(1006)
    rows = []
    for i in range(80):
        j = i % 4
        before = rng.gauss(410 + 8 * j, 38)
        improvement = rng.gauss([31, 22, 16, 6][j], 12)
        rows.append({"operator": f"OP-{i+1:03}", "team": ["一组", "二组", "三组", "四组"][j], "before": round(before, 3), "after": round(before - improvement, 3)})
    return rows


def analyze(records, params):
    team = str(params.get("team", "全部"))
    try:
        confidence = float(params.get("confidence", .95))
    except (ValueError, TypeError):
        raise ValueError("置信度只接受 0.90/0.95/0.99")
    if confidence not in (.9, .95, .99) or team not in ("全部", "一组", "二组", "三组", "四组"):
        raise ValueError("未知小组或置信度")
    clean, seen = [], set()
    for r in records:
        try:
            name, group = str(r["operator"]), str(r["team"])
            before, after = float(r["before"]), float(r["after"])
            if name in seen or not all(math.isfinite(x) and x > 0 for x in (before, after)):
                raise ValueError()
            seen.add(name)
            if team == "全部" or team == group:
                clean.append({"operator": name, "team": group, "before": before, "after": after, "difference": before - after})
        except (KeyError, ValueError, TypeError):
            raise ValueError("每人仅能有一条完整配对，测时必须为正有限数")
    if len(clean) < 3:
        raise ValueError("至少需要 3 组完整配对")
    diffs = np.array([r["difference"] for r in clean])
    n, mean, sd = len(diffs), float(diffs.mean()), float(diffs.std(ddof=1))
    if sd <= 1e-12:
        raise ValueError("配对差完全相同，无法估计标准误")
    se, df = sd / math.sqrt(n), n - 1
    t = mean / se
    p = float(2 * stats.t.sf(abs(t), df))
    margin = float(stats.t.ppf((1 + confidence) / 2, df)) * se
    low, high = mean - margin, mean + margin
    rows = [{**r, "before": round(r["before"], 3), "after": round(r["after"], 3), "difference": round(r["difference"], 3), "review": "缩短" if r["difference"] > 0 else "需走查"} for r in sorted(clean, key=lambda r: r["difference"])]
    teams = sorted(set(r["team"] for r in clean))
    return {"summary": f"{n} 人完整配对，平均节省 {mean:.3f} 秒；{confidence*100:g}% 区间 [{low:.3f}, {high:.3f}] 秒。",
            "metrics": [{"label": "平均节省", "value": round(mean, 5), "unit": "秒"}, {"label": "配对 p 值", "value": float(f"{p:.6g}")}, {"label": "配对效应 dz", "value": round(mean / sd, 5)}, {"label": "需走查人员", "value": int(sum(diffs <= 0)), "unit": "人"}],
            "table": {"columns": [{"key": "operator", "label": "匿名人员"}, {"key": "team", "label": "小组"}, {"key": "before", "label": "原路线/秒"}, {"key": "after", "label": "新路线/秒"}, {"key": "difference", "label": "节省/秒"}, {"key": "review", "label": "复测建议"}], "rows": rows},
            "chart": {"type": "bar", "labels": teams, "series": [{"name": "平均节省秒数", "values": [round(float(np.mean([r["difference"] for r in clean if r["team"] == x])), 4) for x in teams]}]},
            "findings": [f"区间下界 {low:.4f} 秒，上界 {high:.4f} 秒；配对差标准差 {sd:.4f} 秒。", f"t={t:.4f}，df={df}，分析小组：{team}。", f"{int(sum(diffs > 0))} 人路线缩短，{int(sum(diffs <= 0))} 人需要走查，不能仅依据总均值推断所有人受益。"], "method": metadata()["method"], "warnings": ["前后顺序固定，不能排除学习效应；结果用于下一轮复测设计。"]}

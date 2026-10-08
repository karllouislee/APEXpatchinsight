from __future__ import annotations

from pathlib import Path

from ..core.aggregation import aggregate
from ..core.comment_cleaner import clean_comments
from ..core.deduplicator import deduplicate_comments
from .insight_generator import deterministic_insights
from ..core.models import STAGE_DONE, Article, CommentAnalysis, PatchChange, Project, RawComment
from ..core.review_manager import build_review_queue

DISCLAIMER = "演示数据为虚构内容，不代表真实 Apex 玩家反馈。"


def build_demo_project(demo_dir: Path) -> Project:
    demo_dir.mkdir(parents=True, exist_ok=True)
    changes = _changes()
    raw, analyses = _comments_and_analyses(changes)
    cleaned = deduplicate_comments(clean_comments(raw))
    canonical_ids = {comment.comment_id for comment in cleaned if comment.is_valid and not comment.duplicate_of}
    analyses = [analysis for analysis in analyses if analysis.comment_id in canonical_ids]
    stats = aggregate(changes, cleaned, analyses)
    insights = deterministic_insights(changes, stats)
    project = Project(
        project_id="demo-apex-patch", name="Apex 版本反馈演示项目", is_demo=True, demo_disclaimer=DISCLAIMER,
        article=Article(
            title="虚构 Designer’s Notes：内部演示版本", url="https://www.ea.com/games/apex-legends/apex-legends/news",
            published_at="2026-01-15", text="这是完全虚构的演示文章，不代表 EA 官方改动。",
            sections=[{"heading": c.source_heading, "paragraphs": [c.source_excerpt], "items": []} for c in changes],
        ),
        changes=changes, comments=cleaned, analyses=analyses,
        insights={item.target: item.model_dump(mode="json") for item in insights},
    )
    project.reviews = build_review_queue(project.comments, project.analyses)
    return project


def _changes() -> list[PatchChange]:
    return [
        PatchChange(section="虚构英雄改动", category="英雄削弱", target="星锚", ability_or_system="战术技能",
                    change_direction="削弱", change_summary="虚构：延长星锚战术技能的冷却窗口。", design_goal="降低连续脱战能力。",
                    original_problem="高频位移压缩对手反应时间。", exact_values=[{"before":"20 秒","after":"25 秒"}], source_heading="STARANCHOR",
                    source_excerpt="Fictional demo: Tactical cooldown increased from 20s to 25s.", aliases=["星锚", "StarAnchor", "SA"], parse_confidence=0.96, confirmed=True),
        PatchChange(section="虚构英雄改动", category="英雄增强", target="熔羽", ability_or_system="被动技能",
                    change_direction="增强", change_summary="虚构：提高熔羽被动技能在受击后的可靠性。", design_goal="减少被动被轻易打断的情况。",
                    original_problem="被动在实战中过于不稳定。", source_heading="MOLTENWING",
                    source_excerpt="Fictional demo: Passive reliability improved after taking damage.", aliases=["熔羽", "MoltenWing", "MW"], parse_confidence=0.93, confirmed=True),
        PatchChange(section="虚构英雄改动", category="机制调整", target="雾巡", ability_or_system="终极技能",
                    change_direction="调整", change_summary="虚构：调整雾巡终极技能的视野遮挡机制。", design_goal="让交战双方获得更清晰的反馈。",
                    original_problem="遮挡信息过强且反馈不一致。", source_heading="MISTWALKER",
                    source_excerpt="Fictional demo: Ultimate visibility behavior adjusted for both teams.", aliases=["雾巡", "MistWalker", "MWK"], parse_confidence=0.94, confirmed=True),
    ]


def _comments_and_analyses(changes: list[PatchChange]) -> tuple[list[RawComment], list[CommentAnalysis]]:
    raw: list[RawComment] = []
    analyses: list[CommentAnalysis] = []
    comment_id = 1
    for change_index, change in enumerate(changes):
        target = change.target
        texts = [
            f"支持{target}这次调整，方向是对的，先观察实战。",
            f"{target}确实需要改，但这个力度不够，核心问题还在。",
            f"{target}这样改比较合理，力度刚好。",
            f"方向支持，不过{target}只改数值没有碰到机制问题。",
            f"赞成调整{target}，高分段连续使用确实难以反制。",
            f"{target}改动方向没问题，但普通玩家可能受影响更大。",
            f"反对这次{target}改动，削得太狠了。",
            f"{target}不该这样改，机制会变得更难用。",
            f"这波{target}调整太过头，使用体验明显变差。",
            f"不赞成，{target}原来的强点根本不在这里。",
            f"{target}更新后出现技能卡住的 Bug，需要先修。",
            f"真棒啊，{target}现在直接卡死，太合理了。",
            f"{target}改完偶尔会异常退出，方向先不评价。",
            f"服务器延迟还是很高，和{target}改动关系不大。",
            f"排位匹配质量没有变化，不知道这次{target}是否有效。",
            f"支持{target}这次调整，方向是对的，先观察实战。",
        ]
        for local, text in enumerate(texts):
            cid = f"COM-{comment_id:04d}"
            image_num = (comment_id - 1) // 12 + 1
            platform = "B站" if image_num <= 2 else "论坛"
            raw.append(RawComment(
                comment_id=cid, local_index=(comment_id - 1) % 12 + 1,
                platform=platform, content=text, likes=(comment_id * 7) % 83, is_complete=local not in {11, 12},
                source_file=f"demo_comments_{image_num}.csv",
            ))
            support = local <= 5 or local == 15
            oppose = 6 <= local <= 9
            direction = "支持改动方向" if support else "反对改动方向" if oppose else "对方向没有明确态度"
            intensity = "力度不足" if local in {1, 3, 9} else "力度过大" if local in {6, 8} else "力度适中" if local in {2, 4} else "不适用"
            domain = "Bug" if local in {10, 11, 12} else "服务器与性能" if local == 13 else "匹配与排位" if local == 14 else "平衡"
            stance = "条件性支持" if support and intensity == "力度不足" else "支持" if support else "反对" if oppose else "仅描述现象"
            root = "产生了新问题" if domain == "Bug" else "原问题仍未解决" if local in {1, 3, 9} else "原问题部分缓解" if support else "无法判断"
            analyses.append(CommentAnalysis(
                comment_id=cid, analysis_stage=STAGE_DONE,
                primary_target=target if local not in {13, 14} else None,
                problem_domain=domain, problem_reason=["Bug或异常"] if domain == "Bug" else ["改动未触及核心问题"] if local in {1, 3, 9} else [],
                direction_attitude=direction, intensity_attitude=intensity, overall_stance=stance, root_issue_status=root,
                information_quality="高" if len(text) >= 25 else "中", analysis_confidence=0.64 if local in {11, 12} else 0.88,
                reasoning_summary="虚构演示标签，用于验证产品流程。", evidence_quote=text,
                suspected_sarcasm=local == 11,
            ))
            comment_id += 1
    return raw, analyses

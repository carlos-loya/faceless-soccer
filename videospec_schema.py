"""
TikiTakaFootyTV — VideoSpec schema (the pipeline contract).

This is the typed contract the DETERMINISTIC pipeline consumes (Nano Banana graphics,
ElevenLabs VO, Remotion assembly). It deliberately does NOT call the Claude API — the
"brain" that PRODUCES a VideoSpec runs through the Claude Code subscription via the
`videospec` skill (.claude/skills/videospec/SKILL.md), not metered API calls.

The schema still encodes the viral formula (see VIRAL-FORMULA.md) and the no-footage
model (see PLAYBOOK.md §5): there is no "clip" field, only `graphic_prompt`s for
generated graphics.

Usage (downstream pipeline):
    from videospec_schema import load_spec
    spec = load_spec("out/specs/yamal-breakout.json")   # validates or raises
    for scene in spec.scenes: ...

Keep this in sync with the field spec restated in the skill's SKILL.md.

Deps:  pip install pydantic
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Format = Literal[
    # Story/news formats — the channel's PRIMARY mode (daily World Cup news & stories).
    "news_story",      # a topical news beat (selection, injury, transfer, milestone) told as a narrative
    "player_story",    # a player's arc — redemption, rise, last dance (e.g. the Pulisic redemption video)
    "post_match",      # a finished-match recap: running scoreboard told goal-by-goal + a group-standings table wrap-up scene
    # Stat/quiz/ranking formats — still in the toolkit (quiz_top5 is a proven outlier), secondary.
    "shock_stat", "top5_countdown", "this_or_that",
    "season_in_numbers", "disrespectful_ranking", "did_you_know", "tactical_breakdown",
    "quiz_top5",  # "Can you name X's top 5 …?" — proven outlier (Tifo); accuracy-critical
]
GraphicType = Literal[
    "title_card", "stat_card", "ranking_row",
    "comparison_split", "pitch_diagram", "full_bleed_bg",
    "quiz_board",  # numbered slots, hidden/blurred for the "guess now" beat
    "scorers_split",  # two scorers slide in from opposite sides (player photo or silhouette) with the score between them
    "group_table",  # a ranked group-standings table (flag + code + points); pair with a `group_table` data list
]
HookType = Literal["shock_number", "bold_claim", "curiosity_gap", "question"]
RetentionMechanic = Literal["open_loop", "countdown", "seamless_loop", "reveal"]
VisualSource = Literal["entity", "commons", "stock", "stock_video", "ai", "graphic"]


class Hook(BaseModel):
    first_frame_text: str = Field(description="Scroll-stopper on frame 1. <=7 words, sound-off readable.")
    spoken_hook: str = Field(description="First VO line; lands the promise in under 2 seconds.")
    hook_type: HookType


class GroupRow(BaseModel):
    team: str = Field(description="KB nation/club entity slug (must have a flag image + `code`), e.g. 'australia'.")
    points: int = Field(description="Points to display for this team.")
    played: Optional[int] = Field(default=None, description="Matches played (optional column).")
    gd: Optional[int] = Field(default=None, description="Goal difference (optional column, signed).")
    highlight: bool = Field(default=False, description="Highlight this row (the video's team) in gold.")


class Scene(BaseModel):
    index: int = Field(description="1-based; scene 1 is the hook.")
    on_screen_text: str = Field(description="Bold overlay, <=8 words. Carries the story sound-off.")
    voiceover: str = Field(description="What ElevenLabs narrates over this scene.")
    stat_callout: str = Field(description='Big number/data, e.g. "27 G/A". "" if none.')
    graphic_type: GraphicType
    graphic_prompt: str = Field(
        description="Nano Banana prompt for this scene's GENERATED graphic. Brand style "
        "(black bg, gold #F7D774->#C8881B, bold condensed white type, 9:16). "
        "NO real player faces, NO broadcast imagery — crests/kits/silhouettes/abstract only."
    )
    visual_source: VisualSource = Field(
        description="Background for THIS beat, matched to its voiceover. Pick by SPECIFICITY: "
        "'entity' = a SPECIFIC player/club/stadium/nation the VO names (CC image from the KB — "
        "prefer this whenever a real subject is named; map a club to its stadium); 'stock' = "
        "GENERIC atmosphere photo (crowd, goal net, floodlights); 'stock_video' = MOVING generic "
        "atmosphere b-roll (crowd, stadium, confetti) for hooks/guess beats/outros; 'ai' = a "
        "specific thing with no CC image (Nano Banana); 'graphic' = pure brand card, no photo."
    )
    visual_query: str = Field(
        description="For 'entity': the KB entity slug (e.g. 'lamine-yamal', 'camp-nou'). For "
        "'stock'/'ai': a vivid phrase matching the VO ('football stadium floodlights night crowd'); "
        "do NOT name real players/clubs in a stock query (stock won't have them). '' for 'graphic'."
    )
    sticker_entity: str = Field(
        default="",
        description="Optional KB entity slug whose image is pinned as a PER-SCENE corner sticker "
        "(e.g. a nation flag on a 'name the winner' reveal). '' = no per-scene sticker. Distinct "
        "from the video-wide subject sticker.",
    )
    score: str = Field(
        default="",
        description="Match-summary running scoreboard score for THIS beat as 'HOME-AWAY' "
        "(e.g. '0-0','1-0','4-1'); home = matchup[0]. Only used when the top-level `matchup` is "
        "set: the persistent top-left scoreboard shows this value and pops when it changes. "
        "'' inherits the previous beat's score. Do NOT also put the score in `stat_callout` — the "
        "scoreboard carries it and the center stays free for visuals.",
    )
    group_table: List[GroupRow] = Field(
        default_factory=list,
        description="Group-standings rows to render as a ranked table on THIS beat (use with "
        "graphic_type 'group_table'). Order the list by rank (top first). Each row needs a KB "
        "nation slug + points. The running scoreboard is auto-HIDDEN on any scene that has a "
        "group_table (and on the comment-bait end card), so use it for the standings/wrap-up beat.",
    )
    duration_seconds: float


class Thumbnail(BaseModel):
    text: str = Field(description="Huge thumbnail text, <=4 words.")
    concept: str = Field(description="Nano Banana prompt / visual idea (brand style, no faces).")


class VideoSpec(BaseModel):
    format: Format
    topic: str
    subject: str = Field(
        default="",
        description="Entity slug of the video's MAIN subject (its photo becomes the corner "
        "sticker that anchors the whole video, e.g. 'lamine-yamal'). Must be a KB entity with a "
        "free image. '' if the video has no single subject (e.g. a multi-player ranking).",
    )
    matchup: List[str] = Field(
        default_factory=list,
        description="OPTIONAL — for head-to-head match videos (preview/recap). Exactly TWO KB "
        "entity slugs (the two nations/clubs, home first), e.g. ['brazil','morocco']. Their flags "
        "render as a persistent 'FLAG vs FLAG' badge top-left, under the watermark, for the whole "
        "video. Leave [] for non-match videos. Each slug must be a KB entity whose image is its flag/crest.",
    )
    target_duration_seconds: float = Field(description="<=30 for Shorts.")
    hook: Hook
    retention_mechanic: RetentionMechanic
    scenes: List[Scene]
    comment_bait: str = Field(description="Engineered debate question — REQUIRED on every video.")
    cta: str
    music_mood: str
    thumbnail: Thumbnail
    youtube_title: str
    youtube_description: str
    instagram_caption: str
    tiktok_caption: str
    hashtags: List[str] = Field(description="5–10; broad + niche/brand mix.")


def load_spec(path: str | Path) -> VideoSpec:
    """Load + validate a VideoSpec JSON produced by the `videospec` skill."""
    data = json.loads(Path(path).read_text())
    return VideoSpec.model_validate(data)


if __name__ == "__main__":
    # Print the JSON Schema — handy reference when tuning the skill, and what the
    # skill's output must satisfy.
    print(json.dumps(VideoSpec.model_json_schema(), indent=2))

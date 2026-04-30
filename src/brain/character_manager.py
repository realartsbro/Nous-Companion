"""
Nous Companion — Character Manager

Manages multiple characters with hot-switching support.
Each character bundles: sprites, personality, voice, config.
"""

import base64
import io
import json
import logging
from pathlib import Path, PurePosixPath
import re
import shutil
import zipfile
from typing import Optional

import yaml

from compositor.cutout_compositor import CutoutCompositor

logger = logging.getLogger(__name__)

CHARACTER_ARCHIVE_MANIFEST = "nous-companion-character.json"
LEGACY_CHARACTER_ARCHIVE_MANIFEST = "codec-companion-character.json"
CHARACTER_ARCHIVE_VERSION = 1
CHARACTER_ARCHIVE_EXTENSION = ".nous-companion-character.zip"
LEGACY_CHARACTER_ARCHIVE_EXTENSION = ".codec-character.zip"


def _sanitize_character_id(value: str) -> str:
    sanitized = re.sub(r"[^a-z0-9_]+", "_", value.strip().lower())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "character"


class Character:
    """A single character: sprites + personality + voice config."""

    def __init__(self, char_dir: Path):
        self.char_dir = char_dir
        self.id = char_dir.name

        # Load config
        config_path = char_dir / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                self.config = yaml.safe_load(f) or {}
        else:
            self.config = {}

        self.name = self.config.get("name", self.id)
        self.description = self.config.get("description", "")

        # Sprite offsets (per expression group)
        self.sprite_offsets = self.config.get("offsets", {})

        # Sprite order (per expression group) — user-defined ordering for eyes/mouths
        self.sprite_order = self.config.get("sprite_order", {})

        # Idle rarity weights — 1-5, higher = more frequent in idle rotation
        # Missing expressions default to 3; 0 means excluded from idle
        self.idle_rarity: dict[str, int] = self.config.get("idle_rarity", {})

        # Speech allowed — True by default, False means idle-only (hidden from LLM)
        self.speech_allowed: dict[str, bool] = self.config.get("speech_allowed", {})

        # Idle lines — spontaneous spoken lines after long inactivity
        # Loaded from idle_lines.txt (preferred) or config.yaml idle_lines list
        self.idle_lines: list[str] = []
        idle_lines_file = char_dir / "idle_lines.txt"
        if idle_lines_file.exists():
            raw = idle_lines_file.read_text(encoding="utf-8")
            self.idle_lines = [line.strip() for line in raw.split("\n") if line.strip()]
            if self.idle_lines:
                logger.info(f"Loaded {len(self.idle_lines)} idle lines from {idle_lines_file.name}")
        if not self.idle_lines:
            self.idle_lines = self.config.get("idle_lines", [])

        # Prompt acks — instant acknowledgments when user sends a message
        # Loaded from prompt_acks.txt (preferred), then config.yaml prompt_acks list,
        # then a hardcoded default list.
        self.prompt_acks: list[str] = []
        prompt_acks_file = char_dir / "prompt_acks.txt"
        if prompt_acks_file.exists():
            raw = prompt_acks_file.read_text(encoding="utf-8")
            self.prompt_acks = [line.strip() for line in raw.split("\n") if line.strip()]
            if self.prompt_acks:
                logger.info(f"Loaded {len(self.prompt_acks)} prompt acks from {prompt_acks_file.name}")
        if not self.prompt_acks:
            self.prompt_acks = self.config.get("prompt_acks", [])
        if not self.prompt_acks:
            self.prompt_acks = [
                "Let me think about that...",
                "Understood. Processing...",
                "Got it. Looking into this...",
                "Acknowledged. Working on it...",
                "Copy that. Analyzing now...",
                "Heard. Digging in...",
                "On it. Give me a moment...",
                "Roger. Checking this out...",
            ]

        # Brief quips — quick completion acknowledgments (brief mode)
        # Loaded from brief_quips.txt (preferred), then config.yaml brief_quips list,
        # then a hardcoded default list.
        self.brief_quips: list[str] = []
        brief_quips_file = char_dir / "brief_quips.txt"
        if brief_quips_file.exists():
            raw = brief_quips_file.read_text(encoding="utf-8")
            self.brief_quips = [line.strip() for line in raw.split("\n") if line.strip()]
            if self.brief_quips:
                logger.info(f"Loaded {len(self.brief_quips)} brief quips from {brief_quips_file.name}")
        if not self.brief_quips:
            self.brief_quips = self.config.get("brief_quips", [])
        if not self.brief_quips:
            self.brief_quips = [
                "Done.",
                "Sorted.",
                "All set.",
                "Roger that.",
                "Copy.",
            ]

        # Voice config
        voice = self.config.get("voice", {})
        self.voice_engine = voice.get("engine", "omnivoice")
        self.voice_ref_audio = voice.get("reference_audio")
        if self.voice_ref_audio and not Path(self.voice_ref_audio).is_absolute():
            self.voice_ref_audio = str(char_dir / self.voice_ref_audio)
        self.voice_settings = voice.get("settings", {})
        self.expression_voices = voice.get("expression_voices", {})  # { "serious": { "reference_audio": "..." } }

        # Portrait image
        portrait = self.config.get("portrait", "")
        self.portrait_path = str(char_dir / portrait) if portrait else None

        # Animation config
        anim = self.config.get("animation", {})
        self.speaking_cycle = anim.get("speaking_cycle", ["speaking"])
        self.flap_interval_ms = anim.get("flap_interval_ms", 180)
        self.mouth_open_threshold = anim.get("mouth_open_threshold", 0.35)
        self.mouth_close_threshold = anim.get("mouth_close_threshold", 0.18)

        # Display mode: how the character is rendered in the main window
        self.display_mode = self.config.get("display_mode", "stretch")

        # Personality (LLM system prompt)
        personality_path = char_dir / "personality.md"
        self.personality = personality_path.read_text() if personality_path.exists() else ""

        # Character description for auto-mode selection
        desc_path = char_dir / "description.md"
        if desc_path.exists():
            self.character_desc = desc_path.read_text()
        else:
            # Fallback: first 2 lines of personality
            lines = self.personality.strip().split("\n")[:3]
            self.character_desc = " ".join(l.strip("# ").strip() for l in lines if l.strip())

        # Find sprite directory — look for subdirs containing _expression groups
        self.compositor = None
        self.sprite_dir_name = None

        try:
            # Check direct _groups in char_dir
            direct_groups = [d for d in char_dir.iterdir() if d.is_dir() and d.name.startswith("_")]
            if direct_groups:
                self.compositor = CutoutCompositor(str(char_dir), character_offsets=self.sprite_offsets, sprite_order=self.sprite_order)
                self.sprite_dir_name = char_dir.name
            else:
                # Check subdirectories for _groups
                for sub in char_dir.iterdir():
                    if sub.is_dir() and not sub.name.startswith("."):
                        sub_groups = [d for d in sub.iterdir() if d.is_dir() and d.name.startswith("_")]
                        if sub_groups:
                            self.compositor = CutoutCompositor(str(sub), character_offsets=self.sprite_offsets, sprite_order=self.sprite_order)
                            self.sprite_dir_name = sub.name
                            break
        except Exception as e:
            logger.warning(f"Character {self.id}: failed to load compositor — {e}")

        logger.info(f"Character loaded: {self.name} ({self.id}) — "
                    f"sprite_dir={self.sprite_dir_name}, "
                    f"expressions={self.compositor.expression_names if self.compositor else 'none'}")

    @property
    def has_sprites(self) -> bool:
        return self.compositor is not None

    @property
    def has_voice(self) -> bool:
        return self.voice_engine != "none" and self.voice_ref_audio is not None

    def get_voice_for_expression(self, expression: str) -> dict:
        """Return effective voice config for an expression, with expression overrides applied."""
        result = {
            "engine": self.voice_engine,
            "reference_audio": self.voice_ref_audio,
            "settings": dict(self.voice_settings),
        }
        expr_voice = self.expression_voices.get(expression)
        if expr_voice:
            if "reference_audio" in expr_voice:
                ref = expr_voice["reference_audio"]
                if ref and not Path(ref).is_absolute():
                    ref = str(self.char_dir / ref)
                result["reference_audio"] = ref
            if "settings" in expr_voice:
                result["settings"].update(expr_voice["settings"])
        return result


class CharacterManager:
    """Manages multiple characters with switching and auto-mode."""

    def __init__(self, characters_dir: str | Path):
        self.characters_dir = Path(characters_dir)
        self.characters: dict[str, Character] = {}
        self.active_id: str = "default"
        self.auto_mode: bool = False

        # Load all characters
        self._load_all()

    def _preferred_active_id(self, previous_active: str = "") -> str:
        """Choose the best active character after a reload."""
        if previous_active and previous_active in self.characters:
            return previous_active
        if "default" in self.characters:
            return "default"
        return next(iter(self.characters), "")

    def _unique_character_id(self, candidate: str) -> str:
        """Generate a filesystem-safe character id that does not already exist."""
        base_id = _sanitize_character_id(candidate)
        unique_id = base_id
        suffix = 2
        while unique_id in self.characters or (self.characters_dir / unique_id).exists():
            unique_id = f"{base_id}_{suffix}"
            suffix += 1
        return unique_id

    def _load_all(self):
        """Load all characters from the characters directory."""
        previous_active = self.active_id
        self.characters = {}
        if not self.characters_dir.exists():
            self.active_id = ""
            return

        loaded_ids = []
        for d in sorted(self.characters_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            # Only load dirs that look like characters (have config.yaml or personality.md)
            if (d / "config.yaml").exists() or (d / "personality.md").exists():
                try:
                    char = Character(d)
                except Exception as e:
                    logger.warning(f"Failed to load character from {d}: {e}")
                    continue
                if char.has_sprites:  # must have sprites to be usable
                    self.characters[char.id] = char
                    loaded_ids.append(char.id)
                    logger.info(f"Loaded character: {char.id} ({char.name})")
                else:
                    logger.debug(f"Skipping character {char.id} — no sprites")
        self.active_id = self._preferred_active_id(previous_active)
        print(f"[_load_all] Loaded: {loaded_ids}", flush=True)

    @property
    def active(self) -> Optional[Character]:
        return self.characters.get(self.active_id)

    @property
    def character_list(self) -> list[dict]:
        """Return list of available characters for the UI."""
        result = []
        for c in self.characters.values():
            item = {"id": c.id, "name": c.name, "description": c.description}
            # Sprite preview: composited base image from first expression group
            if c.compositor and c.compositor.expression_names:
                try:
                    first_expr = c.compositor.expression_names[0]
                    preview_b64 = c.compositor.composite_to_base64(
                        expression=first_expr,
                        eye_index=0,
                        mouth_index=-1,
                    )
                    item["sprite_preview_b64"] = f"data:image/png;base64,{preview_b64}"
                except Exception as e:
                    logger.debug(f"Failed to generate sprite preview for {c.id}: {e}")
            # Portrait as base64 data URL if exists
            if c.portrait_path and Path(c.portrait_path).exists():
                try:
                    portrait_bytes = Path(c.portrait_path).read_bytes()
                    ext = Path(c.portrait_path).suffix.lstrip(".") or "png"
                    item["portrait_b64"] = f"data:image/{ext};base64," + base64.b64encode(portrait_bytes).decode()
                except Exception:
                    pass
            result.append(item)
        return result

    def switch(self, character_id: str) -> bool:
        """Switch active character. Returns True if successful."""
        if character_id in self.characters:
            self.active_id = character_id
            logger.info(f"Switched to character: {self.characters[character_id].name}")
            return True
        logger.warning(f"Unknown character: {character_id}")
        return False

    def pick_for_context(self, context: str) -> str:
        """
        Auto-mode: pick the best character for a given context.
        For now, returns active character. Can be enhanced with LLM routing.
        """
        # TODO: LLM-based routing when multiple characters exist
        return self.active_id

    def should_chime_in(self, primary_id: str, context: str) -> Optional[str]:
        """
        Auto-mode: occasionally another character chimes in.
        Returns a character_id or None.
        """
        # TODO: Probabilistic + context-based chime-in logic
        import random
        others = [cid for cid in self.characters if cid != primary_id]
        if others and random.random() < 0.15:  # 15% chance
            return random.choice(others)
        return None

    def save_character(self, char_id: str, data: dict) -> bool:
        """Save character data to disk. Handles config.yaml, personality.md, portrait.

        Returns True on success, False on failure.
        """
        char = self.characters.get(char_id)
        if not char:
            logger.warning(f"save_character: unknown character {char_id}")
            return False

        char_dir = char.char_dir
        try:
            import yaml

            # 1. Update config.yaml
            config_path = char_dir / "config.yaml"
            config = char.config.copy()

            if "name" in data:
                config["name"] = data["name"]
            if "description" in data:
                config["description"] = data["description"]

            # Voice updates
            voice_updates = {}
            if "voice_engine" in data:
                voice_updates["engine"] = data["voice_engine"]
            if "voice_ref_audio" in data:
                voice_updates["reference_audio"] = data["voice_ref_audio"]
            if "voice_speed" in data:
                voice_updates["settings"] = config.get("voice", {}).get("settings", {})
                voice_updates["settings"]["speed"] = data["voice_speed"]
            if voice_updates:
                config["voice"] = config.get("voice", {})
                config["voice"].update(voice_updates)

            # Animation updates
            anim_updates = {}
            if "mouth_open_threshold" in data:
                anim_updates["mouth_open_threshold"] = data["mouth_open_threshold"]
            if "mouth_close_threshold" in data:
                anim_updates["mouth_close_threshold"] = data["mouth_close_threshold"]
            if "flap_interval_ms" in data:
                anim_updates["flap_interval_ms"] = data["flap_interval_ms"]
            if "speaking_cycle" in data:
                anim_updates["speaking_cycle"] = data["speaking_cycle"]
            if anim_updates:
                config["animation"] = config.get("animation", {})
                config["animation"].update(anim_updates)

            # Display mode
            if "display_mode" in data:
                config["display_mode"] = data["display_mode"]

            # Sprite offsets
            if "sprite_offsets" in data:
                config["offsets"] = data["sprite_offsets"]

            # Sprite order (user-defined eyes/mouths ordering)
            if "sprite_order" in data:
                config["sprite_order"] = data["sprite_order"]
                print(f"[SAVE-CM] Writing sprite_order: {data['sprite_order']}", flush=True)
            else:
                print(f"[SAVE-CM] No sprite_order in data. Keys: {list(data.keys())}", flush=True)

            # Idle rarity weights
            if "idle_rarity" in data:
                config["idle_rarity"] = data["idle_rarity"]
                print(f"[SAVE-CM] Writing idle_rarity: {data['idle_rarity']}", flush=True)

            # Speech allowed
            if "speech_allowed" in data:
                config["speech_allowed"] = data["speech_allowed"]
                print(f"[SAVE-CM] Writing speech_allowed: {data['speech_allowed']}", flush=True)

            # Portrait: decode base64 and save
            portrait_b64 = data.get("portrait_b64", "")
            if portrait_b64:
                # Strip data URL prefix if present
                if "," in portrait_b64:
                    portrait_b64 = portrait_b64.split(",", 1)[1]
                portrait_bytes = base64.b64decode(portrait_b64)
                ext = "png"  # default
                if portrait_bytes[:4] == b"\xff\xd8\xff\xe0" or portrait_bytes[:4] == b"\xff\xd8\xff\xe1":
                    ext = "jpg"
                elif portrait_bytes[:4] == b"RIFF":
                    ext = "webp"
                portrait_filename = f"portrait.{ext}"
                portrait_path = char_dir / portrait_filename
                portrait_path.write_bytes(portrait_bytes)
                config["portrait"] = portrait_filename
                logger.info(f"Saved portrait for {char_id}: {portrait_filename} ({len(portrait_bytes)} bytes)")

            # Voice reference audio: decode base64 and save
            voice_b64 = data.get("voice_b64", "")
            if voice_b64:
                if "," in voice_b64:
                    voice_b64 = voice_b64.split(",", 1)[1]
                voice_bytes = base64.b64decode(voice_b64)
                voice_filename = data.get("voice_filename", "voice_ref.wav")
                voice_path = char_dir / voice_filename
                voice_path.write_bytes(voice_bytes)
                config["voice"] = config.get("voice", {})
                config["voice"]["reference_audio"] = voice_filename
                logger.info(f"Saved voice ref for {char_id}: {voice_filename} ({len(voice_bytes)} bytes)")

            # Sprite files: decode base64 and save to _group/ folders
            sprite_files = data.get("sprite_files", {})
            # Determine sprite root (may be a subdir like campbell2/)
            sprite_save_root = char_dir
            if char.sprite_dir_name and char.sprite_dir_name != char.char_dir.name:
                sprite_save_root = char_dir / char.sprite_dir_name
            sprites_saved_count = 0

            # Pre-clean placeholders from groups that will receive new sprites
            groups_receiving_sprites = set()
            for rel_path in sprite_files.keys():
                group_name = Path(rel_path).parent.name
                if group_name.startswith("_"):
                    groups_receiving_sprites.add(group_name)
            for group_name in groups_receiving_sprites:
                group_dir = sprite_save_root / group_name
                # Remove distinctive placeholder
                for ph_name in ("__cc_placeholder__.png", "placeholder.png"):
                    ph_path = group_dir / ph_name
                    if ph_path.exists() and ph_path.stat().st_size < 500:
                        ph_path.unlink()
                        logger.info(f"Pre-removed placeholder from {group_name}")

            for rel_path, file_b64 in sprite_files.items():
                # Validate path: must be under sprite_save_root and in a _group folder
                safe_path = Path(rel_path).name
                group_name = Path(rel_path).parent.name
                if not group_name.startswith("_"):
                    logger.warning(f"Skipping invalid sprite path: {rel_path}")
                    continue
                group_dir = sprite_save_root / group_name
                group_dir.mkdir(exist_ok=True)
                # Strip data URL prefix
                if "," in file_b64:
                    file_b64 = file_b64.split(",", 1)[1]
                try:
                    file_bytes = base64.b64decode(file_b64)
                    # Convert any image format to PNG for consistency
                    from PIL import Image
                    import io
                    img = Image.open(io.BytesIO(file_bytes))
                    if img.mode != "RGBA":
                        img = img.convert("RGBA")
                    # Save as PNG regardless of original format
                    png_path = group_dir / (Path(safe_path).stem + ".png")
                    img.save(png_path, "PNG")
                    sprites_saved_count += 1
                    logger.info(f"Saved sprite for {char_id}: {rel_path} -> {png_path.name} ({len(file_bytes)} bytes)")
                except Exception as e:
                    logger.warning(f"Failed to save sprite {rel_path}: {e}")

            # Delete sprites marked for removal
            delete_sprites = data.get("delete_sprites") or []
            deleted_count = 0
            for rel_path in delete_sprites:
                group_name = Path(rel_path).parent.name
                if not group_name.startswith("_"):
                    logger.warning(f"Skipping invalid delete path: {rel_path}")
                    continue
                file_path = sprite_save_root / rel_path
                # Security: ensure the resolved path is under sprite_save_root
                try:
                    resolved = file_path.resolve()
                    resolved_root = sprite_save_root.resolve()
                    if not str(resolved).startswith(str(resolved_root)):
                        logger.warning(f"Delete path escapes sprite root: {rel_path}")
                        continue
                except Exception:
                    pass
                if file_path.exists():
                    file_path.unlink()
                    deleted_count += 1
                    logger.info(f"Deleted sprite for {char_id}: {rel_path}")
                else:
                    logger.debug(f"Delete sprite not found: {rel_path}")
                # Remove from sprite_order if present
                group_key = group_name.lstrip("_")
                if "sprite_order" in config and group_key in config["sprite_order"]:
                    for part in ("eyes", "mouths"):
                        order_list = config["sprite_order"][group_key].get(part, [])
                        fname_stem = Path(rel_path).stem
                        if fname_stem in order_list:
                            order_list.remove(fname_stem)
                            config["sprite_order"][group_key][part] = order_list

            # Expression-specific voice files: decode base64 and save
            expr_voice_files = data.get("expression_voice_files", {})
            # expr_voice_files: { "serious": "data:audio/wav;base64,...", "shouting": "..." }
            if expr_voice_files:
                config["voice"] = config.get("voice", {})
                expr_voices_cfg = config["voice"].get("expression_voices", {})
                for expr_name, file_b64 in expr_voice_files.items():
                    if not file_b64:
                        continue
                    if "," in file_b64:
                        file_b64 = file_b64.split(",", 1)[1]
                    try:
                        file_bytes = base64.b64decode(file_b64)
                        # Strip underscore prefix so filename and config key
                        # match the compositor's expression names (e.g. "cheerful" not "_cheerful")
                        clean_name = expr_name.lstrip("_")
                        voice_filename = f"voice_{clean_name}.wav"
                        voice_path = char_dir / voice_filename
                        voice_path.write_bytes(file_bytes)
                        expr_voices_cfg[clean_name] = {"reference_audio": voice_filename}
                        logger.info(f"Saved expression voice for {char_id}/{clean_name}: {voice_filename} ({len(file_bytes)} bytes)")
                    except Exception as e:
                        logger.warning(f"Failed to save expression voice {expr_name}: {e}")
                config["voice"]["expression_voices"] = expr_voices_cfg

            # Write config atomically via temp file
            temp_config = char_dir / ".config.yaml.tmp"
            with open(temp_config, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
            temp_config.replace(config_path)

            # 2. Update personality.md
            personality = data.get("personality", "")
            if personality is not None:
                personality_path = char_dir / "personality.md"
                temp_personality = char_dir / ".personality.md.tmp"
                temp_personality.write_text(personality, encoding="utf-8")
                temp_personality.replace(personality_path)

            logger.info(f"Character saved: {char_id} (sprites_saved={sprites_saved_count}, deleted={deleted_count})")
            return True

        except Exception as e:
            logger.error(f"Failed to save character {char_id}: {e}")
            import traceback
            traceback.print_exc()
            return False

    def create_character(self, char_id: str, name: str) -> Optional[Path]:
        """Create a new skeleton character directory.

        Returns the character directory path on success, None on failure.
        """
        char_dir = self.characters_dir / char_id
        if char_dir.exists():
            logger.warning(f"create_character: {char_id} already exists")
            return None

        try:
            char_dir.mkdir(parents=True)

            # Write skeleton config.yaml
            config = {
                "name": name,
                "description": "",
                "display_mode": "stretch",
                "voice": {
                    "engine": "none",
                    "settings": {"speed": 0.9}
                },
                "animation": {
                    "speaking_cycle": ["speaking"],
                    "flap_interval_ms": 180,
                    "mouth_open_threshold": 0.35,
                    "mouth_close_threshold": 0.18,
                }
            }
            import yaml
            (char_dir / "config.yaml").write_text(
                yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True),
                encoding="utf-8"
            )

            # Write skeleton personality.md
            (char_dir / "personality.md").write_text(
                f"# Personality Profile: {name}\n\n"
                "## Core Identity\n"
                f"You are {name}.\n\n"
                "## Tone & Demeanor\n"
                "*   **Direct:** You get straight to the point.\n"
                "*   **Concise:** You speak in short, punchy sentences.\n\n"
                "## Communication Style\n"
                "*   Speak as if over a secure radio network.\n"
                "*   React with ONE punchy line — 15 to 25 words.\n\n"
                "## Output Format\n"
                "Respond with JSON only:\n"
                "```json\n"
                '{\n  "quip": "your punchy line",\n  "expression": "normal"\n}\n'
                "```\n\n"
                "Available expressions: normal\n"
                "Pick the expression that fits the moment.\n",
                encoding="utf-8"
            )

            # Create placeholder sprite directories
            (char_dir / "_normal").mkdir()
            # Place a transparent placeholder so the compositor loads
            from PIL import Image
            placeholder = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
            placeholder.save(char_dir / "_normal" / "sprite-base.png")

            logger.info(f"Created new character: {char_id} at {char_dir}")
            return char_dir

        except Exception as e:
            logger.error(f"Failed to create character {char_id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def export_character(self, char_id: str) -> Optional[tuple[str, bytes]]:
        """Package a character into a shareable zip archive."""
        char = self.characters.get(char_id)
        if not char:
            logger.warning(f"export_character: unknown character {char_id}")
            return None

        archive_root = _sanitize_character_id(char.id)
        archive_name = f"{archive_root}{CHARACTER_ARCHIVE_EXTENSION}"
        manifest = {
            "format": "nous-companion-character",
            "version": CHARACTER_ARCHIVE_VERSION,
            "character_id": char.id,
            "name": char.name,
        }

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                CHARACTER_ARCHIVE_MANIFEST,
                json.dumps(manifest, indent=2, ensure_ascii=False),
            )
            for path in sorted(char.char_dir.rglob("*")):
                if not path.is_file():
                    continue
                rel_path = path.relative_to(char.char_dir)
                if any(part == "__pycache__" for part in rel_path.parts):
                    continue
                if any(part.startswith(".") for part in rel_path.parts):
                    continue
                archive_path = PurePosixPath(archive_root, *rel_path.parts).as_posix()
                archive.writestr(archive_path, path.read_bytes())

        logger.info(f"Exported character archive: {char_id} -> {archive_name}")
        return archive_name, buffer.getvalue()

    def import_character(self, archive_bytes: bytes, source_name: str = "") -> tuple[str, str]:
        """Import a character from a shareable zip archive."""
        try:
            archive = zipfile.ZipFile(io.BytesIO(archive_bytes))
        except zipfile.BadZipFile as exc:
            raise ValueError("The selected file is not a valid character archive.") from exc

        with archive:
            manifest = {}
            manifest_name = None
            if CHARACTER_ARCHIVE_MANIFEST in archive.namelist():
                manifest_name = CHARACTER_ARCHIVE_MANIFEST
            elif LEGACY_CHARACTER_ARCHIVE_MANIFEST in archive.namelist():
                manifest_name = LEGACY_CHARACTER_ARCHIVE_MANIFEST

            if manifest_name:
                try:
                    manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
                except Exception as exc:
                    raise ValueError("The character archive manifest is invalid.") from exc

            members: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for info in archive.infolist():
                if info.is_dir() or info.filename in {
                    CHARACTER_ARCHIVE_MANIFEST,
                    LEGACY_CHARACTER_ARCHIVE_MANIFEST,
                }:
                    continue
                member_path = PurePosixPath(info.filename)
                if member_path.is_absolute() or any(part in ("", "..") for part in member_path.parts):
                    raise ValueError("The character archive contains an unsafe file path.")
                members.append((info, member_path))

            if not members:
                raise ValueError("The character archive is empty.")

            root_dirs = {
                member_path.parts[0]
                for _, member_path in members
                if len(member_path.parts) > 1
            }
            shared_root = None
            if len(root_dirs) == 1 and all(len(member_path.parts) > 1 for _, member_path in members):
                shared_root = next(iter(root_dirs))

            extracted_files: list[tuple[zipfile.ZipInfo, PurePosixPath]] = []
            for info, member_path in members:
                rel_path = (
                    PurePosixPath(*member_path.parts[1:])
                    if shared_root
                    else member_path
                )
                if not rel_path.parts or any(part in ("", "..") for part in rel_path.parts):
                    raise ValueError("The character archive contains an unsafe file path.")
                extracted_files.append((info, rel_path))

            extracted_names = {rel_path.as_posix() for _, rel_path in extracted_files}
            if "config.yaml" not in extracted_names or "personality.md" not in extracted_names:
                raise ValueError("The character archive is missing config.yaml or personality.md.")

            fallback_name = Path(source_name or "imported-character.zip").stem
            if fallback_name.endswith(".nous-companion-character"):
                fallback_name = fallback_name[: -len(".nous-companion-character")]
            if fallback_name.endswith(".codec-character"):
                fallback_name = fallback_name[: -len(".codec-character")]
            requested_id = (
                manifest.get("character_id")
                or shared_root
                or fallback_name
            )
            char_id = self._unique_character_id(requested_id)
            char_dir = self.characters_dir / char_id
            char_dir.mkdir(parents=True, exist_ok=False)

            try:
                for info, rel_path in extracted_files:
                    dest_path = char_dir.joinpath(*rel_path.parts)
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    dest_path.write_bytes(archive.read(info))

                imported = Character(char_dir)
                if not imported.has_sprites:
                    raise ValueError("The imported character does not contain any usable sprite groups.")
            except Exception:
                shutil.rmtree(char_dir, ignore_errors=True)
                raise

        self._load_all()
        imported_char = self.characters.get(char_id)
        imported_name = imported_char.name if imported_char else char_id
        logger.info(f"Imported character archive: {source_name or '<memory>'} -> {char_id}")
        return char_id, imported_name

    def delete_character(self, char_id: str) -> tuple[bool, str]:
        """Delete a character directory from disk."""
        char = self.characters.get(char_id)
        if not char:
            return False, "Character not found."
        if len(self.characters) <= 1:
            return False, "You need at least one character."
        if char_id == "nous":
            return False, "Nous cannot be deleted."

        resolved_root = self.characters_dir.resolve()
        resolved_char_dir = char.char_dir.resolve()
        if resolved_char_dir == resolved_root or resolved_root not in resolved_char_dir.parents:
            logger.warning(f"delete_character: refused unsafe path {resolved_char_dir}")
            return False, "Refused to delete an unsafe character path."

        try:
            shutil.rmtree(resolved_char_dir)
            self._load_all()
            logger.info(f"Deleted character: {char_id}")
            return True, ""
        except Exception as e:
            logger.error(f"Failed to delete character {char_id}: {e}")
            return False, "Failed to delete character."

    def get_character_data(self, char_id: str) -> Optional[dict]:
        """Return full character data for the editor."""
        char = self.characters.get(char_id)
        if not char:
            return None
        data = {
            "id": char.id,
            "name": char.name,
            "description": char.description,
            "personality": char.personality,
            "voice_engine": char.voice_engine,
            "voice_ref_audio": char.voice_ref_audio,
            "voice_settings": char.voice_settings,
            "expression_voices": char.expression_voices,
            "mouth_open_threshold": char.mouth_open_threshold,
            "mouth_close_threshold": char.mouth_close_threshold,
            "flap_interval_ms": char.flap_interval_ms,
            "speaking_cycle": char.speaking_cycle,
            "sprite_offsets": char.sprite_offsets,
            "sprite_order": char.sprite_order,
            "idle_rarity": char.idle_rarity,
            "speech_allowed": char.speech_allowed,
            "idle_lines": char.idle_lines,
            "prompt_acks": char.prompt_acks,
            "brief_quips": char.brief_quips,
            "expression_names": char.compositor.expression_names if char.compositor else [],
            "display_mode": char.display_mode,
        }
        # Scan sprite groups (_normal, _serious, etc.)
        # Use the compositor's actual sprite directory, which may be a subdir
        sprite_root = char.char_dir
        if char.sprite_dir_name and char.sprite_dir_name != char.char_dir.name:
            sprite_root = char.char_dir / char.sprite_dir_name
        sprite_groups = {}
        for item in sprite_root.iterdir():
            if item.is_dir() and item.name.startswith("_"):
                files = sorted([f.name for f in item.iterdir() if f.is_file() and f.suffix.lower() == ".png"])
                group_offsets = char.sprite_offsets.get(item.name, {})
                # Read sprite files as base64 for thumbnails
                sprite_b64 = {}
                for fname in files:
                    fpath = item / fname
                    try:
                        fb64 = base64.b64encode(fpath.read_bytes()).decode()
                        sprite_b64[fname] = f"data:image/png;base64,{fb64}"
                    except Exception:
                        pass
                # Get counts and classifications from compositor if available
                counts = {"base": 0, "eyes": 0, "mouths": 0, "standalone": 0, "unclassified": 0}
                classified = {"base": "", "eyes": [], "mouths": [], "standalones": [], "unclassified": []}
                if char.compositor and item.name.lstrip("_") in char.compositor.groups:
                    g = char.compositor.groups[item.name.lstrip("_")]
                    counts["base"] = 1
                    counts["eyes"] = len(g.eyes)
                    counts["mouths"] = len(g.mouths)
                    counts["standalone"] = len(g.standalone_bases) if g.is_standalone else 0
                    counts["unclassified"] = len(g.unclassified)
                    classified["base"] = g.base_name + ".png"
                    classified["eyes"] = [name + ".png" for name, _ in g.eyes]
                    classified["mouths"] = [name + ".png" for name, _ in g.mouths]
                    classified["standalones"] = [name + ".png" for name, _ in g.standalone_bases] if g.is_standalone else []
                    classified["unclassified"] = [name + ".png" for name, _ in g.unclassified]
                sprite_groups[item.name] = {
                    "files": files,
                    "sprite_b64": sprite_b64,
                    "counts": counts,
                    "classified": classified,
                    "offsets": {
                        "eyes": group_offsets.get("eyes", [4, 23]),
                        "mouth": group_offsets.get("mouth", [10, 34]),
                    }
                }
                print(f"[GET-DATA] {item.name}: files={files}, eyes={classified['eyes']}, mouths={classified['mouths']}, unclassified={classified['unclassified']}", flush=True)
        data["sprite_groups"] = sprite_groups

        # Sprite preview: composited base image from first expression group
        if char.compositor and char.compositor.expression_names:
            try:
                first_expr = char.compositor.expression_names[0]
                preview_b64 = char.compositor.composite_to_base64(
                    expression=first_expr,
                    eye_index=0,
                    mouth_index=-1,
                )
                data["sprite_preview_b64"] = f"data:image/png;base64,{preview_b64}"
            except Exception:
                pass

        # Voice reference audio as base64 if exists
        if char.voice_ref_audio and Path(char.voice_ref_audio).exists():
            try:
                voice_bytes = Path(char.voice_ref_audio).read_bytes()
                ext = Path(char.voice_ref_audio).suffix.lstrip(".") or "wav"
                data["voice_ref_b64"] = f"data:audio/{ext};base64," + base64.b64encode(voice_bytes).decode()
            except Exception:
                pass

        # Portrait as base64 data URL if exists
        if char.portrait_path and Path(char.portrait_path).exists():
            portrait_bytes = Path(char.portrait_path).read_bytes()
            ext = Path(char.portrait_path).suffix.lstrip(".") or "png"
            data["portrait_b64"] = f"data:image/{ext};base64," + base64.b64encode(portrait_bytes).decode()
        return data

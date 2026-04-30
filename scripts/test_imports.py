"""Quick smoke test for the new Nous Companion modules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from brain.character_loader import load_character
from brain.brain import Brain, Quip
from tts.engine import NoOpTTS, create_engine
from server.companion_server import CompanionServer

char = load_character(Path(__file__).resolve().parent.parent / "characters" / "default")
print(f"Character: {char.name}")
print(f"Expressions: {char.expression_names}")
print(f"Voice engine: {char.voice_engine}")
print(f"Speaking cycle: {char.speaking_cycle}")
print(f"System prompt length: {len(char.build_system_prompt())} chars")

# Test base64 output
b64 = char.get_expression_base64("neutral")
print(f"neutral.png base64 length: {len(b64)} chars")
print(f"Size: {char.get_expression_size('neutral')}")

# Test fallback
b64_missing = char.get_expression_base64("nonexistent")
print(f"Missing expression falls back correctly: {len(b64_missing) > 0}")

# Test TTS factory
tts_noop = create_engine({"engine": "none"})
print(f"NoOp TTS: {tts_noop.name}")

print("\nAll imports and basic tests passed.")

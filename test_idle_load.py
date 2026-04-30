"""Quick smoke test: verify idle_lines, prompt_acks, brief_quips load correctly."""
from pathlib import Path
import sys
sys.path.insert(0, "src")

from brain.character_manager import Character

char_dir = Path("characters/nous")
char = Character(char_dir)

print("=== Character:", char.name, "===")
print()
print("idle_lines:", len(char.idle_lines), "lines")
print("  first:", char.idle_lines[0][:60])
print("  last: ", char.idle_lines[-1][:60])
print()
print("prompt_acks:", len(char.prompt_acks), "lines")
for i, l in enumerate(char.prompt_acks):
    print(f"  [{i}] {l}")
print()
print("brief_quips:", len(char.brief_quips), "lines")
for i, l in enumerate(char.brief_quips):
    print(f"  [{i}] {l}")
print()

assert char.prompt_acks, "prompt_acks empty!"
assert char.brief_quips, "brief_quips empty!"
assert char.idle_lines, "idle_lines empty!"
print("ALL OK —", len(char.prompt_acks), "acks,", len(char.brief_quips), "quips,", len(char.idle_lines), "idle lines")

# Also test a character WITHOÜT the new files (should fall back to hardcoded defaults)
fallback_char = Character(Path("characters/mei_ling"))
print()
print("=== Fallback test (Mei Ling — no prompt_acks/brief_quips files) ===")
print("prompt_acks:", len(fallback_char.prompt_acks), "lines")
assert fallback_char.prompt_acks, "fallback prompt_acks empty!"
assert len(fallback_char.prompt_acks) == 8, f"expected 8 fallback acks, got {len(fallback_char.prompt_acks)}"
print("brief_quips:", len(fallback_char.brief_quips), "lines")
assert fallback_char.brief_quips, "fallback brief_quips empty!"
assert len(fallback_char.brief_quips) == 5, f"expected 5 fallback quips, got {len(fallback_char.brief_quips)}"
print("FALLBACK OK")

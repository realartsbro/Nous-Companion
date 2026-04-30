"""
OmniVoice TTS — standalone wrapper via Windows-hosted Gradio API.

Connects to OmniVoice running locally or via a forwarded host port.
Do NOT install omnivoice or torch in WSL.

Usage:
  python3 omnivoice_tts.py "Text to speak" output.wav [reference.wav]
"""

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from hermes_runtime import get_default_omnivoice_url

DEFAULT_REF = str(Path(__file__).resolve().parent.parent / "characters" / "default" / "campbell2" / "vc115902.wav")


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 omnivoice_tts.py 'text' output.wav [reference.wav]", file=sys.stderr)
        sys.exit(1)

    text = sys.argv[1]
    output_path = sys.argv[2]
    ref_audio = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_REF

    from gradio_client import Client, handle_file

    url = os.environ.get("OMNIVOICE_URL") or get_default_omnivoice_url()
    print(f"Connecting to OmniVoice at {url}...", file=sys.stderr)

    client = Client(url)

    result = client.predict(
        text=text,
        lang="English",
        ref_aud=handle_file(ref_audio),
        ref_text="",
        instruct="",
        ns=32, gs=2.0, dn=True, sp=0.9, du=0.0, pp=True, po=True,
        api_name="/_clone_fn",
    )

    audio_path = result[0] if isinstance(result, (tuple, list)) else result
    Path(audio_path).rename(output_path)

    size = os.path.getsize(output_path)
    print(f"OK {size}", file=sys.stderr)


if __name__ == "__main__":
    main()

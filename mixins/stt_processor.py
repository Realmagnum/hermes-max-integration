from __future__ import annotations
import os
import sys
import logging
import asyncio.subprocess
from pathlib import Path
from typing import Optional
from .base import MaxBaseMixin

logger = logging.getLogger(__name__)

class STTProcessorMixin(MaxBaseMixin):
    """
    Mixin for faster-whisper STT processing.
    """
    async def _transcribe_media(self, media_urls: list, media_types: list) -> Optional[str]:
        if not self._stt_enabled:
            return None

        transcriptions = []
        for path, mtype in zip(media_urls, media_types):
            if not mtype.startswith("audio/"):
                continue
            try:
                venv_path = os.getenv("MAX_STT_VENV", str(Path.home() / ".hermes" / "stt-venv"))
                python = str(Path(venv_path) / "bin" / "python3")
                if not os.path.exists(python):
                    python = "python3"
                
                # FIXED: Using sys.argv instead of f-string injection
                script = "import sys; from faster_whisper import WhisperModel; m=WhisperModel('base','cpu','int8'); segs,_=m.transcribe(sys.argv[1],language='ru'); [print(s.text.strip()) for s in segs]"
                
                proc = await asyncio.subprocess.create_subprocess_exec(
                    python, "-c", script, path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
                if proc.returncode == 0 and stdout:
                    transcriptions.append(stdout.decode().strip())
                elif stderr:
                    logger.warning("MAX: STT failed: %s", stderr.decode()[:200])
            except Exception as e:
                logger.error("MAX: STT error: %s", e)

        return "\n".join(transcriptions) if transcriptions else None

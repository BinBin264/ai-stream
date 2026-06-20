import asyncio
import logging
from pathlib import Path

from app.core.config import settings
from app.models.domain import LiveSession, LiveStatus

logger = logging.getLogger(__name__)


class StreamBroadcaster:
    """Owns the FFmpeg RTMPS process for one live session."""

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    async def start(self, live: LiveSession) -> LiveSession:
        if live.id in self._processes:
            return live

        rtmps_url = live.rtmps_url or settings.RTMPS_URL
        stream_key = live.stream_key or settings.RTMPS_STREAM_KEY
        if not rtmps_url or not stream_key:
            raise RuntimeError("Missing RTMPS_URL or RTMPS_STREAM_KEY")

        idle_video = Path(settings.IDLE_VIDEO_PATH)
        if not idle_video.exists():
            await self._create_idle_video(idle_video)

        output_url = f"{rtmps_url.rstrip('/')}/{stream_key}"
        cmd = [
            "ffmpeg",
            "-re",
            "-stream_loop",
            "-1",
            "-i",
            str(idle_video),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-f",
            "flv",
            output_url,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._processes[live.id] = proc
        live.status = LiveStatus.PREVIEW
        logger.info("Started FFmpeg broadcaster for live=%s", live.id)
        return live

    async def _create_idle_video(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=1280x720:rate=30",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-t",
            "10",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"Failed to create idle video: {stderr.decode(errors='ignore')[-500:]}")

    async def stop(self, live: LiveSession) -> LiveSession:
        proc = self._processes.pop(live.id, None)
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        live.status = LiveStatus.STOPPED
        return live

    def is_running(self, live_id: str) -> bool:
        proc = self._processes.get(live_id)
        return bool(proc and proc.returncode is None)


stream_broadcaster = StreamBroadcaster()

from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QWidget


class VideoPlayerController:
    """Manages media player playback control."""

    SEEK_STEP_MS = 5000

    def __init__(self, player: QMediaPlayer, parent: QWidget | None = None) -> None:
        self.player = player
        self.parent = parent
        self._is_user_scrubbing = False

    @property
    def is_user_scrubbing(self) -> bool:
        return self._is_user_scrubbing

    @is_user_scrubbing.setter
    def is_user_scrubbing(self, value: bool) -> None:
        self._is_user_scrubbing = value

    def toggle_play_pause(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def seek_forward(self) -> None:
        self._seek_relative(self.SEEK_STEP_MS)

    def seek_backward(self) -> None:
        self._seek_relative(-self.SEEK_STEP_MS)

    def _seek_relative(self, delta_ms: int) -> None:
        duration = max(self.player.duration(), 0)
        if duration <= 0:
            return

        next_position = self.player.position() + delta_ms
        next_position = max(0, min(duration, next_position))
        self.player.setPosition(next_position)

    def toggle_mute(self, audio_output) -> None:  # type: ignore[no-untyped-def]
        is_muted = audio_output.isMuted()
        audio_output.setMuted(not is_muted)
        return not is_muted

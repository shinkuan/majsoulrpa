import platform
import random
import time
from abc import ABCMeta, abstractmethod
from collections.abc import Iterable
from fractions import Fraction
from logging import getLogger
from typing import Any, Final

if platform.system() == "Windows":
    import pygetwindow  #type: ignore[import-untyped]

from playwright.sync_api import sync_playwright

logger = getLogger(__name__)

TITLE_MAJSOUL: Final[str] = "雀魂 -じゃんたま-| 麻雀を無料で気軽に"
URL_MAJSOUL: Final[str] = "https://game.mahjongsoul.com/"

STD_WIDTH: Final[int] = 1920
STD_HEIGHT: Final[int] = 1080
MIN_WIDTH: Final[int] = STD_WIDTH * 2 // 3
MIN_HEIGHT: Final[int] = STD_HEIGHT * 2 // 3
MAX_WIDTH: Final[int] = STD_WIDTH * 2
MAX_HEIGHT: Final[int] = STD_HEIGHT * 2

ASPECT_RATIO: Final[Fraction] = Fraction(16, 9)


def _get_random_point_in_region(
    left: int, top: int, width: int, height: int,
    edge_sigma: float=0.2,
) -> tuple[int, int]:
    """Return random point in region.

    This function does not validate parameters.
    """
    def _impl_get_point(distance_origin: int, length_region: int) -> int:
        mu = distance_origin + length_region/2.0
        sigma = (mu - distance_origin) / edge_sigma
        while True:
            p = random.normalvariate(mu, sigma)
            p = round(p)
            if distance_origin < p and p < (distance_origin + length_region):
                break
        return p

    x = _impl_get_point(left, width)
    y = _impl_get_point(top, height)

    return (x, y)


class BrowserBase(metaclass=ABCMeta):

    def __init__(self) -> None:
        self._window: Any = None

    def is_singleton(self) -> None:
        """Check if only one target window exists.

        Throws a runtime error if the target does not exist or
        if two or more targets exist.
        """
        if platform.system() == "Windows":
            if self._window is None:
                windows = [
                    w for w in pygetwindow.getAllWindows() \
                        if w.title.startwith(TITLE_MAJSOUL)
                ]
                if len(windows) == 0:
                    msg = "No window for Mahjong Soul is found."
                    raise RuntimeError(msg)
                if len(windows) > 1:
                    msg = "Multiple windows for Mahjong Soul are found."
                    raise RuntimeError(msg)
                self._window = windows[0]
        else:
            raise NotImplementedError(platform.system())

    @property
    @abstractmethod
    def zoom_ratio(self) -> float:
        pass

    @abstractmethod
    def refresh(self) -> None:
        pass

    @abstractmethod
    def write(self, text: str, delay: float | None = None) -> None:
        pass

    @abstractmethod
    def press(self, keys: str | Iterable[str]) -> None:
        pass

    @abstractmethod
    def press_hotkey(self, *args: str) -> None:
        pass

    @abstractmethod
    def scroll(self, clicks: int) -> None:
        pass

    @abstractmethod
    def click_region(  # noqa: PLR0913
        self, left: int, top: int, width: int, height: int,
        edge_sigma: float=2.0,
    ) -> None:
        pass

    @abstractmethod
    def get_screenshot(self) -> bytes:
        pass

    @abstractmethod
    def close(self) -> None:
        pass


class DesktopBrowser(BrowserBase):

    def __init__(  # noqa: PLR0913
        self, *, proxy_port: int = 8080,
        initial_left: int = 0, initial_top: int = 0,
        width: int = STD_WIDTH, height: int = STD_HEIGHT,
    ) -> None:
        super().__init__()

        if not self._validate_viewport_size(width, height):
            msg = (
                "Supported viewport sizes are "
                f"from {MIN_WIDTH} x {MIN_HEIGHT} "
                f"to {MAX_WIDTH} x {MAX_HEIGHT} and 16:9 aspect ratio."
            )
            raise RuntimeError(msg)

        self._viewport_size = {"width": width, "height": height}
        self._zoom_ratio = width / STD_WIDTH

        initial_position = f"--window-position={initial_left},{initial_top}"
        proxy_server = f"--proxy-server=http://localhost:{proxy_port}"
        ignore_certifi_errors = "--ignore-certificate-errors"
        options = [initial_position, proxy_server, ignore_certifi_errors]

        self._context_manager = sync_playwright()
        self._browser = self._context_manager.start().chromium.launch(
            args=options,
            ignore_default_args=["--mute-audio"],
            headless=False,
        )
        self._context = self._browser.new_context(viewport=self._viewport_size)  #type: ignore[arg-type]
        self._page = self._context.new_page()
        self._page.goto(URL_MAJSOUL)

    def _validate_viewport_size(self, width: int, height: int) -> bool:
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            return False
        if width > MAX_WIDTH or height > MAX_HEIGHT:
            return False
        if Fraction(width, height) != ASPECT_RATIO:
            return False
        return True

    @property
    def zoom_ratio(self) -> float:
        return self._zoom_ratio

    def refresh(self) -> None:
        self._page.reload()

    def write(self, text: str, delay: float | None = None) -> None:
        self._page.keyboard.type(text, delay=delay)

    def press(self, keys: str | Iterable[str]) -> None:
        if isinstance(keys, str):
            self._page.keyboard.press(keys)
        else:
            for k in keys:
                self._page.keyboard.press(k)

    def press_hotkey(self, *args: str) -> None:
        keys = "+".join(args)
        self._page.keyboard.press(keys)

    def scroll(self, clicks: int) -> None:
        if clicks == 0:
            return

        if clicks > 0:
            delta = 58 * 2
        else:
            logger.debug("scroll clicks is smaller than 0.")
            assert clicks < 0  # noqa: S101
            delta = -58 * 2
            clicks = abs(clicks)

        self._page.mouse.wheel(delta_x=0, delta_y=delta)
        for _ in range(clicks -1):
            time.sleep(0.1)
            self._page.mouse.wheel(delta_x=0, delta_y=delta)

    def _validate_region(  # noqa: PLR0911
            self, left: int, top: int, width: int, height: int) -> bool:
        if left < 0 or top < 0:
            return False
        if width <= 0 or height <= 0:
            return False
        if left >= self._viewport_size["width"]:
            return False
        if top >= self._viewport_size["height"]:
            return False
        if width > (self._viewport_size["width"] - left):
            return False
        if height > (self._viewport_size["height"] - top):
            return False
        return True

    def click_region(  # noqa: PLR0913
        self, left: int, top: int, width: int, height: int,
        edge_sigma: float=2.0,
    ) -> None:
        if not self._validate_region(left, top, width, height):
            msg = ("A click was requested into an invalid area."
                   f"{left=}, {top=}, {width=}, {height=}")
            raise RuntimeError(msg)
        if edge_sigma <= 0.0:  # noqa: PLR2004
            msg = "Invalid edge sigma was input."
            raise RuntimeError(msg)

        x, y = _get_random_point_in_region(
            left, top, width, height, edge_sigma=edge_sigma,
        )
        self._page.mouse.click(x, y)

    def get_screenshot(self) -> bytes:
        """Return bytes in png format.
        """
        return self._page.screenshot()

    def close(self) -> None:
        self._context.close()
        self._browser.close()
        self._context_manager.__exit__()
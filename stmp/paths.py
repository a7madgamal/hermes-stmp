"""Where a file may be read from, and where one may be written to.

The model chooses both `file_path` and `save_to`, so neither is a boundary on its
own. A prompt-injected turn can ask for `~/.bashrc` or `~/.ssh/authorized_keys`
and the phone's approval card shows a Drive file name, not the host path — so the
human could be approving a harmless-looking write to a dangerous place.

Two rules, both enforced before anything is sent or written:

- **Downloads land inside `download_dir`**, default the plugin's own data folder.
  `save_to` is resolved relative to it and the RESOLVED path must still be under
  it, which refuses `..` and symlink escapes in one comparison. Existing files are
  not replaced unless `allow_overwrite` is on.
- **Uploads come from `upload_dir`** when it is set. When it is not, the sources
  that hold credentials are refused outright, so the default posture is deny.

Pure path logic, no HTTP, so every rule here is unit-testable without a phone.
"""

from __future__ import annotations

import os
from pathlib import Path

from .bridge import Config, ConfigError


class PathRefused(Exception):
    """A path the user's settings do not allow. Never a crash, always a reason."""


def _under(path: Path, root: Path) -> bool:
    """True when `path` is `root` or lives inside it. Inputs are already resolved."""
    return path == root or root in path.parents


def _hermes_home() -> Path:
    """Hermes's own home. Imported lazily: this module is exercised without Hermes."""
    try:
        from hermes_constants import get_hermes_home  # type: ignore[import-not-found]
    except ImportError:
        return Path.home() / ".hermes"
    return Path(str(get_hermes_home()))


def _plugin_data_dir() -> Path:
    """The sanctioned per-plugin data root. Lazy for the same reason as above."""
    try:
        from plugins.plugin_storage import plugin_data_dir  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - only outside Hermes
        raise ConfigError(
            "no download_dir is configured and this plugin cannot reach Hermes's data "
            "directory. Set plugins.entries.stmp.settings.download_dir to a directory "
            "downloads may be written to."
        ) from exc
    return Path(str(plugin_data_dir("stmp")))


def download_root(config: Config) -> Path:
    """The one directory downloads may be written to."""
    raw = config.download_dir or str(_plugin_data_dir() / "downloads")
    root = Path(os.path.expanduser(raw)).resolve()
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ConfigError(
            f"download_dir {str(root)!r} cannot be created: {exc.strerror or exc}"
        ) from exc
    return root


def resolve_destination(config: Config, save_to: object) -> Path:
    """Turn `save_to` into an approved absolute path, or refuse it.

    Absolute or relative, the answer is the same: the RESOLVED path must sit under
    `download_dir`. Resolving first is what makes a symlink inside the directory
    that points outside it a refusal rather than an escape.
    """
    root = download_root(config)
    raw = Path(os.path.expanduser(str(save_to)))
    candidate = raw if raw.is_absolute() else root / raw
    target = candidate.resolve()

    if not _under(target, root):
        raise PathRefused(
            f"save_to {str(raw)!r} resolves outside the configured download_dir "
            f"{str(root)!r}. Downloads may only be written inside that directory; "
            "use a path relative to it, or change the setting."
        )
    if target == root:
        raise PathRefused(f"save_to {str(raw)!r} is the download_dir itself, not a file")
    if target.is_dir():
        raise PathRefused(f"save_to {str(raw)!r} is a directory")
    if target.exists() and not config.allow_overwrite:
        raise PathRefused(
            f"save_to {str(raw)!r} already exists and allow_overwrite is off. Pick another "
            "name, or turn overwriting on in the plugin settings."
        )
    if not target.parent.is_dir():
        raise PathRefused(f"save_to's parent directory does not exist: {target.parent}")
    return target


#: Directories under the user's home that hold credentials. Refused as upload
#: sources whenever `upload_dir` is not set, because these are the files a
#: prompt-injected call would reach for. Dotted names: these are dotfiles, and a
#: missing dot silently points the deny-list at a directory that never exists.
_PRIVATE_DIRS = (".ssh", ".gnupg", ".aws", ".config", ".kube", ".docker")


def _refuse_private(source: Path) -> None:
    """Refuse a credential store, `.env*`, or Hermes's own home."""
    if source.name.startswith(".env"):
        raise PathRefused(
            f"file_path {str(source)!r} is an environment file. Set "
            "plugins.entries.stmp.settings.upload_dir to the directory uploads may come "
            "from if this file should be uploadable."
        )
    forbidden = [Path.home() / name for name in _PRIVATE_DIRS]
    forbidden.append(_hermes_home())
    for root in forbidden:
        resolved = root.resolve()
        if _under(source, resolved):
            raise PathRefused(
                f"file_path {str(source)!r} is inside {str(resolved)!r}, which holds "
                "credentials. Set plugins.entries.stmp.settings.upload_dir to the "
                "directory uploads may come from."
            )


def resolve_source(config: Config, file_path: object) -> Path:
    """Turn `file_path` into an approved absolute path, or refuse it."""
    raw = Path(os.path.expanduser(str(file_path)))
    if not raw.is_absolute():
        raise PathRefused(f"file_path must be absolute, got {str(raw)!r}")
    source = raw.resolve()
    if not source.is_file():
        raise PathRefused(f"file_path is not a readable file: {source}")

    if config.upload_dir:
        root = Path(os.path.expanduser(config.upload_dir)).resolve()
        if not _under(source, root):
            raise PathRefused(
                f"file_path {str(source)!r} is outside the configured upload_dir "
                f"{str(root)!r}. Uploads may only come from that directory."
            )
    else:
        _refuse_private(source)
    return source

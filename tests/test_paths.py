"""The file boundaries: what a download may write, what an upload may read.

The model picks both paths, so these are the tests that make the settings mean
something. Each one is a case a prompt-injected turn would actually try.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

from stmp.bridge import Config
from stmp.paths import PathRefused, resolve_destination, resolve_source

from support import TempDirTest


def config(tmp: Path, **kwargs) -> Config:
    options = {"base_url": "http://phone.local:8787", "timeout": 75.0}
    options.update(kwargs)
    return Config(**options)


class DownloadConfines(TempDirTest):
    def test_relative_path_lands_inside_the_download_dir(self):
        target = resolve_destination(config(self.tmp, download_dir=str(self.tmp)), "out.pdf")
        self.assertEqual(target, (self.tmp / "out.pdf").resolve())

    def test_absolute_path_inside_the_download_dir_is_allowed(self):
        inner = self.tmp / "deep" / "out.pdf"
        inner.parent.mkdir()
        target = resolve_destination(config(self.tmp, download_dir=str(self.tmp)), str(inner))
        self.assertEqual(target, inner.resolve())

    def test_traversal_out_of_the_download_dir_is_refused(self):
        cfg = config(self.tmp, download_dir=str(self.tmp / "downloads"))
        (self.tmp / "downloads").mkdir()
        (self.tmp / "outside").mkdir()
        with self.assertRaises(PathRefused):
            resolve_destination(cfg, "../outside/pwned")

    def test_absolute_path_outside_the_download_dir_is_refused(self):
        cfg = config(self.tmp, download_dir=str(self.tmp / "downloads"))
        (self.tmp / "downloads").mkdir()
        with self.assertRaises(PathRefused):
            resolve_destination(cfg, "/etc/passwd")

    def test_a_symlink_pointing_out_of_the_directory_is_refused(self):
        root = self.tmp / "downloads"
        root.mkdir()
        outside = self.tmp / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        link = root / "link.txt"
        os.symlink(outside, link)
        with self.assertRaises(PathRefused):
            resolve_destination(config(self.tmp, download_dir=str(root)), "link.txt")

    def test_an_existing_file_is_not_replaced_by_default(self):
        target = self.tmp / "out.pdf"
        target.write_text("keep me", encoding="utf-8")
        with self.assertRaises(PathRefused):
            resolve_destination(config(self.tmp, download_dir=str(self.tmp)), "out.pdf")

    def test_overwrite_is_allowed_when_the_setting_says_so(self):
        target = self.tmp / "out.pdf"
        target.write_text("replace me", encoding="utf-8")
        resolved = resolve_destination(
            config(self.tmp, download_dir=str(self.tmp), allow_overwrite=True), "out.pdf"
        )
        self.assertEqual(resolved, target.resolve())

    def test_the_directory_itself_is_not_a_file(self):
        with self.assertRaises(PathRefused):
            resolve_destination(config(self.tmp, download_dir=str(self.tmp)), ".")


class UploadConfines(TempDirTest):
    def test_a_file_inside_the_upload_dir_is_allowed(self):
        source = self.tmp / "report.csv"
        source.write_text("a,b\n", encoding="utf-8")
        resolved = resolve_source(config(self.tmp, upload_dir=str(self.tmp)), str(source))
        self.assertEqual(resolved, source.resolve())

    def test_a_file_outside_the_upload_dir_is_refused(self):
        allowed = self.tmp / "allowed"
        allowed.mkdir()
        secret = self.tmp / "elsewhere.txt"
        secret.write_text("x", encoding="utf-8")
        with self.assertRaises(PathRefused):
            resolve_source(config(self.tmp, upload_dir=str(allowed)), str(secret))

    def test_relative_paths_are_refused(self):
        with self.assertRaises(PathRefused):
            resolve_source(config(self.tmp), "report.csv")

    def test_an_env_file_is_refused_without_an_upload_dir(self):
        env = self.tmp / ".env"
        env.write_text("TOKEN=1", encoding="utf-8")
        with self.assertRaises(PathRefused):
            resolve_source(config(self.tmp), str(env))

    def test_the_hermes_home_is_refused_without_an_upload_dir(self):
        with self.assertRaises(PathRefused):
            resolve_source(config(self.tmp), str(Path.home() / ".hermes" / "config.yaml"))

    def test_a_private_key_store_is_refused_without_an_upload_dir(self):
        with self.assertRaises(PathRefused):
            resolve_source(config(self.tmp), str(Path.home() / ".ssh" / "id_ed25519"))

    def test_an_upload_dir_overrides_the_private_deny_list(self):
        # The user naming a directory is the decision; the deny list is only the
        # default posture for when they have not.
        ssh_dir = self.tmp / "keys"
        ssh_dir.mkdir()
        key = ssh_dir / "id_ed25519"
        key.write_text("fake", encoding="utf-8")
        resolved = resolve_source(config(self.tmp, upload_dir=str(ssh_dir)), str(key))
        self.assertEqual(resolved, key.resolve())


if __name__ == "__main__":
    unittest.main()

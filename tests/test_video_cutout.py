import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image


TOOL_DIR = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = TOOL_DIR / "video_cutout.py"


def load_module():
    spec = importlib.util.spec_from_file_location("video_cutout", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class VideoCutoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_default_output_path_preserves_source_size_and_avoids_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = pathlib.Path(temp_dir) / "clip.mkv"
            video_path.write_bytes(b"fake")
            video_path.with_name("clip_cutout.mov").write_bytes(b"existing")

            output_path = self.module.build_default_output_path(video_path, max_width=0)

            self.assertEqual(video_path.with_name("clip_cutout_2.mov"), output_path)

    def test_default_output_path_can_include_preview_width(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = pathlib.Path(temp_dir) / "clip.mkv"
            video_path.write_bytes(b"fake")

            output_path = self.module.build_default_output_path(video_path, max_width=960)

            self.assertEqual(video_path.with_name("clip_cutout_960w.mov"), output_path)

    def test_ffmpeg_uses_exedir_before_other_locations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ffmpeg = pathlib.Path(temp_dir) / "ffmpeg.exe"
            ffmpeg.touch()
            with patch.dict(self.module.os.environ, {"EXEDIR": temp_dir}):
                self.assertEqual(ffmpeg, self.module.find_ffmpeg())

    def test_ffmpeg_can_live_beside_standalone_script(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = pathlib.Path(temp_dir) / "repo"
            repo.mkdir()
            ffmpeg = repo / "ffmpeg.exe"
            ffmpeg.touch()
            with patch.object(self.module, "__file__", str(repo / "video_cutout.py")):
                with patch.dict(self.module.os.environ, {"EXEDIR": ""}):
                    self.assertEqual(ffmpeg.resolve(), self.module.find_ffmpeg())

    def test_ffmpeg_uses_path_and_never_searches_repo_ancestors(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ancestor = pathlib.Path(temp_dir).resolve()
            repo = ancestor / "nested" / "repo"
            repo.mkdir(parents=True)
            (ancestor / "ffmpeg.exe").touch()
            with patch.object(self.module, "__file__", str(repo / "video_cutout.py")):
                with patch.dict(self.module.os.environ, {"EXEDIR": ""}):
                    with patch.object(self.module.shutil, "which", return_value="/bin/ffmpeg"):
                        # Ignore the developer's shared Windows install, but expose
                        # the ancestor binary so a monorepo lookup would fail this test.
                        with patch.object(pathlib.Path, "exists", lambda path: path == ancestor / "ffmpeg.exe"):
                            self.assertEqual(pathlib.Path("/bin/ffmpeg"), self.module.find_ffmpeg())

    def test_rvm_cache_falls_back_to_complete_legacy_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            current, legacy = root / "video-cutout", root / "legacy"
            current.mkdir()
            legacy.mkdir()
            (legacy / "RobustVideoMatting").mkdir()
            (legacy / "rvm_mobilenetv3.pth").touch()
            with patch.object(self.module, "RVM_MODEL_DIR", current):
                with patch.object(self.module, "LEGACY_RVM_MODEL_DIR", legacy):
                    self.assertEqual(
                        (legacy / "RobustVideoMatting", legacy / "rvm_mobilenetv3.pth"),
                        self.module.ensure_rvm_available(),
                    )
                    (current / "RobustVideoMatting").mkdir()
                    (current / "rvm_mobilenetv3.pth").touch()
                    self.assertEqual(
                        (current / "RobustVideoMatting", current / "rvm_mobilenetv3.pth"),
                        self.module.ensure_rvm_available(),
                    )

    def test_missing_rvm_files_point_to_standalone_dependency_script(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = pathlib.Path(temp_dir) / "missing"
            with patch.object(self.module, "RVM_MODEL_DIR", missing):
                with patch.object(self.module, "LEGACY_RVM_MODEL_DIR", missing):
                    with self.assertRaisesRegex(RuntimeError, r"Run \.\\deps\.ps1"):
                        self.module.ensure_rvm_available()

    def test_model_normalization_accepts_supported_models(self):
        self.assertEqual("u2net_human_seg", self.module.normalize_model(""))
        self.assertEqual("u2net_human_seg", self.module.normalize_model("u2net_human_seg"))
        self.assertEqual("isnet-general-use", self.module.normalize_model("isnet-general-use"))
        self.assertEqual("birefnet-portrait", self.module.normalize_model("birefnet-portrait"))

    def test_model_normalization_rejects_unknown_model(self):
        with self.assertRaises(ValueError):
            self.module.normalize_model("made-up-model")

    def test_alpha_tuning_shrinks_edge(self):
        image = Image.new("RGBA", (3, 3), (255, 255, 255, 255))
        tuned = self.module.apply_alpha_tuning(image, shrink=1, blur=0)

        alpha_values = list(tuned.getchannel("A").getdata())

        self.assertEqual([255] * 9, alpha_values)

    def test_alpha_tuning_preserves_transparent_border(self):
        image = Image.new("RGBA", (5, 5), (255, 255, 255, 0))
        image.putpixel((2, 2), (255, 255, 255, 255))

        tuned = self.module.apply_alpha_tuning(image, shrink=1, blur=0)

        self.assertEqual(0, tuned.getpixel((2, 2))[3])

    def test_alpha_mov_command_can_map_optional_audio(self):
        command = self.module.build_alpha_mov_command(
            ffmpeg=pathlib.Path(r"C:\dev\tools\ffmpeg.exe"),
            frame_pattern=pathlib.Path("frames/%06d.png"),
            input_path=pathlib.Path("input.mkv"),
            output_path=pathlib.Path("output.mov"),
            fps=30,
            include_audio=True,
        )

        self.assertIn("1:a?", command)
        self.assertIn("-shortest", command)
        self.assertEqual("output.mov", command[-1])

    def test_raw_alpha_mov_command_streams_rgba(self):
        command = self.module.build_raw_alpha_mov_command(
            ffmpeg=pathlib.Path(r"C:\dev\tools\ffmpeg.exe"),
            width=3840,
            height=2160,
            fps=30,
            input_path=pathlib.Path("input.mkv"),
            output_path=pathlib.Path("output.mov"),
            include_audio=False,
            codec="qtrle",
        )

        self.assertIn("rawvideo", command)
        self.assertIn("rgba", command)
        self.assertIn("3840x2160", command)
        self.assertIn("pipe:0", command)
        self.assertIn("qtrle", command)
        self.assertEqual("output.mov", command[-1])

    def test_raw_alpha_mov_command_can_use_prores_4444(self):
        command = self.module.build_raw_alpha_mov_command(
            ffmpeg=pathlib.Path(r"C:\dev\tools\ffmpeg.exe"),
            width=3840,
            height=2160,
            fps=30,
            input_path=pathlib.Path("input.mkv"),
            output_path=pathlib.Path("output.mov"),
            include_audio=True,
            codec="prores",
            duration_seconds=60,
        )

        self.assertIn("prores_ks", command)
        self.assertIn("yuva444p10le", command)
        self.assertEqual("12", command[command.index("-qscale:v") + 1])
        self.assertEqual("8", command[command.index("-alpha_bits") + 1])
        self.assertIn("1:a?", command)
        self.assertIn("-t", command)
        self.assertIn("60.000000", command)
        self.assertEqual("output.mov", command[-1])

    def test_format_duration_uses_compact_human_text(self):
        self.assertEqual("0s", self.module.format_duration(0))
        self.assertEqual("59s", self.module.format_duration(59))
        self.assertEqual("1m 01s", self.module.format_duration(61))
        self.assertEqual("1h 02m 03s", self.module.format_duration(3723))

    def test_get_session_providers_handles_missing_inner_session(self):
        self.assertEqual([], self.module.get_session_providers(object()))


if __name__ == "__main__":
    unittest.main()

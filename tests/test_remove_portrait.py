import importlib.util
import pathlib
import tempfile
import unittest

from PIL import Image


TOOL_DIR = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = TOOL_DIR / "remove_portrait.py"


def load_module():
    spec = importlib.util.spec_from_file_location("remove_portrait", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RemovePortraitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_default_output_path_preserves_source_size_and_avoids_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = pathlib.Path(temp_dir) / "clip.mkv"
            video_path.write_bytes(b"fake")
            video_path.with_name("clip_portrait_removed.mov").write_bytes(b"existing")

            output_path = self.module.build_default_output_path(video_path, max_width=0)

            self.assertEqual(video_path.with_name("clip_portrait_removed_2.mov"), output_path)

    def test_default_output_path_can_include_preview_width(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = pathlib.Path(temp_dir) / "clip.mkv"
            video_path.write_bytes(b"fake")

            output_path = self.module.build_default_output_path(video_path, max_width=960)

            self.assertEqual(video_path.with_name("clip_portrait_removed_960w.mov"), output_path)

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

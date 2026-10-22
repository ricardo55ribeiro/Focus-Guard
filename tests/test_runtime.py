import importlib
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "agent"))
from classifier import ai, rules
import install
import ollama_manager


class RuntimeTests(unittest.TestCase):
    def test_ai_ignores_remote_host_and_proxy(self):
        with patch.dict(os.environ, {"OLLAMA_HOST": "https://remote.invalid", "HTTPS_PROXY": "http://proxy.invalid:8080", "HTTP_PROXY": "http://proxy.invalid:8080"}):
            with patch("ollama.Client") as client:
                importlib.reload(ai)
                client.assert_called_once_with(host="http://127.0.0.1:11434", trust_env=False, follow_redirects=False, timeout=120)
        importlib.reload(ai)

    def test_classification_thresholds_and_clamping_are_unchanged(self):
        for score, expected, category in ((-10, 0, "distracted"), (35, 35, "distracted"), (36, 36, "neutral"), (65, 65, "neutral"), (66, 66, "productive"), (200, 100, "productive")):
            with self.subTest(score=score):
                response = SimpleNamespace(message=SimpleNamespace(content=json.dumps({"score": score, "reason": "test"})))
                with patch.object(ai.ollama, "chat", return_value=response):
                    result = ai.classify(study_goal="test")
                self.assertEqual(result["score"], expected)
                self.assertEqual(result["category"], category)

    def test_background_violation_and_fallback(self):
        for text, category in (("VIOLATION: blocked topic", "distracted"), ("OK: study", "neutral")):
            with patch.object(ai.ollama, "chat", return_value=SimpleNamespace(message=SimpleNamespace(content=text))):
                self.assertEqual(ai.classify_background(["example rule"])["category"], category)
        with patch.object(ai.ollama, "chat", side_effect=ConnectionError("offline")):
            self.assertEqual(ai.classify()["category"], "neutral")

    def test_prompt_and_pledge_generation_still_work(self):
        args = ("study", "browser", "title", "https://example.org", "page")
        response = SimpleNamespace(message=SimpleNamespace(content="I will focus."))
        with patch.object(ai.ollama, "chat", return_value=response):
            self.assertEqual(ai.generate_heckler(*args), "I will focus.")
            self.assertEqual(ai.generate_pledge(*args), "I will focus.")
            self.assertEqual(ai.generate_session_nudge(*args), "I will focus.")
            self.assertEqual(ai.generate_background_nudge(["rule"], *args[1:]), "I will focus.")

    def test_rule_precedence_is_unchanged(self):
        settings = {"always_block_processes": ["game.exe"], "always_block_domains": ["blocked.example"], "always_allow_domains": ["allowed.example"]}
        with patch.object(rules, "SETTINGS", settings):
            self.assertEqual(rules.check_rules("GAME.EXE", "https://allowed.example"), "block")
            self.assertEqual(rules.check_rules("browser.exe", "https://www.blocked.example/path"), "block")
            self.assertEqual(rules.check_rules("browser.exe", "https://allowed.example"), "allow")
            self.assertEqual(rules.check_rules("browser.exe", "https://unknown.example"), "ambiguous")

    def test_model_server_started_only_on_loopback(self):
        with patch.object(ollama_manager, "_is_running", side_effect=[False, True]), patch.object(ollama_manager.time, "sleep"), patch.object(ollama_manager.subprocess, "Popen") as popen:
            self.assertTrue(ollama_manager.ensure_running())
            self.assertEqual(popen.call_args.kwargs["env"]["OLLAMA_HOST"], "127.0.0.1:11434")
            ollama_manager.shutdown_if_started()

    def test_installer_settings_preserve_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config" / "settings.json"
            with patch.object(install, "SETTINGS_FILE", path):
                install.create_settings_if_missing(queue.Queue())
                self.assertEqual(json.loads(path.read_text()), install.DEFAULT_SETTINGS)
                path.write_text('{"custom": true}')
                install.create_settings_if_missing(queue.Queue())
                self.assertEqual(json.loads(path.read_text()), {"custom": True})

    def test_example_matches_installer_defaults(self):
        self.assertEqual(json.loads((ROOT / "settings.example.json").read_text()), install.DEFAULT_SETTINGS)

    def test_installer_does_not_download_into_repository(self):
        self.assertFalse(install.OLLAMA_INSTALLER_PATH.is_relative_to(ROOT))

    def test_installer_model_pull_uses_local_server(self):
        process = Mock(stdout=[], wait=Mock(return_value=0))
        with patch.object(install.subprocess, "Popen", return_value=process) as popen:
            self.assertTrue(install.pull_model(queue.Queue(), "qwen2.5:3b", 0, 100, "test"))
            self.assertEqual(popen.call_args.kwargs["env"]["OLLAMA_HOST"], "127.0.0.1:11434")

    def test_python_minimum_matches_patched_dependencies(self):
        with patch.object(install.sys, "version_info", (3, 10, 0)):
            self.assertFalse(install.check_python_version(queue.Queue()))
        with patch.object(install.sys, "version_info", (3, 11, 0)):
            self.assertTrue(install.check_python_version(queue.Queue()))

    @unittest.skipUnless(sys.platform == "win32", "Windows tray")
    def test_tray_icon_renders_with_patched_pillow(self):
        import tray
        self.assertEqual(tray._make_icon("#4caf50").size, (64, 64))


if __name__ == "__main__":
    unittest.main()

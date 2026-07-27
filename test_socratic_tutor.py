import unittest
import os
import tempfile
import shutil
import base64
import json
from unittest.mock import patch, MagicMock

# Import the functions to test.
# Since we are in the same directory, we can import them from socratic_tutor
import socratic_tutor

class TestSocraticTutor(unittest.TestCase):
    def setUp(self):
        # Set up a temporary directory to avoid cluttering the filesystem
        self.test_dir = tempfile.mkdtemp()
        
        # Patch the file constants in socratic_tutor to point to our temp dir
        self.orig_key_file = socratic_tutor.KEY_FILE
        self.orig_config_file = socratic_tutor.TUTOR_CONFIG_FILE
        self.orig_progress_file = socratic_tutor.TUTOR_PROGRESS_FILE
        
        socratic_tutor.KEY_FILE = os.path.join(self.test_dir, ".tutor_key")
        socratic_tutor.TUTOR_CONFIG_FILE = os.path.join(self.test_dir, ".tutor_config")
        socratic_tutor.TUTOR_PROGRESS_FILE = os.path.join(self.test_dir, ".tutor_progress")

    def tearDown(self):
        # Restore the original constants
        socratic_tutor.KEY_FILE = self.orig_key_file
        socratic_tutor.TUTOR_CONFIG_FILE = self.orig_config_file
        socratic_tutor.TUTOR_PROGRESS_FILE = self.orig_progress_file
        # Clean up temporary directory
        shutil.rmtree(self.test_dir)

    def test_config_load_and_save(self):
        # Test loading when config file doesn't exist
        config = socratic_tutor.load_tutor_config()
        self.assertEqual(config["voice_speed"], 1.1)
        self.assertEqual(config["voice_name"], "Aoede")

        # Save config and load it back
        new_config = {"voice_speed": 1.5, "voice_name": "Journey"}
        socratic_tutor.save_tutor_config(new_config)
        
        loaded = socratic_tutor.load_tutor_config()
        self.assertEqual(loaded["voice_speed"], 1.5)
        self.assertEqual(loaded["voice_name"], "Journey")

    def test_obfuscated_key_save_and_get(self):
        # Test loading when key file doesn't exist
        key = socratic_tutor.get_obfuscated_key()
        self.assertEqual(key, "")

        # Save key and retrieve it
        test_key = "AIzaSyTestKey12345"
        success = socratic_tutor.save_obfuscated_key(test_key)
        self.assertTrue(success)

        retrieved_key = socratic_tutor.get_obfuscated_key()
        self.assertEqual(retrieved_key, test_key)

    def test_scan_directory(self):
        # Create a mock directory structure in our temp dir
        src_dir = os.path.join(self.test_dir, "src")
        os.makedirs(src_dir)
        
        # Create a Python file and a text file
        py_file_path = os.path.join(src_dir, "script.py")
        with open(py_file_path, "w") as f:
            f.write("print('hello')")
            
        txt_file_path = os.path.join(src_dir, "doc.txt")
        with open(txt_file_path, "w") as f:
            f.write("Some documentation")
            
        # Create an ignored directory and a file in it
        git_dir = os.path.join(src_dir, ".git")
        os.makedirs(git_dir)
        git_file_path = os.path.join(git_dir, "config")
        with open(git_file_path, "w") as f:
            f.write("[core]")

        # Create an unsupported extension file
        unsupported_file_path = os.path.join(src_dir, "audio.mp3")
        with open(unsupported_file_path, "w") as f:
            f.write("some binary data")

        # Run scan_directory
        file_tree = socratic_tutor.scan_directory(src_dir)

        # Verify findings
        self.assertIn("script.py", file_tree)
        self.assertIn("doc.txt", file_tree)
        self.assertNotIn(".git/config", file_tree)
        self.assertNotIn("audio.mp3", file_tree)

    @patch('urllib.request.urlopen')
    def test_scrape_url(self, mock_urlopen):
        # Set up mock response
        mock_response = MagicMock()
        mock_response.read.return_value = b"<html><head><title>Test</title><style>body {color: red;}</style><script>console.log('hi');</script></head><body><h1>Hello World</h1>  <p>Socratic tutor test.</p></body></html>"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Scrape and verify cleaning
        scraped_text = socratic_tutor.scrape_url("http://example.com")
        
        # Style and script should be completely stripped
        self.assertNotIn("color: red", scraped_text)
        self.assertNotIn("console.log", scraped_text)
        
        # Main text should be present and whitespace normalized
        self.assertIn("Hello World", scraped_text)
        self.assertIn("Socratic tutor test.", scraped_text)

    @patch('urllib.request.urlopen')
    def test_extract_concepts(self, mock_urlopen):
        # 1. Success case
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"candidates": [{"content": {"parts": [{"text": "[\\"SYN Connection\\", \\"SYN-ACK Verification\\", \\"ACK Establishment\\"]"}]}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        concepts = socratic_tutor.extract_concepts("api_key", "Dense study material about TCP Handshake.")
        self.assertEqual(len(concepts), 3)
        self.assertEqual(concepts[0]["concept"], "SYN Connection")
        self.assertEqual(concepts[0]["status"], "Unvisited")
        self.assertEqual(concepts[0]["score"], 0.0)

        # 2. Failure fallback case
        mock_urlopen.side_effect = Exception("HTTP 500 Server Error")
        fallback_concepts = socratic_tutor.extract_concepts("api_key", "Dense study material.")
        self.assertEqual(len(fallback_concepts), 3)
        self.assertEqual(fallback_concepts[0]["concept"], "Core Definitions and Fundamentals")

    def test_draw_progress_dashboard(self):
        concepts = [
            {"id": 1, "concept": "SYN Connection", "status": "Mastered", "score": 1.0},
            {"id": 2, "concept": "SYN-ACK Verification", "status": "Testing", "score": 0.5},
            {"id": 3, "concept": "ACK Establishment", "status": "Unvisited", "score": 0.0}
        ]
        # Just ensure drawing function executes without throwing any exceptions
        try:
            socratic_tutor.draw_progress_dashboard(concepts)
            success = True
        except Exception as e:
            success = False
        self.assertTrue(success)

    @patch('urllib.request.urlopen')
    def test_query_gemini_json_parsing(self, mock_urlopen):
        # Set up mock response containing structured JSON string in the text part
        mock_response = MagicMock()
        json_payload = {
            "tutor_speech": "Exactly! Now how does the server respond?",
            "assessed_concept_id": 1,
            "comprehension_score_change": 0.5,
            "concept_mastered": False,
            "next_concept_id_to_test": 2
        }
        json_string = json.dumps(json_payload)
        
        # Structure matching Gemini API response
        mock_response.read.return_value = json.dumps({
            "candidates": [{
                "content": {
                    "parts": [{"text": json_string}]
                }
            }]
        }).encode('utf-8')
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Execute query_gemini (it should not try to run TTS because model is set to gemini-3.5-flash-lite)
        ai_text, audio_base64, evaluation = socratic_tutor.query_gemini(
            "api_key",
            "gemini-3.5-flash-lite",
            "System instructions...",
            "User prompt...",
            []
        )

        # Verify parsing and three-value return
        self.assertEqual(ai_text, "Exactly! Now how does the server respond?")
        self.assertIsNone(audio_base64)
        self.assertIsNotNone(evaluation)
        self.assertEqual(evaluation["assessed_concept_id"], 1)
        self.assertEqual(evaluation["comprehension_score_change"], 0.5)

    def test_progress_load_and_save(self):
        # 1. Test load when progress file doesn't exist
        progress = socratic_tutor.load_tutor_progress()
        self.assertEqual(progress, {})

        # 2. Save progress and load it back
        test_progress = {
            "track::module": [
                {"id": 1, "concept": "Test Concept", "status": "Mastered", "score": 1.0}
            ]
        }
        success = socratic_tutor.save_tutor_progress(test_progress)
        self.assertTrue(success)

        loaded = socratic_tutor.load_tutor_progress()
        self.assertEqual(len(loaded["track::module"]), 1)
        self.assertEqual(loaded["track::module"][0]["concept"], "Test Concept")
        self.assertEqual(loaded["track::module"][0]["status"], "Mastered")
        self.assertEqual(loaded["track::module"][0]["score"], 1.0)

if __name__ == '__main__':
    unittest.main()

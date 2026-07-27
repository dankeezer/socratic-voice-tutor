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
        
        socratic_tutor.KEY_FILE = os.path.join(self.test_dir, ".tutor_key")
        socratic_tutor.TUTOR_CONFIG_FILE = os.path.join(self.test_dir, ".tutor_config")

    def tearDown(self):
        # Restore the original constants
        socratic_tutor.KEY_FILE = self.orig_key_file
        socratic_tutor.TUTOR_CONFIG_FILE = self.orig_config_file
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

if __name__ == '__main__':
    unittest.main()

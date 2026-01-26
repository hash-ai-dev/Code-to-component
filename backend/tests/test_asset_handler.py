import unittest
import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from core.asset_handler import AssetHandler

class TestAssetHandler(unittest.TestCase):
    def setUp(self):
        self.mock_assets = {
            "Design School Illustration": "data:image/svg+xml;base64,MOCK_ILLUSTRATION",
            "Google Logo": "data:image/png;base64,MOCK_GOOGLE"
        }
        self.handler = AssetHandler(self.mock_assets)
        
    def test_token_mapping(self):
        """Test that tokens are assigned correctly and deterministically"""
        # Sorted keys: 'Design School Illustration' (0), 'Google Logo' (1)
        self.assertEqual(self.handler.token_map["__ASSET_0__"], "data:image/svg+xml;base64,MOCK_ILLUSTRATION")
        self.assertEqual(self.handler.token_map["__ASSET_1__"], "data:image/png;base64,MOCK_GOOGLE")
        
    def test_prompt_generation(self):
        """Test prompt section contains instructions and tokens"""
        prompt = self.handler.get_prompt_section()
        self.assertIn("__ASSET_0__", prompt)
        self.assertIn("Design School Illustration", prompt)
        self.assertIn("CRITICAL: ASSET PLACEMENT RULES", prompt)
        
    def test_replacement_success(self):
        """Test replacing tokens in code"""
        code = '<img src="__ASSET_0__" /> <img src="__ASSET_1__" />'
        new_code, count, missing = self.handler.replace_tokens(code)
        
        self.assertEqual(count, 2)
        self.assertEqual(len(missing), 0)
        self.assertIn('src="data:image/svg+xml;base64,MOCK_ILLUSTRATION"', new_code)
        
    def test_missing_tokens(self):
        """Test detection of unused tokens"""
        code = '<img src="__ASSET_0__" />' # Missing ASSET_1
        new_code, count, missing = self.handler.replace_tokens(code)
        
        self.assertEqual(count, 1)
        self.assertEqual(len(missing), 1)
        self.assertIn("__ASSET_1__", missing)

if __name__ == '__main__':
    unittest.main()

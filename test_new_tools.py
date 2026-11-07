"""Tests for new v1.6.19 tools - network and data utilities."""
import unittest
from agent_core.network import check_port
from agent_core.data_utils import (
    flatten_dict,
    format_csv,
    format_json,
    merge_dicts,
    parse_csv,
    parse_json,
)


class TestDataUtils(unittest.TestCase):
    """Test data transformation utilities."""

    def test_parse_json_valid(self):
        result = parse_json('{"name": "test", "value": 42}')
        self.assertEqual(result["name"], "test")
        self.assertEqual(result["value"], 42)

    def test_parse_json_invalid(self):
        with self.assertRaises(ValueError):
            parse_json("not valid json")

    def test_format_json(self):
        data = {"key": "value"}
        result = format_json(data, indent=2)
        self.assertIn('"key": "value"', result)

    def test_parse_csv_basic(self):
        csv_text = "Name,Age\nAlice,30\nBob,25"
        result = parse_csv(csv_text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["Name"], "Alice")
        self.assertEqual(result[1]["Age"], "25")

    def test_parse_csv_custom_delimiter(self):
        csv_text = "Name;Age\nAlice;30"
        result = parse_csv(csv_text, delimiter=";")
        self.assertEqual(result[0]["Name"], "Alice")

    def test_format_csv(self):
        data = [{"Name": "Alice", "Age": 30}]
        result = format_csv(data)
        self.assertIn("Name,Age", result)
        self.assertIn("Alice,30", result)

    def test_merge_dicts_simple(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = merge_dicts(base, override)
        self.assertEqual(result, {"a": 1, "b": 3, "c": 4})

    def test_merge_dicts_nested(self):
        base = {"a": 1, "b": {"x": 1, "y": 2}}
        override = {"b": {"y": 3, "z": 4}, "c": 5}
        result = merge_dicts(base, override)
        self.assertEqual(result["a"], 1)
        self.assertEqual(result["b"]["x"], 1)
        self.assertEqual(result["b"]["y"], 3)
        self.assertEqual(result["b"]["z"], 4)
        self.assertEqual(result["c"], 5)

    def test_flatten_dict_simple(self):
        data = {"a": {"b": {"c": 1}}, "d": 2}
        result = flatten_dict(data)
        self.assertEqual(result["a.b.c"], 1)
        self.assertEqual(result["d"], 2)

    def test_flatten_dict_custom_sep(self):
        data = {"a": {"b": 1}}
        result = flatten_dict(data, sep="/")
        self.assertIn("a/b", result)
        self.assertEqual(result["a/b"], 1)


class TestNetwork(unittest.TestCase):
    """Test network utilities."""

    def test_check_port_closed(self):
        """Test checking a port that should be closed."""
        result = check_port("localhost", 59999, timeout=1)
        self.assertFalse(result["open"])
        self.assertEqual(result["host"], "localhost")
        self.assertEqual(result["port"], 59999)

    def test_check_port_invalid_host(self):
        """Test checking an invalid host."""
        result = check_port("invalid.host.that.does.not.exist", 80, timeout=1)
        self.assertFalse(result["open"])
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()

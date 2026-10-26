import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import inventario


class InventarioTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        inventario.init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def add_sample(self, tag="IT-0001", status="Disponible", asset_type="Laptop", assigned_to=""):
        return inventario.add_asset(
            tag, asset_type, "Lenovo", "ThinkPad", "SER-123", "Oficinas", assigned_to,
            status, "2025-01-15", "Equipo de prueba", db_path=self.db_path,
        )

    def test_add_and_list_asset(self):
        self.add_sample()
        rows = inventario.list_assets(db_path=self.db_path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["asset_tag"], "IT-0001")

    def test_duplicate_asset_tag_is_rejected(self):
        self.add_sample()
        with self.assertRaises(ValueError):
            self.add_sample()

    def test_search_by_location(self):
        self.add_sample()
        results = inventario.search_assets("Oficinas", db_path=self.db_path)
        self.assertEqual(len(results), 1)

    def test_update_status(self):
        self.add_sample(assigned_to="Eduardo Demo")
        updated = inventario.update_status("IT-0001", "Asignado", "Eduardo Demo", db_path=self.db_path)
        self.assertTrue(updated)
        row = inventario.list_assets(db_path=self.db_path)[0]
        self.assertEqual(row["status"], "Asignado")
        self.assertEqual(row["assigned_to"], "Eduardo Demo")

    def test_enter_style_none_preserves_current_assignee(self):
        self.add_sample(assigned_to="Usuario de prueba")
        updated = inventario.update_status("IT-0001", "En mantenimiento", None, db_path=self.db_path)
        self.assertTrue(updated)
        row = inventario.list_assets(db_path=self.db_path)[0]
        self.assertEqual(row["status"], "En mantenimiento")
        self.assertEqual(row["assigned_to"], "Usuario de prueba")
        self.assertEqual(row["manufacturer"], "Lenovo")
        self.assertEqual(row["model"], "ThinkPad")

    def test_update_to_a_different_assignee(self):
        self.add_sample(assigned_to="Usuario de prueba")
        updated = inventario.update_status(
            "IT-0001", "En mantenimiento", "Nueva persona", db_path=self.db_path
        )
        self.assertTrue(updated)
        row = inventario.list_assets(db_path=self.db_path)[0]
        self.assertEqual(row["assigned_to"], "Nueva persona")
        self.assertEqual(row["status"], "En mantenimiento")

    def test_assignment_prompt_accepts_new_assignee(self):
        with patch("builtins.input", side_effect=["2", "Nueva persona"]):
            new_assignee = inventario.ask_assignment_change("Usuario de prueba")
        self.assertEqual(new_assignee, "Nueva persona")

    def test_assignment_prompt_enter_preserves_current(self):
        with patch("builtins.input", side_effect=[""]):
            new_assignee = inventario.ask_assignment_change("Usuario de prueba")
        self.assertIsNone(new_assignee)

    def test_assignment_prompt_option_three_clears_assignee(self):
        with patch("builtins.input", side_effect=["3"]):
            new_assignee = inventario.ask_assignment_change("Usuario de prueba")
        self.assertEqual(new_assignee, "")

    def test_explicit_empty_assignment_clears_assignee(self):
        self.add_sample(assigned_to="Usuario de prueba")
        inventario.update_status("IT-0001", "Asignado", "", db_path=self.db_path)
        row = inventario.list_assets(db_path=self.db_path)[0]
        self.assertEqual(row["assigned_to"], "")

    def test_asset_type_and_status_are_case_insensitive(self):
        self.add_sample(tag="IT-UPPER", status="dIsPoNiBlE", asset_type="lApToP")
        row = inventario.list_assets(db_path=self.db_path)[0]
        self.assertEqual(row["asset_type"], "Laptop")
        self.assertEqual(row["status"], "Disponible")

    def test_update_status_is_case_insensitive(self):
        self.add_sample()
        inventario.update_status("IT-0001", "eN mAnTeNiMiEnTo", db_path=self.db_path)
        row = inventario.list_assets(db_path=self.db_path)[0]
        self.assertEqual(row["status"], "En mantenimiento")

    def test_filter_status_is_case_insensitive(self):
        self.add_sample(status="En mantenimiento")
        rows = inventario.list_assets(db_path=self.db_path, status="EN MANTENIMIENTO")
        self.assertEqual(len(rows), 1)

    def test_invalid_date_is_rejected(self):
        with self.assertRaises(ValueError):
            inventario.add_asset("IT-2", "Laptop", "Dell", "Latitude", "S2", "IT", "", "Disponible", "15-01-2025", "", db_path=self.db_path)

    def test_invalid_type_shows_allowed_options(self):
        with self.assertRaisesRegex(ValueError, "Opciones permitidas"):
            self.add_sample(asset_type="Notebook")


if __name__ == "__main__":
    unittest.main(verbosity=2)

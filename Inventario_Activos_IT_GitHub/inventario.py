"""Inventario de activos IT con SQLite y exportación a CSV.

Proyecto personal de portafolio. Ejecuta `python inventario.py` y usa el menú.
"""
from __future__ import annotations

import csv
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "inventario_it.db"
EXPORT_DIR = BASE_DIR / "exports"
STATUSES = ("Disponible", "Asignado", "En mantenimiento", "Retirado")
ASSET_TYPES = ("Laptop", "Desktop", "Monitor", "Impresora", "Switch", "Router", "Otro")


def normalize_choice(value: str, choices: tuple[str, ...], field_label: str) -> str:
    """Return the canonical spelling of a choice, ignoring letter case and outer spaces."""
    cleaned = value.strip()
    for choice in choices:
        if cleaned.casefold() == choice.casefold():
            return choice
    options = ", ".join(choices)
    raise ValueError(f"{field_label} no válido. Opciones permitidas: {options}.")


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    with closing(connect(db_path)) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_tag TEXT NOT NULL UNIQUE,
                asset_type TEXT NOT NULL,
                manufacturer TEXT NOT NULL,
                model TEXT NOT NULL,
                serial_number TEXT NOT NULL DEFAULT '',
                location TEXT NOT NULL,
                assigned_to TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Disponible',
                purchase_date TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_location ON assets(location)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status)")
        conn.commit()


def add_asset(asset_tag: str, asset_type: str, manufacturer: str, model: str,
              serial_number: str, location: str, assigned_to: str, status: str,
              purchase_date: str, notes: str, db_path: Path = DB_PATH) -> int:
    required = {"etiqueta": asset_tag, "tipo": asset_type, "fabricante": manufacturer,
                "modelo": model, "ubicación": location}
    missing = [label for label, value in required.items() if not value.strip()]
    if missing:
        raise ValueError("Faltan campos obligatorios: " + ", ".join(missing))
    # Accept input in any letter case, but store consistent canonical values.
    asset_type = normalize_choice(asset_type, ASSET_TYPES, "Tipo de activo")
    status = normalize_choice(status, STATUSES, "Estado")
    if purchase_date:
        try:
            date.fromisoformat(purchase_date)
        except ValueError as exc:
            raise ValueError("La fecha debe tener formato AAAA-MM-DD.") from exc

    with closing(connect(db_path)) as conn:
        try:
            cursor = conn.execute(
                """INSERT INTO assets
                   (asset_tag, asset_type, manufacturer, model, serial_number, location,
                    assigned_to, status, purchase_date, notes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (asset_tag.strip(), asset_type, manufacturer.strip(), model.strip(), serial_number.strip(),
                 location.strip(), assigned_to.strip(), status, purchase_date.strip(), notes.strip(),
                 date.today().isoformat()),
            )
            conn.commit()
            return int(cursor.lastrowid)
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            raise ValueError("Ya existe un activo con esa etiqueta; usa una etiqueta única.") from exc


def list_assets(db_path: Path = DB_PATH, status: str = "") -> list[sqlite3.Row]:
    with closing(connect(db_path)) as conn:
        if status.strip():
            canonical_status = normalize_choice(status, STATUSES, "Estado")
            rows = conn.execute(
                "SELECT * FROM assets WHERE status = ? ORDER BY asset_tag", (canonical_status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM assets ORDER BY asset_tag").fetchall()
        return rows


def search_assets(term: str, db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    like = f"%{term.strip()}%"
    with closing(connect(db_path)) as conn:
        return conn.execute(
            """SELECT * FROM assets
               WHERE asset_tag LIKE ? OR serial_number LIKE ? OR manufacturer LIKE ?
                  OR model LIKE ? OR location LIKE ? OR assigned_to LIKE ?
               ORDER BY asset_tag""",
            (like, like, like, like, like, like),
        ).fetchall()


def get_asset(asset_tag: str, db_path: Path = DB_PATH) -> sqlite3.Row | None:
    """Return one asset by its exact tag, or None if it does not exist."""
    with closing(connect(db_path)) as conn:
        return conn.execute(
            "SELECT * FROM assets WHERE asset_tag = ?", (asset_tag.strip(),)
        ).fetchone()


def ask_assignment_change(current_assignee: str) -> str | None:
    """Ask whether to keep, replace, or clear an asset's current assignee.

    Returns None to preserve the current value, an entered name to replace it,
    or an empty string to clear the assignment.
    """
    shown_assignee = current_assignee or "(sin responsable)"
    print(f"Responsable actual: {shown_assignee}")
    print("1. Conservar responsable actual (predeterminado)")
    print("2. Asignar a otra persona")
    print("3. Quitar asignación")
    choice = ask("Selecciona una opción [1]: ").casefold()
    if choice in ("", "1"):
        return None
    if choice == "2":
        return ask("Nombre del nuevo responsable: ", required=True)
    if choice == "3":
        return ""
    raise ValueError("Opción de asignación no válida. Escribe 1, 2 o 3.")


def update_status(asset_tag: str, status: str, assigned_to: str | None = None,
                  db_path: Path = DB_PATH) -> bool:
    status = normalize_choice(status, STATUSES, "Estado")
    with closing(connect(db_path)) as conn:
        if assigned_to is None:
            cursor = conn.execute("UPDATE assets SET status = ? WHERE asset_tag = ?", (status, asset_tag.strip()))
        else:
            cursor = conn.execute(
                "UPDATE assets SET status = ?, assigned_to = ? WHERE asset_tag = ?",
                (status, assigned_to.strip(), asset_tag.strip()),
            )
        conn.commit()
        return cursor.rowcount > 0


def summary(db_path: Path = DB_PATH) -> list[sqlite3.Row]:
    with closing(connect(db_path)) as conn:
        return conn.execute(
            "SELECT status, COUNT(*) AS total FROM assets GROUP BY status ORDER BY status"
        ).fetchall()


def export_csv(db_path: Path = DB_PATH, export_dir: Path = EXPORT_DIR) -> Path:
    export_dir.mkdir(parents=True, exist_ok=True)
    path = export_dir / f"inventario_activos_{date.today().isoformat()}.csv"
    rows = list_assets(db_path)
    columns = ["asset_tag", "asset_type", "manufacturer", "model", "serial_number", "location",
               "assigned_to", "status", "purchase_date", "notes", "created_at"]
    with path.open("w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in columns})
    return path


def ask(label: str, required: bool = False) -> str:
    while True:
        value = input(label).strip()
        if value or not required:
            return value
        print("Este campo es obligatorio.")


def show_rows(rows: list[sqlite3.Row]) -> None:
    if not rows:
        print("No se encontraron registros.")
        return
    print("\nETIQUETA      TIPO       FABRICANTE / MODELO        UBICACIÓN       ESTADO              ASIGNADO A")
    print("-" * 105)
    for row in rows:
        maker_model = f"{row['manufacturer']} {row['model']}"[:25]
        print(f"{row['asset_tag'][:13]:13} {row['asset_type'][:10]:10} {maker_model:26} "
              f"{row['location'][:15]:15} {row['status'][:19]:19} {row['assigned_to'][:20]}")


def create_from_prompt() -> None:
    print("\nAlta de activo (los campos con * son obligatorios)")
    asset_tag = ask("Etiqueta / ID del activo *: ", True)
    asset_type = ask(f"Tipo {ASSET_TYPES} *: ", True)
    manufacturer = ask("Fabricante *: ", True)
    model = ask("Modelo *: ", True)
    serial_number = ask("Número de serie: ")
    location = ask("Ubicación / área *: ", True)
    assigned_to = ask("Persona asignada: ")
    status = ask(f"Estado {STATUSES} [Disponible]: ") or "Disponible"
    purchase_date = ask("Fecha de compra AAAA-MM-DD: ")
    notes = ask("Notas: ")
    new_id = add_asset(asset_tag, asset_type, manufacturer, model, serial_number,
                       location, assigned_to, status, purchase_date, notes)
    print(f"Activo guardado correctamente (ID interno {new_id}).")


def main() -> None:
    init_db()
    while True:
        print("\n=== INVENTARIO DE ACTIVOS IT ===")
        print("1. Registrar activo")
        print("2. Listar activos")
        print("3. Buscar activo")
        print("4. Actualizar estado / asignación")
        print("5. Resumen por estado")
        print("6. Exportar inventario a CSV")
        print("0. Salir")
        choice = input("Selecciona una opción: ").strip()
        try:
            if choice == "1":
                create_from_prompt()
            elif choice == "2":
                filter_status = ask(f"Filtrar por estado {STATUSES} o Enter para todos: ")
                show_rows(list_assets(status=filter_status))
            elif choice == "3":
                show_rows(search_assets(ask("Buscar por etiqueta, serie, fabricante, modelo, área o responsable: ")))
            elif choice == "4":
                tag = ask("Etiqueta del activo a modificar: ", True)
                current_asset = get_asset(tag)
                if current_asset is None:
                    print("No se encontró la etiqueta indicada.")
                    continue
                status = ask(f"Nuevo estado {STATUSES}: ", True)
                assigned = ask_assignment_change(current_asset["assigned_to"])
                if update_status(tag, status, assigned):
                    updated_asset = get_asset(tag)
                    print("Activo actualizado correctamente.")
                    print(f"Estado guardado: {updated_asset['status']}")
                    print(f"Responsable guardado: {updated_asset['assigned_to'] or '(sin responsable)'}")
                else:
                    print("No se encontró la etiqueta indicada.")
            elif choice == "5":
                report = summary()
                if not report:
                    print("Todavía no hay activos registrados.")
                else:
                    print("\nResumen por estado")
                    for item in report:
                        print(f"{item['status']:<20} {item['total']:>4}")
            elif choice == "6":
                print(f"CSV exportado: {export_csv()}")
            elif choice == "0":
                print("Saliendo del inventario.")
                break
            else:
                print("Opción no válida.")
        except ValueError as exc:
            print(f"No se pudo completar la operación: {exc}")
        except (sqlite3.Error, OSError) as exc:
            print(f"Ocurrió un error de base de datos o archivo: {exc}")


if __name__ == "__main__":
    main()

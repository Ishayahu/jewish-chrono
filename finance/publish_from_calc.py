# VERSION: 2026-11-23T08:07:54.416+00:00
#!/usr/bin/env python3
"""Публикация финансового дашборда из сохранённой локальной таблицы Calc.

По умолчанию ничего не публикует: python publish_from_calc.py
После настройки и проверки: python publish_from_calc.py --publish

Зависимости: pip install python-calamine cryptography
Читает сохранённые значения формул .ods/.xlsx; НЕ пересчитывает формулы.
Перед запуском сохраните книгу в LibreOffice и закройте окно сохранения.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from python_calamine import CalamineWorkbook


# ============================================================================
# НАСТРОЙКИ. При изменении расположения значений правьте ТОЛЬКО этот раздел.
# Пока листа «Экспорт» нет, ячейки ниже — ПРИМЕР предлагаемой раскладки,
# а не утверждение о структуре вашей существующей локальной таблицы.
# Можно поставить ссылку на ЛЮБОЙ другой лист: ("Название листа", "B25").
# В Calc удобно создать лист «Экспорт» с формулами-ссылками на старые ячейки.
# ============================================================================
WORKBOOK_PATH = Path(r"ЗАМЕНИТЬ_НА_ПУТЬ_К_БЮДЖЕТУ.ods")
REPOSITORY = "Ishayahu/jewish-chrono"
BRANCH = "main"
PUBLISH_ENABLED = False  # Поменять на True ТОЛЬКО после переключения workflow!
TZ = "Europe/Moscow"

# Один адрес = (лист, ячейка); все суммы — числовые результаты формул Calc.
CELLS = {
    "familyDeficit": ("Экспорт", "B2"),       # Исторический дефицит на 14.10
    "deficit": ("Экспорт", "B3"),             # Прогнозный дефицит цикла
    "balance": ("Экспорт", "B4"),             # Необязательный старый показатель
    "usdDebt": ("Экспорт", "B5"),             # Остаток ГМАХ в USD
    "rate": ("Экспорт", "B6"),                # Сценарный курс RUB/USD
    "savedRub": ("Экспорт", "B7"),            # Реально отложено для ГМАХ, RUB
    "reserveTargetRub": ("Экспорт", "B8"),   # Теоретический долговой резерв, RUB
    "dayTarget": ("Экспорт", "B9"),           # ФИКСИРОВАННАЯ дневная цель
    "dayReceived": ("Экспорт", "B10"),       # Фактически доступные приходы дня
    "unmappedTotal": ("Экспорт", "B11"),     # Неклассифицированные RUB-расходы
}

RUB_DEBTS = {
    "Цдока МЕОЦ": ("Экспорт", "B12"),
    "Маме": ("Экспорт", "B13"),
    "Бюджет МЕОЦ": ("Экспорт", "B14"),
    "Собственный ГМАХ": ("Экспорт", "B15"),
}
CHILDREN = {
    "Дочь": ("Экспорт", "B17"),
    "Леви": ("Экспорт", "B18"),
    "Давид": ("Экспорт", "B19"),
}
INSTALLMENTS = {
    "Алиса с экраном": {
        "count": ("Экспорт", "B21"),
        "payment": ("Экспорт", "C21"),
    },
    "Алиса в гостиной": {
        "count": ("Экспорт", "B22"),
        "payment": ("Экспорт", "C22"),
    },
}

# В каждой записи label/income/expenses — обычные адреса ячеек Calc.
# budget_sheet + колонки задают ячейки категорий по BUDGET_ROWS ниже.
# Текущий цикл, следующий, затем через один. Должно быть ровно три записи.
CYCLES = [
    {
        "label": ("Экспорт", "B25"),
        "income": ("Экспорт", "B26"),
        "expenses": ("Экспорт", "B27"),
        "budget_sheet": "Экспорт",
        "limit_col": "B",
        "spent_col": "C",
    },
    {
        "label": ("Экспорт", "D25"),
        "income": ("Экспорт", "D26"),
        "expenses": ("Экспорт", "D27"),
        "budget_sheet": "Экспорт",
        "limit_col": "D",
        "spent_col": "E",
    },
    {
        "label": ("Экспорт", "F25"),
        "income": ("Экспорт", "F26"),
        "expenses": ("Экспорт", "F27"),
        "budget_sheet": "Экспорт",
        "limit_col": "F",
        "spent_col": "G",
    },
]

# Ряд бюджета — одна строка на категорию, в том числе для всех трёх циклов.
# Это имена на ДАШБОРДЕ; названия категорий в Calc могут отличаться.
BUDGET_ROWS = {
    "Шаббат": 32,
    "Продукты": 33,
    "Прочие дети": 34,
    "Бытовая химия": 35,
    "Аренда": 36,
    "Психолог": 37,
    "Седжаро": 38,
    "Прочее лечение": 39,
    "Уход за собой": 40,
    "Развозка": 41,
    "Хор": 42,
    "Сотовая связь": 43,
    "Интернет": 44,
    "Страхование квартиры": 45,
    "Рассрочка — Алиса с экраном": 46,
    "Рассрочка — Алиса в гостиной": 47,
    "Подписки (USD-резерв)": 48,
    "Непредвиденные траты": 49,
}
INFORMATIONAL_BUDGETS = {
    "Подписки (USD-резерв)":
        "75 USD резервируются до конвертации в RUB; не включать повторно в расходы.",
}

# Если одна категория лежит не в общей таблице, для каждого цикла можно
# задать произвольные адреса (лимит, факт) — тоже только в конфигурации.
# Пример: ("Аренда", 0): (("Другой лист", "G9"), ("Траты", "F12")).
BUDGET_CELL_OVERRIDES = {}

# ============================================================================
# ЛОГИКА. Ниже не требуется редактировать листы и адреса ячеек.
# ============================================================================


class ConfigError(ValueError):
    """Не хватает или неверно настроены данные из локального файла."""


class CalcReader:
    def __init__(self, path: Path):
        if not path.is_file():
            raise ConfigError(f"Нет файла таблицы: {path}")
        if path.suffix.lower() not in {".ods", ".xlsx", ".xls", ".xlsb"}:
            raise ConfigError("Поддерживаются .ods, .xlsx, .xls и .xlsb.")
        self.path = path
        self.workbook = CalamineWorkbook.from_path(str(path))
        self.cache: dict[str, list[list[object]]] = {}

    def value(self, cell: tuple[str, str], label: str = "") -> object:
        if not (isinstance(cell, tuple) and len(cell) == 2):
            raise ConfigError(f"{label}: нужен адрес ('Лист', 'B25').")
        sheet, addr = cell
        match = re.fullmatch(r"([A-Za-z]+)([1-9][0-9]*)", str(addr))
        if not sheet or not match:
            raise ConfigError(f"{label}: неверная ссылка {cell!r}")
        if sheet not in self.cache:
            try:
                self.cache[sheet] = self.workbook.get_sheet_by_name(sheet).to_python(
                    skip_empty_area=False
                )
            except Exception as exc:
                raise ConfigError(f"Лист {sheet!r} недоступен: {exc}") from exc
        col = 0
        for letter in match.group(1).upper():
            col = col * 26 + ord(letter) - 64
        row = int(match.group(2)) - 1
        col -= 1
        values = self.cache[sheet]
        result = values[row][col] if row < len(values) and col < len(values[row]) else None
        if result is None or result == "":
            raise ConfigError(f"{label}: пусто в {sheet}!{addr}; сохраните формулы Calc.")
        if isinstance(result, str) and result.startswith(
            ("#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#N/A", "#NUM!", "#NULL!")
        ):
            raise ConfigError(f"{label}: ошибка формулы в {sheet}!{addr}: {result}")
        return result

    def money(self, cell: tuple[str, str], label: str) -> float:
        raw = self.value(cell, label)
        if isinstance(raw, bool):
            raise ConfigError(f"{label}: ожидается число, не логическое значение.")
        try:
            number = Decimal(str(raw).replace("\u00a0", "").replace(" ", "").replace(",", "."))
        except (InvalidOperation, ValueError) as exc:
            raise ConfigError(f"{label}: {cell} не содержит число ({raw!r}).") from exc
        if not number.is_finite():
            raise ConfigError(f"{label}: число не конечное.")
        return float(number.quantize(Decimal("0.01")))

    def text(self, cell: tuple[str, str], label: str) -> str:
        value = str(self.value(cell, label)).strip()
        if not value:
            raise ConfigError(f"{label}: пустая подпись.")
        return value


def budget_refs(name: str, index: int, cycle: dict) -> tuple[tuple[str, str], tuple[str, str]]:
    custom = BUDGET_CELL_OVERRIDES.get((name, index))
    if custom is not None:
        return custom
    row = BUDGET_ROWS[name]
    return (
        (cycle["budget_sheet"], f"{cycle['limit_col']}{row}"),
        (cycle["budget_sheet"], f"{cycle['spent_col']}{row}"),
    )


def build_report(reader: CalcReader) -> dict:
    if len(CYCLES) != 3:
        raise ConfigError("Дашборд ожидает три бюджетных цикла.")
    if not BUDGET_ROWS:
        raise ConfigError("Нет ни одной бюджетной категории.")
    report: dict = {
        "familyDeficit": reader.money(CELLS["familyDeficit"], "Исторический дефицит"),
        "deficit": reader.money(CELLS["deficit"], "Прогнозный дефицит"),
        "usdDebt": reader.money(CELLS["usdDebt"], "ГМАХ USD"),
        "rate": reader.money(CELLS["rate"], "Курс RUB/USD"),
        "savedRub": reader.money(CELLS["savedRub"], "В копилках RUB"),
        "reserveTargetRub": reader.money(CELLS["reserveTargetRub"], "Долговой резерв RUB"),
        "rubDebts": [
            {"name": name, "amount": reader.money(ref, f"Долг {name}")}
            for name, ref in RUB_DEBTS.items()
        ],
        "children": [
            {"name": name, "amount": reader.money(ref, f"Накопления {name}")}
            for name, ref in CHILDREN.items()
        ],
        "installments": [],
        "cycles": [],
    }
    if CELLS.get("balance"):
        report["balance"] = reader.money(CELLS["balance"], "Справочный учётный баланс")
    if report["rate"] <= 0 or report["usdDebt"] <= 0:
        raise ConfigError("Действующий интерфейс пока требует курс > 0 и ГМАХ USD > 0.")
    if any(report[k] < 0 for k in ("familyDeficit", "deficit", "savedRub", "reserveTargetRub")):
        raise ConfigError("Дефициты, накопления и резервы не могут быть отрицательными.")

    for name, refs in INSTALLMENTS.items():
        count_float = reader.money(refs["count"], f"Осталось платежей: {name}")
        if count_float < 0 or int(count_float) != count_float:
            raise ConfigError(f"Число платежей по {name} должно быть целым и >= 0.")
        payment = reader.money(refs["payment"], f"Платёж: {name}")
        if payment < 0:
            raise ConfigError(f"Платёж по {name} отрицателен.")
        report["installments"].append({"name": name, "count": int(count_float), "payment": payment})

    target = reader.money(CELLS["dayTarget"], "Утренняя цель")
    received = reader.money(CELLS["dayReceived"], "Получено за день")
    report["day"] = {"target": target, "received": received}
    if target < 0 or received < 0:
        raise ConfigError("Дневная цель или поступления отрицательны.")

    unmapped = reader.money(CELLS["unmappedTotal"], "Неклассифицированные расходы")
    if unmapped < 0:
        raise ConfigError("Неклассифицированные расходы не могут быть отрицательными.")

    labels = []
    for index, cycle in enumerate(CYCLES):
        label = reader.text(cycle["label"], f"Цикл #{index+1}")
        if label in labels:
            raise ConfigError("Два цикла имеют одинаковую подпись.")
        labels.append(label)
        income = reader.money(cycle["income"], f"Доход цикла {label}")
        expenses = reader.money(cycle["expenses"], f"Расход цикла {label}")
        if income < 0 or expenses < 0:
            raise ConfigError(f"Отрицательный план доходов/расходов в цикле {label}.")
        budgets = []
        total_limits = 0.0
        for name in BUDGET_ROWS:
            limit_ref, spent_ref = budget_refs(name, index, cycle)
            limit = reader.money(limit_ref, f"Лимит {name}, цикл {label}")
            if limit < 0:
                raise ConfigError(f"Отрицательный лимит {name}, цикл {label}.")
            is_info = name in INFORMATIONAL_BUDGETS
            # Информационный USD-резерв НЕ прибавляется к рублёвому итогу.
            spent = None if is_info else reader.money(spent_ref, f"Факт {name}, цикл {label}")
            item = {"name": name, "limit": limit, "spent": spent, "prepaid": 0}
            if is_info:
                item.update({
                    "informational": True,
                    "accountingNote": INFORMATIONAL_BUDGETS[name],
                })
            else:
                total_limits += limit
            budgets.append(item)
        if total_limits > expenses + 1.0:
            raise ConfigError(
                f"В цикле {label} сумма рублёвых лимитов {total_limits:.2f} "
                f"больше плана расходов {expenses:.2f}: проверьте двойной учёт."
            )
        report["cycles"].append({
            "label": label,
            "income": income,
            "expenses": expenses,
            "possibleReturn": None,
            "budgets": budgets,
            "unmappedExpenses": (
                [{"row": 0, "amount": unmapped, "category": "Не разнесено в Calc",
                  "subcategory": "Требует классификации"}]
                if index == 0 and unmapped > 0 else []
            ),
        })

    file_saved = datetime.fromtimestamp(reader.path.stat().st_mtime, ZoneInfo(TZ))
    now = datetime.now(ZoneInfo(TZ))
    report["asOf"] = file_saved.strftime("%d.%m.%Y %H:%M МСК")
    report["sourceSavedAt"] = file_saved.isoformat()
    report["exportedAt"] = now.isoformat()
    return report


def encrypt_report(data: dict, password: str) -> str:
    # Совместимо с finance/app.js и finance/family/app.js.
    if len(password) < 16:
        raise ConfigError("Пароль отчёта должен иметь хотя бы 16 символов; лучше случайные 20+.")
    from secrets import token_bytes

    salt, iv = token_bytes(16), token_bytes(12)
    key = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600_000
    ).derive(password.encode("utf-8"))
    enc = lambda data: base64.b64encode(data).decode("ascii")
    ciphertext = AESGCM(key).encrypt(
        iv, json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), None
    )
    return json.dumps({
        "v": 1, "kdf": "PBKDF2-SHA256", "cipher": "AES-256-GCM",
        "iterations": 600_000, "salt": enc(salt), "iv": enc(iv),
        "ciphertext": enc(ciphertext),
    }, separators=(",", ":"))


def github_json(method: str, endpoint: str, token: str, data: dict | None = None) -> dict:
    url = "https://api.github.com/repos/" + REPOSITORY + "/" + endpoint.lstrip("/")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "finance-local-calc-publisher",
    }
    raw = None
    if data is not None:
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=raw, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=35) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Не печатать запрос: даже зашифрованный payload не нужен в логах.
        raise RuntimeError(f"GitHub API {method} {endpoint}: HTTP {exc.code}") from exc


def require_switched_workflow(token: str) -> None:
    path = ".github/workflows/finance.yml"
    encoded_path = urllib.parse.quote(path, safe="/")
    obj = github_json("GET", f"contents/{encoded_path}?ref={BRANCH}", token)
    text = base64.b64decode(obj["content"]).decode("utf-8")
    if "FINANCE_GOOGLE_SERVICE_ACCOUNT_JSON" in text or "build_encrypted.py" in text:
        raise ConfigError(
            "Публикация заблокирована: finance.yml всё ещё пересобирает отчёт из "
            "Google Sheets и может перезаписать ваш локальный. Сначала переключите "
            "workflow на публикацию готовых owner.enc и family.enc."
        )


def publish_encrypted(files: dict[str, str], token: str) -> str:
    """Атомарный коммит двух ЗАШИФРОВАННЫХ файлов, без раскрытия исходных данных."""
    require_switched_workflow(token)
    head = github_json("GET", f"git/ref/heads/{BRANCH}", token)["object"]["sha"]
    commit = github_json("GET", f"git/commits/{head}", token)
    new_tree = github_json("POST", "git/trees", token, {
        "base_tree": commit["tree"]["sha"],
        "tree": [
            {"path": path, "mode": "100644", "type": "blob", "content": content}
            for path, content in files.items()
        ],
    })["sha"]
    new_commit = github_json("POST", "git/commits", token, {
        "message": "chore(finance): publish encrypted snapshot from local Calc",
        "tree": new_tree,
        "parents": [head],
    })["sha"]
    # force=False: при параллельном коммите GitHub откажет; ничего не перезапишем.
    github_json("PATCH", f"git/refs/heads/{BRANCH}", token, {
        "sha": new_commit, "force": False,
    })
    return new_commit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", type=Path, default=WORKBOOK_PATH,
                        help="Путь к локальному .ods/.xlsx (иначе WORKBOOK_PATH).")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--publish", action="store_true",
                       help="Шифровать и отправить в GitHub (только после переключения workflow).")
    modes.add_argument("--export-only", action="store_true",
                       help="Создать только локальные .enc, ничего не отправляя в GitHub.")
    parser.add_argument("--output-dir", type=Path, default=Path.home() / "finance-export",
                        help="Каталог для --export-only; не добавляйте его в git.")
    args = parser.parse_args(argv)

    report = build_report(CalcReader(args.book))
    print(f"Сохранённая книга: {args.book}")
    print(f"Данные на: {report['asOf']} | экспорт: {report['exportedAt']}")
    print(f"План текущего цикла: {report['cycles'][0]['expenses']:.2f} RUB")
    print(f"Прогнозный дефицит: {report['deficit']:.2f} RUB")
    print(f"Дневная цель: {report['day']['target']:.2f} RUB")
    if not (args.publish or args.export_only):
        print("ПРОВЕРКА ПРОЙДЕНА. Dry-run: ничего не опубликовано.")
        return 0

    owner_password = os.environ.get("FINANCE_OWNER_PASSWORD", "")
    family_password = os.environ.get("WIFE_PASSWORD", "")
    owner = encrypt_report(report, owner_password)
    family = encrypt_report({
        "asOf": report["asOf"], "cycle": report["cycles"][0]
    }, family_password)
    files = {"finance/data/owner.enc": owner, "finance/data/family.enc": family}

    if args.export_only:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        for path, content in files.items():
            dest = args.output_dir / Path(path).name
            dest.write_text(content, encoding="utf-8")
            print(f"Шифрованный файл создан: {dest}")
        return 0

    if not PUBLISH_ENABLED:
        raise ConfigError(
            "PUBLISH_ENABLED=False. Не включайте публикацию, пока workflow "
            "и локальные показатели не проверены."
        )
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise ConfigError("Не задан GITHUB_TOKEN (fine-grained PAT: Contents write).")
    commit = publish_encrypted(files, token)
    print(f"Опубликованы ТОЛЬКО зашифрованные данные. Коммит: {commit}")
    print("https://github.com/" + REPOSITORY + "/commit/" + commit)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ConfigError, OSError, ValueError, RuntimeError) as exc:
        print("ОШИБКА: " + str(exc), file=sys.stderr)
        sys.exit(1)

"""Exports tabulaires CSV (format français : « ; », BOM UTF-8, JJ/MM/AAAA) et Excel (cellules typées)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from decimal import Decimal

from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.styles import Font

from app.core.clock import to_local

XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _csv_cell(value, tz: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Oui" if value else "Non"
    if isinstance(value, datetime):
        return to_local(value, tz).strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float | Decimal):
        return f"{value:.2f}".replace(".", ",")
    return str(value)


def csv_response(filename: str, headers: Sequence[str], rows: Iterable[Sequence], tz: str) -> Response:
    buf = io.StringIO()
    buf.write("﻿")  # BOM : Excel français ouvre le fichier en UTF-8
    writer = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_csv_cell(v, tz) for v in row])
    return Response(
        buf.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}.csv"'},
    )


def xlsx_response(filename: str, sheet: str, headers: Sequence[str], rows: Iterable[Sequence], tz: str) -> Response:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet[:31]
    ws.append(list(headers))
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        values = []
        for v in row:
            if isinstance(v, datetime):
                v = to_local(v, tz).replace(tzinfo=None)
            elif isinstance(v, bool):
                v = "Oui" if v else "Non"
            values.append(v)
        ws.append(values)
        for cell in ws[ws.max_row]:
            if isinstance(cell.value, datetime):
                cell.number_format = "dd/mm/yyyy hh:mm"
            elif isinstance(cell.value, date):
                cell.number_format = "dd/mm/yyyy"
            elif isinstance(cell.value, float | Decimal):
                cell.number_format = "#,##0.00"
    for column in ws.columns:
        width = max(len(str(c.value or "")) for c in column)
        ws.column_dimensions[column[0].column_letter].width = min(max(width + 2, 10), 60)
    ws.freeze_panes = "A2"
    out = io.BytesIO()
    wb.save(out)
    return Response(
        out.getvalue(),
        media_type=XLSX_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}.xlsx"'},
    )

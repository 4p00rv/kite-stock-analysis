from unittest.mock import MagicMock

from stocks_analysis.sheets.formatting import (
    DATE_COLOR_A,
    DATE_COLOR_B,
    HEADER_BG,
    HEADER_FG,
    _apply_alternating_date_colors,
    _col_letter,
    _format_header_row,
    _get_date_groups,
)


class TestColLetter:
    def test_single_letter(self) -> None:
        assert _col_letter(1) == "A"
        assert _col_letter(11) == "K"
        assert _col_letter(26) == "Z"

    def test_double_letter(self) -> None:
        assert _col_letter(27) == "AA"


class TestFormatHeaderRow:
    def test_applies_correct_style_and_range(self) -> None:
        mock_ws = MagicMock()
        _format_header_row(mock_ws, num_cols=11)
        mock_ws.format.assert_called_once()
        args, kwargs = mock_ws.format.call_args
        assert args[0] == "A1:K1"
        fmt = args[1]
        assert fmt["textFormat"]["bold"] is True
        assert fmt["textFormat"]["foregroundColorStyle"]["rgbColor"] == HEADER_FG
        assert fmt["backgroundColor"] == HEADER_BG
        assert fmt["horizontalAlignment"] == "CENTER"

    def test_freezes_header_row(self) -> None:
        mock_ws = MagicMock()
        _format_header_row(mock_ws, num_cols=3)
        mock_ws.freeze.assert_called_once_with(rows=1)

    def test_small_column_count(self) -> None:
        mock_ws = MagicMock()
        _format_header_row(mock_ws, num_cols=2)
        args, _ = mock_ws.format.call_args
        assert args[0] == "A1:B1"


class TestGetDateGroups:
    def test_consecutive_grouping(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = [
            "date",
            "2024-01-15",
            "2024-01-15",
            "2024-01-16",
            "2024-01-16",
            "2024-01-16",
        ]
        result = _get_date_groups(mock_ws)
        assert result == [
            ("2024-01-15", 2, 3),
            ("2024-01-16", 4, 6),
        ]

    def test_single_row(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = ["date", "2024-01-15"]
        result = _get_date_groups(mock_ws)
        assert result == [("2024-01-15", 2, 2)]

    def test_empty_sheet(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = ["date"]
        result = _get_date_groups(mock_ws)
        assert result == []

    def test_non_contiguous_same_dates(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = [
            "date",
            "2024-01-15",
            "2024-01-16",
            "2024-01-15",
        ]
        result = _get_date_groups(mock_ws)
        assert result == [
            ("2024-01-15", 2, 2),
            ("2024-01-16", 3, 3),
            ("2024-01-15", 4, 4),
        ]


class TestApplyAlternatingDateColors:
    def test_batch_format_args_for_two_groups(self) -> None:
        mock_ws = MagicMock()
        # 2 dates, 2 rows each, 3 columns
        mock_ws.col_values.return_value = [
            "date",
            "2024-01-15",
            "2024-01-15",
            "2024-01-16",
            "2024-01-16",
        ]
        _apply_alternating_date_colors(mock_ws, num_cols=3)
        mock_ws.batch_format.assert_called_once()
        fmt_list = mock_ws.batch_format.call_args[0][0]
        assert len(fmt_list) == 2
        # First group: DATE_COLOR_A (no fill)
        assert fmt_list[0]["range"] == "A2:C3"
        assert fmt_list[0]["format"]["backgroundColor"] is DATE_COLOR_A
        # Second group: DATE_COLOR_B
        assert fmt_list[1]["range"] == "A4:C5"
        assert fmt_list[1]["format"]["backgroundColor"] == DATE_COLOR_B

    def test_no_op_on_empty(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = ["date"]
        _apply_alternating_date_colors(mock_ws, num_cols=3)
        mock_ws.batch_format.assert_not_called()

    def test_three_group_alternation(self) -> None:
        mock_ws = MagicMock()
        mock_ws.col_values.return_value = [
            "date",
            "2024-01-15",
            "2024-01-16",
            "2024-01-17",
        ]
        _apply_alternating_date_colors(mock_ws, num_cols=2)
        fmt_list = mock_ws.batch_format.call_args[0][0]
        assert len(fmt_list) == 3
        # Alternates: A, B, A
        assert fmt_list[0]["format"]["backgroundColor"] is DATE_COLOR_A
        assert fmt_list[1]["format"]["backgroundColor"] == DATE_COLOR_B
        assert fmt_list[2]["format"]["backgroundColor"] is DATE_COLOR_A

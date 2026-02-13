from unittest.mock import MagicMock, patch

import gspread

from stocks_analysis.sheets import SheetsClient


class TestSetupPricesSheet:
    def test_creates_prices_sheet_with_formulas(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = []
        mock_ws.id = 500
        mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Prices")
        mock_spreadsheet.add_worksheet.return_value = mock_ws

        client.setup_prices_sheet()

        # Should write header formula in A1
        mock_ws.update.assert_called()
        calls = mock_ws.update.call_args_list
        # A1 = "date"
        assert any(c.kwargs.get("range_name") == "A1" and c[0][0] == [["date"]] for c in calls)
        # B1 has TRANSPOSE formula filtering to latest date only
        b1_calls = [c for c in calls if c.kwargs.get("range_name") == "B1"]
        assert len(b1_calls) == 1
        assert "TRANSPOSE" in str(b1_calls[0][0][0])
        # Uses text-sorted latest date (not MAX, which fails on text dates)
        assert "SORT" in str(b1_calls[0][0][0])
        assert "INDEX" in str(b1_calls[0][0][0])
        # A2 has SORT/UNIQUE formula
        a2_calls = [c for c in calls if c.kwargs.get("range_name") == "A2"]
        assert len(a2_calls) == 1
        assert "SORT" in str(a2_calls[0][0][0])
        # B2 has INDEX/FILTER formula with absolute Holdings column refs
        b2_calls = [c for c in calls if c.kwargs.get("range_name") == "B2"]
        assert len(b2_calls) == 1
        b2_str = str(b2_calls[0][0][0])
        assert "IFERROR" in b2_str
        assert "Holdings!$E:$E" in b2_str
        assert "Holdings!$A:$A" in b2_str
        assert "Holdings!$B:$B" in b2_str

        # Should use batchUpdate for copyPaste fill
        mock_spreadsheet.batch_update.assert_called_once()
        body = mock_spreadsheet.batch_update.call_args[0][0]
        requests = body["requests"]
        copy_requests = [r for r in requests if "copyPaste" in r]
        assert len(copy_requests) == 2  # fill right + fill down

    def test_deletes_existing_sheet_before_recreating(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        old_ws = MagicMock()
        new_ws = MagicMock()
        new_ws.id = 501
        mock_spreadsheet.worksheet.return_value = old_ws
        mock_spreadsheet.add_worksheet.return_value = new_ws

        client.setup_prices_sheet()

        mock_spreadsheet.del_worksheet.assert_called_once_with(old_ws)
        mock_spreadsheet.add_worksheet.assert_called_once_with(title="Prices", rows=1000, cols=104)


class TestSetupPortfolioHistorySheet:
    def test_creates_portfolio_history_with_formulas(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = []
        mock_ws.id = 600
        mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Portfolio History")
        mock_spreadsheet.add_worksheet.return_value = mock_ws

        client.setup_portfolio_history_sheet()

        calls = mock_ws.update.call_args_list
        # A2 has SORT/UNIQUE dates formula
        a2_calls = [c for c in calls if c.kwargs.get("range_name") == "A2"]
        assert len(a2_calls) == 1
        assert "SORT" in str(a2_calls[0][0][0])
        # B2 has SUMPRODUCT for total_value
        b2_calls = [c for c in calls if c.kwargs.get("range_name") == "B2"]
        assert len(b2_calls) == 1
        assert "SUMPRODUCT" in str(b2_calls[0][0][0])

        # Should use batchUpdate for copyPaste fill down
        mock_spreadsheet.batch_update.assert_called_once()


class TestSetupAllocationSheet:
    def test_creates_allocation_with_formulas(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = []
        mock_ws.id = 700
        mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Allocation")
        mock_spreadsheet.add_worksheet.return_value = mock_ws

        client.setup_allocation_sheet()

        calls = mock_ws.update.call_args_list
        # H1 = "latest_date" (helper cells moved to col H)
        h1_calls = [c for c in calls if c.kwargs.get("range_name") == "H1"]
        assert len(h1_calls) == 1
        # A2 has SORT/FILTER formula including cost
        a2_calls = [c for c in calls if c.kwargs.get("range_name") == "A2"]
        assert len(a2_calls) == 1
        a2_formula = str(a2_calls[0][0][0])
        assert "SORT" in a2_formula
        assert "Holdings!D2:D*Holdings!C2:C" in a2_formula  # cost column
        # D2 has weight_pct ARRAYFORMULA
        d2_calls = [c for c in calls if c.kwargs.get("range_name") == "D2"]
        assert len(d2_calls) == 1
        assert "ARRAYFORMULA" in str(d2_calls[0][0][0])
        # F2 has return_pct ARRAYFORMULA
        f2_calls = [c for c in calls if c.kwargs.get("range_name") == "F2"]
        assert len(f2_calls) == 1
        assert "ARRAYFORMULA" in str(f2_calls[0][0][0])


class TestSetupDashboardSheet:
    def test_creates_dashboard_with_labels_and_formulas(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = []
        mock_ws.id = 800
        mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Dashboard")
        mock_spreadsheet.add_worksheet.return_value = mock_ws

        client.setup_dashboard_sheet()

        calls = mock_ws.update.call_args_list
        # Should write labels and formulas
        # Check A1:A14 contains labels
        a_col_calls = [c for c in calls if c.kwargs.get("range_name") == "A1:A14"]
        assert len(a_col_calls) == 1
        labels = a_col_calls[0][0][0]
        assert labels[0] == ["Metric"]
        assert labels[1] == ["Portfolio Value"]
        assert labels[8] == ["Days Invested"]
        assert labels[9] == ["XIRR"]

        # Check B1:B14 has formulas
        b_col_calls = [c for c in calls if c.kwargs.get("range_name") == "B1:B14"]
        assert len(b_col_calls) == 1
        formulas = b_col_calls[0][0][0]
        assert formulas[0] == ["Value"]
        assert "IFERROR" in str(formulas[1][0])  # Portfolio Value formula


class TestSetupCharts:
    def test_creates_four_charts(self, client: SheetsClient, mock_spreadsheet: MagicMock) -> None:
        def make_ws(title: str, sheet_id: int) -> MagicMock:
            ws = MagicMock()
            ws.title = title
            ws.id = sheet_id
            return ws

        mock_spreadsheet.worksheets.return_value = [
            make_ws("Portfolio History", 600),
            make_ws("Allocation", 700),
            make_ws("Dashboard", 800),
        ]
        mock_spreadsheet.fetch_sheet_metadata.return_value = {
            "sheets": [
                {"properties": {"sheetId": 600}, "charts": []},
                {"properties": {"sheetId": 700}, "charts": []},
                {"properties": {"sheetId": 800}, "charts": []},
            ]
        }

        client.setup_charts()

        mock_spreadsheet.batch_update.assert_called_once()
        body = mock_spreadsheet.batch_update.call_args[0][0]
        requests = body["requests"]
        add_chart_requests = [r for r in requests if "addChart" in r]
        assert len(add_chart_requests) == 5

    def test_updates_existing_charts(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        def make_ws(title: str, sheet_id: int) -> MagicMock:
            ws = MagicMock()
            ws.title = title
            ws.id = sheet_id
            return ws

        mock_spreadsheet.worksheets.return_value = [
            make_ws("Portfolio History", 600),
            make_ws("Allocation", 700),
            make_ws("Dashboard", 800),
        ]
        mock_spreadsheet.fetch_sheet_metadata.return_value = {
            "sheets": [
                {
                    "properties": {"sheetId": 800},
                    "charts": [
                        {
                            "chartId": 1,
                            "position": {},
                            "spec": {"title": "Portfolio Value vs Cost"},
                        },
                        {"chartId": 2, "position": {}, "spec": {"title": "Drawdown"}},
                        {"chartId": 3, "position": {}, "spec": {"title": "P&L Over Time"}},
                    ],
                },
                {
                    "properties": {"sheetId": 700},
                    "charts": [
                        {"chartId": 4, "position": {}, "spec": {"title": "Allocation"}},
                        {
                            "chartId": 5,
                            "position": {},
                            "spec": {"title": "Stock Performance"},
                        },
                    ],
                },
            ]
        }

        client.setup_charts()

        body = mock_spreadsheet.batch_update.call_args[0][0]
        requests = body["requests"]
        update_requests = [r for r in requests if "updateChartSpec" in r]
        assert len(update_requests) == 5


class TestSetupAll:
    @patch.object(SheetsClient, "setup_charts")
    @patch.object(SheetsClient, "setup_dashboard_sheet")
    @patch.object(SheetsClient, "setup_allocation_sheet")
    @patch.object(SheetsClient, "setup_portfolio_history_sheet")
    @patch.object(SheetsClient, "setup_prices_sheet")
    def test_calls_all_setup_methods(
        self,
        mock_prices: MagicMock,
        mock_history: MagicMock,
        mock_alloc: MagicMock,
        mock_dash: MagicMock,
        mock_charts: MagicMock,
        client: SheetsClient,
    ) -> None:
        client.setup_all()

        mock_prices.assert_called_once()
        mock_history.assert_called_once()
        mock_alloc.assert_called_once()
        mock_dash.assert_called_once()
        mock_charts.assert_called_once()

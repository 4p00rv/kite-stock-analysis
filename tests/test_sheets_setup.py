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


class TestSetupCapitalFlowsSheet:
    def test_creates_capital_flows_with_headers(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = []
        mock_ws.id = 850
        mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Capital Flows")
        mock_spreadsheet.add_worksheet.return_value = mock_ws

        client.setup_capital_flows_sheet()

        calls = mock_ws.update.call_args_list
        # Should write headers: date, type, amount, notes
        header_calls = [c for c in calls if c.kwargs.get("range_name") == "A1:D1"]
        assert len(header_calls) == 1
        headers = header_calls[0][0][0]
        assert headers == [["date", "type", "amount", "notes"]]

    def test_reuses_existing_worksheet(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = ["date", "type", "amount", "notes"]
        mock_spreadsheet.worksheet.return_value = mock_ws

        client.setup_capital_flows_sheet()

        mock_spreadsheet.add_worksheet.assert_not_called()


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
        # Check A1:A17 contains labels (14 original + 3 new capital metrics)
        a_col_calls = [c for c in calls if c.kwargs.get("range_name") == "A1:A17"]
        assert len(a_col_calls) == 1
        labels = a_col_calls[0][0][0]
        assert labels[0] == ["Metric"]
        assert labels[1] == ["Portfolio Value"]
        assert labels[8] == ["Days Invested"]
        assert labels[9] == ["XIRR"]
        assert labels[14] == ["Capital Deployed"]
        assert labels[15] == ["True P&L"]
        assert labels[16] == ["True Return %"]

        # Check B1:B17 has formulas
        b_col_calls = [c for c in calls if c.kwargs.get("range_name") == "B1:B17"]
        assert len(b_col_calls) == 1
        formulas = b_col_calls[0][0][0]
        assert formulas[0] == ["Value"]
        assert "IFERROR" in str(formulas[1][0])  # Portfolio Value formula

    def test_capital_deployed_formula_references_capital_flows(
        self, client: SheetsClient, mock_spreadsheet: MagicMock
    ) -> None:
        mock_ws = MagicMock()
        mock_ws.row_values.return_value = []
        mock_ws.id = 800
        mock_spreadsheet.worksheet.side_effect = gspread.WorksheetNotFound("Dashboard")
        mock_spreadsheet.add_worksheet.return_value = mock_ws

        client.setup_dashboard_sheet()

        calls = mock_ws.update.call_args_list
        b_col_calls = [c for c in calls if c.kwargs.get("range_name") == "B1:B17"]
        formulas = b_col_calls[0][0][0]
        # Capital Deployed (row 15, index 14) uses SUMPRODUCT on Capital Flows
        capital_deployed = str(formulas[14][0])
        assert "Capital Flows" in capital_deployed
        assert "DEPOSIT" in capital_deployed
        assert "WITHDRAWAL" in capital_deployed
        # True P&L (row 16, index 15) references B2 and B15
        true_pnl = str(formulas[15][0])
        assert "B2" in true_pnl
        assert "B15" in true_pnl
        # True Return % (row 17, index 16) references B16 and B15
        true_return = str(formulas[16][0])
        assert "B16" in true_return
        assert "B15" in true_return


class TestSetupAll:
    @patch.object(SheetsClient, "setup_charts")
    @patch.object(SheetsClient, "setup_dashboard_sheet")
    @patch.object(SheetsClient, "setup_capital_flows_sheet")
    @patch.object(SheetsClient, "setup_allocation_sheet")
    @patch.object(SheetsClient, "setup_portfolio_history_sheet")
    @patch.object(SheetsClient, "setup_prices_sheet")
    def test_calls_all_setup_methods(
        self,
        mock_prices: MagicMock,
        mock_history: MagicMock,
        mock_alloc: MagicMock,
        mock_capital_flows: MagicMock,
        mock_dash: MagicMock,
        mock_charts: MagicMock,
        client: SheetsClient,
    ) -> None:
        client.setup_all()

        mock_prices.assert_called_once()
        mock_history.assert_called_once()
        mock_alloc.assert_called_once()
        mock_capital_flows.assert_called_once()
        mock_dash.assert_called_once()
        mock_charts.assert_called_once()

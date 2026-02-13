from unittest.mock import MagicMock

from stocks_analysis.sheets import SheetsClient


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

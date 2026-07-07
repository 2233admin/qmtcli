$requests = @(
  '{"id":1,"command":"status"}',
  '{"id":2,"command":"data_call","method":"get_stock_list_in_sector","args":["沪深A股"]}'
)

$requests | uv run qmtcli server

resource "azurerm_storage_account_network_rules" "data" {
  storage_account_id = azurerm_storage_account.data.id
  default_action     = "Allow"
  bypass             = ["AzureServices"]
}
